#!/usr/bin/env python3
"""Check bundled DMA, PCI and firmware/RPC preparation without loading a kext."""
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
SOURCE = ROOT / 'packages/nvidia-hardware-transport'
NVIDIA_COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_true(result: dict, fields: tuple[str, ...], description: str) -> None:
    missing = [field for field in fields if result.get(field) is not True]
    if missing:
        raise ValueError('Incomplete ' + description + ': ' + ', '.join(missing))


def verify_result(result: dict, stem: str, component: str) -> None:
    if (result.get('format') != 1 or result.get('component') != component
            or type(result.get('failures')) is not int or result['failures'] != 0):
        raise ValueError('Unexpected native transport preparation result: ' + stem)
    if stem == 'check_dma_native':
        expected = {'checks': 309, 'dma_checks': 30, 'dma_failures': 0,
                    'fault_cases': 21, 'cleanup_cases': 3, 'lifecycle_cycles': 64}
        if any(type(result.get(key)) is not int or result[key] != value
               for key, value in expected.items()):
            raise ValueError('The DMA stage/fault/recovery coverage changed.')
    elif stem == 'check_pci_transport_native':
        if result.get('checks') != 172 or result.get('interrupts_armed') is not False:
            raise ValueError('The read-only PCI/IRQ inventory contract changed.')
        require_true(result, ('malformed_capabilities', 'invalid_handles',
                              'bounded_config_reads', 'msix_geometry'),
                     'PCI malformed-input coverage')
    elif stem == 'check_firmware_native':
        if result.get('checks') != 349 or result.get('real_image_ready') is not False:
            raise ValueError('Synthetic firmware checks changed or claim a real image.')
        require_true(result, ('parser', 'rpc', 'layout', 'cleanup'),
                     'firmware parser/layout/RPC validation')
    elif stem == 'check_hardware_runtime_native':
        expected = {'foundation_checks': 23, 'caller_checks': 35,
                    'lifecycle_checks': 72, 'support_checks': 128}
        if any(result.get(key) != value for key, value in expected.items()):
            raise ValueError('The bundled startup no longer preserves all 258 v7 checks.')
        if (result.get('entrypoint') != 'S540NvidiaHardwareRuntime::checkIntegrated'
                or result.get('dma_mode') != 'provider_mapped'
                or result.get('dma_reason') != 'none'
                or result.get('dma_bytes') != 65536
                or result.get('dma_segments') != 16
                or result.get('pci_reason') != 'complete'
                or type(result.get('pci_capabilities')) is not int
                or result['pci_capabilities'] != 2
                or type(result.get('msi_vectors')) is not int
                or result['msi_vectors'] != 1
                or type(result.get('msix_vectors')) is not int
                or result['msix_vectors'] != 0
                or result.get('msi_observed_enabled') is not False
                or result.get('msix_observed_enabled') is not False):
            raise ValueError('The exact aggregate entry or native DMA geometry changed.')
        require_true(result, ('previous_blocks_passed', 'host_dma', 'pci_read_adapter',
                              'interrupt_inventory', 'firmware_parser', 'firmware_rpc',
                              'cleanup', 'acquired', 'reserve_cold_after',
                              'core_cold_after', 'os_objects_released'),
                     'bundled production startup')
    elif stem == 'check_hardware_faults_native':
        if (result.get('checks') != 47 or result.get('cross_stage_faults') != 7
                or result.get('workers') != 4
                or result.get('iterations_per_worker') != 8
                or type(result.get('completed_runs')) is not int
                or type(result.get('lease_refusals')) is not int
                or result['completed_runs'] < 1 or result['lease_refusals'] < 0
                or result['completed_runs'] + result['lease_refusals'] != 32
                or type(result.get('worker_errors')) is not int
                or result['worker_errors'] != 0):
            raise ValueError('The cross-stage transport failure coverage changed.')
        require_true(result, ('nested_lease_refusal', 'recovery', 'cleanup', 'cold_after'),
                     'cross-stage failure/refusal/recovery')
    if stem in ('check_hardware_runtime_native', 'check_hardware_faults_native'):
        activities = ('device_dma_verified', 'firmware_loaded', 'firmware_image_verified',
                      'interrupts_enabled', 'gpu_initialized', 'rm_initialized')
        if any(result.get(field) is not False for field in activities):
            raise ValueError('Native preparation claimed unimplemented GPU activity.')


def check(sdk: Path, destination: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS check host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the checked source.')
    sdk = sdk.resolve(strict=True)
    if transport.run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != transport.SDK_COMMIT:
        raise ValueError('The kernel SDK differs from its pinned revision.')
    provenance_test = SOURCE / 'tests/test_nvidia_firmware_provenance.py'
    tested = transport.run(sys.executable, str(provenance_test))
    print((tested.stdout + tested.stderr).strip())
    manifest = json.loads((SOURCE / 'firmware/PROVENANCE.json').read_text())
    if (manifest.get('commit') != NVIDIA_COMMIT
            or manifest.get('firmware_assets') != []
            or manifest.get('approved_image_hashes') != []
            or manifest.get('synthetic_fixture_only') is not True):
        raise ValueError('The selected firmware source/image readiness profile changed.')
    destination = destination.absolute()
    destination.mkdir(parents=True, exist_ok=True)
    report = destination / 'transport-preparation-checks.json'
    if report.exists():
        raise ValueError('The transport preparation check output already exists.')
    results = {}
    standalone = (
        ('check_dma_native', 'nvidia-dma-transport', 'src/S540NvidiaDma.cpp'),
        ('check_pci_transport_native', 'nvidia-pci-transport', 'src/S540NvidiaPci.cpp'),
        ('check_firmware_native', 'nvidia-firmware-transport',
         'firmware/S540NvidiaFirmware.cpp'),
    )
    aggregate = (
        ('check_hardware_runtime_native', 'nvidia-hardware-runtime'),
        ('check_hardware_faults_native', 'nvidia-hardware-faults'),
    )
    with tempfile.TemporaryDirectory(prefix='s540-nvidia-hardware-') as temporary:
        work = Path(temporary)
        for instrumented in (False, True):
            label = 'sanitized' if instrumented else 'native'
            flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer'] if instrumented else []
            for stem, component, source in standalone:
                binary = transport.compile_native_harness(
                    work, label + '-' + stem, SOURCE / ('tests/' + stem + '.cpp'),
                    flags, source_closure=([SOURCE / source], []))
                result = transport.native_check(binary)
                verify_result(result, stem, component)
                results[label + '/' + stem] = result
            for stem, component in aggregate:
                binary = transport.compile_native_harness(
                    work, label + '-' + stem, SOURCE / ('tests/' + stem + '.cpp'),
                    flags, with_preparation=True)
                result = transport.native_check(binary)
                verify_result(result, stem, component)
                results[label + '/' + stem] = result
    cpp_sources, c_sources = transport.full_sources()
    source_paths = {path for path in SOURCE.rglob('*') if path.is_file()
                    and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    source_paths.update(cpp_sources)
    source_paths.update(c_sources)
    source_paths.add(Path(__file__).resolve())
    source_paths.add(ROOT / 'builders/build_nvidia_transport.py')
    for path in source_paths:
        transport.plain(path)
    record = {
        'format': 1, 'component': 'nvidia-hardware-transport', 'version': '0.1.0',
        'status': 'passed', 'github_sha': commit, 'architecture': 'x86_64',
        'kernel_sdk_commit': transport.SDK_COMMIT, 'firmware_provenance': manifest,
        'native_execution': results,
        'production_source_closure': [p.relative_to(ROOT).as_posix()
                                      for p in [*cpp_sources, *c_sources]],
        'kernel_compile': 'not performed by this checker; required by the enclosing package build',
        'kernel_runtime': 'not_tested', 'interrupt_runtime': 'not_tested',
        'native_dma_backend': 'host allocation and deterministic operation-state emulation',
        'darwin_dma_backend': 'IOBufferMemoryDescriptor and IODMACommand; kernel runtime not tested by CI',
        'firmware_assets': [], 'real_firmware_ready': False,
        'gpu_dma_submission': False, 'interrupt_registration': False,
        'gpu_operations': 'none', 'full_resource_manager_integration': False,
        'source_sha256': {p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
                          for p in sorted(source_paths)},
    }
    report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    report.with_suffix('.json.sha256').write_text(sha(report.read_bytes()) + '  ' + report.name + '\n')
    print('Bundled NVIDIA transport preparation checks passed: ' + str(report))
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
        print('Transport preparation checks failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stdout or '')[-6000:] + (error.stderr or '')[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
