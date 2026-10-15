#!/usr/bin/env python3
"""Check actual NVIDIA ResourceServer/NVOC and Darwin host-service backends."""
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
RM = transport.RM_SERVICES
RS = transport.RESOURCE_SERVER
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
BLOCKED = ('full_rm_initialized', 'firmware_loaded', 'gpu_initialized',
           'device_dma_verified', 'interrupts_enabled')


def exact(result: dict, expected: dict, description: str) -> None:
    mismatches = {key: {'expected': value, 'observed': result.get(key)}
                  for key, value in expected.items()
                  if type(result.get(key)) is not type(value) or result[key] != value}
    if mismatches:
        raise ValueError(description + ': ' + json.dumps(mismatches, sort_keys=True)[:3000])


def verify_result(result: dict, stem: str, component: str) -> None:
    exact(result, {'format': 1, 'component': component, 'failures': 0}, stem)
    if stem == 'check_memory_native':
        exact(result, {'checks': 166, 'startup_checks': 24, 'startup_failures': 0,
                       'fault_cases': 11, 'threads': 4, 'lifecycle_cycles': 256,
                       'worker_failures': 0}, 'RM host-page/CPU-map coverage changed')
    elif stem == 'check_provider_session_native':
        exact(result, {'checks': 252, 'concurrent_reads': 4000,
                       'retention_balanced': True, 'pci_writes': False,
                       'interrupt_registration': False}, 'Retained PCI coverage changed')
    elif stem == 'check_resource_server_native':
        exact(result, {'checks': 45, **dict.fromkeys(('server', 'clients', 'resources', 'sharing',
                                    'control', 'cleanup'), True)}, 'Actual ResourceServer lifecycle')
    elif stem == 'check_resource_faults_native':
        exact(result, {'checks': 598, 'constructor_cases': 31, 'resource_cases': 31,
                       'pressure_failures': 29, 'minimum_free_slots': 29,
                       'recovery': True, 'cleanup': True}, 'Actual constructor/resource allocation unwind')
    elif stem == 'check_resource_backend_native':
        exact(result, {'checks': 134, 'tls_threads': 32, 'entries_per_thread': 16,
                       'rw_updates': 4800, 'cleanup': True}, 'ResourceServer host backend')
    elif stem == 'check_rm_runtime_native':
        exact(result, {'entrypoint': 'S540NvidiaRmRuntime::checkIntegrated',
                       'checks': 96, 'resource_server_checks': 45,
                       'previous_cpu_checks': 258, 'preparation_checks': 131,
                       'host_memory_checks': 24, 'pci_session_checks': 20,
                       'profile': 'standalone-resource-server-cached-host-readonly-pci',
                       **dict.fromkeys(('previous_blocks_passed', 'acquired',
                           'resource_server', 'host_memory', 'pci_session', 'clients',
                           'resources', 'sharing', 'control', 'cleanup', 'cold_after',
                           'os_objects_released'), True),
                       **dict.fromkeys(BLOCKED, False)}, 'Same-lease production aggregate')
        if (type(result.get('resource_server_checks')) is not int or result['resource_server_checks'] < 1
                or result['checks'] != result['resource_server_checks'] + 24 + 20 + 7):
            raise ValueError('The aggregate component totals do not agree: ' + json.dumps(result)[:2500])
    elif stem == 'check_rm_faults_native':
        exact(result, {'checks': 33, 'cross_stage_faults': 6, 'workers': 4,
                       'iterations_per_worker': 6, 'worker_errors': 0,
                       **dict.fromkeys(('nested_lease_refusal', 'recovery', 'cleanup',
                                        'cold_after'), True),
                       **dict.fromkeys(BLOCKED, False)}, 'Cross-generation fault/recovery coverage')
        completed, refused = result.get('completed_runs'), result.get('lease_refusals')
        if (type(completed) is not int or type(refused) is not int or completed < 1
                or refused < 0 or completed + refused != 24):
            raise ValueError('All 24 mixed-generation lease attempts must be accounted for.')


def validate_full_rm_inventory() -> dict:
    record = json.loads((ROOT / 'builders/reference/nvidia-rm-full-closure.json').read_text())
    if (record.get('commit') != COMMIT or record.get('source_units') != 1099
            or record.get('status') != 'compiled-closure-inventory'
            or record.get('runtime_status', {}).get('rm_initialization') != 'not_executed'):
        raise ValueError('The normalized full RM source/compile inventory changed.')
    expected = {'linux-control': (401, 225), 'non-linux-unix-control': (387, 215)}
    for name, counts in expected.items():
        profile = record['profiles'][name]
        for kind, count in zip(('all_exported_rm', 'selected_rm_startup'), counts):
            item = profile[kind]
            symbols = item['relocation_required_undefined']
            if (item['external_count'] != count or len(symbols) != count
                    or symbols != sorted(set(symbols))
                    or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', symbol) for symbol in symbols)):
                raise ValueError('The full RM external symbol inventory is inconsistent.')
    return record



def analyze_full_rm(upstream: Path, output: Path) -> Path:
    """Optional ELF compile analysis; never a Darwin runtime or GPU test."""
    if sys.platform != 'linux':
        raise ValueError('The reproducible GNU/ELF inventory requires a Linux host.')
    upstream = upstream.resolve(strict=True)
    if transport.run('git', '-C', str(upstream), 'rev-parse', 'HEAD').stdout.strip() != COMMIT:
        raise ValueError('The full RM source differs from the pinned NVIDIA commit.')
    if transport.run('git', '-C', str(upstream), 'status', '--porcelain').stdout:
        raise ValueError('The full RM inventory requires an unchanged upstream checkout.')
    expected = validate_full_rm_inventory()
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    observed = {}
    for profile in expected['profiles']:
        work = output / profile
        if work.exists():
            raise ValueError('Use an empty full RM analysis output directory.')
        work.mkdir()
        command = ['make', '-C', str(upstream / 'src/nvidia'),
                   'OUTPUTDIR=' + str(work), 'NV_BUILD_USER=build',
                   'NV_BUILD_HOST=ci', 'NV_VERBOSE=0', '-j4']
        if profile == 'non-linux-unix-control':
            command += ['TARGET_OS=Darwin',
                        'EXTRA_CFLAGS=-U__linux__ -U__linux -DNV_UNIX -D__NV_UNIX_VERSION_H__ -DNV_VERSION_STRING=\\"615.78.08\\"']
        compiled = transport.run(*command, timeout=1200)
        (work / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        objects = sorted(path for path in work.glob('*.o') if path.name != 'nv-kernel.o')
        if len(objects) != 1100:
            raise ValueError('The original full RM compilation did not produce all 1100 objects.')
        selected = work / 'selected-startup.o'
        transport.run('ld', '-r', '--gc-sections', '--undefined=rm_init_rm',
                      '--undefined=rm_shutdown_rm', *(str(path) for path in objects),
                      '-o', str(selected), timeout=300)
        stripped = work / 'selected-startup-stripped.o'
        transport.run('objcopy', '--strip-unneeded', str(selected), str(stripped))
        full_stripped = work / 'all-exported-rm-stripped.o'
        transport.run('objcopy', '--strip-unneeded', str(work / 'nv-kernel.o'), str(full_stripped))
        observed[profile] = {}
        for kind, path in (('all_exported_rm', full_stripped),
                           ('selected_rm_startup', stripped)):
            symbols = sorted(set(transport.run('nm', '-u', path.as_posix()).stdout.split()[1::2]))
            if symbols != expected['profiles'][profile][kind]['relocation_required_undefined']:
                raise ValueError('The reproduced full RM external contract differs: ' + profile + '/' + kind
                                 + '; missing=' + str(sorted(set(expected['profiles'][profile][kind]['relocation_required_undefined']) - set(symbols)))
                                 + '; unexpected=' + str(sorted(set(symbols) - set(expected['profiles'][profile][kind]['relocation_required_undefined']))))
            observed[profile][kind] = {'external_count': len(symbols),
                'relocation_required_undefined': symbols, 'object_bytes': path.stat().st_size}
    report = output / 'full-rm-closure-reproduction.json'
    report.write_text(json.dumps({'format': 1, 'status': 'matched-pinned-inventory',
        'commit': COMMIT, 'compiler': transport.run('gcc', '--version').stdout.splitlines()[0],
        'profiles': observed, 'darwin_compile': False, 'rm_initialized': False,
        'gpu_operations': 'none'}, indent=2, sort_keys=True) + '\n')
    return report

def check(sdk: Path, output: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS check host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the checked source.')
    if transport.run('/usr/bin/git', '-C', str(sdk.resolve(strict=True)), 'rev-parse', 'HEAD').stdout.strip() != transport.SDK_COMMIT:
        raise ValueError('The kernel SDK differs from its pinned revision.')
    inventory = validate_full_rm_inventory()
    for test in sorted((RS / 'tests').glob('test_*.py')):
        checked = transport.run(sys.executable, str(test))
        print((checked.stdout + checked.stderr).strip())
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'rm-services-checks.json'
    if report.exists():
        raise ValueError('The RM service check output already exists.')
    cpu_cpp, cpu_c = transport.production_sources()
    rs_cpp, rs_c = transport.resource_server_sources()
    cases = (
        ('check_memory_native', 'nvidia-rm-memory-services', RM / 'memory/tests/check_memory_native.cpp',
         ([RM / 'memory/S540NvidiaRmMemory.cpp'], [])),
        ('check_provider_session_native', 'nvidia-provider-session', RM / 'pci/tests/check_provider_session_native.cpp',
         ([RM / 'pci/S540NvidiaProviderSession.cpp', RM / 'pci/S540NvidiaProviderSessionCheck.cpp'], [])),
        ('check_resource_server_native', 'nvidia-resource-server', RS / 'tests/check_resource_server_native.cpp',
         ([*cpu_cpp, *rs_cpp], [*cpu_c, *rs_c])),
        ('check_resource_faults_native', 'nvidia-resource-faults', RS / 'tests/check_resource_faults_native.cpp',
         ([*cpu_cpp, *rs_cpp], [*cpu_c, *rs_c])),
        ('check_resource_backend_native', 'resource-server-backend', RS / 'tests/check_resource_backend_native.cpp',
         ([*cpu_cpp, RS / 'src/S540NvidiaResourceBackend.cpp'], cpu_c)),
        ('check_rm_runtime_native', 'nvidia-rm-services-runtime', RM / 'tests/check_rm_runtime_native.cpp',
         transport.rm_full_sources()),
        ('check_rm_faults_native', 'nvidia-rm-services-faults', RM / 'tests/check_rm_faults_native.cpp',
         transport.rm_full_sources()),
    )
    results = {}
    with tempfile.TemporaryDirectory(prefix='s540-nvidia-rm-services-') as temporary:
        work = Path(temporary)
        for instrumented in (False, True):
            label = 'sanitized' if instrumented else 'native'
            flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer'] if instrumented else []
            for stem, component, harness, closure in cases:
                binary = transport.compile_native_harness(work, label + '-' + stem,
                    harness, flags, source_closure=closure)
                result = transport.native_check(binary)
                verify_result(result, stem, component)
                results[label + '/' + stem] = result
    for label in ('native', 'sanitized'):
        if results[label + '/check_resource_server_native']['checks'] != results[label + '/check_rm_runtime_native']['resource_server_checks']:
            raise ValueError('Standalone and integrated actual server checks do not agree.')
    inputs = {p for package in (RS, RM) for p in package.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    inputs.update([Path(__file__), ROOT / 'builders/build_nvidia_transport.py',
                   ROOT / 'builders/reference/nvidia-rm-full-closure.json'])
    record = {'format': 1, 'component': 'nvidia-rm-services', 'version': '0.1.0',
              'status': 'passed', 'github_sha': commit, 'architecture': 'x86_64',
              'kernel_sdk_commit': transport.SDK_COMMIT, 'native_execution': results,
              'full_rm_compile_inventory': inventory,
              'kernel_runtime': 'not_tested', 'gpu_operations': 'none',
              'resource_server_profile': 'RS_STANDALONE=1; actual NVOC server/client/resource objects',
              'full_rm_initialized': False, 'device_dma_verified': False,
              'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(inputs)}}
    report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print('Bundled NVIDIA ResourceServer/host-service checks passed: ' + str(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-sdk', type=Path)
    parser.add_argument('--analyze-full-rm-upstream', type=Path,
                        help='Optional Linux-only reproduction of the full original RM compile inventory.')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.analyze_full_rm_upstream:
            print(analyze_full_rm(args.analyze_full_rm_upstream, args.output_dir))
        elif args.kernel_sdk:
            check(args.kernel_sdk, args.output_dir)
        else:
            raise ValueError('--kernel-sdk is required for native RM service checks.')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('RM service checks failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stdout or '')[-6000:] + (error.stderr or '')[-6000:], file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
