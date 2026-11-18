#!/usr/bin/env python3
"""Create one OSS-Fuzz project per benchmark case for the OFG baseline.

Each case gets a copy of its project's directory from the pinned OSS-Fuzz tree
(955c6866), renamed <project>-c<k>.  Two lines are added to the end of its
Dockerfile:

1. Every git repository in the case's srcmap (version_pins.all_repos) is checked
   out at the pinned revision.  The library OFG generates against is then the same
   revision that gold and every other system are measured on.
2. The gold harness of THIS case is replaced with an empty stub, the same stub
   QuartetFuzz's flow.py uses.  OFG's container tools, its project-example
   collector and the local Fuzz Introspector build therefore cannot read the
   answer.  Sibling harnesses stay visible, as they do for QuartetFuzz.

Writes cases.json (case_id -> project name, fuzzer, gold path, language) beside
the projects.
"""
import ast, json, os, re, shutil, sys

DATASET = '/path/to/QuartetFuzz/benchmark/benchmark_100.jsonl'
PINNED_OF = '/path/to/home/oss-fuzz-955c6866'

STUB_HEAD = r'''/* Gold harness replaced by an empty stub for baseline generation. */
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
#define QF_EXTERN extern "C"
#else
#define QF_EXTERN extern
#endif
'''

STUB_TAIL = r'''QF_EXTERN int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  (void)data;
  (void)size;
  return 0;
}
'''


def stub_source(symbols):
  # References keep the target function linked, so Fuzz Introspector records it
  # (as it does on the public server, where the gold harness links it).  They
  # carry nothing beyond the target's name, which every system is given.
  out = [STUB_HEAD]
  if symbols:
    out.append('/* Keep the target function linked (no call, no arguments). */\n')
    for i, sym in enumerate(symbols):
      out.append(f'QF_EXTERN void qf_target_{i}(void) __asm__("{sym}");\n')
    refs = ', '.join(f'qf_target_{i}' for i in range(len(symbols)))
    out.append('__attribute__((used)) static void (*const qf_keep[])(void) = {'
               + refs + '};\n')
  out.append(STUB_TAIL)
  return ''.join(out)

PIN_SH = r'''#!/bin/bash
# Check out every srcmap repository at its pinned revision.  Fails the image
# build if a repository that exists cannot be pinned.
set -u
while read -r path url rev; do
  [ -z "$path" ] && continue
  if [ ! -d "$path/.git" ] && [ ! -f "$path/.git" ]; then
    echo "qf-pin: $path absent at image build time (cloned later or not used); skipped"
    continue
  fi
  cd "$path" || exit 1
  if ! git cat-file -e "$rev^{commit}" 2>/dev/null; then
    git fetch -q --depth=1 origin "$rev" 2>/dev/null || git fetch -q --unshallow origin 2>/dev/null || git fetch -q origin 2>/dev/null
  fi
  git -c advice.detachedHead=false checkout -q -f "$rev" || { echo "qf-pin: FAILED $path $rev"; exit 1; }
  git submodule update -q --init --recursive 2>/dev/null || echo "qf-pin: submodule update failed in $path (left as is)"
  echo "qf-pin: $path -> $(git rev-parse HEAD)"
done < /qf/pins.txt
'''


STUB_SH = r'''#!/bin/bash
# Replace the gold harness of this case with the stub.
#  - The gold is the file at the declared path; if that path is only created at
#    build time (binutils copies $SRC/fuzz_*.c into the tree), the gold is the
#    same-named file that defines LLVMFuzzerTestOneInput.
#  - Every other file under /src with byte-identical content is a copy of the
#    gold and is replaced too.  Same-named files with other content (a sibling
#    harness of another branch, an unrelated sample program) are left alone.
#  - A harness embedded in library source inside #ifdef FUZZ_TARGET (util-linux)
#    has only that block replaced, so the library code stays.
# Fails the image build if no gold is found.
set -u
D=$1; B=$(basename "$1")
if [ -f "$D" ]; then ref=$D
else ref=$(find /src -name .git -prune -o -type f -name "$B" -print0 | xargs -0 -r grep -l LLVMFuzzerTestOneInput | head -1)
fi
[ -n "$ref" ] && [ -f "$ref" ] || { echo "qf-stub: FAILED, gold $D not found"; exit 1; }
cp "$ref" /qf/gold_original
n=0
while IFS= read -r -d '' f; do
  cmp -s "$f" /qf/gold_original || continue
  if grep -q '^#ifdef FUZZ_TARGET' "$f"; then
    python3 /qf/stub_block.py "$f" /qf/gold_stub.c || exit 1
    echo "qf-stub: $f (FUZZ_TARGET block)"
  else
    cp /qf/gold_stub.c "$f"; echo "qf-stub: $f"
  fi
  n=$((n+1))
done < <(find /src -name .git -prune -o -type f -name "$B" -print0)
rm -f /qf/gold_original
[ "$n" -gt 0 ] || { echo "qf-stub: FAILED, nothing replaced"; exit 1; }
'''

STUB_BLOCK_PY = r'''import re, sys
# Replace the #ifdef FUZZ_TARGET ... #endif block that defines
# LLVMFuzzerTestOneInput with the stub's body (includes dropped).
path, stub = sys.argv[1], open(sys.argv[2]).read()
# The target is defined in this very file, so the symbol references are dropped.
body = '\n'.join(l for l in stub.splitlines()
                 if not l.startswith('#include') and 'qf_target_' not in l
                 and 'qf_keep' not in l and 'Keep the target' not in l)
src = open(path).read()
out, pos, done = [], 0, False
for m in re.finditer(r'^#ifdef FUZZ_TARGET\n', src, re.M):
  end = src.find('\n#endif', m.end())
  block = src[m.end():end]
  if 'LLVMFuzzerTestOneInput' in block and not done:
    out.append(src[pos:m.end()] + body + '\n')
    pos, done = end, True
out.append(src[pos:])
if not done:
  sys.exit('no FUZZ_TARGET block with LLVMFuzzerTestOneInput')
open(path, 'w').write(''.join(out))
'''


def case_name(project, k):
  return re.sub(r'[^a-z0-9_-]', '-', project.lower()) + f'-c{k}'


SYMBOLS = {}


def main(out_root, skip=()):
  global SYMBOLS
  SYMBOLS = json.load(open(os.path.join(os.path.dirname(out_root.rstrip('/')),
                                        'target_symbols.json')))
  cases = [json.loads(l) for l in open(DATASET)]
  os.makedirs(f'{out_root}/projects', exist_ok=True)
  per_project = {}
  index = {}
  for c in cases:
    proj = c['project']
    per_project[proj] = per_project.get(proj, 0) + 1
    name = case_name(proj, per_project[proj])
    if name in skip:
      index[c['case_id']] = json.load(open(os.path.join(
          os.path.dirname(out_root.rstrip('/')), 'cases.json')))[c['case_id']]
      continue
    src = f'{PINNED_OF}/projects/{proj}'
    dst = f'{out_root}/projects/{name}'
    if os.path.exists(dst):
      shutil.rmtree(dst)
    shutil.copytree(src, dst)

    pins = c['version_pins']
    pins = ast.literal_eval(pins) if isinstance(pins, str) else pins
    os.makedirs(f'{dst}/qf', exist_ok=True)
    with open(f'{dst}/qf/pins.txt', 'w') as f:
      for path, r in sorted(pins.get('all_repos', {}).items()):
        f.write(f"{path} {r['url']} {r['rev']}\n")
    with open(f'{dst}/qf/pin.sh', 'w') as f:
      f.write(PIN_SH)
    with open(f'{dst}/qf/stub.sh', 'w') as f:
      f.write(STUB_SH)
    with open(f'{dst}/qf/stub_block.py', 'w') as f:
      f.write(STUB_BLOCK_PY)
    with open(f'{dst}/qf/gold_stub.c', 'w') as f:
      f.write(stub_source(SYMBOLS.get(c['case_id'], {}).get('syms', [])))

    gold = c['harness_source']
    with open(f'{dst}/Dockerfile', 'a') as f:
      f.write('\n# --- QuartetFuzz baseline setup (pinned revisions, gold stubbed) ---\n')
      f.write('COPY qf /qf\n')
      f.write('RUN bash /qf/pin.sh\n')
      f.write(f'RUN bash /qf/stub.sh {gold}\n')
      # Fresh apt index: the introspector build installs packages at build time.
      f.write('RUN apt-get update -q\n')

    index[c['case_id']] = {
        'oss_fuzz_project': name,
        'project': proj,
        'fuzzer_name': c['fuzzer_name'],
        'gold_path': gold,
        'language': c['language'],
        'target_function': c['target_function'],
        'target_declaration': c['target_declaration'],
    }
  with open(f'{out_root}/cases.json', 'w') as f:
    json.dump(index, f, indent=1)
  print(f'{len(index)} case projects written under {out_root}/projects')


if __name__ == '__main__':
  main(sys.argv[1], set(sys.argv[2:]))
