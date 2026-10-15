#!/usr/bin/env python3
"""Check the CPU-only NVIDIA clock adapter on Intel macOS; never install a kext."""
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
SYMBOLS = ('os_get_monotonic_time_ns', 'os_get_monotonic_time_ns_hr',
           'os_get_monotonic_tick_resolution_ns', 'portTimeGetUptimeMicroseconds',
           'portTimeGetUptimeNanoseconds', 'portTimeGetUptimeNanosecondsHighPrecision',
           'portTimeGetUptimeResolution')


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


def check(sdk: Path, destination: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS check host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the checked source.')
    sdk = sdk.resolve(strict=True)
    if run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != SDK_COMMIT:
        raise ValueError('The kernel SDK differs from its pinned revision.')
    for test in ('test_nvidia_clock_provenance.py', 'test_nvidia_clock_policy.py'):
        result = run(sys.executable, str(ROOT / 'tests' / test))
        print((result.stdout + result.stderr).strip())
    spec = importlib.util.spec_from_file_location('clock_provenance', ROOT / 'tests/test_nvidia_clock_provenance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    provenance = module.verify_upstream()
    if provenance['commit'] != NVIDIA_COMMIT:
        raise ValueError('Unexpected NVIDIA source revision.')
    destination = destination.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    report = destination / 'clock-adapter-checks.json'
    if report.exists():
        raise ValueError('The check output already exists.')
    with tempfile.TemporaryDirectory(prefix='nvidia-clock-') as temporary:
        work = Path(temporary)
        backend = SOURCE / 'src/S540NvidiaClock.cpp'
        caller = SOURCE / 'upstream/nvport_time_uptime.c'
        harness = SOURCE / 'tests/check_clock_native.cpp'
        common = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-O2', '-Wall', '-Wextra', '-Werror']
        kernel = [*common, '-mkernel', '-fno-builtin', '-fno-common', '-fno-stack-protector',
                  '-mno-red-zone', '-DKERNEL', '-D__KERNEL__', '-nostdinc',
                  '-isystem', str(sdk / 'Headers')]
        kernel_objects = []
        native_objects = []
        for source, compiler, standard in ((backend, 'clang++', 'c++17'), (caller, 'clang', 'c11')):
            obj = work / ('kernel-' + source.stem + '.o')
            extra = ['-fapple-kext', '-fno-exceptions', '-fno-rtti', '-nostdinc++'] if compiler == 'clang++' else []
            run('/usr/bin/xcrun', compiler, *kernel, *extra, '-std=' + standard, '-c', str(source), '-o', str(obj))
            macho(obj, 1)
            kernel_objects.append(str(obj))
            obj = work / ('native-' + source.stem + '.o')
            run('/usr/bin/xcrun', compiler, *common, '-std=' + standard, '-c', str(source), '-o', str(obj))
            native_objects.append(str(obj))
        linked = work / 'kernel-clock-combined.o'
        run('/usr/bin/xcrun', 'ld', '-r', '-arch', 'x86_64', *kernel_objects, '-o', str(linked))
        macho(linked, 1)
        defined = run('/usr/bin/nm', '-g', str(linked)).stdout
        for symbol in SYMBOLS:
            if not re.search(r'\bT _' + re.escape(symbol) + r'$', defined, re.M):
                raise ValueError('The real kernel adapter/caller symbol is absent: ' + symbol)
        imports = set(run('/usr/bin/nm', '-u', '-j', str(linked)).stdout.split())
        expected = {'_clock_get_uptime', '_absolutetime_to_nanoseconds', '_clock_timebase_info'}
        if imports != expected:
            raise ValueError('Unexpected kernel imports: ' + ', '.join(sorted(imports)))
        executable = work / 'check-clock-native'
        run('/usr/bin/xcrun', 'clang++', *common, '-std=c++17', str(harness),
            *native_objects, '-o', str(executable))
        macho(executable, 2)
        run('/usr/bin/codesign', '--force', '--sign', '-', str(executable))
        run('/usr/bin/codesign', '--verify', '--strict', str(executable))
        native = json.loads(run(str(executable)).stdout)
        if (native.get('status') != 'passed' or native.get('execution') != 'native-user-space'
                or native.get('gpu_access') is not False or native.get('kernel_runtime') != 'not_tested'):
            raise ValueError('The native harness returned an unexpected result.')
        record = {
            'format': 1, 'component': 'nvidia-os-clock', 'version': '0.1.0',
            'status': 'passed', 'github_sha': commit, 'architecture': 'x86_64',
            'kernel_sdk_commit': SDK_COMMIT, 'upstream': provenance,
            'native_execution': native,
            'kernel_compile': {'status': 'passed', 'kind': 'relocatable-object',
                               'resolved_clock_and_caller_symbols': list(SYMBOLS),
                               'remaining_platform_imports': sorted(imports)},
            'checks': ['pinned upstream provenance and adapted caller', 'conversion and quantization policy',
                       'kernel object compilation and relocatable link', 'kernel import audit',
                       'native user-space ABI/caller and deadline execution', 'native harness signature'],
            'kernel_runtime': 'not_tested', 'gpu_operations': 'none',
            'transport_probe': 'unchanged version 0.3.0', 'laptop_package': False,
            'binary_sha256': {'kernel_object': sha(linked.read_bytes()), 'native_harness': sha(executable.read_bytes())},
            'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(SOURCE.rglob('*'))
                              if p.is_file() and p.suffix in ('.c', '.cpp', '.h', '.hpp', '.json')},
        }
        report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    report.with_suffix('.json.sha256').write_text(sha(report.read_bytes()) + '  ' + report.name + '\n')
    print('NVIDIA clock adapter targeted checks passed: ' + str(report))
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
        print('Clock checks failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stdout or '')[-6000:] + (error.stderr or '')[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
