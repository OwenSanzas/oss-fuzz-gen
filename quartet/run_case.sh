#!/bin/bash
# Run OFG on one benchmark case: upstream agent mode, without Fuzz Introspector.
# Model: Claude Sonnet 5 (no sampling parameters accepted, so no temperature
# list).  Evaluation runs 300 s, max 100 rounds, as in upstream's published
# experiments.
#
# One sample: OFG's output for the case is that sample's own result
# (status/01/result.json, which OFG writes from the trial's best_result); we
# do not select among samples.
#
# usage: run_case.sh <oss_fuzz_project> [num_samples]
set -u
P=$1
N=${2:-1}
OFG=/path/to/baselines/ofg-fair
WORK=/path/to/baselines/ofg-work
OUT=$WORK/results-nofi/$P
mkdir -p "$OUT"
set -a; . ~/.config/agf/anthropic.env; set +a
. $OFG/.venv/bin/activate
cd $OFG
# Keep the shared pinned OSS-Fuzz tree as is (no git clean of our case projects).
export OFG_CLEAN_UP_OSS_FUZZ=0
# No FI anywhere: project examples look for a local report in an empty
# directory (none found), and every FI query goes to a closed local port, so
# nothing is fetched from the public FI server or bucket (which hold the gold).
mkdir -p $WORK/no-fi
export OFG_LOCAL_FI_OUT=$WORK/no-fi
export OFG_USAGE_LOG=$OUT/usage.jsonl
# Upstream defaults: 3 parallel trial evaluations per benchmark.
export LLM_NUM_EVA=${LLM_NUM_EVA:-3}
# Start clean: OFG reuses an existing generated project directory
# (projects/<proj>-<function>-<trial>), so leftovers from an earlier run would
# carry their agent-written build scripts into this one.
for d in $WORK/oss-fuzz/projects/$P-*; do
  [ -d "$d" ] || continue
  docker rmi -f "gcr.io/oss-fuzz/$(basename $d)" > /dev/null 2>&1
  rm -rf "$d"
done
docker run --rm -v $WORK/oss-fuzz/build:/b --entrypoint bash \
  gcr.io/oss-fuzz-base/base-runner -c "rm -rf /b/out/$P-* /b/work/$P-*" > /dev/null 2>&1
# OFG's containers leave root-owned files in the work directory.
docker run --rm -v "$OUT":/o --entrypoint bash gcr.io/oss-fuzz-base/base-runner \
  -c "rm -rf /o/work /o/exit_code /o/finished" > /dev/null 2>&1
date -u +%FT%TZ > "$OUT/started"
python3 run_all_experiments.py \
  --benchmark-yaml "$WORK/benchmarks-nofi/$P.yaml" \
  --model claude-sonnet-5-chat \
  --agent \
  --template-directory prompts/template_xml \
  --num-samples "$N" \
  --run-timeout 300 \
  --max-round 100 \
  --introspector-endpoint http://127.0.0.1:9/api \
  --oss-fuzz-dir "$WORK/oss-fuzz" \
  --work-dir "$OUT/work" \
  > "$OUT/run.log" 2>&1
echo $? > "$OUT/exit_code"
date -u +%FT%TZ > "$OUT/finished"
