#!/usr/bin/env python3
"""
Extract coverage metrics from OFG experiment output.

After `run_experiment.py` produces an output directory with `run_result.json`
files, this script collects the four coverage metrics (Lines, Branches,
Functions, Regions) per case from OFG's coverage reports and writes a single
`coverage_metrics.json` summary at the output root.

Coverage data is sourced from OFG's own `code-coverage-reports/{trial}/linux/
summary.json` files inside each case's `ofg_workdir/`. The best trial
(highest line coverage) is selected per case.

Usage:
    python extract_coverage.py --output ./results
    python extract_coverage.py --output ./results --report coverage.json
"""

import argparse
import json
from pathlib import Path


def find_best_summary(case_dir: Path) -> dict | None:
    """Find the highest-line-coverage summary.json across all OFG trials."""
    cov_root = case_dir / 'ofg_workdir' / 'code-coverage-reports'
    if not cov_root.exists():
        return None

    best = None
    best_lines = -1.0
    for trial_dir in cov_root.iterdir():
        if not trial_dir.is_dir():
            continue
        summary_path = trial_dir / 'linux' / 'summary.json'
        if not summary_path.exists():
            continue
        try:
            data = json.loads(summary_path.read_text())
            totals = data['data'][0]['totals']
        except Exception:
            continue
        lines_pct = totals.get('lines', {}).get('percent', 0.0)
        if lines_pct > best_lines:
            best_lines = lines_pct
            best = {
                'trial': trial_dir.name,
                'lines_percent':     totals['lines']['percent'],
                'lines_covered':     totals['lines']['covered'],
                'lines_count':       totals['lines']['count'],
                'branches_percent':  totals['branches']['percent'],
                'branches_covered':  totals['branches']['covered'],
                'branches_count':    totals['branches']['count'],
                'functions_percent': totals['functions']['percent'],
                'functions_covered': totals['functions']['covered'],
                'functions_count':   totals['functions']['count'],
                'regions_percent':   totals['regions']['percent'],
                'regions_covered':   totals['regions']['covered'],
                'regions_count':     totals['regions']['count'],
            }
    return best


def main():
    parser = argparse.ArgumentParser(
        description='Extract OFG coverage metrics into a single JSON summary.'
    )
    parser.add_argument('--output', type=Path, required=True,
                        help='OFG experiment output directory '
                             '(same path passed to run_experiment.py --output).')
    parser.add_argument('--report', type=Path, default=None,
                        help='Where to write the coverage summary JSON. '
                             'Defaults to {output}/coverage_metrics.json.')
    args = parser.parse_args()

    if not args.output.is_dir():
        raise SystemExit(f'Output dir not found: {args.output}')

    summary_path = args.report or (args.output / 'coverage_metrics.json')

    rows = []
    succeeded_with_cov = 0
    succeeded_without_cov = 0
    failed = 0

    for run_result_file in sorted(args.output.rglob('run_result.json')):
        rr = json.loads(run_result_file.read_text())
        case_id = rr['case_id']
        project = rr['project']
        fuzzer_name = rr['fuzzer_name']
        status = rr['status']

        entry = {
            'case_id': case_id,
            'project': project,
            'fuzzer_name': fuzzer_name,
            'status': status,
        }

        if status != 'succeeded':
            failed += 1
            entry.update({
                'lines_percent': None,
                'branches_percent': None,
                'functions_percent': None,
                'regions_percent': None,
                'error': rr.get('error', ''),
            })
            rows.append(entry)
            continue

        cov = find_best_summary(run_result_file.parent)
        if cov is None:
            succeeded_without_cov += 1
            entry.update({
                'lines_percent': None,
                'branches_percent': None,
                'functions_percent': None,
                'regions_percent': None,
                'error': 'no coverage report found',
            })
        else:
            succeeded_with_cov += 1
            entry.update(cov)
        rows.append(entry)

    payload = {
        'summary': {
            'total': len(rows),
            'succeeded_with_coverage': succeeded_with_cov,
            'succeeded_without_coverage': succeeded_without_cov,
            'failed': failed,
        },
        'results': rows,
    }
    summary_path.write_text(json.dumps(payload, indent=2) + '\n')

    print(f'Total cases:              {len(rows)}')
    print(f'Succeeded with coverage:  {succeeded_with_cov}')
    print(f'Succeeded without cov:    {succeeded_without_cov}')
    print(f'Failed:                   {failed}')

    if succeeded_with_cov:
        cov_rows = [r for r in rows if r.get('lines_percent') is not None]
        for metric in ('lines', 'branches', 'functions', 'regions'):
            vals = [r[f'{metric}_percent'] for r in cov_rows]
            mean = sum(vals) / len(vals)
            print(f'  Mean {metric:9s}: {mean:6.2f}%')

    print(f'Wrote: {summary_path}')


if __name__ == '__main__':
    main()
