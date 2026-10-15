#!/usr/bin/env python3
"""Verify the bundled v7 CPU-side runtime and actual RM container consumer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

import build_nvidia_transport as transport

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-nvport-runtime'
NVIDIA_COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
PROVENANCE_TESTS = ('test_nvidia_runtime_provenance.py',
                    'test_nvidia_rm_consumer_provenance.py')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def required_true(result: dict, keys: tuple[str, ...], description: str) -> None:
    if any(result.get(key) is not True for key in keys):
        raise ValueError('Incomplete ' + description + ' evidence: '
                         + ', '.join(key for key in keys if result.get(key) is not True))


def verify_native_result(result: dict, stem: str, component: str) -> None:
    if (result.get('format') != 1 or result.get('component') != component
            or type(result.get('failures')) is not int or result['failures'] != 0):
        raise ValueError('Unexpected runtime check result: ' + stem)
    if stem == 'check_support_runtime_native':
        if (result.get('entrypoint') != 'S540NvidiaSupportRuntime::checkIntegrated'
                or result.get('foundation_checks') != 23
                or result.get('caller_checks') != 35
                or result.get('lifecycle_checks') != 72):
            raise ValueError('The aggregate production startup entry or prior counts changed.')
        required_true(result, ('core', 'utilities', 'consumer', 'cleanup', 'acquired',
                              'previous_blocks_passed', 'reserve_cold_after',
                              'core_cold_after', 'os_objects_released'),
                      'aggregate production startup')
    elif stem == 'check_rm_consumer_native':
        if (result.get('model_cycles') != 64 or result.get('model_steps_per_cycle') != 128
                or result.get('injected_failure_positions') != 12
                or type(result.get('consumer_checks')) is not int
                or result['consumer_checks'] < 1):
            raise ValueError('The RM consumer model/failure coverage changed.')
        required_true(result, ('vector', 'list', 'allocation_failure', 'cleanup',
                              'reserve_cold_after'), 'original RM container consumer')
    elif stem == 'check_support_faults_native':
        if (result.get('checks') != 60
                or result.get('workers') != 4 or result.get('iterations_per_worker') != 12
                or type(result.get('completed_runs')) is not int
                or type(result.get('lease_refusals')) is not int
                or result['completed_runs'] < 1 or result['lease_refusals'] < 0
                or result['completed_runs'] + result['lease_refusals'] != 48
                or type(result.get('errors')) is not int or result['errors'] != 0
                or result.get('kernel_contention') != 'not_tested'):
            raise ValueError('The mixed-entry startup lease stress contract changed.')
        required_true(result, ('cleanup', 'os_objects_released', 'reserve_cold_after',
                              'core_cold_after'), 'runtime failure rollback')


def check(sdk: Path, destination: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS check host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the checked source.')
    sdk = sdk.resolve(strict=True)
    if transport.run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != transport.SDK_COMMIT:
        raise ValueError('The kernel SDK differs from its pinned revision.')
    provenance_paths = [ROOT / 'tests' / name for name in PROVENANCE_TESTS]
    for test in provenance_paths:
        tested = transport.run(sys.executable, str(test))
        print((tested.stdout + tested.stderr).strip())
    manifests = {}
    for relative in ('upstream/PROVENANCE.json', 'upstream/consumer/PROVENANCE.json'):
        path = SOURCE / relative
        value = json.loads(path.read_text())
        if value.get('commit') != NVIDIA_COMMIT:
            raise ValueError('Unexpected NVIDIA runtime source revision: ' + relative)
        manifests[relative] = value
    destination = destination.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    report = destination / 'runtime-checks.json'
    if report.exists():
        raise ValueError('The runtime check output already exists.')
    results = {}
    with tempfile.TemporaryDirectory(prefix='s540-nvidia-runtime-') as temporary:
        work = Path(temporary)
        for instrumented in (False, True):
            label = 'sanitized' if instrumented else 'native'
            flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer'] if instrumented else []
            for stem, component in (
                    ('check_support_runtime_native', 'nvport-support-runtime'),
                    ('check_rm_consumer_native', 'nvport-rm-consumer'),
                    ('check_support_faults_native', 'nvport-support-faults')):
                binary = transport.compile_native_harness(
                    work, label + '-' + stem, SOURCE / ('tests/' + stem + '.cpp'),
                    flags, with_runtime=True)
                result = transport.native_check(binary)
                verify_native_result(result, stem, component)
                results[label + '/' + stem] = result
    cpp_sources, c_sources = transport.production_sources()
    source_paths = {p for p in SOURCE.rglob('*') if p.is_file()
                    and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    source_paths.update(cpp_sources)
    source_paths.update(c_sources)
    source_paths.update(provenance_paths)
    source_paths.add(Path(__file__).resolve())
    source_paths.add(ROOT / 'builders/build_nvidia_transport.py')
    for path in source_paths:
        transport.plain(path)
    record = {
        'format': 1, 'component': 'nvidia-nvport-runtime', 'version': '0.1.0',
        'status': 'passed', 'github_sha': commit, 'architecture': 'x86_64',
        'kernel_sdk_commit': transport.SDK_COMMIT, 'upstream': manifests,
        'native_execution': results,
        'production_source_closure': [p.relative_to(ROOT).as_posix()
                                      for p in [*cpp_sources, *c_sources]],
        'kernel_compile': 'not performed by this checker; required by the enclosing package build',
        'kernel_runtime': 'not_tested', 'interrupt_runtime': 'not_tested',
        'gpu_operations': 'none', 'full_resource_manager_integration': False,
        'full_nvport_profile': False, 'laptop_package': False,
        'scope': 'checked core lifecycle, string/PRNG utilities, actual RM containers, rollback and shared startup lease',
        'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
                          for p in sorted(source_paths)},
    }
    report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    report.with_suffix('.json.sha256').write_text(sha(report.read_bytes()) + '  ' + report.name + '\n')
    print('Bundled NVIDIA runtime/RM consumer checks passed: ' + str(report))
    print('Report SHA256: ' + sha(report.read_bytes()))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-sdk', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.kernel_sdk, args.output_dir)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Runtime/RM consumer checks failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stdout or '')[-6000:] + (error.stderr or '')[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
