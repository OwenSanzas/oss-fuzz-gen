#!/usr/bin/env python3
"""Write one OFG benchmark YAML per case, the way upstream does for one function.

Upstream's single-function path is data_prep.introspector.
generate_benchmark_for_targeted_function(): it looks the function up in Fuzz
Introspector and fills name, signature, return type and params with the same
helpers used for every published benchmark set.  We do the same against the
local FI built at the pinned revision with the case's gold harness stubbed.
There are two differences:

* target_path / target_name are the gold harness's slot.  Upstream takes the
  project's first harness; using the gold slot builds the generated harness the
  same way gold and the other systems are built.
* The function is matched by its qualified name from the dataset.  C++ entries in
  FI carry mangled names, so they are matched on the demangled name, with
  overloads resolved by the dataset declaration.  If FI has no entry (for example
  an uninstantiated template), the benchmark is built from the dataset's
  declaration and the fallback is recorded.

Writes <out>/<oss_fuzz_project>.yaml and <out>/_report.json.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_prep import introspector  # noqa: E402
from experiment import benchmark as benchmarklib  # noqa: E402


def strip_templates(name: str) -> str:
  out, depth = [], 0
  for ch in name:
    if ch == '<':
      depth += 1
    elif ch == '>':
      depth -= 1
    elif depth == 0:
      out.append(ch)
  return ''.join(out)


def qualified_name(fn: dict, project: str) -> str:
  raw = introspector.get_raw_function_name(fn, project)
  dem = introspector.demangle(raw) if raw.startswith('_Z') else raw
  dem = strip_templates(dem)
  dem = dem.split('(')[0].strip()
  # Drop a return type that some demanglings keep for templates.
  return dem.split(' ')[-1]


def n_params(decl: str) -> int:
  inner = decl[decl.find('(') + 1:decl.rfind(')')]
  inner = strip_templates(inner).strip()
  if not inner or inner == 'void':
    return 0
  return inner.count(',') + 1


def pick(cands: list[dict], decl: str, project: str) -> dict:
  want = n_params(decl)
  scored = []
  for fn in cands:
    args = introspector._get_clean_arg_types(fn, project)  # pylint: disable=protected-access
    # Member functions carry `this` in FI's argument list.
    has_this = bool(
        introspector._get_arg_names(fn, project, 'c++')[:1] == ['this'])  # pylint: disable=protected-access
    n = len(args) - (1 if has_this else 0)
    toks = set(re.findall(r'[A-Za-z_]\w*', ' '.join(args)))
    dtoks = set(re.findall(r'[A-Za-z_]\w*', decl))
    scored.append((n == want, len(toks & dtoks), fn))
  scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
  return scored[0][2]


CPP_NAMES = json.load(open('/path/to/baselines/ofg-work/cpp_names.json'))


def from_declaration(case: dict) -> benchmarklib.Benchmark:
  decl = case['target_declaration'].rstrip(';').strip()
  name = case['target_function']
  head = decl[:decl.find('(')]
  ret = head[:head.rfind(name.split('::')[-1])].strip()
  ret = re.sub(r'^(template\s*<.*?>\s*)', '', ret)
  ret = re.sub(r'\b(extern|static|inline|virtual|YR_API|ASSIMP_API)\b', '', ret).strip()
  # OFG checks that the target is called by searching the disassembly of
  # LLVMFuzzerTestOneInput for function_name; upstream benchmarks carry the
  # mangled name for C++ (from FI).  For C++ targets we use the Itanium
  # encoding of the qualified name (e.g. 4pugi12xml_document11load_buffer),
  # which every mangled symbol of that function contains, whatever its
  # overload or template arguments.
  if '::' in name:
    name = CPP_NAMES[case['case_id']]['chain']
  return benchmarklib.Benchmark(
      benchmark_id='cli',
      project=case['oss_fuzz_project'],
      language='c++' if case['gold_path'].endswith(('.cc', '.cpp', '.cxx')) else 'c',
      function_signature=decl,
      function_name=name,
      return_type=ret or 'void',
      params=[],
      target_path=TARGET_PATH_FIX.get(case['oss_fuzz_project'], {}).get(
          'stubbed', [case['gold_path']])[0],
      preferred_target_name=case['fuzzer_name'])


# The gold's location in the image before the build runs, where it differs from
# the dataset path (binutils: build.sh copies $SRC/fuzz_*.c into the tree, so
# writing a harness at the in-tree path makes its `mkdir fuzz` fail).
TARGET_PATH_FIX = json.load(open('/path/to/baselines/ofg-work/target_path_fix.json'))


def main(cases_json: str, out_dir: str, endpoint: str, only: list[str]):
  cases = json.load(open(cases_json))
  if endpoint == 'none':
    # No Fuzz Introspector: every benchmark is built from the dataset's
    # declaration of the target function (name, full declaration, header).
    os.makedirs(out_dir, exist_ok=True)
    for case_id, c in cases.items():
      c = dict(c, case_id=case_id)
      if only and c['oss_fuzz_project'] not in only:
        continue
      benchmarklib.Benchmark.to_yaml([from_declaration(c)], outdir=out_dir,
                                     out_basename=f"{c['oss_fuzz_project']}.yaml")
    print(f'{len(os.listdir(out_dir))} benchmark yamls in {out_dir}')
    return
  introspector.set_introspector_endpoints(endpoint)
  os.makedirs(out_dir, exist_ok=True)
  report_path = f'{out_dir}/_report.json'
  report = json.load(open(report_path)) if os.path.exists(report_path) else {}
  for case_id, c in cases.items():
    c = dict(c, case_id=case_id)
    proj = c['oss_fuzz_project']
    if only and proj not in only:
      continue
    lang = 'c++' if c['gold_path'].endswith(('.cc', '.cpp', '.cxx')) else 'c'
    fns = introspector.query_introspector_all_functions(proj)
    target = c['target_function']
    cands = [fn for fn in fns if qualified_name(fn, proj) == target]
    entry = {'case_id': case_id, 'fi_functions': len(fns),
             'candidates': [fn.get('function_signature', '') for fn in cands]}
    if cands:
      fn = pick(cands, c['target_declaration'], proj)
      bench = benchmarklib.Benchmark(
          benchmark_id='cli',
          project=proj,
          language=lang,
          function_signature=fn.get('function_signature', ''),
          function_name=introspector.get_raw_function_name(fn, proj),
          return_type=introspector._get_clean_return_type(fn, proj),  # pylint: disable=protected-access
          params=introspector._group_function_params(  # pylint: disable=protected-access
              introspector._get_clean_arg_types(fn, proj),  # pylint: disable=protected-access
              introspector._get_arg_names(fn, proj, lang), lang),  # pylint: disable=protected-access
          target_path=c['gold_path'],
          preferred_target_name=c['fuzzer_name'],
          function_dict=fn)
      entry['source'] = 'fuzz-introspector'
      entry['chosen'] = fn.get('function_signature', '')
    else:
      bench = from_declaration(c)
      entry['source'] = 'dataset-declaration (FI has no entry)'
      entry['chosen'] = c['target_declaration']
    benchmarklib.Benchmark.to_yaml([bench], outdir=out_dir, out_basename=f'{proj}.yaml')
    report[proj] = entry
    print(proj, entry['source'], '|', entry['chosen'][:100], '| cands', len(cands))
  json.dump(report, open(report_path, 'w'), indent=1)


if __name__ == '__main__':
  main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
