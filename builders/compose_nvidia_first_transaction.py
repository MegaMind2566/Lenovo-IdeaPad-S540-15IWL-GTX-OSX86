#!/usr/bin/env python3
"""Materialize one exact source-only first-transaction image input.

All original translation units use the composed headers. Optional compilation
produces development objects only; it never links, loads, enables or packages
the driver. The final linker must independently validate complete imports,
structor graphs, retained roots and target-kernel compatibility.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import struct
import sys

import build_nvidia_execution as execution
import compile_nvidia_global_rm as original
import nvidia_stack_usage as stack

ROOT = Path(__file__).resolve().parents[1]
GSP = ROOT / 'packages/nvidia-gsp-bootstrap'
FIRST = GSP / 'prospective-first-transaction'
LOCK = GSP / 'prospective-rm-lock-ownership'
GPU = GSP / 'prospective-work-gpu-binding'
LOADER = GSP / 'prospective-loader'
LOCK_EXPORTS = {'s540ProspectiveOriginalApiOwnership', 's540ProspectiveOriginalGpuOwnership'}
ORIGINAL_PROJECT_EXPORTS = LOCK_EXPORTS | {
    's540FirstTxnOriginalDescriptors', 's540FirstTxnOriginalDescriptorCount',
    's540FirstTxnObjDeleteChecked'}
ORIGINAL_PROJECT_OWNERS = {
    's540ProspectiveOriginalApiOwnership': 'src/nvidia/src/kernel/rmapi/rmapi.c',
    's540ProspectiveOriginalGpuOwnership': 'src/nvidia/src/kernel/core/locks.c',
    's540FirstTxnOriginalDescriptors': 'src/nvidia/arch/nvalloc/unix/src/osapi.c',
    's540FirstTxnOriginalDescriptorCount': 'src/nvidia/arch/nvalloc/unix/src/osapi.c',
    's540FirstTxnObjDeleteChecked': 'src/nvidia/src/libraries/nvoc/src/runtime.c'}
SOURCE_SUFFIXES = {'.c', '.cpp', '.h', '.hpp', '.inc'}
LIVE_ORIGINAL_DEFINITIONS = {
    'src/nvidia/arch/nvalloc/unix/src/vbioscall.c': {
        'S540_NVIDIA_NONPRIMARY_X86_EMULATION': '1'},
    'src/nvidia/src/kernel/rmapi/event_api.c': {'S540_NVIDIA_NO_OS_EVENT_BACKEND': '1'},
    'src/nvidia/src/kernel/rmapi/event_buffer.c': {'S540_NVIDIA_NO_OS_EVENT_BACKEND': '1'},
    'src/nvidia/src/kernel/gpu/mem_mgr/sem_surf.c': {'S540_NVIDIA_NO_OS_EVENT_BACKEND': '1'}}
CONTROL_UNIT = 'packages/nvidia-gsp-bootstrap/prospective-control-state/S540NvidiaControlState.c'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Composed source symlinks are not admitted: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                'sha256': sha(path), 'mode': '100755' if path.stat().st_mode & 0o111 else '100644'}
    return result


def tree_sha(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked_relative(value: str) -> Path:
    result = Path(value)
    if result.is_absolute() or '..' in result.parts or not result.parts or str(result) == '.':
        raise ValueError('Source inventory path must be a confined relative path: ' + value)
    return result


def new_output(output: Path, inputs: list[Path]) -> Path:
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError('Output symlinks are not admitted')
    output = output.resolve()
    for path in inputs:
        path = path.resolve(strict=True)
        if output.is_relative_to(path) or path.is_relative_to(output):
            raise ValueError('Output overlaps an input: ' + str(path))
    if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / 'build'):
        raise ValueError('Repository output is allowed only below build/')
    if output.exists():
        raise ValueError('A fresh composition output is required')
    return output


def apply_exact_successor(source: Path, manifest: Path) -> dict:
    """Optional explicit source successor; every changed input/output is pinned.

    Schema: {"format":1,"sources": {"relative.c": {"input_sha256":...,
    "output_sha256":...,"source":"relative-to-manifest.c"}}}. No gate fields
    are consumed. This is recorded source composition, not policy approval.
    """
    value = json.loads(manifest.read_text())
    if value.get('format') != 1 or not value.get('sources'):
        raise ValueError('An exact successor source manifest is required')
    changes = {}
    pending = []
    for relative, row in sorted(value['sources'].items()):
        target = source / checked_relative(relative)
        addition = manifest.parent / checked_relative(row['source'])
        if addition.is_symlink() or not addition.resolve(strict=True).is_relative_to(manifest.parent.resolve()):
            raise ValueError('Successor source escapes its manifest directory')
        if target.is_symlink() or sha(target) != row['input_sha256']:
            raise ValueError('Successor input differs: ' + relative)
        if sha(addition) != row['output_sha256']:
            raise ValueError('Successor output differs: ' + relative)
        pending.append((target, addition.read_bytes()))
        changes[relative] = {'input_sha256': row['input_sha256'], 'output_sha256': row['output_sha256']}
    for path, data in pending:
        path.write_bytes(data)
    return {'manifest_sha256': sha(manifest), 'sources': changes}


def copy_code(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('Project source symlink is not admitted: ' + str(path))
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def checked_contract(path: Path, groups: dict[str, Path]) -> dict:
    """Verify actual reviewed source bytes without rewriting their contracts."""
    value = json.loads(path.read_text())
    for group, root in groups.items():
        if not value.get(group):
            raise ValueError('Source contract requires nonempty hashes: ' + group)
        for relative, digest in value[group].items():
            source = root / checked_relative(relative)
            if source.is_symlink() or sha(source) != digest:
                raise ValueError('Fixed source contract changed: ' + str(source))
    return value


def original_source_flags(value: dict, relative: str) -> list[str]:
    """Allow the exact original feature macros only on their reviewed units."""
    profiles = value.get('fixed_source_profiles', {})
    expected = LIVE_ORIGINAL_DEFINITIONS if profiles.get('live_abi_closure') else {}
    if profiles.get('per_original_source_compile_definitions', {}) != expected:
        raise ValueError('Unreviewed per-original-source compile definitions')
    return ['-D' + name + '=' + definition
            for name, definition in sorted(expected.get(relative, {}).items())]


def fixed_profile_overlays(source: Path, project: Path, output: Path, *,
                           retained_diagnostic: bool, rc_participant: bool,
                           shutdown_protocol: bool, platform_closure: bool = False,
                           retained_backends: bool = False, global_epoch: bool = False,
                           live_abi_closure: bool = False,
                           upstream: Path | None = None) -> tuple[dict, dict]:
    """Compose selected real source successors; these flags grant no admission."""
    additions, edits, helpers, exports = {}, [], {}, {}
    private_exports, row_requirements, per_source_definitions = {}, {}, {}
    def replace_file(scope: str, relative: str, text: str, profile: str):
        root = source if scope == 'original' else project
        target = root / checked_relative(relative)
        before = sha(target) if target.is_file() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        edits.append({'scope': scope, 'source': relative, 'profile': profile,
                      'input_sha256': before, 'output_sha256': sha(target)})
    if rc_participant:
        directory = GSP / 'prospective-event-owner-policy'
        path = directory / 'prepare.py'
        helpers[path.relative_to(ROOT).as_posix()] = sha(path)
        rc = load('s540_composition_rc_prepare', path)
        # Exercise the actual parent's full freeze checks before taking its
        # fixed transforms onto the stronger GPU-bound generated inputs.
        rc.prepare(output / 'inputs/rc-parent')
        base = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/'
        for name, transform in [('S540NvidiaGspFirstTransaction.c', rc.record_overlay),
                                ('S540NvidiaGspFirstTransaction.h', rc.header_overlay)]:
            replace_file('project', base + name, transform((project / base / name).read_text()), 'rc-participant')
        timers = 'packages/nvidia-gsp-bootstrap/timers/S540NvidiaGspTimersOriginal.c'
        replace_file('project', timers, rc.timers_overlay((project / timers).read_text()), 'rc-participant')
        osapi = 'src/nvidia/arch/nvalloc/unix/src/osapi.c'
        replace_file('original', osapi, rc.original_policy_overlay((source / osapi).read_text()), 'rc-participant')
        probe = 'packages/nvidia-gsp-bootstrap/prospective-event-owner-policy/S540NvidiaFirstTxnRcOriginal.c'
        replace_file('project', probe, rc.RC_ORIGINAL, 'rc-participant')
        additions[probe] = 'original-c'
        exports['s540FirstTxnInspectOriginalRc'] = probe
    if retained_diagnostic:
        path = GSP / 'prospective-retained-diagnostic/prepare.py'
        helpers[path.relative_to(ROOT).as_posix()] = sha(path)
        retained = load('s540_composition_retained_prepare', path)
        names = [retained.RECORD, retained.HEADER, retained.HOST,
                 retained.RETENTION, retained.RETENTION_ORIGIN]
        before = {name: (project / name).read_text() for name in names}
        changed = retained.transforms(before)
        if set(changed) != set(names):
            raise ValueError('Retained diagnostic successor changed its exact source set')
        for relative, text in sorted(changed.items()):
            replace_file('project', relative, text, 'retained-diagnostic')
        exports['s540FirstTxnHostRetainDiagnostic'] = retained.RECORD
    for enabled, profile, directory_name, names in [
            (retained_backends, 'retained-backends', 'prospective-retained-backends',
             ['s540FirstTxnBackendBegin', 's540FirstTxnBackendEnd', 's540FirstTxnBackendBeginRelease']),
            (global_epoch, 'global-epoch', 'prospective-global-epoch',
             ['s540FirstTxnMasterIdentity', 's540FirstTxnGlobalReadMaster',
              's540FirstTxnGlobalGetSnapshot', 's540FirstTxnGlobalEnter',
              's540FirstTxnGlobalAbort', 's540FirstTxnGlobalOriginalReturned',
              's540FirstTxnGlobalValidated'])]:
        if not enabled:
            continue
        directory = GSP / directory_name
        for path in directory.rglob('*'):
            if path.is_file() and (path.suffix in SOURCE_SUFFIXES or path.suffix == '.py'):
                helpers[path.relative_to(ROOT).as_posix()] = sha(path)
        transform = load('s540_composition_' + profile.replace('-', '_'), directory / 'prepare.py')
        before = {name: (project / name).read_text() for name in transform.INPUTS}
        changed = transform.transforms(before)
        if set(changed) != set(before):
            raise ValueError('Fixed lifetime successor changed its exact source set: ' + profile)
        for relative, text in sorted(changed.items()):
            replace_file('project', relative, text, profile)
        exports.update({name: transform.RECORD for name in names})
    shutdown = None
    if shutdown_protocol:
        directory = GSP / 'prospective-shutdown-protocol'
        freeze = directory / 'FROZEN-SHA256.json'
        manifest = json.loads(freeze.read_text())
        expected = {row['path']: row['sha256'] for row in manifest['files']}
        observed = {path.relative_to(directory).as_posix() for path in directory.rglob('*')
            if path.is_file() and '__pycache__' not in path.parts and path.name != 'FROZEN-SHA256.json'}
        if observed != set(expected):
            raise ValueError('Shutdown successor full frozen file set changed')
        for relative, digest in expected.items():
            path = directory / checked_relative(relative)
            if path.is_symlink() or sha(path) != digest:
                raise ValueError('Shutdown successor frozen input changed: ' + relative)
        contract = json.loads((directory / 'SOURCE-CONTRACT.json').read_text())
        if sha(source / contract['gpu_source']) != contract['gpu_source_sha256']:
            raise ValueError('Shutdown successor requires its exact guarded original GPU source')
        if sha(FIRST / 'original/SOURCE-CONTRACT.json') != contract['first_transaction_source_contract_sha256']:
            raise ValueError('Shutdown successor original transaction contract changed')
        for name in ['S540NvidiaShutdownProtocol.c', 'S540NvidiaShutdownProtocol.h', 'SourceProfile.h']:
            relative = 'packages/nvidia-gsp-bootstrap/prospective-shutdown-protocol/' + name
            replace_file('project', relative, (directory / name).read_text(), 'shutdown-protocol')
        unit = 'packages/nvidia-gsp-bootstrap/prospective-shutdown-protocol/S540NvidiaShutdownProtocol.c'
        additions[unit] = 'original-c'
        exports['s540ShutdownProtocolRun'] = unit
        shutdown = {'freeze_sha256': sha(freeze), 'source_contract_sha256': sha(directory / 'SOURCE-CONTRACT.json'),
                    'whole_gpu_dma_stop_proven': False, 'physical_reclamation_authorized': False}
    platform = None
    if platform_closure:
        if upstream is None:
            raise ValueError('Platform callbacks require the verified actual original source tree')
        directory = GSP / 'prospective-platform-closure'
        contract_path = directory / 'SOURCE-CONTRACT.json'
        contract = json.loads(contract_path.read_text())
        callbacks = ['os_get_is_openrm', 'nv_dynamic_power_available', 'os_get_tegra_platform',
                     'nvlink_strcpy', 'nvlink_strlen', 'nvlink_strcmp', 'nvlink_get_platform_time']
        if contract.get('callbacks') != callbacks or contract.get('original_commit') != original.COMMIT:
            raise ValueError('Platform callback contract changed its exact original ABI selection')
        for group, root in [('source_sha256', directory), ('original_source_sha256', upstream),
                            ('repository_dependency_sha256', ROOT)]:
            for relative, digest in contract[group].items():
                path = root / checked_relative(relative)
                if path.is_symlink() or sha(path) != digest:
                    raise ValueError('Platform callback source contract changed: ' + relative)
        unit = 'packages/nvidia-gsp-bootstrap/prospective-platform-closure/S540ProspectivePlatformClosure.c'
        replace_file('project', unit, (directory / 'S540ProspectivePlatformClosure.c').read_text(), 'platform-closure')
        additions[unit] = 'original-c'
        private_exports.update({original.PREFIX + name: unit for name in callbacks})
        definitions = {'S540_NVIDIA_DARWIN_PLATFORM_CLOSURE': '1',
            'NV_SUPPORTS_PLATFORM_DEVICE': '0', 'NV_SUPPORTS_PLATFORM_DISPLAY_DEVICE': '0'}
        per_source_definitions[unit] = definitions
        row_requirements[unit] = {'compile_definitions': definitions,
            'expected_definitions': sorted(private_exports),
            'expected_imports': sorted(['s540GlobalRmRecordServiceName',
                's540GlobalRmRecordUnavailable', 's540Darwin_os_get_monotonic_time_ns_hr'])}
        platform = {'source_contract_sha256': sha(contract_path), 'original_callbacks': callbacks,
            'runtime_pm_available_macro': 'must remain absent; even a definition of zero is refused',
            'runtime_power_implemented': False, 'tegra_platform_implemented': False,
            'nvlink_hardware_implemented': False}
    live = None
    if live_abi_closure:
        if upstream is None:
            raise ValueError('Live ABI closure requires the actual original source tree')
        directory = GSP / 'prospective-live-abi-closure/nonprimary-x86'
        contract_path = directory / 'SOURCE-CONTRACT.json'
        nonprimary_contract_sha = sha(contract_path)
        contract = checked_contract(contract_path, {'source_sha256': directory,
            'original_source_sha256': upstream, 'project_source_sha256': ROOT})
        prepare = directory / 'prepare.py'
        helpers[prepare.relative_to(ROOT).as_posix()] = sha(prepare)
        emulation = load('s540_composition_nonprimary_x86', prepare)
        replace_file('original', emulation.SOURCE,
            emulation.overlay((source / emulation.SOURCE).read_text()), 'nonprimary-x86-emulation')
        mapping_directory = GSP / 'prospective-mapping-closure'
        mapping_guard = mapping_directory / 'profile_guard.py'
        helpers[mapping_guard.relative_to(ROOT).as_posix()] = sha(mapping_guard)
        mapping = load('s540_composition_mapping_guard', mapping_guard)
        mapping_profile = mapping.validate_profile(project)
        configurations = [
            ('prospective-uvm-disabled', 'UVM-DISABLED-CONTRACTS.json',
             'S540ProspectiveUvmDisabled.c',
             ['nv_schedule_uvm_isr', 'nv_schedule_uvm_drain_p2p', 'nv_schedule_uvm_resume_p2p'],
             {'S540_NVIDIA_NO_UVM_BACKEND': '1'},
             {'source_sha256': None, 'original_source_sha256': upstream}),
            ('prospective-mapping-closure', 'SOURCE-CONTRACT.json',
             'S540NvidiaMappingClosure.c',
             ['nv_acquire_mmap_lock', 'nv_release_mmap_lock',
              'nv_get_all_mappings_revoked_locked', 'nv_set_safe_to_mmap_locked', 'nv_revoke_gpu_mappings'],
             {'S540_NVIDIA_NO_USER_MAPPINGS': '1'}, {'source_sha256': None}),
            ('prospective-live-platform-closure', 'SOURCE-CONTRACT.json',
             'S540ProspectiveLivePlatformClosure.c',
             ['os_is_bif_reset_supported', 'os_allocate_temporary_file', 'os_close_file',
              'os_read_file', 'os_write_file', 'os_disable_console_access', 'os_enable_console_access'],
             {'S540_NVIDIA_LIVE_PLATFORM_CLOSURE': '1', 'S540_NVIDIA_MANUAL_ADAPTER_START': '1',
              'S540_NVIDIA_NO_FILE_BACKEND': '1', 'S540_NVIDIA_NO_NVIDIA_CONSOLE': '1'},
             {'source_sha256': None, 'original_source_sha256': upstream,
              'repository_dependency_sha256': ROOT}),
            ('prospective-control-state', 'SOURCE-CONTRACT.json', 'S540NvidiaControlState.c',
             ['nv_get_ctl_state', 'nv_get_dev_minor', 'nv_get_file_private',
              'nv_put_file_private', 'nv_post_event'],
             {'S540_NVIDIA_NO_CHARACTER_DEVICE': '1', 'S540_NVIDIA_NO_OS_EVENT_BACKEND': '1'},
             {'source_sha256': None, 'original_sha256': upstream, 'project_sha256': ROOT})]
        contracts = {}
        for name, contract_name, filename, callbacks, definitions, groups in configurations:
            directory = GSP / name
            contract_path = directory / contract_name
            module_contract = checked_contract(contract_path,
                {key: root or directory for key, root in groups.items()})
            unit = 'packages/nvidia-gsp-bootstrap/' + name + '/' + filename
            replace_file('project', unit, (directory / filename).read_text(), 'live-abi-closure')
            additions[unit] = 'original-c'
            expected = [original.PREFIX + callback for callback in callbacks]
            private_exports.update({symbol: unit for symbol in expected})
            if name == 'prospective-control-state':
                public = ['s540ControlStatePrepare', 's540ControlStateBindAdapter']
                exports.update({symbol: unit for symbol in public})
                expected += public
            per_source_definitions[unit] = definitions
            row_requirements[unit] = {'compile_definitions': definitions,
                'expected_definitions': sorted(expected)}
            if name == 'prospective-uvm-disabled':
                row_requirements[unit]['expected_imports'] = []
            elif name == 'prospective-mapping-closure':
                if module_contract['callbacks'] != callbacks:
                    raise ValueError('Mapping profile changed its exact original callbacks')
                row_requirements[unit]['expected_imports'] = sorted(module_contract['expected_imports'])
                row_requirements[unit]['allowed_compiler_memory_imports'] = module_contract['allowed_compiler_memory_imports']
            elif name == 'prospective-live-platform-closure':
                if module_contract['callbacks'] != callbacks:
                    raise ValueError('Live platform profile changed its exact original callbacks')
                row_requirements[unit]['expected_imports'] = sorted([
                    's540FirstTxnGetSnapshot', 's540GlobalRmRecordServiceName',
                    's540GlobalRmRecordUnavailable', original.PREFIX + 'os_bug_check'])
                # Apple Clang lowers the original zero-initialized snapshot to
                # __bzero; LLVM's cross target can inline those same stores.
                # This is a public memory helper, never a private RM callback.
                row_requirements[unit]['allowed_compiler_memory_imports'] = ['__bzero']
            contracts[name] = sha(contract_path)
        row_requirements[CONTROL_UNIT]['original_include_directories'] = ['src/nvidia/src/libraries']
        live = {'source_contract_sha256': contracts,
            'nonprimary_source_contract_sha256': nonprimary_contract_sha,
            'mapping_profile': mapping_profile, 'primary_emulation_implemented': False,
            'control_event_ingress': {
                'original_osapi_source': 'src/nvidia/arch/nvalloc/unix/src/osapi.c',
                'original_osapi_source_sha256': sha(upstream / 'src/nvidia/arch/nvalloc/unix/src/osapi.c'),
                'composed_osapi_source_sha256': sha(source / 'src/nvidia/arch/nvalloc/unix/src/osapi.c'),
                'sole_control_event_insertion_function': 'allocate_os_event',
                'original_user_dispatcher': 'rm_ioctl',
                'original_ioctl': 'NV_ESC_ALLOC_OS_EVENT',
                'private_user_dispatcher_exposed_by_loader': False,
                'final_dead_strip_dispatcher_absence_requires_independent_link_check': True},
            'user_mapping_ingress': False, 'file_descriptor_registration': False,
            'os_event_delivery': False, 'runtime_pm_implemented': False}
    for name, digest in helpers.items():
        if sha(ROOT / name) != digest:
            raise ValueError('A fixed source-profile helper changed during composition: ' + name)
    return additions, {'retained_diagnostic': retained_diagnostic, 'rc_participant': rc_participant,
        'shutdown_protocol': shutdown_protocol, 'platform_closure': platform_closure,
        'retained_backends': retained_backends, 'global_epoch': global_epoch,
        'live_abi_closure': live_abi_closure,
        'transform_helper_sha256': helpers,
        'exact_source_replacements': edits, 'additional_project_exports': exports,
        'additional_private_original_exports': private_exports,
        'source_row_requirements': row_requirements,
        'per_source_compile_definitions': per_source_definitions,
        'per_original_source_compile_definitions': LIVE_ORIGINAL_DEFINITIONS if live_abi_closure else {},
        'shutdown_source_profile': shutdown,
        'platform_source_profile': platform,
        'live_abi_source_profile': live,
        'required_compile_definitions': {'S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE': '1'},
        'original_entry_admission': False, 'hardware_admission': False,
        'final_release_issued': False, 'stop_receipt_issued': False}


def materialize(upstream: Path, v3_root: Path, namespace: Path, output: Path,
                *, successor_manifest: Path | None = None,
                project_successor_manifest: Path | None = None,
                retained_diagnostic: bool = False, rc_participant: bool = False,
                shutdown_protocol: bool = False, platform_closure: bool = False,
                retained_backends: bool = False, global_epoch: bool = False,
                live_abi_closure: bool = False) -> dict:
    if retained_backends and not retained_diagnostic:
        raise ValueError('Retained backends require the exact retained diagnostic Host')
    if global_epoch and not (retained_diagnostic and retained_backends):
        raise ValueError('Global epoch requires retained diagnostic Host and backends')
    if live_abi_closure and not all([retained_diagnostic, rc_participant, shutdown_protocol,
                                   platform_closure, retained_backends, global_epoch]):
        raise ValueError('Live ABI closure requires all four fixed profiles, retained backends and global epoch')
    upstream = original._pinned_upstream(upstream)
    v3_root, namespace = v3_root.resolve(strict=True), namespace.resolve(strict=True)
    inputs = [upstream, v3_root, namespace, GSP, ROOT / 'packages/nvidia-global-rm',
              ROOT / 'packages/nvidia-darwin-services', ROOT / 'packages/nvidia-device-transport']
    if successor_manifest:
        successor_manifest = successor_manifest.resolve(strict=True)
        inputs.append(successor_manifest.parent)
    if project_successor_manifest:
        if any([retained_diagnostic, rc_participant, shutdown_protocol, platform_closure,
                retained_backends, global_epoch, live_abi_closure]):
            raise ValueError('Fixed source profiles and an arbitrary project successor require separate compositions')
        project_successor_manifest = project_successor_manifest.resolve(strict=True)
        inputs.append(project_successor_manifest.parent)
    output = new_output(output, inputs)
    expected_namespace = json.loads((ROOT / 'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    if sha(namespace) != expected_namespace['namespace_sha256']:
        raise ValueError('The baseline private namespace differs from its frozen bytes')
    gpu = load('s540_composition_gpu_prepare', GPU / 'prepare.py')
    gpu.parent_guard()
    lock = load('s540_composition_lock_prepare', LOCK / 'prepare.py')
    host = load('s540_composition_retention_prepare', GSP / 'prospective-host-retention/prepare_heap_retention.py')
    output.mkdir(parents=True)
    # Both helpers verify the complete immutable V3 inventory, independently.
    lock_record = lock.prepare(upstream, v3_root / 'source', output / 'inputs/rm-lock')
    work = gpu.prepare(upstream, v3_root, output / 'inputs/work-gpu')
    host_root = output / 'inputs/retention'
    host_root.mkdir(parents=True)
    host_record = host.prepare(ROOT, host_root)
    source = output / 'source'
    shutil.copytree(work['base_source'], source)
    replaced = {}
    event_profile = None
    if live_abi_closure:
        directory = GSP / 'prospective-os-event-policy'
        contract = checked_contract(directory / 'OS-EVENT-POLICY-CONTRACTS.json',
            {'source_sha256': directory, 'base_sources_sha256': source,
             'supporting_original_source_sha256': upstream})
        event = load('s540_composition_os_event_prepare', directory / 'prepare_event_policy.py')
        event_profile = event.prepare(v3_root / 'source', output / 'inputs/os-event-policy')
        if event_profile['proposed_source_sha256'] != contract['proposed_source_sha256']:
            raise ValueError('The exact three original OS-event guards changed')
        for relative, digest in sorted(contract['proposed_source_sha256'].items()):
            target = source / relative
            before = sha(target)
            shutil.copyfile(output / 'inputs/os-event-policy/source' / relative, target)
            if sha(target) != digest:
                raise ValueError('The original OS-event successor source changed')
            replaced[relative] = [{'layer': 'os-event-policy', 'input_sha256': before,
                                   'output_sha256': digest}]
    for label, directory in [('first-transaction', work['parent_source']),
                             ('work-gpu-binding', work['source']),
                             ('rm-lock-ownership', output / 'inputs/rm-lock')]:
        for path in sorted(directory.rglob('*.c')):
            relative = path.relative_to(directory).as_posix()
            if not relative.startswith('src/'):
                continue
            target = source / checked_relative(relative)
            before = sha(target)
            shutil.copyfile(path, target)
            replaced.setdefault(relative, []).append({'layer': label, 'input_sha256': before,
                                                      'output_sha256': sha(target)})
    successor = apply_exact_successor(source, successor_manifest) if successor_manifest else None
    if event_profile:
        for relative, digest in event_profile['proposed_source_sha256'].items():
            if sha(source / relative) != digest:
                raise ValueError('A later source layer replaced the mandatory OS-event guard')
    # Keep project-relative includes real: use a complete code/header companion,
    # then replace one source per canonical path rather than appending objects.
    project = output / 'project'
    names = ['nvidia-global-rm/src', 'nvidia-global-rm-crypto/src',
             'nvidia-darwin-services/src', 'nvidia-device-transport/src',
             'nvidia-gsp-bootstrap/src', 'nvidia-gsp-bootstrap/platform',
             'nvidia-gsp-bootstrap/evidence', 'nvidia-gsp-bootstrap/timers',
             'nvidia-gsp-bootstrap/cancellation',
             'nvidia-gsp-bootstrap/prospective-first-transaction/original',
             'nvidia-gsp-bootstrap/prospective-first-transaction/record',
             'nvidia-gsp-bootstrap/prospective-first-transaction/services',
             'nvidia-gsp-bootstrap/prospective-host-retention',
             'nvidia-gsp-bootstrap/prospective-rm-lock-ownership',
             'nvidia-gsp-bootstrap/prospective-loader',
             'nvidia-hardware-transport/src', 'nvidia-hardware-transport/firmware',
             'nvidia-firmware-assets/src', 'nvidia-os-adapter/upstream/include']
    if platform_closure:
        names.append('nvidia-gsp-bootstrap/prospective-platform-closure')
    if live_abi_closure:
        names += ['nvidia-gsp-bootstrap/' + name for name in [
            'prospective-uvm-disabled', 'prospective-mapping-closure',
            'prospective-control-state', 'prospective-live-platform-closure']]
    for name in names:
        copy_code(ROOT / 'packages' / name, project / 'packages' / name)
    # V3 owns checked cancellation and timer declarations, before stronger ports.
    copy_code(v3_root / 'project-overlay', project)
    copy_code(host_root / 'packages', project / 'packages')
    canonical = {
        'S540NvidiaDarwinWork.cpp': 'packages/nvidia-darwin-services/src',
        'S540NvidiaDarwinTimer.cpp': 'packages/nvidia-darwin-services/src',
        'S540NvidiaGspTimersOriginal.c': 'packages/nvidia-gsp-bootstrap/timers',
        'S540NvidiaGspTimers.h': 'packages/nvidia-gsp-bootstrap/timers',
        'S540NvidiaGspContext.c': 'packages/nvidia-gsp-bootstrap/src',
        'S540NvidiaGspFirstTransaction.c': 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        'S540NvidiaGspFirstTransaction.h': 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        'S540NvidiaGspFirstTransactionOriginal.c': 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original',
        'S540NvidiaGspFirstTransactionOriginal.h': 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original'}
    for directory in [work['services'], work['project']]:
        for name, relative in canonical.items():
            path = directory / name
            if path.is_file():
                shutil.copyfile(path, project / relative / name)
    # The strong record consumes actual participant leases. Its frozen complete
    # cancellation implementation replaces the baseline implementation once;
    # compiling both would duplicate its existing cancellation ABI exports.
    participants = FIRST / 'record/deps/S540NvidiaGspCancellation.c'
    shutil.copyfile(participants,
        project / 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c')
    fixed_additions, profiles = fixed_profile_overlays(source, project, output,
        retained_diagnostic=retained_diagnostic, rc_participant=rc_participant,
        shutdown_protocol=shutdown_protocol, platform_closure=platform_closure,
        retained_backends=retained_backends, global_epoch=global_epoch,
        live_abi_closure=live_abi_closure, upstream=upstream)
    profiles['os_event_source_profile'] = event_profile
    if live_abi_closure:
        profiles['live_abi_source_profile']['control_event_ingress'].update({
            'exact_guarded_original_source_sha256': event_profile['proposed_source_sha256'],
            'os_event_source_contract_sha256': sha(
                GSP / 'prospective-os-event-policy/OS-EVENT-POLICY-CONTRACTS.json')})
    project_successor = (apply_exact_successor(project, project_successor_manifest)
                         if project_successor_manifest else None)
    cpp, c, plain = execution.project_sources()
    rows = {p.relative_to(ROOT).as_posix(): ('cpp' if p in cpp else 'original-c' if p in c else 'plain-c')
            for p in [*cpp, *c, *plain]}
    additions = {
        'packages/nvidia-hardware-transport/src/S540NvidiaPci.cpp': 'cpp',
        'packages/nvidia-hardware-transport/firmware/S540NvidiaFirmware.cpp': 'cpp',
        'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellationOriginal.c': 'original-c',
        'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c': 'plain-c',
        'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original/S540NvidiaGspFirstTransactionOriginal.c': 'original-c',
        'packages/nvidia-gsp-bootstrap/prospective-first-transaction/services/S540NvidiaFirstTxnServices.cpp': 'cpp',
        'packages/nvidia-gsp-bootstrap/prospective-rm-lock-ownership/S540ProspectiveRmLockOwnership.c': 'original-c',
        'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderState.c': 'plain-c',
        'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp': 'cpp',
        'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKmod.cpp': 'cpp',
        'packages/nvidia-gsp-bootstrap/prospective-loader/roots/S540NvidiaGspOriginalRoots.c': 'original-c'}
    if set(rows) & set(additions):
        raise ValueError('An additional project translation unit duplicates a production source')
    rows.update(additions)
    if set(rows) & set(fixed_additions):
        raise ValueError('A fixed profile duplicates an existing translation unit')
    rows.update(fixed_additions)
    original_files = inventory(source)
    if len(original_files) != 4005:
        raise ValueError('The composed original source inventory must retain exactly 4005 files')
    ns = output / 'S540ComposedNamespace.h'
    private = json.loads((GSP / 'prospective-v2/PROSPECTIVE-SOURCE-PROFILE.json').read_text())['new_original_private_names']
    ns.write_text(namespace.read_text() + '\n/* Exact V2/V3 additional original aliases. */\n' +
                  ''.join('#define ' + key + ' ' + value + '\n' for key, value in sorted(private.items())))
    report = {'format': 1, 'status': 'materialized-source-only', 'source': 'source', 'project': 'project',
        'namespace': ns.name, 'namespace_sha256': sha(ns), 'baseline_namespace_sha256': sha(namespace),
        'original_files': original_files, 'original_tree_sha256': tree_sha(original_files),
        'original_file_count': len(original_files), 'replacement_history': replaced,
        'project_files': inventory(project), 'project_translation_units': [
            {'source': relative, 'kind': kind, 'sha256': sha(project / relative),
             **profiles['source_row_requirements'].get(relative, {})}
            for relative, kind in sorted(rows.items())],
        'inputs': {'v3_tree_sha256': lock_record['v3_tree_sha256'],
            'gpu_source_manifest_sha256': sha(output / 'inputs/work-gpu/source-manifest.json'),
            'lock_source_manifest_sha256': sha(output / 'inputs/rm-lock/prepared-source.json'),
            'retention_source_manifest_sha256': sha(host_root / 'source-manifest.json')},
        'participant_cancellation_source_sha256': sha(participants),
        'successor': successor, 'project_successor': project_successor,
        'fixed_source_profiles': profiles,
        'new_original_private_names': private,
        'original_entry_admission': False, 'production_candidate_allowed': False,
        'hardware_admission': False, 'kernel_execution': 'not_tested', 'gpu_access': False,
        'final_link': 'not_performed', 'original_full_compilation': 'not_performed'}
    write_json(output / 'composition.json', report)
    return report


def verify_composition(output: Path) -> dict:
    value = json.loads((output / 'composition.json').read_text())
    if value.get('format') != 1 or value.get('status') != 'materialized-source-only':
        raise ValueError('A complete source-only composition is required')
    for field, expected in {'original_entry_admission': False, 'production_candidate_allowed': False,
            'hardware_admission': False, 'kernel_execution': 'not_tested', 'gpu_access': False}.items():
        if type(value.get(field)) is not type(expected) or value[field] != expected:
            raise ValueError('Source composition cannot grant runtime admission: ' + field)
    for field, directory in [('original_files', 'source'), ('project_files', 'project')]:
        if inventory(output / directory) != value[field]:
            raise ValueError('Composed input inventory changed: ' + directory)
    if sha(output / value['namespace']) != value['namespace_sha256']:
        raise ValueError('Composed namespace changed')
    # This also refuses unknown macro names/units before any compiler executes.
    original_source_flags(value, '')
    return value


def include_flags(output: Path) -> list[str]:
    project = output / 'project/packages'
    directories = [project / name for name in [
        'nvidia-gsp-bootstrap/prospective-first-transaction/original',
        'nvidia-gsp-bootstrap/prospective-first-transaction/record',
        'nvidia-gsp-bootstrap/prospective-first-transaction/record/deps',
        'nvidia-gsp-bootstrap/prospective-first-transaction/services',
        'nvidia-gsp-bootstrap/prospective-rm-lock-ownership',
        'nvidia-gsp-bootstrap/cancellation', 'nvidia-gsp-bootstrap/timers',
        'nvidia-gsp-bootstrap/src', 'nvidia-global-rm/src', 'nvidia-global-rm-crypto/src',
        'nvidia-device-transport/src', 'nvidia-darwin-services/src', 'nvidia-os-adapter/upstream/include']]
    return [flag for directory in directories for flag in ['-I', str(directory)]]


def verify_compiled_rows(rows: list[dict], directory: Path) -> None:
    dependencies = {}
    for row in rows:
        obj = directory / checked_relative(row['object'])
        if obj.is_symlink() or sha(obj) != row['object_sha256']:
            raise ValueError('Compiled object changed: ' + row['object'])
        for path, digest in row['dependency_sha256'].items():
            if dependencies.setdefault(path, digest) != digest:
                raise ValueError('An input changed between compile actions: ' + path)
    for path, digest in dependencies.items():
        dependency = Path(path)
        if dependency.is_symlink() or sha(dependency) != digest:
            raise ValueError('A compile dependency changed: ' + path)


def definition_strength(path: Path) -> dict[str, str]:
    """Preserve original Mach-O weak overrides; never equate them to strong."""
    original.macho_symbols(path)
    data = path.read_bytes()
    position, table = 32, None
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, position)
        if command == 2:
            table = struct.unpack_from('<4I', data, position + 8)
        position += size
    if table is None:
        return {}
    symbols, count, strings, string_size = table
    result = {}
    for index in range(count):
        name, kind, _, description, value = struct.unpack_from('<IBBHQ', data, symbols + index * 16)
        if kind & 0xe0 or not kind & 1 or not name or (kind & 0x0e == 0 and value == 0):
            continue
        end = data.index(b'\0', strings + name, strings + string_size)
        spelling = data[strings + name:end].decode().removeprefix('_')
        if spelling in result:
            raise ValueError('Duplicate external nlist definition within one object: ' + spelling)
        result[spelling] = 'weak' if description & 0x80 else 'strong'
    return result


def original_definition_owners(rows: list[dict], directory: Path) -> tuple[dict, dict]:
    strong, weak = {}, {}
    for row in sorted(rows, key=lambda entry: entry['source']):
        actual = definition_strength(directory / checked_relative(row['object']))
        if set(actual) != set(row['definitions']):
            raise ValueError('Exact original definition strength inventory differs')
        row['weak_definitions'] = sorted(name for name, strength in actual.items() if strength == 'weak')
        for name, strength in actual.items():
            if strength == 'weak':
                weak.setdefault(name, []).append(row['source'])
            else:
                if name in strong:
                    raise ValueError('Duplicate strong original definition: ' + name)
                strong[name] = row['source']
    owners = {name: entries[0] for name, entries in weak.items()}
    owners.update(strong)
    for name, owner in ORIGINAL_PROJECT_OWNERS.items():
        if strong.get(name) != owner:
            raise ValueError('An exact strong original project export moved or is missing: ' + name)
    return owners, weak


def composed_bridge_flags(upstream: Path, output: Path, compiler: Path) -> list[str]:
    """Use the real original build ABI with every original header composed."""
    value = verify_composition(output)
    if value.get('fixed_source_profiles', {}).get('live_abi_closure'):
        guard = load('s540_compile_mapping_profile_guard',
                     GSP / 'prospective-mapping-closure/profile_guard.py')
        guard.validate_profile(output / 'project')
    row = original.original_commands(upstream, output / 'bridge-profile', compiler)[0]
    source_root = output / 'source/src/nvidia'
    flags, index = row[1:row.index('-c')], 0
    result = []
    while index < len(flags):
        flag = flags[index]
        result.append(flag)
        if flag in {'-I', '-include'}:
            index += 1
            path = Path(flags[index])
            if path.is_absolute():
                raise ValueError('Unexpected absolute original header path')
            result.append(str((source_root / path).resolve(strict=flag == '-include')))
        index += 1
    return [*result, '-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__',
        '-DNV_VERSION_STRING="615.78.08"', '-include', str(output / value['namespace']),
        *include_flags(output)]


def verify_fixed_project_symbols(row: dict, defined: set[str], imports: set[str]) -> set[str]:
    allowed = set(row.get('allowed_compiler_memory_imports', []))
    if not allowed <= original.COMPILER_MEMORY_IMPORTS:
        raise ValueError('Unreviewed compiler memory import allowance: ' + row['source'])
    compiler_imports = imports & allowed
    expected_definitions = set(row.get('expected_definitions', defined))
    expected_imports = set(row.get('expected_imports', imports - compiler_imports))
    unexpected_definitions = defined - expected_definitions
    missing_definitions = expected_definitions - defined
    unexpected_imports = imports - compiler_imports - expected_imports
    missing_imports = expected_imports - imports
    if unexpected_definitions or missing_definitions or unexpected_imports or missing_imports:
        raise ValueError('A fixed source profile changed its exact compiled exports/imports: ' +
            row['source'] + '; missing definitions=' + str(sorted(missing_definitions)) +
            '; unexpected definitions=' + str(sorted(unexpected_definitions)) +
            '; missing imports=' + str(sorted(missing_imports)) +
            '; unexpected imports=' + str(sorted(unexpected_imports)))
    return compiler_imports


def compile_project_objects(upstream: Path, output: Path, cc: Path, cxx: Path,
                            kernel_flags: list[str], cpp_flags: list[str],
                            *, host_control: bool) -> dict:
    """Compile the actual composed bridge/source inventory; no link or fixtures.

    The caller supplies its independently verified SDK kernel flags and records
    SDK identity. This helper does not turn an arbitrary include path into an
    SDK provenance claim. Source rows select one exact canonical implementation.
    """
    sys.path.insert(0, str(FIRST / 'original'))
    import common
    cc, cxx = common.compiler(str(cc)), common.compiler(str(cxx))
    identity = common.execution_identity(cc, cxx, host_control)
    identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
    upstream = original._pinned_upstream(upstream)
    output = output.resolve(strict=True)
    value = verify_composition(output)
    objects = output / 'project-objects'
    if objects.exists():
        raise ValueError('Project compilation requires a fresh objects directory')
    objects.mkdir()
    bridge = composed_bridge_flags(upstream, output, cc)
    target = (['-target', 'x86_64-apple-macos15'] if host_control else
              ['-arch', 'x86_64', '-mmacosx-version-min=15.0'])
    rows = []
    report = {'format': 1, 'status': 'running', **identity,
        'composition_sha256': sha(output / 'composition.json'), 'results': rows,
        'original_entry_admission': False, 'production_candidate_allowed': False,
        'kernel_execution': 'not_tested', 'gpu_access': False, 'final_link': 'not_performed',
        'sdk_identity': 'caller-owned; flags alone do not prove SDK identity'}
    path = output / 'project-compilation.json'
    write_json(path, report)
    try:
        for index, row in enumerate(value['project_translation_units']):
            source = output / 'project' / row['source']
            obj = objects / ('project-%03d-' % index + source.stem + '.o')
            if row['kind'] == 'original-c':
                compiler = cc
                flags = [*bridge, *target, '-mkernel', '-DKERNEL', '-D__KERNEL__',
                         '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1']
            elif row['kind'] == 'plain-c':
                compiler, flags = cc, [*kernel_flags, '-std=c11', *include_flags(output)]
            elif row['kind'] == 'cpp':
                compiler, flags = cxx, [*kernel_flags, *execution.kernel_cpp_flags(cpp_flags), *include_flags(output)]
            else:
                raise ValueError('Unknown source kind: ' + str(row['kind']))
            if row.get('compile_definitions'):
                expected = value.get('fixed_source_profiles', {}).get(
                    'per_source_compile_definitions', {}).get(row['source'])
                if row['compile_definitions'] != expected:
                    raise ValueError('Unreviewed per-source compile definitions')
                flags += ['-D' + name + '=' + definition
                          for name, definition in sorted(row['compile_definitions'].items())]
            if row.get('original_include_directories'):
                if row['source'] != CONTROL_UNIT or row['original_include_directories'] != ['src/nvidia/src/libraries']:
                    raise ValueError('Unreviewed per-source original include directories')
                for relative in row['original_include_directories']:
                    flags += ['-I', str(output / 'source' / checked_relative(relative))]
            dep = obj.with_suffix('.d')
            command = [str(compiler), *flags, '-Wframe-larger-than=4096',
                '-Werror=frame-larger-than', '-fstack-usage', '-MD', '-MF', str(dep),
                '-c', str(source), '-o', str(obj)]
            original.execute(command, cwd=output / 'project', timeout=300,
                             diagnostic_log=obj.with_suffix('.log'))
            allowed = row['source'] in {
                'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp',
                'packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp'}
            defined, imports, sections = original.macho_symbols(obj, reviewed_project_initializers=allowed)
            compiler_imports = verify_fixed_project_symbols(row, defined, imports)
            dependencies = {}
            for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
                dependency = Path(name)
                dependency = ((output / 'project' / dependency).resolve(strict=True)
                              if not dependency.is_absolute() else dependency.resolve(strict=True))
                if dependency.is_relative_to(upstream) or dependency.is_relative_to(ROOT / 'packages'):
                    raise ValueError('A raw source/header escaped composed companion: ' + str(dependency))
                dependencies[str(dependency)] = sha(dependency)
            rows.append({**row, 'object': obj.name, 'object_sha256': sha(obj),
                'definitions': sorted(defined), 'imports': sorted(imports), 'sections': sections,
                'compiler_memory_imports': sorted(compiler_imports),
                'command': command, 'cwd': str(output / 'project'),
                'dependency_sha256': dependencies,
                'stack_usage': stack.capture_usage(source, obj, command,
                    cwd=output / 'project', native_apple=not host_control)})
            write_json(path, report)
        verify_composition(output)
        verify_compiled_rows(rows, objects)
        report.update(status='compiled-project-source-only', project_objects=len(rows),
            stack_usage=stack.usage_manifest([row['stack_usage'] for row in rows], output / 'project-stack-usage-manifest.json'))
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write_json(path, report)
    return report


def finalize_original_compilation(output: Path, report: dict | None = None) -> dict:
    """Recheck exact compiled bytes, including real weak/strong attribution.

    This may re-run validation after a validator correction without replacing
    compiled input bytes. A partial or failed compiler matrix is never accepted.
    """
    output = output.resolve(strict=True)
    destination = output / 'full-original-compilation.json'
    report = report if report is not None else json.loads(destination.read_text())
    rows, objects = report['results'], output / 'original-objects'
    try:
        for field, expected in {'original_entry_admission': False, 'hardware_admission': False,
                'production_candidate_allowed': False, 'kernel_execution': 'not_tested', 'gpu_access': False}.items():
            if type(report.get(field)) is not type(expected) or report[field] != expected:
                raise ValueError('Compilation report changed its source-only scope: ' + field)
        if report.get('failures') or len(rows) != 1100 or len({row['source'] for row in rows}) != 1100:
            raise ValueError('A complete successful 1100-source compiler matrix is required')
        if report['composition_sha256'] != sha(output / 'composition.json'):
            raise ValueError('The complete compilation composition identity changed')
        for row in rows:
            path = (objects / 'g_nvid_string.c' if row['source'] == 'generated/g_nvid_string.c'
                    else output / 'source' / checked_relative(row['source']))
            if sha(path) != row['source_sha256']:
                raise ValueError('A compiled source changed: ' + row['source'])
        verify_composition(output)
        verify_compiled_rows(rows, objects)
        definitions, weak = original_definition_owners(rows, objects)
        rows.sort(key=lambda row: row['source'])
        report.update(status='compiled-full-original-source-only', original_objects=1100,
            definition_owners=definitions, weak_definition_sources=weak,
            exact_definition_strength_verified=True, final_link='not_performed',
            stack_usage=stack.usage_manifest([row['stack_usage'] for row in rows], output / 'stack-usage-manifest.json'))
        report.pop('error', None)
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write_json(destination, report)
    return report


def compile_original_subset(upstream: Path, output: Path, compiler: Path,
                            relative_sources: list[str], *, host_control: bool) -> dict:
    """Compile changed real original units without claiming a full-profile run."""
    sys.path.insert(0, str(FIRST / 'original'))
    import common
    compiler = common.compiler(str(compiler))
    identity = common.execution_identity(compiler, compiler, host_control)
    identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
    upstream, output = original._pinned_upstream(upstream), output.resolve(strict=True)
    value = verify_composition(output)
    if not relative_sources or len(set(relative_sources)) != len(relative_sources):
        raise ValueError('A nonempty unique original source subset is required')
    selected = {checked_relative(name).as_posix() for name in relative_sources}
    if any(name not in value['original_files'] or not name.endswith('.c') for name in selected):
        raise ValueError('Original subset contains an undeclared source')
    objects = output / 'changed-original-objects'
    if objects.exists():
        raise ValueError('Changed-original compilation requires fresh output')
    objects.mkdir()
    source_root = output / 'source/src/nvidia'
    declared = original.original_commands(upstream, objects, compiler)
    matches = {}
    for index, command in enumerate(declared):
        name = Path(command[command.index('-c') + 1])
        if name.is_absolute():
            continue
        relative = (source_root / name).resolve(strict=True).relative_to(output / 'source').as_posix()
        if relative in selected:
            if relative in matches:
                raise ValueError('Original make profile declares a selected source twice')
            matches[relative] = (index, command)
    if set(matches) != selected:
        raise ValueError('Selected sources differ from the actual original make profile')
    target = (['-target', 'x86_64-macos-none', '-fPIC'] if host_control else
              ['-mkernel', '-arch', 'x86_64', '-mmacosx-version-min=15.0'])
    extra = ['-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__', '-DNV_VERSION_STRING="615.78.08"',
        '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1', '-include', str(output / value['namespace']),
        *include_flags(output), '-Wframe-larger-than=4096', '-Werror=frame-larger-than',
        '-fstack-usage', *target]
    rows = []
    report = {'format': 1, 'status': 'running', **identity, 'results': rows,
        'composition_sha256': sha(output / 'composition.json'), 'full_profile_validated': False,
        'make_declared_translation_units': 1100, 'original_entry_admission': False,
        'hardware_admission': False, 'production_candidate_allowed': False,
        'kernel_execution': 'not_tested', 'gpu_access': False, 'final_link': 'not_performed'}
    destination = output / 'changed-original-compilation.json'
    write_json(destination, report)
    try:
        for relative in sorted(matches):
            index, base = matches[relative]
            source = output / 'source' / relative
            obj = Path(base[base.index('-o') + 1]);dep = obj.with_suffix('.d')
            definitions = original_source_flags(value, relative)
            command = [*base, *extra, *definitions, '-MD', '-MF', str(dep)]
            original.execute(command, cwd=source_root, timeout=300,
                diagnostic_log=objects / ('compile-%04d.log' % index))
            definitions, imports, _ = original.macho_symbols(obj)
            escaped = {name for name in definitions if not name.startswith(original.PREFIX)}
            if escaped - ORIGINAL_PROJECT_EXPORTS:
                raise ValueError('Unexpected project exports in changed original source')
            for name in escaped:
                if ORIGINAL_PROJECT_OWNERS[name] != relative:
                    raise ValueError('A strong project export moved to another original source')
            dependencies = {}
            for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
                path = Path(name)
                path = (source_root / path).resolve(strict=True) if not path.is_absolute() else path.resolve(strict=True)
                if path.is_relative_to(upstream):
                    raise ValueError('Raw original dependency escaped composed source')
                dependencies[str(path)] = sha(path)
            rows.append({'source': relative, 'source_sha256': sha(source), 'object': obj.name,
                'compile_definitions': value.get('fixed_source_profiles', {}).get(
                    'per_original_source_compile_definitions', {}).get(relative, {}),
                'object_sha256': sha(obj), 'definitions': sorted(definitions), 'imports': sorted(imports),
                'command': command, 'cwd': str(source_root), 'dependency_sha256': dependencies,
                'stack_usage': stack.capture_usage(source, obj, command, cwd=source_root,
                                                   native_apple=not host_control)})
        verify_composition(output)
        verify_compiled_rows(rows, objects)
        report.update(status='compiled-original-subset-source-only', original_translation_units=len(rows))
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write_json(destination, report)
    return report


def compile_original_objects(upstream: Path, output: Path, compiler: Path, *, host_control: bool) -> dict:
    """Compile every make-declared source against composed headers, no reuse.

    The baseline compiler's relative source/include paths resolve within the
    full composed tree. Original identification is generated deterministically.
    All complete original objects are returned once, by original source path.
    """
    sys.path.insert(0, str(FIRST / 'original'))
    import common
    compiler = common.compiler(str(compiler))
    identity = common.execution_identity(compiler, compiler, host_control)
    identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
    output = output.resolve(strict=True)
    value = verify_composition(output)
    upstream = original._pinned_upstream(upstream)
    objects = output / 'original-objects'
    if objects.exists():
        raise ValueError('Full original compilation requires a fresh objects directory')
    objects.mkdir()
    source_root = output / 'source/src/nvidia'
    commands = original.original_commands(upstream, objects, compiler)
    generated = objects / 'g_nvid_string.c'
    generated.write_text('const char NVRM_ID[] = "nvidia id: NVIDIA UNIX Open Kernel Module for x86_64 '
                         '615.78.08 Release Build (build@ci)";\nconst char *const pNVRM_ID = NVRM_ID + 11;\n')
    targets = [row[row.index('-o') + 1] for row in commands]
    if len(targets) != len(set(targets)):
        raise ValueError('Original compilation object names collide')
    extra = ['-DNV_UNIX=1', '-D__NV_UNIX_VERSION_H__', '-DNV_VERSION_STRING="615.78.08"',
        '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1',
        '-include', str(output / value['namespace']), *include_flags(output),
        '-Wframe-larger-than=4096', '-Werror=frame-larger-than', '-fstack-usage',
        *(['-target', 'x86_64-macos-none', '-fPIC'] if host_control else
          ['-mkernel', '-arch', 'x86_64', '-mmacosx-version-min=15.0'])]
    def one(entry):
        index, row = entry
        path = Path(row[row.index('-c') + 1])
        source = path if path.is_absolute() else source_root / path
        relative = ('generated/g_nvid_string.c' if path.is_absolute() else
                    source.resolve(strict=True).relative_to(output / 'source').as_posix())
        if path.is_absolute() and source != generated:
            raise ValueError('Unexpected external original source: ' + str(source))
        command = [*row, *extra, *original_source_flags(value, relative)]
        obj = Path(row[row.index('-o') + 1])
        dep = obj.with_suffix('.d')
        command += ['-MD', '-MF', str(dep)]
        original.execute(command, cwd=source_root, timeout=300,
                         diagnostic_log=objects / ('compile-%04d.log' % index))
        defined, undefined, _ = original.macho_symbols(obj)
        escaped = {name for name in defined if not name.startswith(original.PREFIX)} - ORIGINAL_PROJECT_EXPORTS
        if escaped:
            raise ValueError('Unexpected unnamespaced original definition: ' + repr(sorted(escaped)))
        dependencies = {}
        for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            dependency = Path(name)
            dependency = (source_root / dependency).resolve(strict=True) if not dependency.is_absolute() else dependency.resolve(strict=True)
            if dependency.is_relative_to(upstream):
                raise ValueError('Raw upstream dependency escaped composed tree: ' + str(dependency))
            dependencies[str(dependency)] = sha(dependency)
        return {'source': relative, 'source_sha256': sha(source), 'object': obj.name,
            'compile_definitions': value.get('fixed_source_profiles', {}).get(
                'per_original_source_compile_definitions', {}).get(relative, {}),
            'object_sha256': sha(obj), 'definitions': sorted(defined), 'imports': sorted(undefined),
            'dependency_sha256': dependencies, 'command': command, 'cwd': str(source_root),
            'stack_usage': stack.capture_usage(source.resolve(strict=True), obj, command,
                                                cwd=source_root, native_apple=not host_control)}
    rows, failures = [], []
    report = {'format': 1, 'status': 'running', **identity, 'original_entry_admission': False,
        'hardware_admission': False, 'production_candidate_allowed': False,
        'native_apple_compiler': not host_control, 'cross_compile_probe': host_control,
        'composition_sha256': sha(output / 'composition.json'), 'kernel_execution': 'not_tested',
        'gpu_access': False, 'results': rows, 'failures': failures}
    destination = output / 'full-original-compilation.json'
    write_json(destination, report)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, pair): pair[0] for pair in enumerate(commands)}
        for future in concurrent.futures.as_completed(futures):
            try:
                rows.append(future.result())
            except Exception as error:
                failures.append({'index': futures[future], 'error': str(error)})
            write_json(destination, report)
    if failures:
        report['status'] = 'failed'
        write_json(destination, report)
        raise ValueError('Composed full original compilation failed: ' + repr(failures[:3]))
    return finalize_original_compilation(output, report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['upstream', 'v3-root', 'namespace', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--successor-manifest', type=Path)
    parser.add_argument('--project-successor-manifest', type=Path)
    parser.add_argument('--retained-diagnostic', action='store_true')
    parser.add_argument('--rc-participant', action='store_true')
    parser.add_argument('--shutdown-protocol', action='store_true')
    parser.add_argument('--platform-closure', action='store_true')
    parser.add_argument('--retained-backends', action='store_true')
    parser.add_argument('--global-epoch', action='store_true')
    parser.add_argument('--live-abi-closure', action='store_true')
    parser.add_argument('--compile-original', action='store_true')
    parser.add_argument('--cc', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--host-control', action='store_true')
    args = parser.parse_args()
    value = materialize(args.upstream, args.v3_root, args.namespace, args.output,
                        successor_manifest=args.successor_manifest,
                        project_successor_manifest=args.project_successor_manifest,
                        retained_diagnostic=args.retained_diagnostic,
                        rc_participant=args.rc_participant,
                        shutdown_protocol=args.shutdown_protocol,
                        platform_closure=args.platform_closure,
                        retained_backends=args.retained_backends,
                        global_epoch=args.global_epoch,
                        live_abi_closure=args.live_abi_closure)
    if args.compile_original:
        value = compile_original_objects(args.upstream, args.output, args.cc, host_control=args.host_control)
    print(json.dumps({'status': value['status'], 'original_entry_admission': False,
                      'production_candidate_allowed': False, 'final_link': 'not_performed'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
