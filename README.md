# OSS-Fuzz-Gen (QuartetFuzz Fork — Claude Sonnet 4.6 + Reproducibility)

This is a fork of [google/oss-fuzz-gen](https://github.com/google/oss-fuzz-gen)
with two additions:

1. **Claude Sonnet 4.6 support** via the direct Anthropic API (no Vertex AI
   account required). Pass `--model claude-sonnet-4-6` and set
   `ANTHROPIC_API_KEY`.
2. **A reproducibility package** at [`quartetfuzz_experiment/`](quartetfuzz_experiment/).
   Three small scripts (`run_experiment.py`, `extract_coverage.py`,
   `build_strict_report.py`) plus a 2-case example dataset that lets anyone
   re-run our OFG baseline experiment end-to-end.

The fork is intended for academic reproducibility of the QuartetFuzz paper.
Upstream OSS-Fuzz-Gen capabilities are unchanged.

---

## Quick start

```bash
# After cloning this repository:
cd oss-fuzz-gen

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r quartetfuzz_experiment/requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...

cd quartetfuzz_experiment
python run_experiment.py \
    --dataset example_data/benchmark_cases.jsonl \
    --benchmarks example_data/ofg_benchmarks \
    --output ./results_example \
    --num-samples 2 --run-timeout 600 --parallel 2

python extract_coverage.py --output ./results_example

python build_strict_report.py \
    --coverage ./results_example/coverage_metrics.json \
    --gold example_data/gold_baseline.jsonl \
    --dataset example_data/benchmark_cases.jsonl \
    --harness-root ./results_example \
    --output ./results_example/ofg_vs_gold_strict
```

For full documentation including how to run on your own dataset, see
[`quartetfuzz_experiment/README.md`](quartetfuzz_experiment/README.md).

---

## Files modified vs. upstream

| File | Change |
|---|---|
| `llm_toolkit/models.py` | Added `ClaudeSonnet46Direct` class (direct Anthropic API). |
| `agent/base_agent.py`   | Relaxed Vertex-AI-only assertion in `ADKBaseAgent`. |
| `experiment/builder_runner.py` | Preserve fuzzer binaries as build artifacts. |

The original upstream README is preserved as
[`README.upstream.md`](README.upstream.md) for reference.

---

## License

Same as upstream OSS-Fuzz-Gen (Apache 2.0). See [`LICENSE`](LICENSE).
