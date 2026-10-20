#!/usr/bin/env python3
"""Fresh native namespace compilation and exact source-only V3 replay.

Only the unchanged raw originals are compiled here. The strict image builder
must compile the composed original/project sources independently; this helper
does not issue a V3 compile receipt or execute any original RM entry.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import tempfile

import compile_nvidia_global_rm as original

ROOT = Path(__file__).resolve().parents[1]
GSP = ROOT / 'packages/nvidia-gsp-bootstrap'
BASELINE_SHA = 'cb79f788baddb7f046e870b1e2e09bfde310b4b12417ec8c737fad1ef440f7a1'
SOURCE_TREE = 'fa8498c3958a559a3466ef6dd4e541bfcea9f55d8809d0a422c784cacd703029'
PROJECT_TREE = 'ec8108f56f4b59b8c9937953206efffba6820d1b6998c55303ceee9d64bc8eb5'
PINNED_CONTRACTS = {
    'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json':
        '7cee49f7c2032ce844fdd6b15b62311ac62a73ac8448a0c8c0604db983ad2100',
    'packages/nvidia-gsp-bootstrap/prospective/PROSPECTIVE-SOURCE-PROFILE.json':
        '061f027f1eb6a1e2ea9c36a0ce8cd75b4d599026e8421a60e7dc2b78c2078894',
    'packages/nvidia-gsp-bootstrap/prospective-v2/PROSPECTIVE-SOURCE-PROFILE.json':
        'ce3fe72438c0548098d94fc0147b7ad036307378578e0b9c418a74aae96b938e',
    'packages/nvidia-gsp-bootstrap/prospective-v3/PROSPECTIVE-SOURCE-PROFILE.json':
        'f23d62032f9c0ac9dc41dd2344fadf2500f3dff35296d157ddb4401a56592ecd',
    'packages/nvidia-gsp-bootstrap/prospective-timer-checked/SOURCE-CONTRACT.json':
        '7a1b6ce37b441e1b8af3bea3b3958818160aaa23c312d4651388676df41370fa',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha(rows: dict) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_contracts() -> dict:
    contracts = {}
    for relative, expected in PINNED_CONTRACTS.items():
        path = ROOT / relative
        if path.is_symlink() or sha(path) != expected:
            raise ValueError('Pinned source contract changed: ' + relative)
        contracts[relative] = json.loads(path.read_bytes())
    # This verifies the full frozen first-transaction/Host inputs and their
    # project/helper dependencies before importing the source replay helpers.
    gpu = load('s540_idle_frozen_parent', GSP / 'prospective-work-gpu-binding/prepare.py')
    gpu.parent_guard()
    for name in ('prospective-v2', 'prospective-v3'):
        contract = contracts[f'packages/nvidia-gsp-bootstrap/{name}/PROSPECTIVE-SOURCE-PROFILE.json']
        for relative, expected in contract['project_input_sha256'].items():
            path = ROOT / relative
            if path.is_symlink() or sha(path) != expected:
                raise ValueError('Frozen V2/V3 dependency changed: ' + relative)
    return contracts


def project_values(contracts: dict) -> dict[str, bytes]:
    v1 = contracts['packages/nvidia-gsp-bootstrap/prospective/PROSPECTIVE-SOURCE-PROFILE.json']
    values = {name: (ROOT / name).read_bytes() for name in v1['project_input_sha256']}
    if any(hashlib.sha256(data).hexdigest() != v1['project_input_sha256'][name]
           for name, data in values.items()):
        raise ValueError('Frozen V1 project companion changed')
    patch = GSP / 'prospective-v2/inputs/cancellation-log-prospective/optional-log-port-prospective.patch'
    if sha(patch) != '1f373cacd791ce5d8d3eca6b937744e686c66397998b428bd8c9d0680a0d9c62':
        raise ValueError('Frozen V2 project patch changed')
    values.update(original._strict_patch(values, patch.read_bytes()))
    timer = contracts['packages/nvidia-gsp-bootstrap/prospective-timer-checked/SOURCE-CONTRACT.json']
    raw = {name: (ROOT / name).read_bytes() for name in timer['original_project_sha256']}
    if {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()} != timer['original_project_sha256']:
        raise ValueError('Original checked-timer companion changed')
    row = timer['patches'][3]
    patch = GSP / 'prospective-timer-checked' / row['path']
    if sha(patch) != row['sha256']:
        raise ValueError('Frozen checked-timer project patch changed')
    raw.update(original._strict_patch(raw, patch.read_bytes()))
    if {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()} != timer['final_project_sha256']:
        raise ValueError('Checked-timer companion replay changed')
    values.update(raw)
    name = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRm.h'
    values[name] = (ROOT / name).read_bytes()
    rows = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'mode': '100644'}
            for name, data in sorted(values.items())}
    verify_tree(rows, 28, PROJECT_TREE)
    return values


def verify_tree(rows: dict, count: int, expected: str) -> None:
    if len(rows) != count or tree_sha(rows) != expected:
        raise ValueError('Exact immutable V3 file count/hash differs')


def fresh_output(output: Path, upstream: Path) -> Path:
    unresolved = output.absolute()
    if any(path.is_symlink() for path in (unresolved, *unresolved.parents)):
        raise ValueError('Output symlinks are not admitted')
    output = unresolved.resolve()
    if output.exists():
        raise ValueError('A fresh output is required; compilation reuse is not supported')
    if output.is_relative_to(upstream) or upstream.is_relative_to(output) or ROOT.is_relative_to(output):
        raise ValueError('Output overlaps source inputs')
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / 'build'):
        raise ValueError('Repository output is allowed only below build/')
    return output


def materialize_v3(upstream: Path, namespace: Path, output: Path, contracts: dict | None = None) -> dict:
    """Replay sources only; callable locally without claiming compilation."""
    upstream = original._pinned_upstream(upstream)
    namespace = namespace.resolve(strict=True)
    if sha(namespace) != BASELINE_SHA:
        raise ValueError('Wrong independently pinned baseline namespace')
    output = fresh_output(output, upstream)
    contracts = contracts or frozen_contracts()
    checked, _ = original._checked_profile(upstream)
    v3 = contracts['packages/nvidia-gsp-bootstrap/prospective-v3/PROSPECTIVE-SOURCE-PROFILE.json']
    expected = dict(checked['files'])
    for name, digest in v3['final_sources_sha256'].items():
        expected[name] = {**expected[name], 'sha256': digest}
    verify_tree(expected, 4005, SOURCE_TREE)
    patch = GSP / 'prospective-v3/all-prospective-overlays-from-raw.patch'
    if sha(patch) != v3['patch_sha256']['raw_to_v3']:
        raise ValueError('Frozen raw-to-V3 patch changed')
    values = {name: (upstream / name).read_bytes() for name in expected}
    values.update(original._strict_patch(values, patch.read_bytes()))
    if any(hashlib.sha256(data).hexdigest() != expected[name]['sha256'] for name, data in values.items()):
        raise ValueError('Raw source replay does not produce the exact V3 inventory')
    companions = project_values(contracts)
    output.mkdir(parents=True)
    for name, data in values.items():
        target = output / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(int(expected[name]['mode'], 8) & 0o777)
    project_rows = {}
    for name, data in sorted(companions.items()):
        target = output / 'project-overlay' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o644)
        project_rows[name] = {'sha256': sha(target), 'mode': '100644'}
    original._verify_workspace(output / 'source', {'files': expected})
    original._verify_workspace(output / 'project-overlay', {'files': project_rows})
    v2 = contracts['packages/nvidia-gsp-bootstrap/prospective-v2/PROSPECTIVE-SOURCE-PROFILE.json']
    header = output / 'prospective-private-namespace.h'
    header.write_text('/* V3 original private aliases; project bridges remain strong. */\n#include "' +
        str(namespace) + '"\n' + ''.join('#define ' + key + ' ' + value + '\n'
        for key, value in sorted(v2['new_original_private_names'].items())))
    gpu = load('s540_idle_namespace_guard', GSP / 'prospective-work-gpu-binding/prepare.py')
    gpu.namespace_guard(header)
    report = {'format': 1, 'status': 'materialized-source-only', 'source_only': True,
        'compiled': False, 'compile_report_issued': False, 'objects_reused': False,
        'source': 'source', 'project': 'project-overlay', 'namespace': header.name,
        'baseline_namespace_sha256': sha(namespace), 'namespace_sha256': sha(header),
        'original_file_count': len(expected), 'original_tree_sha256': tree_sha(expected),
        'original_files': expected, 'project_file_count': len(project_rows),
        'project_tree_sha256': tree_sha(project_rows), 'project_files': project_rows,
        'source_contract_sha256': PINNED_CONTRACTS,
        'kernel_execution': 'not_tested', 'global_rm_executed': False,
        'hardware_admission': False, 'original_entry_admission': False,
        'production_candidate_allowed': False}
    (output / 'materialized-source.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    frozen_contracts()
    return report


def prepare(upstream: Path, output: Path, compiler: Path) -> dict:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('The idle image namespace requires fresh native Intel macOS compilation')
    upstream = original._pinned_upstream(upstream)
    output = fresh_output(output, upstream)
    compiler = compiler.absolute()
    if 'Apple clang' not in original.execute([str(compiler), '--version']).stdout:
        raise ValueError('The actual native Apple compiler is required')
    contracts = frozen_contracts()
    output.mkdir(parents=True)
    baseline = output / 'baseline'
    record = original.compile_original(upstream, baseline, compiler, cross_probe=False)
    expected = contracts['packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json']
    keys = ('format', 'commit', 'release', 'profile', 'source_units',
            'generated_identification_units', 'prefix', 'defined_count', 'alias_count', 'namespace_sha256')
    observed = record['namespace_contract']
    if any(type(observed.get(key)) is not type(expected[key]) or observed.get(key) != expected[key] for key in keys):
        raise ValueError('Fresh raw-original symbols differ from the pinned namespace contract')
    namespace = baseline / 'contract/S540GlobalRmNamespace.h'
    if sha(namespace) != BASELINE_SHA:
        raise ValueError('Fresh native namespace differs from its frozen bytes')
    rows = json.loads((baseline / 'compile-results.json').read_bytes())
    objects = sorted(baseline.glob('*.o'))
    if (len(rows) != 1100 or any(row['status'] != 0 for row in rows) or
            len(objects) != 1100 or len(record['source_sha256']) != 1100 or
            {path.name: sha(path) for path in objects} != record['object_sha256']):
        raise ValueError('Fresh raw-original compilation is incomplete or changed')
    for key, value in {'native_apple_compiler': True, 'cross_compile_probe': False,
                       'namespace_applied': False, 'global_rm_executed': False,
                       'adapter_initialized': False, 'firmware_loaded': False}.items():
        if type(record.get(key)) is not type(value) or record[key] != value:
            raise ValueError('Wrong native raw-original compilation identity: ' + key)
    replay = materialize_v3(upstream, namespace, output / 'v3', contracts)
    result = {'format': 1, 'status': 'native-namespace-and-source-inputs-prepared',
        'baseline_compilation': {'report': 'baseline/darwin-compile.json',
            'report_sha256': sha(baseline / 'darwin-compile.json'), 'fresh_native_units': 1100,
            'namespace': str(namespace.relative_to(output)), 'namespace_sha256': sha(namespace),
            'namespace_contract_verified': True, 'objects_reused_by_image': False},
        'v3': {'root': 'v3', 'report': 'v3/materialized-source.json',
            'report_sha256': sha(output / 'v3/materialized-source.json'), 'compiled': False,
            'original_file_count': replay['original_file_count'], 'original_tree_sha256': SOURCE_TREE,
            'project_file_count': replay['project_file_count'], 'project_tree_sha256': PROJECT_TREE},
        'helper_sha256': sha(Path(__file__)), 'kernel_execution': 'not_tested',
        'image_linked': False, 'module_loaded': False, 'hardware_admission': False,
        'original_entry_admission': False, 'production_candidate_allowed': False}
    (output / 'idle-image-inputs.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def self_test() -> dict:
    contracts = frozen_contracts()
    values = project_values(contracts)
    rows = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'mode': '100644'}
            for name, data in values.items()}
    for changed in ({}, {**rows, 'extra': {'sha256': '0' * 64, 'mode': '100644'}},
                    {**rows, next(iter(rows)): {'sha256': '0' * 64, 'mode': '100644'}}):
        try:
            verify_tree(changed, 28, PROJECT_TREE)
        except ValueError:
            pass
        else:
            raise ValueError('Altered companion inventory was accepted')
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory).resolve()
        upstream = home / 'upstream'
        upstream.mkdir()
        for path in (upstream / 'output', home, ROOT / 'builders/generated'):
            try:
                fresh_output(path, upstream)
            except ValueError:
                pass
            else:
                raise ValueError('Invalid/reused output was accepted')
    return {'status': 'passed-source-controls-only', 'actual_project_files': 28,
            'project_tree_sha256': PROJECT_TREE, 'negative_controls': 6,
            'native_compilation_tested': False, 'original_entry_admission': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compiler', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        if args.upstream or args.output:
            parser.error('--self-test does not compile or accept an upstream/output')
        result = self_test()
    else:
        if args.upstream is None or args.output is None:
            parser.error('--upstream and --output are required')
        result = prepare(args.upstream, args.output, args.compiler)
    print(json.dumps({key: value for key, value in result.items() if key not in ('baseline_compilation', 'v3')}, sort_keys=True))


if __name__ == '__main__':
    main()
