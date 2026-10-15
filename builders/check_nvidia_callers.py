#!/usr/bin/env python3
"""Check the real NVIDIA allocator/mutex callers without changing the v4 probe."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-caller-integration'
SDK_COMMIT = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
NVIDIA_COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
SYMBOLS = (
    'os_alloc_mem', 'os_free_mem', 'os_alloc_mutex', 'os_free_mutex',
    'os_acquire_mutex', 'os_cond_acquire_mutex', 'os_release_mutex',
    '_portMemAllocPagedUntracked', '_portMemAllocNonPagedUntracked', '_portMemFreeUntracked',
    'portSyncMutexInitialize', 'portSyncMutexDestroy', 'portSyncMutexAcquire',
    'portSyncMutexAcquireConditional', 'portSyncMutexRelease', 's540NvidiaCallerAssertionFailed',
)
PLATFORM_IMPORTS = {
    '_IOMallocAligned', '_IOFreeAligned', '_IOMalloc', '_IOFree',
    '_IOSimpleLockAlloc', '_IOSimpleLockFree', '_IOSimpleLockLock', '_IOSimpleLockUnlock',
    '_ml_at_interrupt_context', '_ml_get_interrupts_enabled', '_ml_set_interrupts_enabled',
    '_assert_wait', '_thread_block', '_thread_wakeup_prim', '_panic',
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=120)


def macho(path: Path, kind: int) -> None:
    data = path.read_bytes()[:16]
    if len(data) != 16:
        raise ValueError('Truncated Mach-O output.')
    header = struct.unpack('<IIII', data)
    if header[:2] != (0xFEEDFACF, 0x01000007) or header[3] != kind:
        raise ValueError('Unexpected Intel Mach-O output: ' + path.name)
    if run('/usr/bin/lipo', '-archs', str(path)).stdout.strip() != 'x86_64':
        raise ValueError('Only Intel x86_64 is supported.')


def sign(path: Path) -> None:
    macho(path, 2)
    run('/usr/bin/codesign', '--force', '--sign', '-', str(path))
    run('/usr/bin/codesign', '--verify', '--strict', str(path))


def native_result(path: Path) -> dict:
    result = json.loads(run(str(path)).stdout)
    if (result.get('status') != 'passed' or result.get('execution') != 'native-user-space'
            or result.get('kernel_runtime') != 'not_tested' or result.get('gpu_access') is not False
            or not isinstance(result.get('checks'), int) or result['checks'] <= 0):
        raise ValueError('Unexpected native result: ' + path.name)
    return result


def no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def assertion_result(path: Path) -> dict:
    result = subprocess.run([str(path), '--assert-fail'], capture_output=True, text=True,
                            timeout=30, preexec_fn=no_core)
    if (result.returncode != -signal.SIGABRT
            or 'NVIDIA caller assertion failed: status == NV_OK' not in result.stderr):
        raise ValueError('Original mandatory acquisition assertion did not abort: '
                         + str(result.returncode))
    return {'status': 'passed', 'original_caller': 'portSyncMutexAcquire',
            'failed_os_acquisition': 'fatal assertion', 'signal': 'SIGABRT',
            'returned_unlocked': False}


def check(sdk: Path, destination: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS check host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the checked source.')
    sdk = sdk.resolve(strict=True)
    if run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != SDK_COMMIT:
        raise ValueError('The kernel SDK differs from its pinned revision.')
    provenance_test = ROOT / 'tests/test_nvidia_caller_provenance.py'
    tested = run(sys.executable, str(provenance_test))
    print((tested.stdout + tested.stderr).strip())
    spec = importlib.util.spec_from_file_location('caller_provenance', provenance_test)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    provenance = module.verify_upstream()
    if provenance['commit'] != NVIDIA_COMMIT:
        raise ValueError('Unexpected NVIDIA input revision.')
    destination = destination.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    report = destination / 'caller-checks.json'
    if report.exists():
        raise ValueError('The check output already exists.')

    with tempfile.TemporaryDirectory(prefix='nvidia-callers-') as temporary:
        work = Path(temporary)
        common = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-O2',
                  '-Wall', '-Wextra', '-Werror']
        kernel = [*common, '-mkernel', '-fno-builtin', '-fno-common', '-fno-stack-protector',
                  '-mno-red-zone', '-DKERNEL', '-D__KERNEL__', '-nostdinc',
                  '-isystem', str(sdk / 'Headers')]
        cpp_kernel = ['-fapple-kext', '-fno-exceptions', '-fno-rtti', '-nostdinc++']
        inputs = (
            (SOURCE / 'src/S540NvidiaReserve.cpp', 'clang++', 'c++17'),
            (SOURCE / 'src/S540NvidiaMutex.cpp', 'clang++', 'c++17'),
            (SOURCE / 'src/S540NvidiaCallerAssertions.cpp', 'clang++', 'c++17'),
            (SOURCE / 'upstream/nvport_allocator_callers.c', 'clang', 'c11'),
            (SOURCE / 'upstream/nvport_mutex_callers.c', 'clang', 'c11'),
        )
        kernel_objects = []
        for source, compiler, standard in inputs:
            obj = work / ('kernel-' + source.stem + '.o')
            extra = cpp_kernel if compiler == 'clang++' else []
            run('/usr/bin/xcrun', compiler, *kernel, *extra, '-std=' + standard,
                '-c', str(source), '-o', str(obj))
            macho(obj, 1)
            kernel_objects.append(str(obj))
        combined = work / 'kernel-callers-combined.o'
        run('/usr/bin/xcrun', 'ld', '-r', '-arch', 'x86_64', *kernel_objects, '-o', str(combined))
        macho(combined, 1)
        defined = run('/usr/bin/nm', '-g', str(combined)).stdout
        for symbol in SYMBOLS:
            if not re.search(r'\bT _' + re.escape(symbol) + r'$', defined, re.M):
                raise ValueError('An actual OS-hook/caller symbol is missing: ' + symbol)
        imports = set(run('/usr/bin/nm', '-u', '-j', str(combined)).stdout.split())
        if imports != PLATFORM_IMPORTS:
            raise ValueError('Kernel imports differ: missing=' + str(sorted(PLATFORM_IMPORTS - imports))
                             + ', unexpected=' + str(sorted(imports - PLATFORM_IMPORTS)))
        sections = run('/usr/bin/otool', '-l', str(combined)).stdout
        if '__mod_init_func' in sections or '__mod_term_func' in sections:
            raise ValueError('The candidate gained static constructors or destructors.')

        results = {}
        harnesses = ('check_reserve_native.cpp', 'check_allocator_callers_native.cpp',
                     'check_mutex_callers_native.cpp')
        for instrumented in (False, True):
            label = 'sanitized' if instrumented else 'native'
            flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer'] if instrumented else []
            objects = []
            for source, compiler, standard in inputs:
                obj = work / (label + '-' + source.stem + '.o')
                run('/usr/bin/xcrun', compiler, *common, *flags, '-std=' + standard,
                    '-c', str(source), '-o', str(obj))
                objects.append(str(obj))
            for name in harnesses:
                executable = work / (label + '-' + Path(name).stem)
                run('/usr/bin/xcrun', 'clang++', *common, *flags, '-std=c++17',
                    str(SOURCE / 'tests' / name), *objects, '-pthread', '-o', str(executable))
                sign(executable)
                results[label + '/' + name] = native_result(executable)
                if name == 'check_mutex_callers_native.cpp' and not instrumented:
                    results['mandatory_assertion'] = assertion_result(executable)

        source_paths = set(SOURCE.rglob('*'))
        # Include every unchanged shared reference actually verified by provenance.
        shared = ROOT / 'packages/nvidia-os-adapter/upstream'
        source_paths.update(p for p in shared.rglob('*') if p.is_file()
                            and p.suffix in ('.h', '.c', '.json'))
        record = {
            'format': 1, 'component': 'nvidia-nvport-callers', 'version': '0.1.0',
            'status': 'passed', 'github_sha': commit, 'architecture': 'x86_64',
            'kernel_sdk_commit': SDK_COMMIT, 'upstream': provenance,
            'native_execution': results,
            'kernel_compile': {'status': 'passed', 'kind': 'relocatable-object',
                               'resolved_os_and_caller_symbols': list(SYMBOLS),
                               'remaining_platform_imports': sorted(imports),
                               'static_initializers': False},
            'reserve': {'slots': 32, 'maximum_request_bytes': 131072, 'backing_bytes': 4194304,
                        'lifecycle_requires_quiescence': True, 'full_rm_heap': False},
            'mutex': {'ordinary_owner_thread_only': True, 'recursive': False,
                      'kernel_conditional_and_release': 'spin guard and wake only',
                      'native_backend': 'pthread functional semantics'},
            'kernel_runtime': 'not_tested', 'interrupt_runtime': 'not_tested',
            'gpu_operations': 'none', 'resource_manager_integration': False,
            'transport_probe': 'unchanged confirmed version 0.4.0', 'laptop_package': False,
            'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
                              for p in sorted(source_paths) if p.is_file()
                              and p.suffix in ('.c', '.cpp', '.h', '.hpp', '.json')},
        }
        report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    report.with_suffix('.json.sha256').write_text(sha(report.read_bytes()) + '  ' + report.name + '\n')
    print('NVIDIA caller integration targeted checks passed: ' + str(report))
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
        print('Caller checks failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stdout or '')[-6000:] + (error.stderr or '')[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
