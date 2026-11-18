#!/usr/bin/env python3
"""Check that no gold-harness text reached the model.

The check takes every distinctive line of the gold harness (at least 25
characters after whitespace normalisation, not an #include, not a bare
brace or comment), and searches for it in the text sent TO the model.  That text
is the <CHAT PROMPT> blocks of the OFG logs, which include tool output fed back
to the model.  Model responses are excluded, since a model may write the same
line on its own.

usage: leak_check.py <cases.json> <results_dir> [project ...]
"""
import glob
import json
import re
import subprocess
import sys

SRC = '/path/to/runs/target_check/src'


def norm(s):
  return re.sub(r'\s+', ' ', s).strip()


def gold_lines(case_id):
  p, f = case_id.split('/')
  path = glob.glob(f'{SRC}/{p}__{f}.*')[0]
  out = []
  for line in open(path, errors='replace'):
    n = norm(line)
    if len(n) < 25 or n.startswith(('#include', '//', '/*', '*')):
      continue
    if n in ('extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {',
             'int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {'):
      continue
    out.append(n)
  return out


def unique_lines(case_id, image, lines):
  """Keeps the gold lines that no other file under /src of the case image has
  (the gold itself is stubbed there).  Sibling harnesses are visible to every
  system, so text shared with them is not a leak."""
  if not lines:
    return []
  script = 'for i in "$@"; do grep -rqF --exclude-dir=.git -- "$i" /src 2>/dev/null && echo SHARED || echo UNIQUE; done'
  out = subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'bash', image,
                        '-c', script, '_'] + lines,
                       capture_output=True, text=True, timeout=1800).stdout.split()
  return [l for l, tag in zip(lines, out) if tag == 'UNIQUE']


def prompts_text(result_dir):
  text = []
  for log in glob.glob(f'{result_dir}/**/*.log', recursive=True) + \
             glob.glob(f'{result_dir}/**/log*.txt', recursive=True) + \
             glob.glob(f'{result_dir}/run.log'):
    s = open(log, errors='replace').read()
    text += re.findall(r'<CHAT PROMPT:ROUND \d+>(.*?)</CHAT PROMPT:ROUND \d+>', s, re.S)
  return norm(' '.join(text))


def main(cases_json, results, only):
  cases = json.load(open(cases_json))
  bad = 0
  for case_id, c in cases.items():
    proj = c['oss_fuzz_project']
    if only and proj not in only:
      continue
    rd = f'{results}/{proj}'
    sent = prompts_text(rd)
    if not sent:
      print(f'{proj}: no prompts found')
      continue
    uniq = unique_lines(case_id, f'gcr.io/oss-fuzz/{proj}', gold_lines(case_id))
    hits = [l for l in uniq if l in sent]
    print(f'{proj}: {len(uniq)} gold-unique lines, {len(hits)} found in prompts' + (f' -> {hits[:3]}' if hits else ''))
    bad += bool(hits)
  sys.exit(1 if bad else 0)


if __name__ == '__main__':
  main(sys.argv[1], sys.argv[2], sys.argv[3:])
