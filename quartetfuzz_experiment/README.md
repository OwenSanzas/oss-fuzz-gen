# QuartetFuzz OFG Reproducibility Package

This directory contains everything needed to reproduce our OSS-Fuzz-Gen (OFG)
baseline experiment using **Claude Sonnet 4.6** via the direct Anthropic API.

The fork that hosts this directory adds:

- **`llm_toolkit/models.py`**: `ClaudeSonnet46Direct` class. Lets you pass
  `--model claude-sonnet-4-6` to OFG and have it talk to Anthropic directly
  instead of Vertex AI.
- **`agent/base_agent.py`**: relaxes ADKBaseAgent's Vertex-AI-only check.
- **`experiment/builder_runner.py`**: preserves fuzzer binaries as artifacts.

The scripts in this directory wrap OFG so that:

1. It runs over an arbitrary benchmark dataset (JSONL).
2. Coverage metrics are extracted into a single JSON.
3. A strict comparison report against a gold baseline can be built.

---

## 0. Prerequisites

- **Python 3.10+**
- **Docker** (OSS-Fuzz needs it).
- **An Anthropic API key** with access to `claude-sonnet-4-6`.
- ~30 GB free disk for build artifacts.
- A POSIX environment (Linux is what we tested on).

---

## 1. Clone & install

```bash
# 1a. After cloning this repository:
cd oss-fuzz-gen

# 1b. (Optional) Use a virtualenv.
python3 -m venv .venv
source .venv/bin/activate

# 1c. Install OFG's own deps + the extra deps needed by these scripts.
pip install -r requirements.txt
pip install -r quartetfuzz_experiment/requirements.txt
```

Make sure Docker works without sudo:

```bash
docker info > /dev/null
```

---

## 2. Set the API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The runner refuses to start if this variable is empty.

---

## 3. Quick start (2-case smoke test)

The included example dataset has two small cases:
`zlib/zlib_uncompress2_fuzzer` and `libyaml/libyaml_loader_fuzzer`. Both
build quickly and exercise the full pipeline.

```bash
cd quartetfuzz_experiment

python run_experiment.py \
    --dataset example_data/benchmark_cases.jsonl \
    --benchmarks example_data/ofg_benchmarks \
    --output ./results_example \
    --num-samples 2 \
    --run-timeout 600 \
    --parallel 2

python extract_coverage.py --output ./results_example

python build_strict_report.py \
    --coverage ./results_example/coverage_metrics.json \
    --gold example_data/gold_baseline.jsonl \
    --dataset example_data/benchmark_cases.jsonl \
    --harness-root ./results_example \
    --output ./results_example/ofg_vs_gold_strict
```

After it finishes you should see:

```
results_example/
├── run_manifest.json
├── coverage_metrics.json
├── ofg_vs_gold_strict.md
├── ofg_vs_gold_strict.csv
├── zlib/
│   └── zlib_uncompress2_fuzzer/
│       ├── run_result.json
│       ├── harness.{c|cpp}
│       └── ofg_workdir/...
└── libyaml/
    └── libyaml_loader_fuzzer/
        ├── run_result.json
        ├── harness.{c|cpp}
        └── ofg_workdir/...
```

The smoke test takes roughly 30-60 minutes depending on Docker speed and
how many fuzzing cycles OFG decides to run.

---

## 4. Running on your own dataset

Drop in your own JSONL dataset. Each line must contain at minimum:

```json
{
  "case_id":         "project/fuzzer_name",
  "project":         "project",
  "fuzzer_name":     "fuzzer_name",
  "source_file":     "fuzzer_name.c",
  "target_function": "fully_qualified::target_function"
}
```

Other fields (such as `source_code`, `loc`, `repo_url`) are ignored by these
scripts but are useful in your own dataset for downstream analysis.

If you also have pre-made OFG benchmark YAML files (one per case, named
`{project}_{fuzzer_name}.yaml`), pass their directory with `--benchmarks`.
Hand-written YAMLs with full type information generally produce better OFG
output than the minimal YAML the runner auto-generates.

```bash
python run_experiment.py \
    --dataset path/to/your/cases.jsonl \
    --benchmarks path/to/your/ofg_benchmarks \
    --output ./results_full \
    --num-samples 2 \
    --run-timeout 600 \
    --parallel 4
```

To compare against your own gold baseline, build a JSONL where each line is:

```json
{"case_id": "project/fuzzer_name", "lines": 12.3, "branches": 8.5, "functions": 11.0, "regions": 10.2}
```

Then:

```bash
python extract_coverage.py --output ./results_full
python build_strict_report.py \
    --coverage ./results_full/coverage_metrics.json \
    --gold path/to/your/gold_baseline.jsonl \
    --dataset path/to/your/cases.jsonl \
    --harness-root ./results_full \
    --output ./results_full/ofg_vs_gold_strict
```

---

## 5. Script reference

### `run_experiment.py`

Wraps OFG's `run_one_experiment.run()`. For each case it writes:

- `{output}/{project}/{fuzzer_name}/run_result.json` with status, error, and
  the relative path to the saved harness.
- `{output}/{project}/{fuzzer_name}/harness.{c|cpp}` with the harness OFG
  produced (the highest-coverage trial).
- `{output}/{project}/{fuzzer_name}/ofg_workdir/` with raw OFG artifacts
  (build logs, intermediate fuzz targets, OFG's own coverage reports).

Key flags:

- `--dataset PATH` (required): JSONL benchmark dataset.
- `--benchmarks DIR`: optional pre-made OFG YAMLs.
- `--output DIR` (required): where to write results.
- `--model`: defaults to `claude-sonnet-4-6`.
- `--num-samples`: trials per case (default 2).
- `--run-timeout`: fuzz seconds per trial (default 600).
- `--max-cycle-count`: OFG iteration cycles per trial (default 5).
- `--parallel`: max concurrent cases (default 4).
- `--oss-fuzz-dir`: local OSS-Fuzz checkout. Cloned automatically if missing.
- `--limit N`: only run the first N cases (handy for smoke tests).

### `extract_coverage.py`

Walks the `--output` directory, reads each case's
`ofg_workdir/code-coverage-reports/{trial}/linux/summary.json`, picks the
highest-line-coverage trial, and writes everything into
`{output}/coverage_metrics.json`.

### `build_strict_report.py`

Produces a Markdown + CSV strict comparison. Strict scoring rules:

- `entry_match` if OFG's harness contains an identifier matching the
  benchmark's `target_function` (final identifier for C++ qualified names,
  with namespace/class fallbacks).
- `entry_miss` if it built and ran but matched no identifier.
- `ofg_failed` for everything else.

Rows tagged `entry_miss` or `ofg_failed` have their effective coverage
zeroed when computing the aggregate stats.

---

## 6. Notes & caveats

- Running 100 cases with `run_timeout=600` and `parallel=4` takes 4-8 hours.
- OFG occasionally hangs on its own retry loop for hard cases (notably
  `imagemagick/encoder_mvg_fuzzer` in our experience). If you reproduce on
  the full gold benchmark, watch for stuck workers and exclude that case.
- Auto-generated YAMLs are minimal and biased toward C. Hand-written YAMLs
  with C++ class qualifiers and full parameter types yield noticeably better
  OFG harnesses for C++ projects.
- Gold baselines must be measured under matching conditions (empty corpus,
  same fuzz duration, same OSS-Fuzz commit) for the comparison to be fair.
