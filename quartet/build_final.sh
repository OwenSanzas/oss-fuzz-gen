#!/bin/bash
# Builds of OFG's output for one finished case: ASan (final_asan/) and
# coverage (final_cov/).
# OFG's output is its chosen result (status/01/result.json): fuzz_target_source
# and, if OFG changed it, build_script_source.  Both builds are made the way
# OFG's execution stage builds a target: the source at the benchmark's
# target_path in the case image, the project's build script (or OFG's), OSS-Fuzz
# `compile` with libFuzzer.  The whole /out is kept (runtime libraries).
# OFG keeps no such binaries itself: its output directory ends with the last
# coverage build of whatever version it built last.
set -u
P=$1
WORK=/path/to/baselines/ofg-work
D=$WORK/results-nofi/$P
S=$D/final_src
mkdir -p $S
python3 - "$D" "$S" "$WORK/benchmarks-nofi/$P.yaml" <<'E' || { mkdir -p $D/final_asan $D/final_cov; cp $S/status $D/final_asan/status; cp $S/status $D/final_cov/status; cat $S/status; exit 2; }
import glob, json, sys, re
d, s, bench = sys.argv[1:4]
r = json.load(open(glob.glob(f'{d}/work/output-*/status/01/result.json')[0]))
if str(r.get('compiles')) != 'True' or not r.get('fuzz_target_source'):
    open(f'{s}/status', 'w').write('no compiling harness from OFG\n'); sys.exit(1)
open(f'{s}/harness.src', 'w').write(r['fuzz_target_source'])
if r.get('build_script_source'):
    open(f'{s}/build.sh', 'w').write(r['build_script_source'])
y = open(bench).read()
tp = re.search(r'"target_path": "([^"]+)"', y).group(1)
tn = re.search(r'"target_name": "([^"]+)"', y).group(1)
lang = re.search(r'"language": "([^"]+)"', y).group(1)
open(f'{s}/target', 'w').write(f'{tp}\n{tn}\n{lang}\n')
E
TP=$(sed -n 1p $S/target); TN=$(sed -n 2p $S/target); LG=$(sed -n 3p $S/target)
for SAN in address coverage; do
  [ $SAN = address ] && F=$D/final_asan || F=$D/final_cov
  [ -f $F/status ] && grep -q '^built$' $F/status && continue
  mkdir -p $F
  cp $S/harness.src $F/; [ -f $S/build.sh ] && cp $S/build.sh $F/
  docker run --rm --memory 16g \
    -e SANITIZER=$SAN -e FUZZING_ENGINE=libfuzzer -e ARCHITECTURE=x86_64 \
    -e FUZZING_LANGUAGE="$LG" -v $F:/final \
    --entrypoint bash "gcr.io/oss-fuzz/$P" -c "
      cp /final/harness.src '$TP'
      [ -f /final/build.sh ] && cp /final/build.sh /src/build.sh
      compile > /final/build.log 2>&1; echo \"compile rc=\$?\" >> /final/build.log
      rm -rf /final/out; cp -a /out /final/out 2>/dev/null
      [ -f /final/out/$TN ] && echo built > /final/status || echo 'build failed' > /final/status
      chmod -R a+rwX /final" > /dev/null 2>&1
  echo "$SAN: $(cat $F/status)"
done
