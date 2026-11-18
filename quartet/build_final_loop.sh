#!/bin/bash
# Build OFG's chosen harness (ASan) for every finished case, 2 at a time, only
# while at least 16 GB of memory is available.  Runs until all 100 have one.
WORK=/path/to/baselines/ofg-work
LOG=$WORK/logs/build_final.log
while true; do
  todo=()
  for d in $WORK/results-nofi/*/; do
    p=$(basename $d)
    [ -f $d/exit_code ] && { [ ! -f $d/final_asan/status ] || [ ! -f $d/final_cov/status ]; } && todo+=($p)
  done
  done_n=$(ls $WORK/results-nofi/*/final_cov/status 2>/dev/null | wc -l)
  [ ${#todo[@]} -eq 0 ] && [ $done_n -ge 100 ] && { echo "$(date -u +%FT%TZ) all done" >> $LOG; exit 0; }
  for p in "${todo[@]:0:2}"; do
    while [ $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) -lt 16 ]; do sleep 60; done
    ( s=$(/path/to/baselines/ofg-fair/quartet/build_final.sh $p 2>&1 | tr '\n' ' '); echo "$(date -u +%FT%TZ) $p: $s" >> $LOG ) &
  done
  wait
  [ ${#todo[@]} -eq 0 ] && sleep 120
done
