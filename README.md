# OSS-Fuzz-Gen, as run in the QuartetFuzz evaluation

This repository is [google/oss-fuzz-gen](https://github.com/google/oss-fuzz-gen)
at commit `c0982c5d40a7e93ce70fd319705804b9a29954d0`, plus the changes we made
to run it as a baseline in *QuartetFuzz: Making LLM-Generated Fuzz Harnesses
Reliable with Four Principles* (IEEE S&P 2027).  Upstream's README is kept as
[`README.upstream.md`](README.upstream.md).

The changes connect OSS-Fuzz-Gen to the QuartetFuzz benchmark; none of them
alters how it generates harnesses.

- Upstream agent mode on Claude (`claude-sonnet-5`), one sample, without
  sampling parameters (the model does not accept them).
- No Fuzz Introspector service: its public data contains the reference
  harnesses, so project context comes from local reports instead.
- Each task runs on its own OSS-Fuzz project built from the pinned task image
  with the reference harness stubbed out and removed from git history
  (`quartet/make_case_projects.py`, `quartet/scrub_git.sh`); image builds use
  the layer cache instead of re-cloning upstream.
- C++ target functions are passed as Itanium name fragments; for binutils the
  target path is the reference harness's pre-build location.
- Tool calls with undeclared arguments are dropped instead of aborting the run.
- Final ASan and coverage builds of the chosen harness
  (`quartet/build_final.sh`).

## Running

The scripts in `quartet/` are the ones used in the evaluation.  Paths of the
machine they ran on appear as `/path/to/...`: `/path/to/baselines/ofg-fair` is
this checkout, `/path/to/baselines/ofg-work` a work directory, and
`/path/to/QuartetFuzz` a checkout of the QuartetFuzz artifact, whose
`benchmark/` holds the tasks.

| Script | Purpose |
|---|---|
| `quartet/make_case_projects.py` | per-task OSS-Fuzz projects from the benchmark |
| `quartet/make_benchmarks.py` | OSS-Fuzz-Gen benchmark YAML per task |
| `quartet/run_case.sh` | one task: upstream agent mode, no Fuzz Introspector |
| `quartet/schedule.py`, `quartet/driver.py` | many tasks, memory-aware |
| `quartet/build_final.sh`, `build_final_loop.sh` | ASan / coverage builds of the chosen harness |
| `quartet/leak_check.py` | checks that no run could read the reference harness |

The delivered harnesses are then fuzzed and measured with the QuartetFuzz
artifact's `benchmark/tools/`, exactly as QuartetFuzz's own harnesses.
