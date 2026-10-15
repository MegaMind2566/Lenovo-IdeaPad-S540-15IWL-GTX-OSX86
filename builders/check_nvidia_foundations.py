#!/usr/bin/env python3
"""Check CPU-only NVIDIA memory, atomic and clock integration on Intel macOS."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-os-adapter'
SDK_COMMIT = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
NVIDIA_COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
SYMBOLS = (
    'os_get_monotonic_time_ns', 'os_get_monotonic_time_ns_hr',
    'os_get_monotonic_tick_resolution_ns', 'portTimeGetUptimeMicroseconds',
    'portTimeGetUptimeNanoseconds', 'portTimeGetUptimeNanosecondsHighPrecision',
    'portTimeGetUptimeResolution', 'os_mem_copy', 'os_mem_set', 'os_mem_cmp',
    's540NvidiaMemoryCopy', 's540NvidiaMemorySet', 's540NvidiaMemoryCompare',
    'portMemCopy', 'portMemCopyAligned', 'portMemSet', 'portMemCmp',
    'S540NvidiaAtomicCompileCheck',
)
PLATFORM_IMPORTS = {
    '_clock_get_uptime', '_absolutetime_to_nanoseconds', '_clock_timebase_info',
    '_memcpy', '_memset', '_memcmp',
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
        raise ValueError('Unexpected Intel Mach-O type: ' + path.name)
    if run('/usr/bin/lipo', '-archs', str(path)).stdout.strip() != 'x86_64':
        raise ValueError('Only Intel x86_64 is supported.')


def load_provenance(component: str, test: bool) -> dict:
    path = ROOT / ('tests/test_nvidia_' + component + '_provenance.py')
    if test:
        result = run(sys.executable, str(path))
        print((result.stdout + result.stderr).strip())
    spec = importlib.util.spec_from_file_location(component + '_provenance', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    record = module.verify_upstream()
    if record['commit'] != NVIDIA_COMMIT:
        raise ValueError('An upstream input differs from the selected NVIDIA revision.')
    return record


def native_result(path: Path, expected_mode: str | None = None) -> dict:
    macho(path, 2)
    run('/usr/bin/codesign', '--force', '--sign', '-', str(path))
    run('/usr/bin/codesign', '--verify', '--strict', str(path))
    result = json.loads(run(str(path)).stdout)
    if (result.get('status') != 'passed' or result.get('execution') != 'native-user-space'
            or result.get('kernel_runtime') != 'not_tested' or result.get('gpu_access') is not False
            or not isinstance(result.get('checks'), int) or result['checks'] <= 0):
        raise ValueError('Unexpected native harness result: ' + path.name)
    if expected_mode is not None and result.get('mode') != expected_mode:
        raise ValueError('Unexpected native atomic selection: ' + path.name)
    return result


def check(sdk: Path, destination: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS check host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the checked source.')
    sdk = sdk.resolve(strict=True)
    if run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != SDK_COMMIT:
        raise ValueError('The kernel SDK differs from its pinned revision.')
    provenance = {component: load_provenance(component, component != 'clock')
                  for component in ('clock', 'memory', 'atomic')}
    destination = destination.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    report = destination / 'foundation-checks.json'
    if report.exists():
        raise ValueError('The check output already exists.')
    with tempfile.TemporaryDirectory(prefix='nvidia-foundations-') as temporary:
        work = Path(temporary)
        common = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-O2',
                  '-Wall', '-Wextra', '-Werror', '-I', str(SOURCE / 'upstream/include')]
        kernel = [*common, '-mkernel', '-fno-builtin', '-fno-common', '-fno-stack-protector',
                  '-mno-red-zone', '-DKERNEL', '-D__KERNEL__', '-nostdinc',
                  '-isystem', str(sdk / 'Headers')]
        cpp_kernel = ['-fapple-kext', '-fno-exceptions', '-fno-rtti', '-nostdinc++']
        base_sources = (
            (SOURCE / 'src/S540NvidiaClock.cpp', 'clang++', 'c++17'),
            (SOURCE / 'upstream/nvport_time_uptime.c', 'clang', 'c11'),
            (SOURCE / 'src/S540NvidiaMemory.cpp', 'clang++', 'c++17'),
            (SOURCE / 'upstream/nvport_memory_primitives.c', 'clang', 'c11'),
        )
        kernel_objects, native_objects = [], []
        for source, compiler, standard in base_sources:
            obj = work / ('kernel-' + source.stem + '.o')
            extra = cpp_kernel if compiler == 'clang++' else []
            run('/usr/bin/xcrun', compiler, *kernel, *extra, '-std=' + standard,
                '-c', str(source), '-o', str(obj))
            macho(obj, 1)
            kernel_objects.append(str(obj))
            obj = work / ('native-' + source.stem + '.o')
            run('/usr/bin/xcrun', compiler, *common, '-std=' + standard,
                '-c', str(source), '-o', str(obj))
            native_objects.append(str(obj))

        kernel_results, atomic_results = {}, {}
        kernel_consumer = SOURCE / 'tests/check_atomic_kernel.c'
        for mode, compiler, standard, language, native_name in (
                ('c11', 'clang', 'gnu11', 'c', 'check_atomic_native.c'),
                ('c++clang', 'clang++', 'c++17', 'c++', 'check_atomic_native.cpp')):
            safe_mode = 'c11' if mode == 'c11' else 'cpp-clang'
            obj = work / ('kernel-atomic-' + safe_mode + '.o')
            extra = cpp_kernel if compiler == 'clang++' else []
            atomic_options = ['-ffreestanding', '-x', language, '-std=' + standard]
            run('/usr/bin/xcrun', compiler, *kernel, *extra, *atomic_options,
                '-c', str(kernel_consumer), '-o', str(obj))
            macho(obj, 1)
            if run('/usr/bin/nm', '-u', '-j', str(obj)).stdout.split():
                raise ValueError('Atomic code gained a runtime/platform helper: ' + mode)
            linked = work / ('kernel-foundations-' + safe_mode + '.o')
            run('/usr/bin/xcrun', 'ld', '-r', '-arch', 'x86_64', *kernel_objects,
                str(obj), '-o', str(linked))
            macho(linked, 1)
            defined = run('/usr/bin/nm', '-g', str(linked)).stdout
            for symbol in SYMBOLS:
                if not re.search(r'\bT _' + re.escape(symbol) + r'$', defined, re.M):
                    raise ValueError('A real adapter/caller symbol is absent: ' + symbol)
            imports = set(run('/usr/bin/nm', '-u', '-j', str(linked)).stdout.split())
            if imports != PLATFORM_IMPORTS:
                raise ValueError('Unexpected kernel imports: ' + ', '.join(sorted(imports)))
            kernel_results[mode] = {
                'status': 'passed', 'kind': 'relocatable-object',
                'resolved_adapter_and_caller_symbols': list(SYMBOLS),
                'remaining_platform_imports': sorted(imports),
                'atomic_platform_or_runtime_imports': [], 'sha256': sha(linked.read_bytes()),
            }
            executable = work / ('check-atomic-' + safe_mode)
            run('/usr/bin/xcrun', compiler, *common, '-ffreestanding', '-std=' + standard,
                str(SOURCE / 'tests' / native_name), '-pthread', '-o', str(executable))
            atomic_results[mode] = native_result(executable, mode)

        executable = work / 'check-memory-and-clock'
        harness = SOURCE / 'tests/check_memory_native.cpp'
        run('/usr/bin/xcrun', 'clang++', *common, '-std=c++17', str(harness),
            *native_objects, '-o', str(executable))
        memory_result = native_result(executable)
        # Instrument the actual backend and caller, not only the test harness.
        sanitized = work / 'check-memory-and-clock-sanitized'
        sanitizer_flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        sanitized_objects = []
        for source, compiler, standard in base_sources:
            obj = work / ('sanitized-' + source.stem + '.o')
            run('/usr/bin/xcrun', compiler, *common, *sanitizer_flags, '-std=' + standard,
                '-c', str(source), '-o', str(obj))
            sanitized_objects.append(str(obj))
        run('/usr/bin/xcrun', 'clang++', *common, *sanitizer_flags, '-std=c++17',
            str(harness), *sanitized_objects, '-o', str(sanitized))
        sanitized_result = native_result(sanitized)
        if sanitized_result != memory_result:
            raise ValueError('The instrumented memory harness returned a different result.')

        record = {
            'format': 1, 'component': 'nvidia-os-foundations', 'version': '0.2.0',
            'status': 'passed', 'github_sha': commit, 'architecture': 'x86_64',
            'kernel_sdk_commit': SDK_COMMIT, 'upstream': provenance,
            'native_memory_and_clock': memory_result,
            'native_memory_sanitizers': {'status': 'passed', 'tools': ['address', 'undefined']},
            'native_atomics': atomic_results, 'kernel_compile': kernel_results,
            'checks': ['pinned memory/atomic provenance and adapted memory caller',
                       'native memory bounds, guards, release behavior and clock integration',
                       'instrumented memory backend and caller',
                       'C11 and C++ Clang atomic semantics, contention and publication',
                       'combined kernel object compilation, relocatable links and exact import audit'],
            'kernel_runtime': 'not_tested', 'gpu_operations': 'none',
            'transport_probe': 'unchanged version 0.3.0', 'laptop_package': False,
            'scope': {'ordinary_ram_only': True, 'allocation': False, 'user_copy': False,
                      'interrupt_delivery': False, 'resource_manager_integration': False},
            'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
                              for p in sorted(SOURCE.rglob('*')) if p.is_file()
                              and p.suffix in ('.c', '.cpp', '.h', '.hpp', '.json')},
        }
        report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    report.with_suffix('.json.sha256').write_text(sha(report.read_bytes()) + '  ' + report.name + '\n')
    print('NVIDIA OS foundations targeted checks passed: ' + str(report))
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
        print('Foundation checks failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stdout or '')[-6000:] + (error.stderr or '')[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
