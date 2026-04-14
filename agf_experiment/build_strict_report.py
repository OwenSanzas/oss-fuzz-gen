#!/usr/bin/env python3
"""
Build a strict OFG-vs-Gold comparison report.

Takes the `coverage_metrics.json` produced by `extract_coverage.py` and
compares each case's OFG metrics against a gold baseline. Applies strict
scoring rules:

- entry_match: OFG harness builds, runs, AND calls the benchmark target
  function (matched by the final identifier of `target_function`).
- entry_miss: OFG runs but fuzzes a different API. OFG percentage is
  zeroed in the "effective" columns.
- ofg_failed: OFG failed to produce a usable harness. OFG = 0%.

Outputs a Markdown report and a CSV table.

Gold baseline format (JSONL, one object per line):
    {"case_id": "zlib/compress_fuzzer", "lines": 12.3, "branches": 8.5,
     "functions": 11.0, "regions": 10.2}

If a case appears in coverage_metrics.json but not in the gold baseline,
its gold values are reported as 0 and it is excluded from aggregate stats.

Usage:
    python build_strict_report.py \
        --coverage results/coverage_metrics.json \
        --gold gold_baseline.jsonl \
        --dataset example_data/benchmark_cases.jsonl \
        --output results/ofg_vs_gold_strict
"""

import argparse
import json
import re
from pathlib import Path


def load_dataset(path: Path) -> dict[str, dict]:
    """Load benchmark dataset (case_id -> case dict)."""
    cases = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            cases[c['case_id']] = c
    return cases


def load_gold(path: Path) -> dict[str, dict]:
    """Load gold coverage baseline (case_id -> {lines,branches,functions,regions})."""
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            cid = entry['case_id']
            out[cid] = {
                'lines':     float(entry.get('lines', 0.0)),
                'branches':  float(entry.get('branches', 0.0)),
                'functions': float(entry.get('functions', 0.0)),
                'regions':   float(entry.get('regions', 0.0)),
            }
    return out


def detect_entry_match(harness_src: str, target_function: str) -> bool:
    """Check if the harness contains an identifier matching the target.

    For C++ qualified names like icu::Calendar::createInstance the final
    identifier (createInstance) is the primary check; namespace/class names
    are accepted as fallbacks.
    """
    if not harness_src or not target_function:
        return False
    cleaned = target_function.split('(')[0].strip()
    if '::' in cleaned:
        ident = cleaned.split('::')[-1]
        ns_parts = cleaned.split('::')[:-1]
    else:
        ident = cleaned
        ns_parts = []

    if ident and re.search(rf'\b{re.escape(ident)}\b', harness_src):
        return True
    for ns in ns_parts:
        if ns and re.search(rf'\b{re.escape(ns)}\b', harness_src):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description='Build OFG vs Gold strict comparison report.'
    )
    parser.add_argument('--coverage', type=Path, required=True,
                        help='coverage_metrics.json from extract_coverage.py.')
    parser.add_argument('--gold', type=Path, required=True,
                        help='Gold baseline JSONL '
                             '(case_id, lines, branches, functions, regions).')
    parser.add_argument('--dataset', type=Path, required=True,
                        help='Benchmark dataset JSONL (for target_function info).')
    parser.add_argument('--harness-root', type=Path, required=True,
                        help='Output directory from run_experiment.py '
                             '(used to read harness sources for entry-match).')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output prefix. Writes {prefix}.md and {prefix}.csv.')
    args = parser.parse_args()

    coverage = json.loads(args.coverage.read_text())
    cov_by_case = {r['case_id']: r for r in coverage['results']}
    gold = load_gold(args.gold)
    dataset = load_dataset(args.dataset)

    # Build per-case rows in the order of the gold baseline.
    rows = []
    for case_id, g in gold.items():
        case = dataset.get(case_id, {})
        target_func = case.get('target_function', '')

        cov = cov_by_case.get(case_id)
        ofg_l = ofg_b = ofg_f = ofg_r = 0.0

        if cov is None:
            status = 'ofg_failed'
        elif cov['status'] != 'succeeded' or cov.get('lines_percent') is None:
            status = 'ofg_failed'
        else:
            ofg_l = cov['lines_percent']
            ofg_b = cov['branches_percent']
            ofg_f = cov['functions_percent']
            ofg_r = cov['regions_percent']

            project, fuzzer = case_id.split('/', 1)
            harness_src = ''
            for ext in ('.c', '.cpp'):
                p = args.harness_root / project / fuzzer / f'harness{ext}'
                if p.exists():
                    harness_src = p.read_text(errors='replace')
                    break
            if detect_entry_match(harness_src, target_func):
                status = 'entry_match'
            else:
                status = 'entry_miss'

        # Effective values (entry_miss / ofg_failed -> 0).
        if status == 'entry_match':
            eff_l, eff_b, eff_f, eff_r = ofg_l, ofg_b, ofg_f, ofg_r
        else:
            eff_l = eff_b = eff_f = eff_r = 0.0

        rows.append({
            'case_id': case_id,
            'status': status,
            'gold_l': g['lines'],     'gold_b': g['branches'],
            'gold_f': g['functions'], 'gold_r': g['regions'],
            'ofg_raw_l': ofg_l, 'ofg_raw_b': ofg_b,
            'ofg_raw_f': ofg_f, 'ofg_raw_r': ofg_r,
            'ofg_eff_l': eff_l, 'ofg_eff_b': eff_b,
            'ofg_eff_f': eff_f, 'ofg_eff_r': eff_r,
        })

    n = len(rows)
    from collections import Counter
    status_count = Counter(r['status'] for r in rows)

    means = {}
    for k in ('gold_l', 'gold_b', 'gold_f', 'gold_r',
              'ofg_raw_l', 'ofg_raw_b', 'ofg_raw_f', 'ofg_raw_r',
              'ofg_eff_l', 'ofg_eff_b', 'ofg_eff_f', 'ofg_eff_r'):
        means[k] = (sum(r[k] for r in rows) / n) if n else 0.0

    wins = {
        'lines':     sum(1 for r in rows if r['status'] == 'entry_match'
                         and r['ofg_eff_l'] >= r['gold_l']),
        'branches':  sum(1 for r in rows if r['status'] == 'entry_match'
                         and r['ofg_eff_b'] >= r['gold_b']),
        'functions': sum(1 for r in rows if r['status'] == 'entry_match'
                         and r['ofg_eff_f'] >= r['gold_f']),
        'regions':   sum(1 for r in rows if r['status'] == 'entry_match'
                         and r['ofg_eff_r'] >= r['gold_r']),
    }

    # Markdown report.
    md = []
    md.append('# OFG vs Gold - Strict Report')
    md.append('')
    md.append(f'Total cases compared: **{n}**')
    md.append('')
    md.append('## Status breakdown')
    md.append('')
    md.append('| Status | Count | Meaning |')
    md.append('|---|---:|---|')
    md.append(f'| entry_match | {status_count.get("entry_match", 0)} | '
              'OFG harness builds and calls the target function. |')
    md.append(f'| entry_miss  | {status_count.get("entry_miss", 0)} | '
              'OFG harness runs but fuzzes a different API. |')
    md.append(f'| ofg_failed  | {status_count.get("ofg_failed", 0)} | '
              'OFG produced no usable harness. |')
    md.append('')
    md.append('## Aggregate (mean over all cases)')
    md.append('')
    md.append('| Metric | Gold% | OFG raw% | OFG effective% (strict) | Ratio OFG/Gold |')
    md.append('|---|---:|---:|---:|---:|')
    for label, kg, kraw, keff in (
        ('Lines',     'gold_l', 'ofg_raw_l', 'ofg_eff_l'),
        ('Branches',  'gold_b', 'ofg_raw_b', 'ofg_eff_b'),
        ('Functions', 'gold_f', 'ofg_raw_f', 'ofg_eff_f'),
        ('Regions',   'gold_r', 'ofg_raw_r', 'ofg_eff_r'),
    ):
        g = means[kg]
        raw = means[kraw]
        eff = means[keff]
        ratio = (eff / g * 100.0) if g > 0 else 0.0
        md.append(f'| {label} | {g:.2f} | {raw:.2f} | {eff:.2f} | {ratio:.1f}% |')
    md.append('')
    md.append('**OFG wins (effective >= Gold, entry matched only):**')
    md.append('')
    md.append(f'- Lines:     **{wins["lines"]}** / {n}')
    md.append(f'- Branches:  **{wins["branches"]}** / {n}')
    md.append(f'- Functions: **{wins["functions"]}** / {n}')
    md.append(f'- Regions:   **{wins["regions"]}** / {n}')
    md.append('')
    md.append('## Per-case table')
    md.append('')
    md.append('| # | case_id | Status | Gold L% | OFG L% | OFG eff L% | '
              'Gold B% | OFG B% | OFG eff B% | Gold F% | OFG F% | OFG eff F% | '
              'Gold R% | OFG R% | OFG eff R% |')
    md.append('|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for i, r in enumerate(rows, 1):
        md.append(f'| {i} | {r["case_id"]} | {r["status"]} | '
                  f'{r["gold_l"]:.2f} | {r["ofg_raw_l"]:.2f} | {r["ofg_eff_l"]:.2f} | '
                  f'{r["gold_b"]:.2f} | {r["ofg_raw_b"]:.2f} | {r["ofg_eff_b"]:.2f} | '
                  f'{r["gold_f"]:.2f} | {r["ofg_raw_f"]:.2f} | {r["ofg_eff_f"]:.2f} | '
                  f'{r["gold_r"]:.2f} | {r["ofg_raw_r"]:.2f} | {r["ofg_eff_r"]:.2f} |')
    md.append('')

    md_path = args.output.with_suffix('.md')
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text('\n'.join(md))

    # CSV report.
    csv_path = args.output.with_suffix('.csv')
    csv_lines = [
        'case_id,status,'
        'gold_l,gold_b,gold_f,gold_r,'
        'ofg_raw_l,ofg_raw_b,ofg_raw_f,ofg_raw_r,'
        'ofg_eff_l,ofg_eff_b,ofg_eff_f,ofg_eff_r'
    ]
    for r in rows:
        csv_lines.append(
            f'{r["case_id"]},{r["status"]},'
            f'{r["gold_l"]:.2f},{r["gold_b"]:.2f},'
            f'{r["gold_f"]:.2f},{r["gold_r"]:.2f},'
            f'{r["ofg_raw_l"]:.2f},{r["ofg_raw_b"]:.2f},'
            f'{r["ofg_raw_f"]:.2f},{r["ofg_raw_r"]:.2f},'
            f'{r["ofg_eff_l"]:.2f},{r["ofg_eff_b"]:.2f},'
            f'{r["ofg_eff_f"]:.2f},{r["ofg_eff_r"]:.2f}'
        )
    csv_path.write_text('\n'.join(csv_lines) + '\n')

    print(f'Status: {dict(status_count)}')
    print('Mean lines: gold={:.2f}%  ofg_raw={:.2f}%  ofg_eff={:.2f}%'.format(
        means['gold_l'], means['ofg_raw_l'], means['ofg_eff_l']))
    print(f'Wrote: {md_path}')
    print(f'Wrote: {csv_path}')


if __name__ == '__main__':
    main()
