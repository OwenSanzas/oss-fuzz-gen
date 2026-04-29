#!/usr/bin/env python3
"""
OFG Reproducibility Runner.

Runs OSS-Fuzz-Gen (OFG) over a dataset of fuzz benchmark cases using
Claude Sonnet 4.6 (via the direct Anthropic API) and saves results in a
format compatible with the strict comparison report.

Usage:
    export ANTHROPIC_API_KEY=...
    python run_experiment.py \
        --dataset example_data/benchmark_cases.jsonl \
        --benchmarks example_data/ofg_benchmarks \
        --output ./results

Dataset format (one JSON object per line):
    {
      "case_id": "zlib/compress_fuzzer",
      "project": "zlib",
      "fuzzer_name": "compress_fuzzer",
      "source_file": "compress_fuzzer.c",
      "source_code": "...",
      "target_function": "compress2"
    }

OFG benchmark YAML format (optional, in --benchmarks dir, name = case_id with
'/' replaced by '_'):
    "functions":
    - "name": "compress2"
      "return_type": "void"
      "signature": "compress2(...)"
    "language": "c"
    "project": "zlib"
    "target_name": "compress_fuzzer"
    "target_path": "/src/compress_fuzzer.c"

If a YAML for a case is missing, a minimal one is auto-generated from the
dataset entry. Better-quality YAMLs (with full type information) usually
produce better OFG output, so providing them is recommended.

Output directory layout:
    {output}/
    ├── run_manifest.json
    └── {project}/
        └── {fuzzer_name}/
            ├── run_result.json
            ├── harness.{c|cpp}
            └── ofg_workdir/        (raw OFG artifacts)
"""

import argparse
import json
import os
import shutil
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

# Import OFG modules from the parent package.
SCRIPT_DIR = Path(__file__).resolve().parent
OFG_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(OFG_ROOT))

import llm_toolkit.models as models  # noqa: E402
import run_one_experiment              # noqa: E402
from experiment.benchmark import Benchmark    # noqa: E402
from experiment.workdir import WorkDirs       # noqa: E402


@dataclass
class RunResult:
    case_id: str
    project: str
    fuzzer_name: str
    target_function: str
    status: str           # "succeeded" | "failed"
    mode: str             # "full"
    seed: int
    error: str | None = None
    generated_harness_path: str | None = None
    duration_ms: int = 0


def load_dataset(path: Path) -> list[dict]:
    """Load JSONL dataset of benchmark cases."""
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def case_id_to_yaml_name(case_id: str) -> str:
    """Convert case_id (project/fuzzer_name) to OFG yaml filename stem."""
    return case_id.replace('/', '_') + '.yaml'


def get_or_generate_yaml(case: dict, benchmarks_dir: Path | None,
                          dest_path: Path) -> Path:
    """Find pre-made OFG yaml for the case, or generate one from dataset."""
    yaml_name = case_id_to_yaml_name(case['case_id'])

    if benchmarks_dir is not None:
        src = benchmarks_dir / yaml_name
        if src.exists():
            shutil.copy2(src, dest_path)
            return dest_path

    # Auto-generate a minimal yaml from the dataset entry.
    project = case['project']
    fuzzer_name = case['fuzzer_name']
    target_function = case.get('target_function', '')

    # Heuristic: figure out the source file and language from the dataset.
    source_file = case.get('source_file', f'{fuzzer_name}.c')
    if source_file.endswith(('.cc', '.cpp', '.cxx')):
        language = 'c++'
    else:
        language = 'c'

    target_path = f'/src/{source_file}'

    import yaml
    yaml_data = {
        'functions': [{
            'name': target_function,
            'return_type': 'void',
            'signature': f'{target_function}()',
        }],
        'language': language,
        'project': project,
        'target_name': fuzzer_name,
        'target_path': target_path,
        'use_project_examples': False,
    }
    with open(dest_path, 'w') as f:
        yaml.dump(yaml_data, f, default_flow_style=False)
    return dest_path


class _OFGArgs:
    """Argparse-like namespace passed into run_one_experiment.run()."""

    def __init__(self, model_name: str, num_samples: int, run_timeout: int,
                 max_cycle_count: int, work_dir: str):
        self.ai_binary = ''
        self.model = model_name
        self.model_name = model_name
        self.work_dir = work_dir
        self.num_samples = num_samples
        self.temperature = 0.4
        self.temperature_list = None
        self.run_timeout = run_timeout
        self.max_cycle_count = max_cycle_count
        self.cloud_experiment_bucket = None
        self.cloud_experiment_name = None
        self.no_agent = False
        self.agent = False
        self.function_search_query = None
        self.custom_pipeline = ''
        self.context = False
        self.use_project_examples = False
        self.generate_reproducer = False
        self.coverage_only = False
        self.max_round = 5
        self.trial_dir = None
        self.benchmark_yaml = None
        self.prompt_builder = None
        self.template_directory = str(OFG_ROOT / 'prompts')


class OFGRunner:
    def __init__(self, model_name: str, num_samples: int, run_timeout: int,
                 max_cycle_count: int, oss_fuzz_dir: Path):
        self.model_name = model_name
        self.num_samples = num_samples
        self.run_timeout = run_timeout
        self.max_cycle_count = max_cycle_count
        self.oss_fuzz_dir = oss_fuzz_dir
        self._oss_fuzz_ready = False
        self._prepare_lock = threading.Lock()

        if not os.getenv('ANTHROPIC_API_KEY'):
            raise RuntimeError(
                'ANTHROPIC_API_KEY is not set. '
                'Export it before running this script.'
            )

        # Ask our forked OFG builder to disable the OSS-Fuzz seed corpus so
        # every fuzz run starts cold. This makes coverage comparable to other
        # tools (e.g. gold harnesses) measured under the same conditions.
        os.environ['OFG_EMPTY_CORPUS'] = '1'

    def _prepare_oss_fuzz(self):
        with self._prepare_lock:
            if self._oss_fuzz_ready:
                return True
            try:
                run_one_experiment.prepare(str(self.oss_fuzz_dir))
                self._oss_fuzz_ready = True
                return True
            except Exception as e:
                print(f'OSS-Fuzz preparation failed: {e}', file=sys.stderr)
                return False

    def _run_ofg(self, benchmark_yaml: Path, work_dir: Path):
        args = _OFGArgs(
            model_name=self.model_name,
            num_samples=self.num_samples,
            run_timeout=self.run_timeout,
            max_cycle_count=self.max_cycle_count,
            work_dir=str(work_dir),
        )
        model = models.LLM.setup(
            ai_binary=args.ai_binary,
            name=args.model,
            max_tokens=8192,
            num_samples=args.num_samples,
            temperature=args.temperature,
        )
        benchmarks = Benchmark.from_yaml(str(benchmark_yaml))
        work_dirs = WorkDirs(str(work_dir), keep=True)
        args.work_dirs = work_dirs
        return run_one_experiment.run(
            benchmark=benchmarks[0], model=model, args=args, work_dirs=work_dirs
        )

    @staticmethod
    def _extract_best_harness(result, ofg_work_dir: Path) -> str | None:
        """Find the best harness source produced by OFG for this case."""
        # Prefer source extracted from a successful trial.
        if result is not None and hasattr(result, 'trial_results'):
            for trial in result.trial_results:
                if hasattr(trial, 'fuzz_target_source') and trial.fuzz_target_source:
                    return trial.fuzz_target_source
                if hasattr(trial, 'best_result') and trial.best_result is not None:
                    src = ''
                    if hasattr(trial.best_result, 'get_fuzz_target_source'):
                        src = trial.best_result.get_fuzz_target_source() or ''
                    if src:
                        return src

        # Fallback: read the raw fuzz_targets/01.fuzz_target file from disk.
        fuzz_targets_dir = ofg_work_dir / 'fuzz_targets'
        if not fuzz_targets_dir.exists():
            return None
        for ft_file in sorted(fuzz_targets_dir.glob('*.fuzz_target')):
            content = ft_file.read_text(errors='replace').strip()
            if content and 'LLVMFuzzerTestOneInput' in content:
                return content
        return None

    @staticmethod
    def _has_build_success(result) -> bool:
        if result is None:
            return False
        for attr in ('build_success_rate', 'build_success_count'):
            v = getattr(result, attr, 0)
            if v and v > 0:
                return True
        return False

    def process_case(self, case: dict, output_dir: Path,
                     benchmarks_dir: Path | None) -> dict:
        case_id = case['case_id']
        project = case['project']
        fuzzer_name = case['fuzzer_name']
        target_function = case.get('target_function', '')

        case_dir = output_dir / project / fuzzer_name
        case_dir.mkdir(parents=True, exist_ok=True)
        ofg_work = case_dir / 'ofg_workdir'
        ofg_work.mkdir(parents=True, exist_ok=True)

        print(f'\n--- {case_id} ---', flush=True)
        t_start = time.time()
        error_msg = None
        harness_source = None
        result = None

        try:
            yaml_path = ofg_work / 'benchmark.yaml'
            get_or_generate_yaml(case, benchmarks_dir, yaml_path)
            print(f'  Running OFG ({self.run_timeout}s fuzz, '
                  f'{self.num_samples} samples)...', flush=True)
            result = self._run_ofg(yaml_path, ofg_work)
            harness_source = self._extract_best_harness(result, ofg_work)
            if not harness_source:
                error_msg = 'No harness source produced by OFG'
        except Exception as e:
            error_msg = str(e)
            print(f'  OFG run raised: {e}', flush=True)

        elapsed_ms = int((time.time() - t_start) * 1000)

        harness_rel = None
        status = 'failed'
        if harness_source:
            ext = '.cpp' if '#include <' in harness_source and '::' in harness_source else '.c'
            harness_file = case_dir / f'harness{ext}'
            harness_file.write_text(harness_source)
            harness_rel = str(harness_file.relative_to(output_dir))
            status = 'succeeded'
            print(f'  Harness saved: {harness_rel}', flush=True)
        else:
            print(f'  Failed: {error_msg}', flush=True)

        rr = RunResult(
            case_id=case_id,
            project=project,
            fuzzer_name=fuzzer_name,
            target_function=target_function,
            status=status,
            mode='full',
            seed=42,
            error=error_msg,
            generated_harness_path=harness_rel,
            duration_ms=elapsed_ms,
        )
        (case_dir / 'run_result.json').write_text(
            json.dumps(asdict(rr), indent=2) + '\n'
        )
        return asdict(rr)

    def run_all(self, cases: list[dict], output_dir: Path,
                benchmarks_dir: Path | None, max_parallel: int) -> None:
        print(f'Running OFG on {len(cases)} cases (parallel={max_parallel})',
              flush=True)

        if not self._prepare_oss_fuzz():
            print('OSS-Fuzz environment not ready; aborting.', file=sys.stderr)
            sys.exit(2)

        manifest = {
            'experiment_id': 'ofg_run',
            'mode': 'full',
            'seed': 42,
            'selected_case_ids': [c['case_id'] for c in cases],
        }
        (output_dir / 'run_manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n'
        )

        start = time.time()
        results = []
        lock = threading.Lock()
        completed = 0

        def worker(c):
            try:
                return self.process_case(c, output_dir, benchmarks_dir)
            except Exception as e:
                return {
                    'case_id': c['case_id'],
                    'status': 'failed',
                    'error': str(e),
                }

        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futures = {pool.submit(worker, c): c for c in cases}
            for f in as_completed(futures):
                r = f.result(timeout=7200)
                results.append(r)
                with lock:
                    completed += 1
                    tag = 'OK' if r.get('status') == 'succeeded' else 'FAIL'
                    print(f'[{completed}/{len(cases)}] {tag} '
                          f'{r.get("case_id")}', flush=True)

        ok = sum(1 for r in results if r.get('status') == 'succeeded')
        elapsed = time.time() - start
        print(f'\nDone: {ok}/{len(cases)} succeeded in {elapsed/60:.1f} min')
        print(f'Output: {output_dir}')


def main():
    parser = argparse.ArgumentParser(description='Run OFG over a dataset.')
    parser.add_argument('--dataset', type=Path, required=True,
                        help='Path to benchmark dataset JSONL.')
    parser.add_argument('--benchmarks', type=Path, default=None,
                        help='Optional directory of pre-made OFG yaml files.')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output directory for results.')
    parser.add_argument('--model', default='claude-sonnet-4-6',
                        help='LLM model name (default: claude-sonnet-4-6).')
    parser.add_argument('--num-samples', type=int, default=2,
                        help='Trials per case (default: 2).')
    parser.add_argument('--run-timeout', type=int, default=600,
                        help='Fuzz duration per trial in seconds (default: 600).')
    parser.add_argument('--max-cycle-count', type=int, default=5,
                        help='OFG iteration cycles per trial (default: 5).')
    parser.add_argument('--parallel', type=int, default=4,
                        help='Max parallel cases (default: 4).')
    parser.add_argument('--oss-fuzz-dir', type=Path,
                        default=OFG_ROOT / 'oss-fuzz',
                        help='Local OSS-Fuzz checkout '
                             '(cloned automatically if missing).')
    parser.add_argument('--limit', type=int, default=0,
                        help='Run only the first N cases (0 = all).')
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    cases = load_dataset(args.dataset)
    if args.limit > 0:
        cases = cases[:args.limit]
    print(f'Loaded {len(cases)} cases from {args.dataset}')

    runner = OFGRunner(
        model_name=args.model,
        num_samples=args.num_samples,
        run_timeout=args.run_timeout,
        max_cycle_count=args.max_cycle_count,
        oss_fuzz_dir=args.oss_fuzz_dir,
    )
    runner.run_all(cases, args.output, args.benchmarks, args.parallel)


if __name__ == '__main__':
    main()
