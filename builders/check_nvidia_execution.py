#!/usr/bin/env python3
"""Native checks for the combined global-RM/device/GSP execution milestone.

These checks exercise production CPU-side implementations and explicit native
backend fixtures. They never establish kernel IRQ, DMA, or GPU execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import build_nvidia_transport as transport
import check_nvidia_global_crypto as crypto
import compile_nvidia_global_rm as original
import nvidia_execution_commands as commands

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / 'packages/nvidia-darwin-services'
DEVICE = ROOT / 'packages/nvidia-device-transport'
GLOBAL = ROOT / 'packages/nvidia-global-rm'
GSP = ROOT / 'packages/nvidia-gsp-bootstrap'
SERVICE_NAMES = ('Platform', 'Sync', 'Work', 'Timer', 'Process', 'Runtime', 'Check')


def expect(record: dict, fields: dict, description: str) -> None:
    mismatches = {key: {'expected': value, 'observed': record.get(key)}
                  for key, value in fields.items()
                  if type(record.get(key)) is not type(value) or record[key] != value}
    if mismatches:
        raise ValueError(description + ': ' + json.dumps(mismatches, sort_keys=True))


def native_case(output: Path, name: str, sources: list[Path], harness: Path,
                expected: dict, *, arguments: list[str] | None = None,
                dead_strip: bool = False, host_control: bool = False) -> dict:
    results = {}
    _, cxx = crypto.compiler_pair(host_control)
    target = [] if host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0']
    common = [*target, '-O1', '-g',
              '-Wall', '-Wextra', '-Werror', '-std=c++17', '-pthread',
              '-I', str(ROOT / 'packages/nvidia-os-adapter/upstream/include')]
    for label, instrumentation in (('native', []), ('sanitized', [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
            '-fno-omit-frame-pointer'])):
        work = output / (name + '-' + label)
        work.mkdir(parents=True, exist_ok=True)
        binary = work / 'check'
        flags = ['-ffunction-sections', '-fdata-sections',
                 '-Wl,--gc-sections' if host_control else '-Wl,-dead_strip'] if dead_strip else []
        commands.run(*cxx, *common, *instrumentation, *flags,
                      *(str(path) for path in sources), str(harness), '-o', str(binary),
                      timeout=300, diagnostic_log=work / 'compile.log')
        crypto.verify_binary(binary, 2, host_control)
        record = json.loads(commands.run(str(binary), *(arguments or []), timeout=180,
                                        diagnostic_log=work / 'run.log').stdout)
        expect(record, {'format': 1, 'status': 'passed', 'failures': 0,
                       'execution': 'native-user-space', 'kernel_execution': 'not_tested',
                       'gpu_access': False, **expected}, name + '/' + label)
        results[label] = record
    return results


def services_case(output: Path, *, host_control: bool = False) -> dict:
    return native_case(output, 'darwin-services', [
        SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES],
        SERVICES / 'tests/check_darwin_services_native.cpp',
        {'component': 'nvidia-darwin-services', 'checks': 166,
         'production_checks': 37, 'mutex_updates': 12000,
         'concurrent_work_items': 4000, 'fault_paths': 17, 'cleanup': True},
        host_control=host_control)


@commands.logged(report='services-preflight.json')
def services_preflight(output: Path, *, host_control: bool = False) -> dict:
    if not host_control and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
        raise ValueError('Authoritative services preflight requires Intel macOS.')
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    progress = commands.ComponentProgress(output / 'services-preflight.json', {
        'component': 'nvidia-services-preflight', 'host_system': platform.system(),
        'authoritative_darwin_execution': not host_control,
        'production_candidate_allowed': False, 'kernel_runtime': 'not_tested', 'gpu_access': False})
    progress.component('darwin_services', lambda: services_case(output, host_control=host_control))
    progress.record['status'] = 'passed'
    progress.save()
    return progress.record


def timer_case(output: Path, upstream: Path, namespace: Path,
               *, host_control: bool) -> dict:
    """Only the RM callbacks/host allocator are fixtures; the timer is real code."""
    cc, cxx = crypto.compiler_pair(host_control)
    target = [] if host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0']
    c_compiler = Path(cc[0]) if host_control else Path('/usr/bin/clang')
    bridge = original.original_bridge_flags(upstream.resolve(strict=True), output,
                                             c_compiler, namespace.resolve(strict=True))
    kernel_only = {'-msoft-float', '-mno-red-zone', '-mcmodel=kernel', '-mno-mmx',
                   '-mno-sse', '-mno-sse2', '-mno-3dnow', '-fno-pic'}
    bridge = [flag for flag in bridge if flag not in kernel_only]
    bridge += [*target, '-fPIC']
    if host_control:
        bridge += ['-U__linux__', '-U__linux']
    common = [*target, '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
              '-I', str(ROOT / 'packages/nvidia-os-adapter/upstream/include')]
    results = {}
    for label, instrumentation in (('native', []), ('sanitized', [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
            '-fno-omit-frame-pointer'])):
        work = output / ('gsp-timers-' + label)
        work.mkdir(parents=True, exist_ok=True)
        objects = []
        for source in (GSP / 'timers/S540NvidiaGspTimersOriginal.c',
                       GSP / 'timers/tests/check_gsp_timers_native.c'):
            obj = work / (source.stem + '.o')
            commands.run(*cc, *bridge, '-O1', '-g', *instrumentation,
                          '-c', str(source), '-o', str(obj),
                          diagnostic_log=work / (source.stem + '-compile.log'))
            crypto.verify_binary(obj, 1, host_control)
            objects.append(str(obj))
        for name in SERVICE_NAMES:
            source = SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp')
            obj = work / (source.stem + '.o')
            commands.run(*cxx, *common, '-std=c++17', *instrumentation,
                          '-c', str(source), '-o', str(obj),
                          diagnostic_log=work / (source.stem + '-compile.log'))
            crypto.verify_binary(obj, 1, host_control)
            objects.append(str(obj))
        binary = work / 'check'
        commands.run(*cxx, *common, *instrumentation, *objects, '-o', str(binary),
                     diagnostic_log=work / 'link.log')
        crypto.verify_binary(binary, 2, host_control)
        record = json.loads(commands.run(str(binary), diagnostic_log=work / 'run.log').stdout)
        expect(record, {'component': 'nvidia-gsp-timers', 'format': 1,
                       'status': 'passed', 'checks': 34, 'failures': 0,
                       'rc_callbacks': 1, 'nano_callbacks': 2, 'callback_fixture': True,
                       'stack_abi_verified': True, 'quarantine_retention_verified': True,
                       'cleanup': True, 'execution': 'native-user-space',
                       'kernel_execution': 'not_tested', 'gpu_access': False},
               'gsp-timers/' + label)
        results[label] = record
    return results


@commands.logged(report='execution-checks.json')
def check(output: Path, assets: Path, *, upstream: Path | None = None,
          host_control: bool = False, namespace: Path | None = None) -> dict:
    if not host_control and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
        raise ValueError('Authoritative combined execution checks require Intel macOS.')
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    progress = commands.ComponentProgress(output / 'execution-checks.json', {
        'component': 'nvidia-execution-native', 'host_system': platform.system(),
        'authoritative_darwin_execution': not host_control,
        'production_candidate_allowed': False, 'kernel_runtime': 'not_tested', 'gpu_access': False})
    for package in (SERVICES, DEVICE, GLOBAL, GSP):
        for test in sorted(package.rglob('test_*.py')):
            result = commands.run(sys.executable, str(test))
            print((result.stdout + result.stderr).strip())
    records = progress.record['native_execution']
    progress.component('crypto', lambda: crypto.check(output / 'crypto', upstream, host_control=host_control))
    progress.component('darwin_services', lambda: services_case(output, host_control=host_control))
    progress.component('global_host', lambda: native_case(output, 'global-host', [
        GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp',
        GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp',
        *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES)],
        GLOBAL / 'tests/check_global_host_native.cpp',
        {'component': 'nvidia-global-host-native', 'checks': 24,
         'concurrent_allocations': 2048, 'service_calls': 2048,
         'context_refusals': 3, 'foreign_or_duplicate_frees': 2, 'cleanup': True},
        host_control=host_control))
    progress.component('device_transport', lambda: native_case(output, 'device-transport', [
        DEVICE / ('src/S540Nvidia' + name + '.cpp') for name in
        ('DeviceTransport', 'DeviceServices', 'DeviceCheck')],
        DEVICE / 'tests/check_device_transport_native.cpp',
        {'component': 'nvidia-device-transport', 'checks': 242,
         'production_checks': 21, 'unavailable_mapper_checks': 19,
         'lifecycle_cycles': 128, 'device_dma_verified': False,
         'hardware_interrupt_delivery': False, 'gpu_initialized': False},
        host_control=host_control))
    progress.component('firmware_store', lambda: native_case(output, 'firmware-store', [
        GSP / 'src/S540NvidiaGspFirmware.cpp',
        ROOT / 'packages/nvidia-firmware-assets/src/S540NvidiaFirmwareAssets.cpp',
        ROOT / 'packages/nvidia-hardware-transport/firmware/S540NvidiaFirmware.cpp'],
        GSP / 'tests/check_firmware_store_native.cpp',
        {'component': 'nvidia-gsp-firmware-store', 'checks': 314,
         'maximum_live_leases': 64, 'concurrent_rejections': 1536,
         'real_pair_verified': True, 'firmware_delivered_cpu': True,
         'firmware_loaded': False, 'gpu_initialized': False,
         'bridge_execution': 'not_tested'},
        arguments=[str(assets / 'gsp_tu10x.bin'), str(assets / 'ucodes_tu10x.bin')],
        dead_strip=True, host_control=host_control))
    progress.component('platform_parsers', lambda: native_case(output, 'platform-parsers', [
        GSP / 'platform/S540NvidiaPlatformParsers.cpp',
        GSP / 'platform/S540NvidiaGspPlatform.cpp'],
        GSP / 'platform/tests/check_platform_native.cpp',
        {'component': 'nvidia-gsp-platform-parsers', 'checks': 50,
         'malformed_fixtures': 2048, 'hardware_queried': False},
        host_control=host_control))
    if upstream is None or namespace is None:
        raise ValueError('The exact upstream tree and generated namespace are required for timer ABI checks.')
    progress.component('gsp_timers', lambda: timer_case(output, upstream, namespace, host_control=host_control))
    inputs = [path for package in (SERVICES, DEVICE, GLOBAL, GSP)
              for path in package.rglob('*') if path.is_file()
              and '__pycache__' not in path.parts and path.suffix != '.pyc']
    record = {'format': 1, 'status': 'passed', 'component': 'nvidia-execution-native',
              'host_system': platform.system(),
              'authoritative_darwin_execution': not host_control,
              'production_candidate_allowed': False,
              'global_rm_runtime': 'not_executed; complete production metadata closure unresolved',
              'generated_namespace_sha256': hashlib.sha256(namespace.read_bytes()).hexdigest(),
              'architecture': 'x86_64', 'native_execution': records,
              'kernel_runtime': 'not_tested', 'gpu_access': False,
              'source_sha256': {path.relative_to(ROOT).as_posix():
                  hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(inputs)}}
    (output / 'execution-checks.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--assets-dir', type=Path)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--namespace', type=Path,
                        help='Generated full RM header for the explicit timer callback fixture.')
    parser.add_argument('--host-control', action='store_true',
                        help='Explicit Linux ELF controls; never authoritative Darwin execution.')
    parser.add_argument('--services-preflight', action='store_true',
                        help='Run the existing services CPU case before full RM compilation; no firmware or upstream tree needed.')
    args = parser.parse_args()
    if args.services_preflight:
        services_preflight(args.output_dir, host_control=args.host_control)
        print('Darwin services CPU preflight passed; no kernel or GPU execution claimed.')
        return 0
    if args.assets_dir is None:
        parser.error('--assets-dir is required unless --services-preflight is selected')
    check(args.output_dir, args.assets_dir.resolve(strict=True), upstream=args.upstream,
          namespace=args.namespace, host_control=args.host_control)
    print('Combined execution CPU-side native checks passed; no GPU execution claimed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
