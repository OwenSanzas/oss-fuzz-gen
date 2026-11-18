#!/usr/bin/env python3
"""Run OFG (one sample, no FI) over the benchmark cases under a resource limit.

- At most --parallel cases at once, and at most one case from a large project.
- A new case starts only while MemAvailable >= --min-free-gb.
- A case already finished (exit_code 0) is skipped, so the script can resume.
- Records the machine's memory each minute (logs/mem.tsv) to judge headroom.

OFG's output for a case is what OFG itself writes for its one sample
(results-nofi/<proj>/work/output-*/status/01/result.json); nothing is selected.

usage: schedule.py [--parallel 5] [--min-free-gb 16] [--only proj ...]
"""
import argparse
import json
import os
import subprocess
import time

WORK = '/path/to/baselines/ofg-work'
RUN = '/path/to/baselines/ofg-fair/quartet/run_case.sh'
BIG = {'binutils', 'icu', 'boost', 'capstone', 'assimp', 'libvips', 'gnutls',
       'sentencepiece', 'wabt'}
LOG = f'{WORK}/logs/schedule.log'
MEM = f'{WORK}/logs/mem.tsv'


def log(msg):
  with open(LOG, 'a') as f:
    f.write(time.strftime('%Y-%m-%dT%H:%M:%SZ ', time.gmtime()) + msg + '\n')


def mem_available_gb():
  for line in open('/proc/meminfo'):
    if line.startswith('MemAvailable'):
      return int(line.split()[1]) / 1048576
  return 0.0


def control_parallel(default):
  """Parallel limit, adjustable while running via <WORK>/parallel."""
  try:
    return int(open(f'{WORK}/parallel').read().strip())
  except (OSError, ValueError):
    return default


def control_max_big():
  """Large projects allowed at once, adjustable via <WORK>/max_big (default 1)."""
  try:
    return int(open(f'{WORK}/max_big').read().strip())
  except (OSError, ValueError):
    return 1


def adopt_running():
  """Cases already running from an earlier scheduler: proj -> pid."""
  out = subprocess.run(['ps', '-eo', 'pid,args'], capture_output=True,
                       text=True).stdout
  found = {}
  for line in out.splitlines():
    parts = line.split()
    if len(parts) >= 4 and parts[2] == RUN:
      found[parts[3]] = int(parts[0])
  return found


class Adopted:
  """A running case started by an earlier scheduler."""

  def __init__(self, pid):
    self.pid = pid
    self.returncode = None

  def poll(self):
    if os.path.exists(f'/proc/{self.pid}'):
      return None
    self.returncode = 'adopted'
    return self.returncode


def done(proj):
  # Any finished run counts, failed or not: a case runs once, so a rerun never
  # gives a baseline a second chance or overwrites its first output.
  f = f'{WORK}/results-nofi/{proj}/exit_code'
  return os.path.exists(f)


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('--parallel', type=int, default=5)
  ap.add_argument('--min-free-gb', type=float, default=16)
  ap.add_argument('--only', nargs='*', default=[])
  args = ap.parse_args()

  cases = json.load(open(f'{WORK}/cases.json'))
  queue = [(c['oss_fuzz_project'], c['project']) for c in cases.values()
           if (not args.only or c['oss_fuzz_project'] in args.only)
           and not done(c['oss_fuzz_project'])]
  running = {}  # proj -> (Popen, project)
  project_of = {c['oss_fuzz_project']: c['project'] for c in cases.values()}
  for proj, pid in adopt_running().items():
    running[proj] = (Adopted(pid), project_of.get(proj, ''))
    queue = [q for q in queue if q[0] != proj]
    log(f'{proj}: adopted running case (pid {pid})')
  log(f'start: {len(queue)} cases, parallel={args.parallel}, '
      f'min_free_gb={args.min_free_gb}')
  last_mem = 0.0
  while queue or running:
    for proj, (proc, _) in list(running.items()):
      if proc.poll() is not None:
        log(f'{proj}: finished rc={proc.returncode}')
        del running[proj]
    free = mem_available_gb()
    if time.time() - last_mem >= 60:
      with open(MEM, 'a') as f:
        f.write(f'{int(time.time())}\t{free:.1f}\t{len(running)}\n')
      last_mem = time.time()
    big_running = (sum(p in BIG for _, p in running.values()) >=
                   control_max_big())
    for i, (proj, project) in enumerate(queue):
      if (len(running) >= control_parallel(args.parallel) or
          mem_available_gb() < args.min_free_gb):
        break
      if project in BIG and big_running:
        continue
      queue.pop(i)
      running[proj] = (subprocess.Popen([RUN, proj, '1'],
                                        start_new_session=True), project)
      log(f'{proj}: started (free {mem_available_gb():.1f} GB, '
          f'running {len(running)})')
      break  # one start per loop, so memory is re-read before the next
    time.sleep(20)
  log('all cases finished')


if __name__ == '__main__':
  main()
