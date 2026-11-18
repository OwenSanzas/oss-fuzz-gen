#!/usr/bin/env python3
"""Schedule OFG generation as Fuzz Introspector reports become ready.

Each batch gets its own FI webapp instance built from a snapshot of the reports
finished so far.  Restarting a shared webapp would drop the context queries of
runs in flight, so every run keeps using the instance it started with until it
ends.  Instances no run needs any more are shut down.

usage: driver.py [--samples N] [--parallel K] [--hold proj ...]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

WORK = '/path/to/baselines/ofg-work'
OFG = '/path/to/baselines/ofg-fair'
FI_APP = f'{WORK}/fuzz-introspector/tools/web-fuzzing-introspection/app'
FI_PY = f'{WORK}/fi-venv/bin/python3'
OFG_PY = f'{OFG}/.venv/bin/python3'
STATE = f'{WORK}/driver_state.json'
LOG = f'{WORK}/logs/driver.log'


def log(msg):
  line = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ' ' + msg
  with open(LOG, 'a') as f:
    f.write(line + '\n')


def fi_ready():
  ready = set()
  path = f'{WORK}/logs/fi/_status.txt'
  if os.path.exists(path):
    for line in open(path):
      parts = line.split()
      if len(parts) >= 2 and parts[1].startswith('fi=0'):
        ready.add(parts[0])
  # Pilot reports built by hand.
  for p in os.listdir(f'{WORK}/oss-fuzz/build/out'):
    if os.path.exists(f'{WORK}/oss-fuzz/build/out/{p}/inspector/summary.json') \
        and os.path.exists(f'{WORK}/logs/fi/pilot_{p}.log'):
      ready.add(p)
  return ready


def start_instance(port, projects):
  """FI webapp on |port| over a snapshot holding only |projects|."""
  root = f'{WORK}/fi-inst/{port}'
  if os.path.exists(root):
    shutil.rmtree(root)
  snap = f'{root}/oss-fuzz'
  os.makedirs(f'{snap}/build/out')
  os.makedirs(f'{snap}/projects')
  for p in projects:
    os.symlink(f'{WORK}/oss-fuzz/build/out/{p}', f'{snap}/build/out/{p}')
    os.symlink(f'{WORK}/oss-fuzz/projects/{p}', f'{snap}/projects/{p}')
  app = f'{root}/app'
  shutil.copytree(FI_APP, app, ignore=shutil.ignore_patterns(
      'all-functions-db-*', 'all-constructors-db-*', 'db-archive.zip',
      'db-projects', '__pycache__'))
  dbdir = f'{app}/static/assets/db'
  with open(f'{root}/db_create.log', 'w') as out:
    rc = subprocess.run([FI_PY, './web_db_creator_from_summary.py',
                         '--local-oss-fuzz', snap], cwd=dbdir, stdout=out,
                        stderr=subprocess.STDOUT).returncode
  if rc:
    log(f'instance {port}: DB creation failed rc={rc}')
    return None
  env = dict(os.environ, WEBAPP_PORT=str(port),
             FUZZ_INTROSPECTOR_LOCAL_OSS_FUZZ=snap)
  proc = subprocess.Popen([FI_PY, './main.py'], cwd=app, env=env,
                          stdout=open(f'{root}/webapp.log', 'w'),
                          stderr=subprocess.STDOUT, start_new_session=True)
  for _ in range(180):
    try:
      out = subprocess.run(['curl', '-s', '-m', '3', f'127.0.0.1:{port}'],
                           capture_output=True, text=True).stdout
      if 'Fuzzing' in out:
        log(f'instance {port}: up with {len(projects)} projects (pid {proc.pid})')
        return proc
    except Exception:  # pylint: disable=broad-except
      pass
    time.sleep(5)
  log(f'instance {port}: did not come up')
  proc.kill()
  return None


def make_benchmark(proj, port):
  r = subprocess.run([OFG_PY, f'{OFG}/quartet/make_benchmarks.py',
                      f'{WORK}/cases.json', f'{WORK}/benchmarks',
                      f'http://127.0.0.1:{port}/api', proj],
                     cwd=OFG, capture_output=True, text=True)
  ok = os.path.exists(f'{WORK}/benchmarks/{proj}.yaml')
  log(f'{proj}: benchmark yaml {"ok" if ok else "FAILED"} '
      f'{r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]}')
  return ok


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument('--samples', type=int, default=1)
  ap.add_argument('--parallel', type=int, default=3)
  ap.add_argument('--batch-min', type=int, default=4)
  ap.add_argument('--batch-wait', type=int, default=1200)
  ap.add_argument('--hold', nargs='*', default=[])
  ap.add_argument('--only', nargs='*', default=[])
  args = ap.parse_args()

  cases = json.load(open(f'{WORK}/cases.json'))
  all_projects = [c['oss_fuzz_project'] for c in cases.values()]
  wanted = [p for p in all_projects
            if p not in args.hold and (not args.only or p in args.only)]
  state = json.load(open(STATE)) if os.path.exists(STATE) else {'done': [], 'failed': []}
  done = set(state['done'])
  queue = []            # (proj, port)
  running = {}          # proj -> (Popen, port)
  instances = {}        # port -> Popen
  served = set()        # projects given a benchmark already
  port = int(os.getenv('QF_FI_PORT_BASE', '8100'))
  last_instance = 0.0
  log(f'driver start: {len(wanted)} cases, samples={args.samples}, '
      f'parallel={args.parallel}, hold={args.hold}')

  while True:
    ready = fi_ready()
    fresh = [p for p in wanted if p in ready and p not in served and p not in done]
    # Cases whose FI build failed for good (after the one retry, if any).
    image_failed = set()
    st = f'{WORK}/logs/fi/_status.txt'
    if os.path.exists(st):
      text = open(st).read()
      retry_over = 'RETRYDONE' in text
      for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and not parts[1].startswith('fi=0') and \
            (retry_over or 'skipped_image' in parts[1]):
          image_failed.add(parts[0])
      image_failed -= ready
    # Start a new instance when enough new reports are ready, or the batch waited long enough.
    if fresh and (len(fresh) >= args.batch_min or
                  time.time() - last_instance > args.batch_wait or
                  all(p in ready or p in image_failed for p in wanted)):
      port += 1
      proc = start_instance(port, sorted(ready))
      last_instance = time.time()
      if proc:
        instances[port] = proc
        for p in fresh:
          served.add(p)
          if make_benchmark(p, port):
            queue.append((p, port))
          else:
            state['failed'].append(p)

    # Launch runs.
    def mem_ok():
      for line in open('/proc/meminfo'):
        if line.startswith('MemAvailable'):
          return int(line.split()[1]) // 1048576 >= 16
      return True

    while queue and len(running) < args.parallel and mem_ok():
      p, pport = queue.pop(0)
      res = f'{WORK}/results/{p}'
      if os.path.exists(res):
        shutil.rmtree(res)
      env = dict(os.environ, OFG_FI_ENDPOINT=f'http://127.0.0.1:{pport}/api')
      running[p] = (subprocess.Popen(
          [f'{OFG}/quartet/run_case.sh', p, str(args.samples)], env=env,
          start_new_session=True), pport)
      log(f'{p}: started (FI port {pport})')

    # Reap runs.
    for p, (proc, pport) in list(running.items()):
      if proc.poll() is not None:
        rc = proc.returncode
        log(f'{p}: finished rc={rc}')
        (state['done'] if rc == 0 else state['failed']).append(p)
        done.add(p)
        del running[p]
        json.dump(state, open(STATE, 'w'), indent=1)

    # Retire instances nobody uses.
    in_use = {pp for _, pp in running.values()} | {pp for _, pp in queue}
    for pp, proc in list(instances.items()):
      if pp not in in_use and pp != port:
        proc.terminate()
        del instances[pp]
        log(f'instance {pp}: retired')

    finished = all(p in done or p in image_failed or p in state['failed']
                   for p in wanted)
    if finished and not running and not queue:
      log('driver: all cases finished')
      break
    time.sleep(30)


if __name__ == '__main__':
  main()
