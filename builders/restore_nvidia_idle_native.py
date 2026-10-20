#!/usr/bin/env python3
"""Restore exact native idle-image inputs without compiling or linking.

The original report is immutable evidence. Failed ld-r caches require an
explicit opt-in and remain failed; this helper never grants package admission.
Run the unchanged native linker/packager verification before using any image.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path('/Users/runner/work/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86')
BUILD = ROOT / 'build/nvidia-idle-image'
IMAGE = BUILD / 'first-transaction-image'
COMPOSED = IMAGE / 'composition'
BASELINE_SHA = 'cb79f788baddb7f046e870b1e2e09bfde310b4b12417ec8c737fad1ef440f7a1'
SDK_COMMIT = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
ORIGINAL_LINKER_SHA = '671f6f9c847b2b94f8cd39cd4df2f7e8ec3511479519ead4a59c9c35c8215bb5'
BUILDERS = ('link_nvidia_first_transaction.py', 'compose_nvidia_first_transaction.py',
            'build_nvidia_execution.py', 'build_nvidia_transport.py',
            'compile_nvidia_global_rm.py', 'nvidia_combined_metaclasses.py',
            'nvidia_metaclass_initializers.py', 'embed_nvidia_firmware.py')
FLAGS = ('retained_diagnostic', 'rc_participant', 'shutdown_protocol',
         'platform_closure', 'retained_backends', 'global_epoch', 'live_abi_closure')
RUNTIME_OBJECTS = ('firmware-bytes.o', 'c_start.o', 'c_stop.o')


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(record: dict, values: dict, label: str) -> None:
    for name, expected in values.items():
        require(type(record.get(name)) is type(expected) and record[name] == expected,
                label + ': wrong ' + name)


def relative(value: str) -> Path:
    require(isinstance(value, str) and '\\' not in value, 'Invalid relative path')
    path = Path(value)
    require(bool(value) and bool(path.parts) and str(path) != '.' and not path.is_absolute() and value == path.as_posix()
            and all(p not in ('', '.', '..') for p in path.parts), 'Unconfined relative path: ' + value)
    return path


def no_symlink(path: Path) -> None:
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'Symlink path refused: ' + str(path))


def regular_tree(root: Path) -> list[Path]:
    no_symlink(root)
    require(root.is_dir(), 'Missing artifact directory: ' + str(root))
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'Nonregular artifact entry: ' + str(path))
            if stat.S_ISREG(mode):
                files.append(path)
    return sorted(files)


def read_json(path: Path) -> dict:
    no_symlink(path)
    return json.loads(path.read_bytes())


def cached(artifact: Path, recorded: str) -> Path:
    path = Path(recorded)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(BUILD),
            'Recorded path escaped canonical build: ' + recorded)
    return artifact / relative(path.relative_to(BUILD).as_posix())


def verify_hash(path: Path, expected: str, label: str) -> None:
    no_symlink(path)
    require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected) is not None,
            'Invalid SHA256: ' + label)
    require(path.is_file() and sha(path) == expected, 'Changed bytes: ' + label)


def verify_cache(artifact: Path, report_sha: str, allow_failed: bool = False) -> dict:
    """Read-only cache verification; callable before a canonical checkout exists."""
    files = regular_tree(artifact)
    report_path = artifact / 'first-transaction-image/first-transaction-image.json'
    verify_hash(report_path, report_sha, 'independently supplied native report')
    report = read_json(report_path)
    exact(report, {'format': 1, 'host_system': 'Darwin', 'host_control': False,
                  'native_darwin_compilation': True, 'original_compilation_performed': True,
                  'project_compilation_performed': True, 'module_loaded': False,
                  'installable_bundle_created': False, 'hardware_admission': False,
                  'original_entry_admission': False, 'production_candidate_allowed': False,
                  'gpu_access': False, 'kernel_execution': 'not_tested'}, 'native cache')
    if report.get('status') == 'failed':
        require(allow_failed, 'Failed native cache requires --allow-failed-link-cache')
        exact(report, {'phase': 'link-same-complete-relocatable-image',
                      'actual_link_performed': False, 'final_link_attempted': False}, 'failed cache')
        require('relocatable_image' not in report and 'final_image' not in report,
                'Failed cache unexpectedly claims completed image proof')
    else:
        exact(report, {'status': 'linked-native-development-image', 'phase': 'done',
                      'actual_link_performed': True, 'relocatable_link_performed': True,
                      'final_link_attempted': True, 'native_compilation_reports_verified': True}, 'linked cache')
    require(report.get('composition_directory') == str(COMPOSED), 'Noncanonical composition path')
    require(set(report['builder_source_sha256']) == {str(ROOT / 'builders' / p) for p in BUILDERS},
            'Wrong exact eight builder bindings')
    comp_path = artifact / 'first-transaction-image/composition/composition.json'
    verify_hash(comp_path, report['composition_sha256'], 'cached composition')
    composition = read_json(comp_path)
    exact(composition['fixed_source_profiles'], dict.fromkeys(FLAGS, True), 'fixed source profile')
    plan = report['source_plan']
    exact(plan, {'complete_original_translation_units': 1100, 'canonical_project_translation_units': 60,
                 'make_declared_original_source_plan_verified': True, 'firmware_objects': 1,
                 'pinned_libkmod_c_wrappers': ['c_start.o', 'c_stop.o'],
                 'total_expected_link_objects': 1163}, 'source plan')
    objects = {}
    reports = []
    bindings = report['compilation_reports']
    exact(bindings, {'original_objects': 1100, 'project_objects': 60}, 'compilation counts')
    for original, count, filename, binding, sources in (
            (True, 1100, 'full-original-compilation.json', 'original_sha256', plan['declared_original_sources']),
            (False, 60, 'project-compilation.json', 'project_sha256', plan['project_sources'])):
        path = comp_path.parent / filename
        verify_hash(path, bindings[binding], filename)
        record = read_json(path)
        exact(record, {'status': 'compiled-full-original-source-only' if original else 'compiled-project-source-only',
                       'native_darwin_compilation': True, 'host_control': False,
                       'host_system': 'Darwin', 'composition_sha256': report['composition_sha256']}, filename)
        if original:
            exact(record, {'native_apple_compiler': True, 'cross_compile_probe': False}, filename)
            require(not record.get('failures'), 'Original compilation has failures')
        rows = record['results']
        require(len(rows) == count and len(set(sources)) == count and
                len({r['source'] for r in rows}) == count and {r['source'] for r in rows} == set(sources),
                'Compiler source inventory differs from exact plan')
        folder = COMPOSED / ('original-objects' if original else 'project-objects')
        for row in rows:
            relative(row['source'])
            name = relative(row['object'])
            require(len(name.parts) == 1, 'Object basename escaped its folder')
            obj = str(folder / name)
            require(obj not in objects, 'Duplicate compilation object')
            verify_hash(cached(artifact, obj), row['object_sha256'], obj)
            objects[obj] = row['object_sha256']
        reports.append(record)
    for name in RUNTIME_OBJECTS:
        path = str(IMAGE / name)
        expected = report['input_object_sha256'].get(path)
        verify_hash(cached(artifact, path), expected, path)
        objects[path] = expected
    require(objects == report['input_object_sha256'] and len(objects) == 1163,
            'Exact 1163 input-object mapping differs')
    require(any(c.get('name') == 'complete-relocatable-link' and c.get('status') == 0
                for c in report['commands']), 'No successful native ld-r command')
    for key in ('relocatable_image', 'final_image'):
        if key in report:
            proof = report[key]
            path = artifact / 'first-transaction-image' / relative(proof['path'])
            require(len(relative(proof['path']).parts) == 1, 'Image path escaped image folder')
            verify_hash(path, proof['sha256'], key)
            require(path.stat().st_size == proof['bytes'], 'Image size changed')
    for row in report['firmware_asset_inventory']:
        path = artifact / 'firmware' / relative(row['filename'])
        require(len(relative(row['filename']).parts) == 1, 'Firmware path escaped')
        verify_hash(path, row['sha256'], 'firmware ' + row['filename'])
        require(path.stat().st_size == row['size'], 'Firmware size changed')
    baseline = artifact / 'inputs/baseline'
    raw = read_json(baseline / 'darwin-compile.json')
    exact(raw, {'status': 'compiled', 'native_apple_compiler': True, 'cross_compile_probe': False,
                'namespace_applied': False, 'global_rm_executed': False,
                'adapter_initialized': False, 'firmware_loaded': False}, 'baseline')
    baseline_objects = sorted(baseline.glob('*.o'))
    require(len(baseline_objects) == 1100 and len(raw['source_sha256']) == 1100 and
            {p.name: sha(p) for p in baseline_objects} == raw['object_sha256'], 'Baseline objects changed')
    rows = json.loads((baseline / 'compile-results.json').read_bytes())
    require(len(rows) == 1100 and all(r['status'] == 0 for r in rows), 'Baseline compile results incomplete')
    prepared = read_json(artifact / 'inputs/idle-image-inputs.json')
    verify_hash(baseline / 'darwin-compile.json', prepared['baseline_compilation']['report_sha256'], 'baseline report')
    verify_hash(artifact / 'inputs/v3/materialized-source.json', prepared['v3']['report_sha256'], 'V3 report')
    return {'report': report, 'composition': composition, 'compilation': reports,
            'baseline': raw, 'prepared': prepared, 'files': files}


def generated_source(helper: Path, function: str) -> bytes:
    tree = ast.parse(helper.read_bytes())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    values = [n.args[0].value for n in ast.walk(node) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr == 'write_text' and n.args
              and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
              and n.args[0].value.startswith('const char NVRM_ID[]')]
    require(len(values) == 1, 'Identification source must be one exact helper literal')
    return values[0].encode()


def write_missing(path: Path, data: bytes) -> bool:
    no_symlink(path)
    if path.exists():
        require(path.is_file() and path.read_bytes() == data, 'Refusing conflicting existing bytes: ' + str(path))
        return False
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        return True


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_clean(path: Path, commit: str) -> None:
    for command, expected in ((['rev-parse', 'HEAD'], commit), (['status', '--porcelain'], '')):
        result = subprocess.run(['git', '-C', str(path), *command], check=True, text=True, capture_output=True)
        require(result.stdout.strip() == expected, 'Wrong or dirty pinned checkout: ' + str(path))


def verify_builders(report: dict, original_linker: Path | None = None) -> None:
    """Allow only the independently pinned historical linker to live elsewhere."""
    for name, expected in report['builder_source_sha256'].items():
        source = Path(name)
        if source == ROOT / 'builders/link_nvidia_first_transaction.py' and original_linker is not None:
            require(expected == ORIGINAL_LINKER_SHA, 'Historical linker override has an unknown provenance hash')
            source = original_linker.absolute()
        verify_hash(source, expected, 'report-bound original builder ' + name)


def verify_sources(records: list[dict], composition: dict, linux: bool) -> dict:
    deferred, dependencies = set(), {}
    project = {row['source']: row for row in composition['project_translation_units']}
    for index, record in enumerate(records):
        original = index == 0
        for row in record['results']:
            source = (COMPOSED / 'original-objects/g_nvid_string.c' if original and row['source'] == 'generated/g_nvid_string.c'
                      else COMPOSED / ('source' if original else 'project') / relative(row['source']))
            verify_hash(source, row['source_sha256'] if original else row['sha256'], row['source'])
            if not original:
                declared = project[row['source']]
                require(row['kind'] == declared['kind'] and row['sha256'] == declared['sha256'] and
                        row.get('compile_definitions', {}) == declared.get('compile_definitions', {}),
                        'Project compiler row differs from regenerated source')
            cwd = COMPOSED / ('source/src/nvidia' if original else 'project')
            require(row['cwd'] == str(cwd), 'Compiler cwd differs from canonical source path')
            command = row['command']
            require(command.count('-c') == 1, 'Ambiguous compile command source')
            actual = Path(command[command.index('-c') + 1])
            actual = actual if actual.is_absolute() else cwd / actual
            require(actual.resolve(strict=True) == source.resolve(strict=True), 'Compile command source differs')
            for name, expected in row['dependency_sha256'].items():
                require(name not in dependencies or dependencies[name] == expected, 'Conflicting dependency hashes')
                dependencies[name] = expected
    for name, expected in dependencies.items():
        path = Path(name)
        require(path.is_absolute() and '..' not in path.parts, 'Unconfined compiler dependency')
        if path.is_relative_to(Path('/Applications')) and linux:
            deferred.add(name)
        else:
            verify_hash(path, expected, 'compiler dependency ' + name)
    return {'host_compiler_dependencies_deferred': sorted(deferred),
            'compiler_dependency_files_verified': len(dependencies) - len(deferred),
            'compile_source_rows_verified': sum(len(record['results']) for record in records)}


def restore(args) -> dict:
    artifact = args.artifact_root.absolute()
    evidence = verify_cache(artifact, args.report_sha256, args.allow_failed_link_cache)
    if args.verify_cache_only:
        return {'status': 'verified-cache-only', 'report_status': evidence['report']['status'],
                'input_objects_verified': 1163, 'baseline_objects_verified': 1100,
                'package_allowed': False, 'native_link_continuation_required': evidence['report']['status'] == 'failed'}
    require(args.repo_root.absolute() == ROOT, 'Restore requires the exact original canonical repository path')
    no_symlink(ROOT)
    no_symlink(BUILD)
    require(not BUILD.exists(), 'Restore requires absent canonical build/nvidia-idle-image; existing data is never replaced')
    require(not artifact.is_relative_to(BUILD) and not BUILD.is_relative_to(artifact), 'Artifact and output overlap')
    require(args.upstream is not None and args.kernel_sdk is not None, 'Both pinned checkouts are required')
    upstream, sdk = args.upstream.absolute(), args.kernel_sdk.absolute()
    require(upstream == ROOT / 'build-src/nvidia-upstream' and sdk == ROOT / 'build-src/MacKernelSDK',
            'Pinned input paths must match canonical compiler dependency paths')
    require(not args.linux_source_preflight or sys.platform.startswith('linux'), 'Linux preflight is Linux-only')
    require(args.linux_source_preflight or sys.platform == 'darwin', 'Linux restoration requires explicit source-only preflight')
    report = evidence['report']
    verify_builders(report, args.original_linker_source)
    verify_hash(ROOT / 'builders/prepare_nvidia_idle_image_inputs.py', evidence['prepared']['helper_sha256'], 'V3 replay helper')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / 'builders'))
    original = load('restore_original', ROOT / 'builders/compile_nvidia_global_rm.py')
    prepare = load('restore_prepare', ROOT / 'builders/prepare_nvidia_idle_image_inputs.py')
    compose = load('restore_composition', ROOT / 'builders/compose_nvidia_first_transaction.py')
    original._pinned_upstream(upstream)
    git_clean(sdk, SDK_COMMIT)
    baseline = BUILD / 'inputs/baseline'
    namespace = baseline / 'contract/S540GlobalRmNamespace.h'
    original.namespace_contract(sorted((artifact / 'inputs/baseline').glob('*.o')), namespace.parent)
    verify_hash(namespace, BASELINE_SHA, 'regenerated frozen baseline namespace')
    require((namespace.parent / 'SOURCE-CONTRACT.json').read_bytes() ==
            (artifact / 'inputs/baseline/contract/SOURCE-CONTRACT.json').read_bytes(), 'Regenerated namespace contract differs')
    require(read_json(namespace.parent / 'SOURCE-CONTRACT.json') == evidence['baseline']['namespace_contract'],
            'Baseline compilation namespace contract differs')
    prepare.materialize_v3(upstream, namespace, BUILD / 'inputs/v3')
    require((BUILD / 'inputs/v3/materialized-source.json').read_bytes() ==
            (artifact / 'inputs/v3/materialized-source.json').read_bytes(), 'Regenerated V3 receipt differs')
    compose.materialize(upstream, BUILD / 'inputs/v3', namespace, COMPOSED, **dict.fromkeys(FLAGS, True))
    require((COMPOSED / 'composition.json').read_bytes() ==
            (artifact / 'first-transaction-image/composition/composition.json').read_bytes(), 'Regenerated composition bytes differ')
    verify_hash(COMPOSED / 'composition.json', report['composition_sha256'], 'regenerated composition')
    identification = generated_source(ROOT / 'builders/compose_nvidia_first_transaction.py', 'compile_original_objects')
    require(identification == generated_source(ROOT / 'builders/compile_nvidia_global_rm.py', 'compile_original'),
            'Original and composition identification sources differ')
    write_missing(COMPOSED / 'original-objects/g_nvid_string.c', identification)
    write_missing(baseline / 'g_nvid_string.c', identification)
    restored, identical = 0, 0
    for source in evidence['files']:
        rel = source.relative_to(artifact)
        if rel.parts[0] in ('inputs', 'first-transaction-image', 'firmware'):
            if write_missing(BUILD / rel, source.read_bytes()):
                restored += 1
            else:
                identical += 1
    write_missing(IMAGE / 'cached-native-compilation-report.json',
                  (artifact / 'first-transaction-image/first-transaction-image.json').read_bytes())
    compose.verify_composition(COMPOSED)
    source_checks = verify_sources(evidence['compilation'], evidence['composition'], args.linux_source_preflight)
    for name, expected in report['input_object_sha256'].items():
        verify_hash(Path(name), expected, 'restored object')
    verify_hash(IMAGE / 'first-transaction-image.json', args.report_sha256, 'unaltered original native report')
    verify_builders(report, args.original_linker_source)
    return {'status': 'restored-source-and-native-object-cache', 'report_status': report['status'],
            'report_sha256': args.report_sha256, 'composition_sha256': report['composition_sha256'],
            'immutable_compilation_report': str(IMAGE / 'cached-native-compilation-report.json'),
            'historical_linker_source': str(args.original_linker_source) if args.original_linker_source else None,
            'input_objects_verified': 1163, 'baseline_objects_verified': 1100,
            'cached_files_restored': restored, 'regenerated_cached_files_identical': identical,
            'cached_files_overwritten': 0, 'regenerated_original_files': len(evidence['composition']['original_files']),
            'regenerated_project_files': len(evidence['composition']['project_files']),
            **source_checks, 'source_only_preflight': args.linux_source_preflight,
            'package_allowed': False, 'unchanged_native_verification_required': True,
            'native_link_continuation_required': report['status'] == 'failed',
            'combined_object_attested': 'relocatable_image' in report,
            'compilation_performed': False, 'link_performed': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--kernel-sdk', type=Path)
    parser.add_argument('--original-linker-source', type=Path,
                        help='Exact original linker bytes; only its known 4939252 SHA may be located elsewhere')
    parser.add_argument('--allow-failed-link-cache', action='store_true')
    parser.add_argument('--linux-source-preflight', action='store_true')
    parser.add_argument('--verify-cache-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(restore(args), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
