#!/usr/bin/env python3
"""Verify the v6 CPU-side NVIDIA lifecycle contracts without loading a kext."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import subprocess
import sys
import tempfile

# One explicit production source closure is shared with the final package build.
import build_nvidia_transport as transport

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-nvport-lifecycle'
NVIDIA_COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def fatal_spinlock_contract(binary: Path) -> dict:
    result = subprocess.run([str(binary), '--null-acquire'], capture_output=True,
                            text=True, timeout=30, preexec_fn=no_core)
    if (result.returncode != -signal.SIGABRT
            or 'NVIDIA spinlock contract violated: null acquire' not in result.stderr):
        raise ValueError('A null spinlock acquisition did not terminate: '
                         + str(result.returncode))
    return {'status': 'passed', 'invalid_acquire': 'fatal assertion',
            'signal': 'SIGABRT', 'returned_unlocked': False}


def check(sdk: Path, destination: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS check host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the checked source.')
    sdk = sdk.resolve(strict=True)
    if transport.run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != transport.SDK_COMMIT:
        raise ValueError('The kernel SDK differs from its pinned revision.')
    provenance_path = ROOT / 'tests/test_nvidia_lifecycle_provenance.py'
    tested = transport.run(sys.executable, str(provenance_path))
    print((tested.stdout + tested.stderr).strip())
    # The preceding provenance suite validates every pinned input, body and
    # explicit adaptation. Record that verified manifest without assuming a
    # helper API on a unittest module or running the same suite twice.
    provenance = json.loads((SOURCE / 'upstream/PROVENANCE.json').read_text())
    if provenance.get('commit') != NVIDIA_COMMIT:
        raise ValueError('Unexpected NVIDIA lifecycle source revision.')
    destination = destination.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    report = destination / 'lifecycle-checks.json'
    if report.exists():
        raise ValueError('The lifecycle check output already exists.')
    results = {}
    with tempfile.TemporaryDirectory(prefix='s540-nvidia-lifecycle-') as temporary:
        work = Path(temporary)
        for instrumented in (False, True):
            label = 'sanitized' if instrumented else 'native'
            flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer'] if instrumented else []
            for stem, component in (('check_lifecycle_faults_native', 'nvport-lifecycle-contract'),
                                    ('check_spinlock_native', 'nvport-spinlock')):
                binary = transport.compile_native_harness(
                    work, label + '-' + stem, SOURCE / ('tests/' + stem + '.cpp'), flags)
                result = transport.native_check(binary)
                if (result.get('format') != 1 or result.get('component') != component
                        or result.get('failures') != 0):
                    raise ValueError('Unexpected native lifecycle contract result: ' + stem)
                if component == 'nvport-lifecycle-contract':
                    if result.get('threads') != 4 or result.get('iterations') != 1000:
                        raise ValueError('The tracked allocator concurrent-use contract changed.')
                elif (result.get('checks') != 23 or result.get('workers') != 4 or result.get('protected_updates') != 16000
                      or result.get('interrupt_state') != 'simulated_tls_only'
                      or result.get('kernel_non_sleeping_paths') != 'not_proven_by_native_execution'):
                    raise ValueError('The native spinlock scope or contention contract changed.')
                results[label + '/' + stem] = result
                if stem == 'check_spinlock_native' and not instrumented:
                    results['fatal_spinlock_contract'] = fatal_spinlock_contract(binary)
    cpp_sources, c_sources = transport.adapter_sources()
    source_paths = {path for path in SOURCE.rglob('*') if path.is_file()
                    and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    source_paths.update(cpp_sources)
    source_paths.update(c_sources)
    source_paths.add(provenance_path)
    source_paths.add(Path(__file__).resolve())
    source_paths.add(ROOT / 'builders/build_nvidia_transport.py')
    record = {
        'format': 1, 'component': 'nvidia-nvport-lifecycle', 'version': '0.1.0',
        'status': 'passed', 'github_sha': commit, 'architecture': 'x86_64',
        'kernel_sdk_commit': transport.SDK_COMMIT, 'upstream': provenance,
        'native_execution': results,
        'production_source_closure': [p.relative_to(ROOT).as_posix()
                                      for p in [*cpp_sources, *c_sources]],
        'kernel_compile': 'verified by the enclosing integrated transport builder',
        'kernel_runtime': 'not_tested', 'interrupt_runtime': 'not_tested',
        'gpu_operations': 'none', 'resource_manager_integration': False,
        'full_nvport_core': False, 'laptop_package': False,
        'scope': 'tracked allocations, owned synchronization object lifecycle, failure cleanup and native concurrency',
        'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
                          for p in sorted(source_paths)},
    }
    report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    report.with_suffix('.json.sha256').write_text(sha(report.read_bytes()) + '  ' + report.name + '\n')
    print('NVIDIA lifecycle targeted checks passed: ' + str(report))
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
        print('Lifecycle checks failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stdout or '')[-6000:] + (error.stderr or '')[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
