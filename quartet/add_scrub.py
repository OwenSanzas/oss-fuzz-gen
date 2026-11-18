#!/usr/bin/env python3
"""Remove the gold from git history in every per-case image (scrub_git.sh).

The new case image is built on the archived case image, unchanged apart from
the git history (qf-prescrub/<p>:20261015, the image every baseline run so far
used):
    FROM qf-prescrub/<p>:20261015
    COPY qf_scrub_git.sh /tmp/qf_scrub_git.sh
    RUN bash /tmp/qf_scrub_git.sh <gold basename> <gold blob sha1> && rm -f /tmp/qf_scrub_git.sh
Rebuilding the original Dockerfile instead would re-clone every repository
from the network, and the source tree could then differ from what the
baselines saw.  The original Dockerfile is kept in
<root>/../dockerfiles_prescrub/<p>.Dockerfile.  The gold blob is the dataset's
gold harness (target_check/src).  Idempotent.
usage: add_scrub.py <oss-fuzz root with projects/ and ../cases.json>
"""
import glob, json, os, shutil, subprocess, sys

root = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
work = os.path.dirname(root.rstrip('/'))
cases = json.load(open(f'{work}/cases.json'))
keep = f'{work}/dockerfiles_prescrub'
os.makedirs(keep, exist_ok=True)
OLD_MARK = '# --- QuartetFuzz: gold removed from git history ---'
for cid, c in sorted(cases.items()):
  p = c['oss_fuzz_project']
  d = f'{root}/projects/{p}'
  gold = glob.glob(f"/path/to/runs/target_check/src/{cid.replace('/', '__')}.*")[0]
  h = subprocess.run(['git', 'hash-object', gold], capture_output=True, text=True, check=True).stdout.strip()
  b = os.path.basename(c['gold_path'])
  df = open(f'{d}/Dockerfile').read()
  if not df.startswith('FROM qf-prescrub/'):
    if OLD_MARK in df:  # first version inserted the step into the original Dockerfile
      i = df.index(OLD_MARK)
      j = df.index('RUN apt-get update -q\n', i)
      df = df[:i] + df[j:]
    open(f'{keep}/{p}.Dockerfile', 'w').write(df)
  shutil.copy(f'{here}/scrub_git.sh', f'{d}/qf_scrub_git.sh')
  open(f'{d}/Dockerfile', 'w').write(
      f'FROM qf-prescrub/{p}:20261015\n'
      'COPY qf_scrub_git.sh /tmp/qf_scrub_git.sh\n'
      f'RUN bash /tmp/qf_scrub_git.sh {b} {h} && rm -f /tmp/qf_scrub_git.sh\n')
print('done', len(cases))
