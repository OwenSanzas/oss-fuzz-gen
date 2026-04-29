# Precomputed OFG Outputs (Reference)

This directory contains paper-experiment outputs of OSS-Fuzz-Gen on the
25-case subset (`quartetfuzz_experiment/subset_25.jsonl`). They serve as
a **fallback reference** for reviewers whose live run cannot complete
end-to-end (typically because the OSS-Fuzz Docker pipeline fails or the
project's upstream repo cannot be cloned in their environment).

## What is included per case

```
precomputed_outputs/<project>__<fuzzer>/
├── run_result.json        Per-case status, error, harness path, duration
├── harness.{c|cpp}        The OFG-generated driver (LLM output)
├── paper_coverage.json    OFG headline coverage from the paper run (full_comparison_table.csv):
│                            lines_pct / branches_pct / functions_pct / regions_pct,
│                            ofg_status, entry_match.
└── source.txt             "live_earlier_run" or "paper_csv_only"
```

20 of the 25 cases ship a `run_result.json` and `harness.c|cpp` recovered
from a previous OFG run on the artifact server. The remaining 5 cases
(`openssh/privkey_fuzz`, `ndpi/fuzz_filecfg_category`,
`fftw3/fftw3_fuzzer`, `quickjs/fuzz_compile`, `libpcap/fuzz_both`) ship
only `paper_coverage.json` because the prior run did not produce a
preserved harness for them.

## When the fallback is used

`quartetfuzz_experiment/run_experiment.py` runs OFG live for every case.
After the live run, any case for which
`<output>/<project>/<fuzzer>/run_result.json` is missing is filled from
`precomputed_outputs/<project>__<fuzzer>/`. A `fallback.txt`
file containing `PRECOMPUTED_FALLBACK` is written so a reviewer can
distinguish live-run cases from fallback cases.

Successful live runs are **never** overwritten by the fallback.

## Provenance

- Live earlier-run files: produced on the artifact server with this
  fork (Anthropic-direct Claude Sonnet 4.6, `--num-samples 1`,
  `--run-timeout 30`, `--max-cycle-count 5`, `--parallel 4`). Compatible
  with the live runner shipped here.
- `paper_coverage.json`: extracted from
  `oss_fuzz_harness/baselines/results/ofg_600s/full_comparison_table.csv`
  in the paper artifact (Sonnet 4.6, 600 s libFuzzer, empty corpus,
  ASan, OSS-Fuzz pinned commit `4aeb97ef9658244abc844831afacd204afdb6fca`).
