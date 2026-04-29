# OSS-Fuzz-Gen (QuartetFuzz Fork — 25-case Reproducibility)

This is a fork of [google/oss-fuzz-gen](https://github.com/google/oss-fuzz-gen)
modified to serve as the **OFG baseline** in the manuscript
*"Quality-Assured Fuzz Harness Generation via the Four Principles
Framework"* (CCS 2026 anonymous submission). Upstream OFG behaviour
(prompts, scheduler, ADK agents, build pipeline) is unchanged.

It is shipped together with two sibling forks: the QuartetFuzz system
itself, and the modified PromeFuzz baseline. All three share an
identical `subset_25/` layout for the RQ3 reproducibility experiment.

---

## What this fork adds vs. upstream

| File | Change | Why |
|---|---|---|
| `llm_toolkit/models.py` | Adds `ClaudeSonnet46Direct` (the model class used in the paper). | Talks to Anthropic's REST API directly, so reviewers don't need a Vertex AI account. |
| `agent/base_agent.py` | Relaxes the `ADKBaseAgent` Vertex-AI-only assertion. | Lets the direct Anthropic class plug into the existing ADK plumbing without forking the upstream class hierarchy. |
| `experiment/builder_runner.py` | Preserves the built fuzzer binaries as part of saved artefacts. | Required for the per-case `harness.{c|cpp}` and `run_result.json` shipped under `subset_25/precomputed/`. |
| `quartetfuzz_experiment/` | Wrapper directory: `run_experiment.py`, `extract_coverage.py`, `build_strict_report.py`, `requirements.txt`, and a 2-case demo. | Per-case → per-result driver for the paper's RQ3 sweep, plus the post-run fallback hook. |
| `subset_25/` | 25-case manifest + precomputed reference outputs. | The artefact's headline reproducibility target. |

The original upstream README is preserved as
[`README.upstream.md`](README.upstream.md).

---

## Quick start (25-case reproduction)

```bash
# 1. After cloning (or unpacking) this repository:
cd <this repository>

# 2. Python environment.
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r quartetfuzz_experiment/requirements.txt

# 3. Anthropic credentials.
export ANTHROPIC_API_KEY=sk-ant-...

# 4. Run the 25-case subset.
python3 quartetfuzz_experiment/run_experiment.py \
    --dataset       subset_25/subset_25.jsonl \
    --benchmarks    quartetfuzz_experiment/example_data/ofg_benchmarks \
    --output        ./results_subset25 \
    --model         claude-sonnet-4-6 \
    --num-samples   1 \
    --run-timeout   30 \
    --max-cycle-count 5 \
    --parallel      4
```

Per-case outputs land in `./results_subset25/<project>/<fuzzer_name>/`:

```
results_subset25/zlib/zlib_uncompress2_fuzzer/
├── run_result.json    Status, error, harness path, duration_ms.
├── harness.{c|cpp}    The OFG-generated driver picked for this case.
├── ofg_workdir/       Raw OFG artefacts (build logs, OFG's own coverage reports).
└── fallback.txt       Present only if this case was filled from subset_25/precomputed/.
```

After the live run finishes, any case for which
`run_result.json` is missing is filled from
`subset_25/precomputed/<case>/`. **Successful live runs are never
overwritten.**

The post-processing pipeline (`extract_coverage.py` →
`build_strict_report.py`) reproduces the paper's strict comparison
table:

```bash
python3 quartetfuzz_experiment/extract_coverage.py --output ./results_subset25

python3 quartetfuzz_experiment/build_strict_report.py \
    --coverage    ./results_subset25/coverage_metrics.json \
    --gold        quartetfuzz_experiment/example_data/gold_baseline.jsonl \
    --dataset     subset_25/subset_25.jsonl \
    --harness-root ./results_subset25 \
    --output      ./results_subset25/ofg_vs_gold_strict
```

For full per-script documentation see
[`quartetfuzz_experiment/README.md`](quartetfuzz_experiment/README.md).

---

## Repository layout

```
.
├── llm_toolkit/                 Upstream OFG model classes + ClaudeSonnet46Direct.
├── agent/                       Upstream OFG agent stack (ADK).
├── experiment/                  Upstream OFG build/runner (with binary-preservation patch).
├── quartetfuzz_experiment/      ★ Wrapper for the 25-case sweep.
│   ├── run_experiment.py        Driver + post-run fallback hook.
│   ├── extract_coverage.py      Walks ofg_workdir/ for llvm-cov reports.
│   ├── build_strict_report.py   Produces the entry-match strict-report Markdown/CSV.
│   ├── example_data/            2-case demo manifest + ofg_benchmarks/ yamls.
│   ├── requirements.txt         Extra deps (anthropic ≥ 0.94, PyYAML).
│   └── README.md                Per-script docs.
├── subset_25/                   ★ 25-case reproducibility package.
│   ├── subset_25.jsonl          25-case manifest, identical across the three forks.
│   ├── precomputed/             Per-case fallback (run_result.json, harness.{c|cpp},
│   │                            paper_coverage.json, source.txt).
│   └── README.md                Schema, provenance, fallback contract.
├── README.md                    This file.
└── README.upstream.md           Original upstream OFG README.
```

---

## License

Apache-2.0, inherited from upstream OSS-Fuzz-Gen. See
[`LICENSE`](LICENSE).
