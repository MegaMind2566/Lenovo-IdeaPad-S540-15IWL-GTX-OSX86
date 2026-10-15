"""Audit original RM dependencies reached by the actual compiled project bridge.

This is a link-only development control. Known missing implementations and ABI
reviews are reported as blockers; neither a successful link nor an empty missing
set authorizes execution, firmware boot, or a candidate package.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import re
import struct
import sys

import compile_nvidia_global_rm as original
import nvidia_execution_commands as commands

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONTRACT = ROOT / 'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json'
EXTERNAL_CONTRACTS = ROOT / 'packages/nvidia-global-rm/EXTERNAL-CONTRACTS.json'
CRYPTO_CONTRACTS = ROOT / 'packages/nvidia-global-rm-crypto/upstream/PROVENANCE.json'
COORDINATOR_CONTRACTS = ROOT / 'packages/nvidia-global-rm/COORDINATOR-CONTRACTS.json'
LIFECYCLE_SOURCE = ROOT / 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
EXPECTED_ORIGINAL_OBJECTS = 1100
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _symbols(value, description: str) -> set[str]:
    if (not isinstance(value, list) or any(not isinstance(name, str) or
            not IDENTIFIER.fullmatch(name) for name in value) or
            value != sorted(set(value))):
        raise ValueError(description + ' is not an exact sorted symbol inventory.')
    return set(value)


def derive_roots(project_defined: set[str], project_undefined: set[str],
                 original_defined: set[str]) -> set[str]:
    """Keep exact unresolved original definitions, not project-owned callbacks."""
    return (project_undefined - project_defined) & original_defined


def _validate_original(objects: list[Path], compiled: dict,
                       cross_probe: bool) -> tuple[set[str], set[str]]:
    required = {'status': 'compiled', 'commit': original.COMMIT,
                'source_namespace_verified': True, 'namespace_applied': True,
                'native_apple_compiler': not cross_probe, 'cross_compile_probe': cross_probe}
    if any(type(compiled.get(key)) is not type(value) or compiled.get(key) != value
           for key, value in required.items()):
        raise ValueError('The coordinator control requires a verified matching original RM compilation.')
    if len(objects) != EXPECTED_ORIGINAL_OBJECTS or len(set(objects)) != len(objects):
        raise ValueError('The coordinator control lost or duplicated original RM objects.')
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in objects}
    if len(hashes) != len(objects) or hashes != compiled.get('object_sha256'):
        raise ValueError('The original RM object bytes differ from the verified compilation.')
    contract = compiled.get('namespace_contract', {})
    defined = _symbols(contract.get('defined'), 'Original RM definitions')
    external = _symbols(contract.get('external'), 'Original RM externals')
    expected = json.loads(SOURCE_CONTRACT.read_text())
    if (contract.get('namespace_sha256') != expected.get('namespace_sha256') or
            len(defined) != expected.get('defined_count') or
            any(not name.startswith(original.PREFIX) for name in defined)):
        raise ValueError('The pinned original RM private namespace changed.')
    observed_defined, observed_referenced = set(), set()
    for path in objects:
        definitions, references, _ = original.macho_symbols(path)
        observed_defined.update(definitions)
        observed_referenced.update(references)
    if defined != observed_defined or external != observed_referenced - observed_defined:
        raise ValueError('The original RM definition/external inventory is stale.')
    return defined, external


def _reviewed_contracts() -> tuple[dict[str, dict], set[str], dict]:
    declarations = json.loads(EXTERNAL_CONTRACTS.read_text())
    crypto = json.loads(CRYPTO_CONTRACTS.read_text())
    if (declarations.get('format') != 1 or declarations.get('commit') != original.COMMIT or
            crypto.get('format') != 1 or crypto.get('upstream', {}).get('commit') != original.COMMIT or
            crypto.get('crypto_implemented') is not False):
        raise ValueError('The reviewed callback/crypto contracts have an unexpected source identity.')
    reviewed = {}
    for row in declarations.get('contracts', []):
        name = row.get('namespace_symbol')
        if (not isinstance(name, str) or name != original.PREFIX + row.get('symbol', '') or
                not IDENTIFIER.fullmatch(name) or name in reviewed or
                row.get('kind') not in ('FunctionDecl', 'VarDecl') or
                row.get('unavailable_policy') not in
                ('output-preserving-NV_ERR_NOT_SUPPORTED', 'output-preserving-NULL',
                 'entry-must-be-blocked-before-call', 'not-a-function') or
                (row.get('kind') == 'VarDecl') != (row.get('unavailable_policy') == 'not-a-function')):
            raise ValueError('A reviewed external declaration is invalid or duplicated.')
        reviewed[name] = row
    crypto_names = set()
    for row in crypto.get('symbols', []):
        name = row.get('facade')
        if (not isinstance(name, str) or name != original.PREFIX + row.get('original', '') or
                not IDENTIFIER.fullmatch(name) or name in crypto_names):
            raise ValueError('A reviewed crypto declaration is invalid or duplicated.')
        crypto_names.add(name)
    if len(reviewed) != 244 or len(crypto_names) != 64 or reviewed.keys() & crypto_names:
        raise ValueError('The selected reviewed callback/crypto inventories changed.')
    provenance = {label: hashlib.sha256(path.read_bytes()).hexdigest() for label, path in (
        ('packages/nvidia-global-rm/EXTERNAL-CONTRACTS.json', EXTERNAL_CONTRACTS),
        ('packages/nvidia-global-rm-crypto/upstream/PROVENANCE.json', CRYPTO_CONTRACTS),
        ('packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json', SOURCE_CONTRACT))}
    return reviewed, crypto_names, provenance


def _control_symbols(image: Path, filetype: int):
    result = original.macho_symbols(image, expected_type=filetype)
    # The shared reader enforces this for MH_KEXT_BUNDLE. Also enforce it on
    # the explicitly separate PIC cross-control before reporting no dylibs.
    data = image.read_bytes()
    offset = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        if command in original.DYLIB_LOAD_COMMANDS:
            raise ValueError('The coordinator dependency control links a dynamic library.')
        offset += size
    return result


def review_coordinator_contracts(upstream: Path | None) -> tuple[dict[str, dict], dict]:
    """Verify only the two additional exact ABIs against the pinned source tree."""
    if upstream is None:
        raise ValueError('The pinned upstream tree is required for supplemental coordinator ABI review.')
    upstream = upstream.resolve(strict=True)
    manifest = json.loads(COORDINATOR_CONTRACTS.read_text())
    if manifest.get('format') != 1 or manifest.get('commit') != original.COMMIT:
        raise ValueError('The supplemental coordinator ABI source identity changed.')
    expected = {
        'nv_requires_dma_remap': ('NvBool (nv_state_t *)', 'nv_state_t *'),
        'os_is_queue_flush_ongoing': ('NvBool (struct os_work_queue *)', 'struct os_work_queue *')}
    rows = manifest.get('contracts', [])
    if len(rows) != 2 or {row.get('symbol') for row in rows} != set(expected):
        raise ValueError('Only the two reviewed coordinator ABIs may extend the selected inventory.')
    verified_sources, source_bytes = {}, {}
    for source, expected_hash in manifest.get('source_sha256', {}).items():
        data = (upstream / source).read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError('A supplemental coordinator ABI source hash changed: ' + source)
        source_bytes[source] = data
        verified_sources[source] = actual_hash
    reviewed = {}
    for row in rows:
        symbol = row['symbol']
        if (row.get('namespace_symbol') != original.PREFIX + symbol or
                row.get('kind') != 'FunctionDecl' or row.get('type') != expected[symbol][0] or
                row.get('return_type') != 'NvBool' or
                row.get('parameters') != [{'name': 'p0', 'type': expected[symbol][1]}] or
                row.get('unavailable_policy') != 'entry-must-be-blocked-before-call'):
            raise ValueError('A supplemental coordinator exact ABI changed: ' + symbol)
        lines = source_bytes[row['source']].decode().splitlines()
        if lines[row['line'] - 1] != row['declaration_anchor']:
            raise ValueError('A supplemental coordinator declaration anchor changed: ' + symbol)
        canonical = re.sub(r'\s+', '', row['declaration'])
        if canonical != re.sub(r'\s+', '', row['declaration_anchor']):
            raise ValueError('A supplemental coordinator declaration differs from its original ABI: ' + symbol)
        reviewed[row['namespace_symbol']] = row
    for reference in manifest.get('reference_copies', []):
        if (ROOT / reference['path']).read_bytes() != source_bytes[reference['source']]:
            raise ValueError('A retained supplemental coordinator source copy changed: ' + reference['path'])
    remap = reviewed[original.PREFIX + 'nv_requires_dma_remap']
    if remap.get('implementation_status') != 'missing-operational-backend':
        raise ValueError('The missing DMA-remapping scalar backend must remain explicitly blocked.')
    queue = reviewed[original.PREFIX + 'os_is_queue_flush_ongoing']
    if queue.get('implementation_status') != 'provided-guarded-queue-state':
        raise ValueError('The queue-state ABI must retain its reviewed operational implementation.')
    if not queue.get('admission_requirement'):
        raise ValueError('The queue-state scalar requires its real bound-queue admission policy.')
    implementation = queue['original_implementation']
    original_text = source_bytes[implementation['source']].decode()
    if (original_text.splitlines()[implementation['line'] - 1] != implementation['anchor'] or
            implementation['state_anchor'] not in original_text):
        raise ValueError('The original queue unload-flush implementation anchor changed.')
    project = queue['project_implementation']
    bridge = (ROOT / project['bridge']).read_text()
    backend = (ROOT / project['backend']).read_text()
    if project['bridge_anchor'] not in bridge or any(anchor not in backend for anchor in project['backend_anchors']):
        raise ValueError('The reviewed original-ABI queue bridge/backend changed.')
    body = backend.split(project['backend_anchors'][0], 1)[1].split('extern "C"', 1)[0]
    if any(anchor not in body for anchor in ('resolve(argument)', 'queue->guard.lock()',
            'queue->unloadFlushes != 0', 'queue->guard.unlock(token)',
            'if (queue == nullptr) violation("workqueue flush state requires a bound queue");')):
        raise ValueError('The queue query no longer reads its actual guarded unload-flush state.')
    return reviewed, {
        'status': 'verified-exact-prototypes-and-source', 'contract_count': 2,
        'manifest_sha256': hashlib.sha256(COORDINATOR_CONTRACTS.read_bytes()).hexdigest(),
        'source_sha256': verified_sources,
        'project_implementation_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                          for path in (project['bridge'], project['backend'])},
        'nv_requires_dma_remap_backend': 'missing; no inferred Boolean',
        'os_is_queue_flush_ongoing_backend': 'provided; actual guarded queue unload-flush state',
        'os_is_queue_flush_ongoing_admission_requirement': queue['admission_requirement'],
        'queue_unbound_context_policy': 'contract-violation; no scalar fallback',
        'queue_runtime_admission_verified': False}


def _classify(retained: set[str], project_defined: set[str], original_external: set[str],
              reviewed: dict[str, dict], crypto: set[str]) -> dict:
    unknown = retained - original_external
    compiler = retained & original.COMPILER_MEMORY_IMPORTS
    provided = retained & project_defined
    missing = retained - provided - compiler
    reviewed_missing = missing & reviewed.keys()
    abi_review = missing - reviewed.keys() - crypto
    return {
        'provided_project_callbacks': sorted(provided - crypto - compiler),
        'provided_unavailable_crypto': sorted(provided & crypto),
        'compiler_memory_helpers': sorted(compiler),
        'unmet_reviewed_callbacks': [
            {'symbol': name, **{key: reviewed[name][key] for key in
             ('kind', 'type', 'source', 'line', 'unavailable_policy')},
             **{key: reviewed[name][key] for key in ('implementation_status', 'implementation_requirement')
                if key in reviewed[name]}}
            for name in sorted(reviewed_missing)],
        'unmet_crypto_definitions': sorted(missing & crypto),
        'unmet_abi_review': [
            {'symbol': name, 'identification': 'verified-full-original-external-inventory',
             'abi_review': 'required', 'implementation': 'unresolved',
             'default_value_inferred': False} for name in sorted(abi_review - unknown)],
        'provided_without_selected_abi_contract': sorted(provided - reviewed.keys() - crypto - compiler),
        'unreviewed_retained_imports': sorted(unknown),
    }


def analyze_execution_closure(linked_project: Path, original_objects: list[Path],
                              compiled: dict, output: Path, *,
                              linker: list[str] | None = None,
                              cross_probe: bool = False,
                              upstream: Path | None = None) -> dict:
    """Write execution-closure.json, returning blocked link evidence or raising.

    The caller verifies its checked-source manifest and current bridge bytes.
    Every original object is independently checked against the compiled record.
    A known full-profile import outside the 244 selected ABI declarations is an
    explicit review blocker, not an automatically allowed callback/default.
    """
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'execution-closure.json'
    record = {'format': 1, 'component': 'nvidia-execution-closure', 'status': 'running',
              'phase': 'validate-inputs', 'source_commit': original.COMMIT,
              'source_profile': compiled.get('source_profile', 'original-unmodified'),
              'closure_scope': 'current-compiled-bridges; excludes-source-gated-lifecycle',
              'production_candidate_allowed': False, 'executable': False,
              'kernel_execution': 'not_tested', 'global_rm_executed': False,
              'adapter_initialized': False, 'firmware_loaded': False, 'gpu_access': False,
              'runtime_blockers': ['Kernel global RM lifecycle remains refused before original code.',
                                   'Link closure does not establish kernel/device/GSP execution.']}
    def save():
        report.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    save()
    try:
        if not cross_probe and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
            raise ValueError('The native coordinator control requires Intel macOS and Apple ld.')
        original_defined, original_external = _validate_original(original_objects, compiled, cross_probe)
        reviewed, crypto, provenance = _reviewed_contracts()
        supplemental, supplemental_review = review_coordinator_contracts(upstream)
        if reviewed.keys() & supplemental.keys():
            raise ValueError('The selected and supplemental coordinator ABI inventories overlap.')
        reviewed.update(supplemental)
        record['coordinator_contract_review'] = supplemental_review
        provenance['packages/nvidia-global-rm/COORDINATOR-CONTRACTS.json'] = supplemental_review['manifest_sha256']
        project_defined, project_undefined, _ = original.macho_symbols(linked_project)
        overlap = project_defined & original_defined
        record['project_original_definition_overlap'] = sorted(overlap)
        if overlap:
            raise ValueError('Project sources redefine original RM definitions: ' + str(sorted(overlap)))
        roots = derive_roots(project_defined, project_undefined, original_defined)
        if not roots:
            raise ValueError('The actual compiled bridge references no original RM definition.')
        # This checks the documented current source gate, not a guessed future
        # call graph. Future lifecycle roots require a separate reviewed control.
        lifecycle = LIFECYCLE_SOURCE.read_text()
        gate = lifecycle.split('#if defined(KERNEL)', 1)
        if (len(gate) != 2 or 'return out->startupStatus = NV_ERR_NOT_READY;' not in
                gate[1].split('#endif', 1)[0]):
            raise ValueError('The documented kernel global-lifecycle refusal needs a new source review.')
        filetype = original.MH_BUNDLE if cross_probe else original.MH_KEXT_BUNDLE
        image = output / 'coordinator-original-dependency-control.bundle'
        record.update(
            current_kernel_global_lifecycle_gate='refused-before-original-code',
            lifecycle_source_sha256=hashlib.sha256(LIFECYCLE_SOURCE.read_bytes()).hexdigest(),
            linked_project_sha256=hashlib.sha256(linked_project.read_bytes()).hexdigest(),
            contract_sha256=provenance, original_object_count=len(original_objects),
            original_root_count=len(roots), original_roots=sorted(roots),
            project_original_definition_overlap=sorted(project_defined & original_defined),
            project_unresolved_non_original=sorted(project_undefined - project_defined - original_defined),
            mach_o_filetype=filetype,
            link_profile='explicit-pic-cross-probe' if cross_probe else 'native-kernel-non-pic',
            authoritative_darwin_link=not cross_probe,
            phase='link-original-coordinator-control')
        save()
        args = [*(linker if linker is not None else ['/usr/bin/xcrun', 'ld']),
                '-arch', 'x86_64', '-platform_version', 'macos', '15.0', '15.0',
                '-bundle' if cross_probe else '-kext', '-undefined', 'dynamic_lookup',
                '-dead_strip', '-no_uuid']
        args += [value for name in sorted(roots) for value in ('-exported_symbol', '_' + name)]
        commands.run(*args, *(str(path) for path in original_objects), '-o', str(image),
                     timeout=300, diagnostic_log=output / 'execution-closure-link.log')
        record['phase'] = 'classify-retained-imports'
        save()
        exported, retained, sections = _control_symbols(image, filetype)
        if exported != roots:
            raise ValueError('The coordinator control exports differ from the actual compiled RM roots.')
        classified = _classify(retained, project_defined, original_external, reviewed, crypto)
        record.update(classified, retained_original_external_count=len(retained),
                      retained_original_externals=sorted(retained), sections=sections,
                      image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                      image_executed=False, dynamic_libraries_linked=False)
        if original.PREFIX + 'os_is_queue_flush_ongoing' in retained:
            record['runtime_blockers'].append(
                'Queue-state scalar requires an actual bound context/global work queue; '
                'an unbound queue triggers a contract violation instead of a scalar fallback.')
        save()
        if classified['unreviewed_retained_imports']:
            raise ValueError('The retained original imports escape the verified full compilation inventory: ' +
                             str(classified['unreviewed_retained_imports']))
        blocker_categories = ('unmet_reviewed_callbacks', 'unmet_crypto_definitions',
                              'unmet_abi_review', 'provided_without_selected_abi_contract')
        for key in blocker_categories:
            if classified[key]:
                record['runtime_blockers'].append(key + ': ' + str(len(classified[key])))
        record.update(status='blocked', phase='complete', link_control_status='passed',
                      abi_inventory_status='blocked' if (classified['unmet_abi_review'] or
                          classified['provided_without_selected_abi_contract']) else 'reviewed',
                      closure_implementation_complete=not any(classified[key] for key in blocker_categories))
        save()
        return record
    except Exception as error:
        record.update(status='failed', failure_phase=record['phase'],
                      failure_type=type(error).__name__, failure=str(error))
        save()
        raise
