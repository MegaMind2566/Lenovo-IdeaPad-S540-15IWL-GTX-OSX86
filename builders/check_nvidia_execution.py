#!/usr/bin/env python3
"""Native checks for the combined global-RM/device/GSP execution milestone.

These checks exercise production CPU-side implementations and explicit native
backend fixtures. They never establish kernel IRQ, DMA, or GPU execution.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
SERVICE_NAMES = ('Platform', 'Sync', 'Work', 'Timer', 'Process', 'Runtime', 'Check', 'UserCopy')


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
        {'component': 'nvidia-darwin-services', 'checks': 167,
         'production_checks': 37, 'mutex_updates': 12000,
         'concurrent_work_items': 4000, 'fault_paths': 18, 'cleanup': True},
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


def original_header_case(output: Path, name: str, upstream: Path, namespace: Path,
                         c_sources: list[Path], cpp_sources: list[Path], expected: dict,
                         *, host_control: bool, dead_strip: bool = False,
                         extra_c_flags: list[str] | None = None,
                         extra_cpp_flags: list[str] | None = None,
                         arguments: list[str] | None = None) -> dict:
    """Compile actual original-header bridges with explicit userspace fixtures."""
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
        work = output / (name + '-' + label)
        work.mkdir(parents=True, exist_ok=True)
        objects = []
        for source in c_sources:
            obj = work / (source.stem + '.o')
            commands.run(*cc, *bridge, '-O1', '-g', *(extra_c_flags or []),
                          *(['-ffunction-sections', '-fdata-sections'] if dead_strip else []),
                          *instrumentation,
                          '-c', str(source), '-o', str(obj),
                          diagnostic_log=work / (source.stem + '-compile.log'))
            crypto.verify_binary(obj, 1, host_control)
            objects.append(str(obj))
        for source in cpp_sources:
            obj = work / (source.stem + '.o')
            commands.run(*cxx, *common, '-std=c++17', *(extra_cpp_flags or []),
                          *(['-ffunction-sections', '-fdata-sections'] if dead_strip else []),
                          *instrumentation,
                          '-c', str(source), '-o', str(obj),
                          diagnostic_log=work / (source.stem + '-compile.log'))
            crypto.verify_binary(obj, 1, host_control)
            objects.append(str(obj))
        binary = work / 'check'
        commands.run(*cxx, *common, *instrumentation, *objects,
                     *(['-Wl,--gc-sections' if host_control else '-Wl,-dead_strip'] if dead_strip else []),
                     '-o', str(binary),
                     diagnostic_log=work / 'link.log')
        crypto.verify_binary(binary, 2, host_control)
        record = json.loads(commands.run(str(binary), *(arguments or []),
                                        diagnostic_log=work / 'run.log').stdout)
        expect(record, {'format': 1, 'status': 'passed', 'failures': 0,
                       'execution': 'native-user-space', 'kernel_execution': 'not_tested',
                       'gpu_access': False, **expected}, name + '/' + label)
        results[label] = record
    return results


def timer_case(output: Path, upstream: Path, namespace: Path, *, host_control: bool) -> dict:
    return original_header_case(output, 'gsp-timers', upstream, namespace, [
        GSP / 'timers/S540NvidiaGspTimersOriginal.c',
        GSP / 'timers/tests/check_gsp_timers_native.c'], [
        SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES],
        {'component': 'nvidia-gsp-timers', 'checks': 34,
         'rc_callbacks': 1, 'nano_callbacks': 2, 'callback_fixture': True,
         'stack_abi_verified': True, 'quarantine_retention_verified': True, 'cleanup': True},
        host_control=host_control)


def central_policy_case(output: Path, upstream: Path, namespace: Path, *, host_control: bool) -> dict:
    return original_header_case(output, 'central-policy', upstream, namespace, [
        GLOBAL / 'src/S540NvidiaGlobalRmCentralPolicy.c',
        GLOBAL / 'src/S540NvidiaGlobalRmDiagnostics.c',
        GLOBAL / 'tests/check_central_policy_native.c'], [
        *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
        GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp', GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp'],
        {'component': 'nvidia-central-policy', 'checks': 16,
         'unavailable_runtime_pm_operations': 2, 'hot_remove_tripwire': True,
         'physical_feature_absence_inferred': False},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter', '-I', str(GLOBAL / 'src')])


def firmware_tables_case(output: Path, upstream: Path, namespace: Path, *, host_control: bool) -> dict:
    return original_header_case(output, 'firmware-tables', upstream, namespace, [
        GLOBAL / 'src/S540NvidiaGlobalRmFirmwareTables.c',
        GLOBAL / 'tests/check_firmware_tables_abi_native.c'], [
        GLOBAL / 'src/S540NvidiaGlobalRmFirmwareTablesBackend.cpp',
        GLOBAL / 'tests/check_firmware_tables_native.cpp'],
        {'component': 'nvidia-firmware-table-parser', 'checks': 54,
         'maximum_table_bytes': 4096, 'physical_firmware_read': False},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter', '-I', str(GLOBAL / 'src')],
        extra_cpp_flags=['-I', str(GLOBAL / 'src')])


def context_metadata_case(output: Path, upstream: Path, namespace: Path, *, host_control: bool) -> dict:
    return original_header_case(output, 'gsp-context-metadata', upstream, namespace, [
        ROOT / 'packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',
        DEVICE / 'src/S540NvidiaUnsupportedMemory.c',
        GLOBAL / 'src/S540NvidiaGlobalRmFeatureProfile.c',
        GLOBAL / 'src/S540NvidiaGlobalRmOs.c',
        GLOBAL / 'src/S540NvidiaGlobalRmDiagnostics.c',
        GSP / 'src/S540NvidiaGspContext.c',
        GSP / 'timers/S540NvidiaGspTimersOriginal.c',
        GSP / 'tests/check_context_metadata_native.c'], [
        DEVICE / 'src/S540NvidiaDeviceTransport.cpp', DEVICE / 'src/S540NvidiaDeviceServices.cpp',
        *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
        GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp', GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp'],
        {'component': 'nvidia-gsp-context-metadata', 'checks': 16, 'refusal_cases': 4,
         'provider_facts_fixture': True, 'original_rm_executed': False,
         'ownership_refusals_verified': True, 'cleanup': True},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter'])


def context_lifecycle_case(output: Path, upstream: Path, namespace: Path, *, host_control: bool) -> dict:
    return original_header_case(output, 'gsp-context-lifecycle', upstream, namespace, [
        ROOT / 'packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',
        DEVICE / 'src/S540NvidiaUnsupportedMemory.c',
        GLOBAL / 'src/S540NvidiaGlobalRmFeatureProfile.c',
        GLOBAL / 'src/S540NvidiaGlobalRmOs.c',
        GLOBAL / 'src/S540NvidiaGlobalRmDiagnostics.c',
        GSP / 'src/S540NvidiaGspContext.c',
        GSP / 'timers/S540NvidiaGspTimersOriginal.c',
        GSP / 'tests/check_context_lifecycle_native.c'], [
        DEVICE / 'src/S540NvidiaDeviceTransport.cpp', DEVICE / 'src/S540NvidiaDeviceServices.cpp',
        *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
        GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp', GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp'],
        {'component': 'nvidia-gsp-context-lifecycle', 'checks': 33,
         'real_timer_binding': True, 'recoverable_detach_refusals': 2,
         'original_rm_executed': False, 'callback_fixture': True, 'cleanup': True,
         'crypto_lifetime_refusals': 2},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter'])


def bootstrap_case(output: Path, upstream: Path, namespace: Path, assets: Path, *, host_control: bool) -> dict:
    return original_header_case(output, 'gsp-bootstrap-owner', upstream, namespace, [
        ROOT / 'packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',
        DEVICE / 'src/S540NvidiaUnsupportedMemory.c',
        GLOBAL / 'src/S540NvidiaGlobalRmFeatureProfile.c',
        GLOBAL / 'src/S540NvidiaGlobalRmOs.c',
        GLOBAL / 'src/S540NvidiaGlobalRmDiagnostics.c',
        DEVICE / 'tests/check_transport_policy_abi.c',
        GSP / 'src/S540NvidiaGspContext.c',
        GSP / 'timers/S540NvidiaGspTimersOriginal.c',
        GSP / 'cancellation/S540NvidiaGspCancellation.c',
        GSP / 'tests/check_bootstrap_boundary_native.c'], [
        GSP / 'src/S540NvidiaGspBootstrap.cpp',
        GSP / 'src/S540NvidiaGspDispatcher.cpp',
        GSP / 'platform/S540NvidiaGspPower.cpp',
        GSP / 'tests/check_bootstrap_native.cpp',
        GSP / 'src/S540NvidiaGspFirmware.cpp',
        ROOT / 'packages/nvidia-firmware-assets/src/S540NvidiaFirmwareAssets.cpp',
        ROOT / 'packages/nvidia-hardware-transport/firmware/S540NvidiaFirmware.cpp',
        DEVICE / 'src/S540NvidiaDeviceTransport.cpp', DEVICE / 'src/S540NvidiaDeviceServices.cpp',
        *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
        GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp', GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp'],
        {'component': 'nvidia-gsp-bootstrap-owner', 'checks': 89,
         'preparation_verified': True, 'cleanup_retry_verified': True,
         'platform_fixture': True, 'original_entry_tripwires': True,
         'real_context_store_transport_timers': True, 'original_rm_executed': False,
         'firmware_loaded': False, 'gpu_initialized': False,
         'persistent_worker_verified': True, 'pm_revocation_fixture': True,
         'ack_after_cleanup_verified': True, 'pm_hook_lifetime_verified': True},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter'],
        extra_cpp_flags=['-DS540_GSP_BOOTSTRAP_NATIVE_TEST'],
        arguments=[str(assets / 'gsp_tu10x.bin'), str(assets / 'ucodes_tu10x.bin')])


def registry_overlay_case(output: Path, upstream: Path, namespace: Path, *, host_control: bool) -> dict:
    spec = importlib.util.spec_from_file_location(
        's540_registry_overlay_source', GLOBAL / 'tests/registry_overlay_source.py')
    assert spec is not None and spec.loader is not None
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    header = source.prepare(upstream, output / 'registry-overlay-source')
    return original_header_case(output, 'registry-overlay', upstream, namespace, [
        GLOBAL / 'tests/check_registry_overlay_native.c'], [],
        {'component': 'nvidia-registry-overlay', 'checks': 13,
         'source_extracted_stages': True, 'registry_abi_fixture': True},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter', '-I', str(header.parent)])


def cancellation_record_case(output: Path, upstream: Path, namespace: Path, *, host_control: bool) -> dict:
    here = GSP / 'cancellation'
    return original_header_case(output, 'gsp-cancellation-record', upstream, namespace,
        [here / 'S540NvidiaGspCancellation.c'],
        [here / 'check_cancellation_native.cpp',
         *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES)],
        {'component': 'nvidia-gsp-cancellation', 'checks': 38,
         'concurrent_revocation_producers': 16, 'deadline_extension_refused': True,
         'cleanup_phase_distinct': True, 'original_entry_admission': False},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter'])


def original_cancellation_waits_case(output: Path, upstream: Path, namespace: Path,
                                     *, host_control: bool) -> dict:
    here = GSP / 'cancellation'
    spec = importlib.util.spec_from_file_location(
        's540_prospective_wait_source', here / 'prepare_wait_candidates.py')
    assert spec is not None and spec.loader is not None
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    proposed = output / 'prospective-cancellation-waits'
    source.prepare(upstream, proposed)
    return original_header_case(output, 'gsp-original-cancellation-waits', upstream, namespace,
        [here / 'S540NvidiaGspCancellation.c', here / 'S540NvidiaGspCancellationOriginal.c',
         here / 'check_original_wait_bodies.c'],
        [here / 'check_original_waits_native.cpp',
         *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES)],
        {'component': 'nvidia-gsp-original-wait-cancellation', 'checks': 40,
         'actual_original_wait_bodies': 4, 'revoked_during_wait': True,
         'hardware_cleanup_proven': False, 'original_entry_admission': False},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter',
                       '-I', str(here), '-I', str(proposed)])


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
    progress.component('host_allocation_domains', lambda: native_case(
        output, 'host-allocation-domains', [
            *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
            GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp'],
        GLOBAL / 'tests/check_host_domains_native.cpp',
        {'component': 'nvidia-host-domains', 'checks': 29,
         'wrong_domain_frees_retained': 2, 'concurrent_mixed_allocations': 768,
         'external_storage_preserved': True, 'cleanup': True}, host_control=host_control))
    progress.component('device_transport', lambda: native_case(output, 'device-transport', [
        DEVICE / ('src/S540Nvidia' + name + '.cpp') for name in
        ('DeviceTransport', 'DeviceServices', 'DeviceCheck')] + [
            DEVICE / 'tests/dma_stop_receipt_fixture.cpp'],
        DEVICE / 'tests/check_device_transport_native.cpp',
        {'component': 'nvidia-device-transport', 'checks': 474,
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
        {'component': 'nvidia-gsp-platform-parsers', 'checks': 62,
         'malformed_fixtures': 2048, 'hardware_queried': False},
        host_control=host_control))
    if upstream is None or namespace is None:
        raise ValueError('The exact upstream tree and generated namespace are required for original-header ABI checks.')
    progress.component('gsp_timers', lambda: timer_case(output, upstream, namespace, host_control=host_control))
    progress.component('gsp_context_metadata', lambda: context_metadata_case(
        output, upstream, namespace, host_control=host_control))
    progress.component('gsp_context_lifecycle', lambda: context_lifecycle_case(
        output, upstream, namespace, host_control=host_control))
    progress.component('memory_callbacks', lambda: original_header_case(
        output, 'memory-callbacks', upstream, namespace, [
            DEVICE / 'src/S540NvidiaUnsupportedMemory.c',
            DEVICE / 'tests/check_memory_callback_abi.c'], [
            DEVICE / 'src/S540NvidiaDeviceTransport.cpp',
            DEVICE / 'src/S540NvidiaDeviceServices.cpp',
            DEVICE / 'tests/dma_stop_receipt_fixture.cpp',
            DEVICE / 'tests/check_memory_callbacks_native.cpp'],
        {'component': 'nvidia-memory-callbacks', 'checks': 63,
         'guard_subprocesses': 9, 'linux_page_layouts_fabricated': False,
         'memory_operations_implemented': False},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('pci_pdi', lambda: original_header_case(
        output, 'pci-pdi', upstream, namespace, [
            DEVICE / 'tests/check_transport_policy_abi.c'], [
            DEVICE / 'src/S540NvidiaDeviceTransport.cpp',
            DEVICE / 'src/S540NvidiaDeviceServices.cpp',
            DEVICE / 'tests/dma_stop_receipt_fixture.cpp',
            DEVICE / 'tests/check_pci_pdi_native.cpp'],
        {'component': 'nvidia-pci-pdi', 'checks': 40,
         'maximum_capability_iterations': 480, 'hardware_pdi_read': False},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('global_diagnostics', lambda: original_header_case(
        output, 'global-diagnostics', upstream, namespace, [
            GLOBAL / 'src/S540NvidiaGlobalRmDiagnostics.c',
            GLOBAL / 'tests/check_diagnostics_native.c'], [
            GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp'],
        {'component': 'nvidia-global-diagnostics', 'checks': 37,
         'fatal_bug_checks': 2, 'actual_log_bytes_observed': True},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('global_host_services', lambda: original_header_case(
        output, 'global-host-services', upstream, namespace, [
            GLOBAL / 'src/S540NvidiaGlobalRmUserCopy.c',
            GLOBAL / 'src/S540NvidiaGlobalRmNvlink.c',
            GLOBAL / 'src/S540NvidiaGlobalRmBuildProfile.c',
            GLOBAL / 'tests/check_host_services_native.c'], [
            *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
            GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp',
            GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp',
            GLOBAL / 'tests/host_services_native_context.cpp'],
        {'component': 'nvidia-global-host-services', 'checks': 28,
         'real_os_copy': True, 'usercopy_kernel_execution': False,
         'fatal_endpoint_fixture': True, 'build_profile_verified': True, 'cleanup': True},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('global_system', lambda: original_header_case(
        output, 'global-system', upstream, namespace, [
            GLOBAL / 'src/S540NvidiaGlobalRmSystem.c',
            GLOBAL / 'tests/check_system_native.c'], [
            GLOBAL / 'src/S540NvidiaGlobalRmSystemBackend.cpp'],
        {'component': 'nvidia-global-system', 'checks': 18,
         'darwin_source_profile_user_map_limit': 140737486258176,
         'target_kernel_admission': False, 'nvidia_recycling_pool_bytes': 0},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('central_policy', lambda: central_policy_case(
        output, upstream, namespace, host_control=host_control))
    progress.component('firmware_tables', lambda: firmware_tables_case(
        output, upstream, namespace, host_control=host_control))
    progress.component('feature_profile', lambda: original_header_case(
        output, 'feature-profile', upstream, namespace, [
            GLOBAL / 'src/S540NvidiaGlobalRmFeatureProfile.c',
            GLOBAL / 'src/S540NvidiaGlobalRmOs.c',
            GLOBAL / 'src/S540NvidiaGlobalRmDiagnostics.c',
            GLOBAL / 'tests/check_feature_profile_native.c'], [
            *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
            GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp',
            GLOBAL / 'src/S540NvidiaGlobalRmFormat.cpp'],
        {'component': 'nvidia-feature-profile', 'checks': 55,
         'exact_original_headers': True, 'platform_device_fixture': True,
         'official_disabled_queries': True, 'unavailable_operations': 11,
         'fatal_ownership_tripwires': 4, 'cleanup': True},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('registry_profile', lambda: original_header_case(
        output, 'registry-profile', upstream, namespace, [
            GLOBAL / 'src/S540NvidiaGlobalRmRegistry.c',
            GLOBAL / 'src/S540NvidiaGlobalRmOs.c',
            GLOBAL / 'tests/check_registry_profile_native.c'], [],
        {'component': 'nvidia-registry-profile', 'checks': 62,
         'failure_stages': 8, 'rollback_refusals': 3,
         'original_registry_abi_fixture': True},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('registry_overlay', lambda: registry_overlay_case(
        output, upstream, namespace, host_control=host_control))
    progress.component('acpi_profile', lambda: original_header_case(
        output, 'acpi-profile', upstream, namespace, [
            GLOBAL / 'src/S540NvidiaGlobalRmAcpi.c',
            GLOBAL / 'tests/check_acpi_profile_native.c'], [
            *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES),
            GLOBAL / 'src/S540NvidiaGlobalRmHost.cpp'],
        {'component': 'nvidia-acpi-profile', 'checks': 21,
         'unsupported_methods': 6, 'observed_refusals': 7,
         'real_host_observer': True, 'rm_acpi_events_enabled': False},
        host_control=host_control, dead_strip=True,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter']))
    progress.component('gsp_dispatcher', lambda: native_case(
        output, 'gsp-dispatcher', [GSP / 'src/S540NvidiaGspDispatcher.cpp',
            *(SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp') for name in SERVICE_NAMES)],
        GSP / 'tests/check_dispatcher_native.cpp',
        {'component': 'nvidia-gsp-dispatcher', 'checks': 53,
         'stable_owner_thread': True, 'concurrent_sync_calls': 400,
         'queue_capacity': 16, 'shutdown_drain_verified': True, 'cleanup': True},
        host_control=host_control))
    progress.component('gsp_power_protocol', lambda: native_case(
        output, 'gsp-power-protocol', [GSP / 'platform/S540NvidiaGspPower.cpp'],
        GSP / 'platform/tests/check_power_native.cpp',
        {'component': 'nvidia-gsp-power-protocol', 'checks': 15,
         'pm_events_fixture': True, 'native_protocol_only': True,
         'power_domain_acquired': False}, dead_strip=True, host_control=host_control))
    progress.component('gsp_cancellation_record', lambda: cancellation_record_case(
        output, upstream, namespace, host_control=host_control))
    progress.component('gsp_original_cancellation_waits', lambda: original_cancellation_waits_case(
        output, upstream, namespace, host_control=host_control))
    progress.component('gsp_bootstrap_owner', lambda: bootstrap_case(
        output, upstream, namespace, assets, host_control=host_control))
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
                        help='Generated full RM header for explicit original-header CPU fixtures.')
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
