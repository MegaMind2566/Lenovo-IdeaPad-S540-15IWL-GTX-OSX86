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
import nvidia_metaclass_initializers as metaclass

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONTRACT = ROOT / 'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json'
EXTERNAL_CONTRACTS = ROOT / 'packages/nvidia-global-rm/EXTERNAL-CONTRACTS.json'
CRYPTO_CONTRACTS = ROOT / 'packages/nvidia-global-rm-crypto/upstream/PROVENANCE.json'
COORDINATOR_CONTRACTS = ROOT / 'packages/nvidia-global-rm/COORDINATOR-CONTRACTS.json'
LIFECYCLE_SOURCE = ROOT / 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
MEMORY_PROFILE_CONTRACTS = ROOT / 'packages/nvidia-device-transport/MEMORY-CONTRACTS.json'
FEATURE_PROFILE_CONTRACTS = ROOT / 'packages/nvidia-global-rm/FEATURE-PROFILE-CONTRACTS.json'
CENTRAL_POLICY_CONTRACTS = ROOT / 'packages/nvidia-global-rm/CENTRAL-POLICY-CONTRACTS.json'
USER_PIN_ROOT_CONTRACT = ROOT / 'packages/nvidia-device-transport/USER-PIN-ROOT-CONTRACT.json'
EXPECTED_ORIGINAL_OBJECTS = 1100
GATED_LIFECYCLE_ROOTS = ('coreInitializeRm', 'RmShutdownRm')
# The selected no-RM-ACPI-events backend supplies exact typed refusals for
# method execution. These are present linker definitions, never working ACPI
# methods. Each invocation invalidates the full-RM host's clean admission.
UNAVAILABLE_ACPI = {original.PREFIX + name for name in (
    'nv_acpi_d3cold_dsm_for_upstream_port', 'nv_acpi_ddc_method',
    'nv_acpi_dod_method', 'nv_acpi_dsm_method', 'nv_acpi_get_powersource',
    'nv_acpi_mux_method')}
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
COMMENTS = re.compile(r'/\*.*?\*/|//[^\n]*', re.S)


def _without_comments(text: str) -> str:
    return COMMENTS.sub(lambda match: ''.join('\n' if value == '\n' else ' '
                                              for value in match[0]), text)


def review_user_pin_roots(roots: set[str], retained: set[str], project_symbols: set[str],
                         upstream: Path | None = None, source_tree: Path | None = None) -> dict:
    """Check this image's exact escape-chain exclusion, never a pin backend.

    Static helper exclusion is established by the complete pinned identifier
    inventory. Image conditions use derived public roots and actual retained
    externals, rather than assuming dead stripping removes every local symbol.
    """
    manifest = json.loads(USER_PIN_ROOT_CONTRACT.read_text())
    conditions = manifest.get('required_final_link_conditions', {})
    expected = {
        'forbidden_original_roots': [original.PREFIX + name for name in ('RmIoctl', 'rm_ioctl')],
        'forbidden_retained_original_externals': [original.PREFIX + name for name in
                                                ('os_lock_user_pages', 'os_lookup_user_io_memory')],
        'project_production_must_not_reference': ['rm_ioctl', 'RmIoctl', 'RmCreateOsDescriptor',
                                                 'RmAllocOsDescriptor', 'os_lock_user_pages']}
    expected_sources = {'src/nvidia/arch/nvalloc/unix/' + path for path in
        ('include/nv.h', 'include/os-interface.h', 'include/osapi.h', 'src/escape.c', 'src/osapi.c')}
    if (manifest.get('format') != 1 or manifest.get('commit') != original.COMMIT or
            conditions != expected or manifest.get('production_pin_service_implemented') is not False or
            set(manifest.get('source_sha256', {})) != expected_sources or
            set(manifest.get('exact_identifier_occurrences_src_nvidia_C_H_excluding_comments', {})) !=
            set(expected['project_production_must_not_reference'])):
        raise ValueError('The reviewed user-pin root/source contract changed.')
    if roots & set(expected['forbidden_original_roots']):
        raise ValueError('The final original roots admit the excluded user-pin escape chain.')
    if retained & set(expected['forbidden_retained_original_externals']):
        raise ValueError('The final original imports retain an excluded user-pin acquisition.')
    names = expected['project_production_must_not_reference']
    if project_symbols & {prefix + name for name in names for prefix in ('', original.PREFIX)}:
        raise ValueError('The compiled project references the excluded user-pin escape chain.')
    # Check production source/header directories as well as actual compiled
    # symbols. Extra GSP directories are explicit; isolated prospective body
    # controls and tests are not runtime source. Avoid importing the builder
    # here: source review must not load firmware acquisition/network helpers.
    directories = [path / 'src' for path in (ROOT / 'packages').iterdir()]
    gsp = ROOT / 'packages/nvidia-gsp-bootstrap'
    directories += [gsp / name for name in ('platform', 'evidence', 'timers')]
    selected = {path for directory in directories for extension in ('*.c', '*.cpp', '*.h', '*.hpp')
                for path in directory.glob(extension)}
    selected.update(gsp / ('cancellation/S540NvidiaGspCancellation.' + extension)
                    for extension in ('c', 'h'))
    pattern = re.compile(r'\b(?:' + '|'.join(re.escape(prefix + name)
        for name in names for prefix in ('', original.PREFIX)) + r')\b')
    for source in selected:
        if pattern.search(_without_comments(source.read_text())):
            raise ValueError('A selected project source references the excluded user-pin escape chain: ' +
                             source.relative_to(ROOT).as_posix())
    if upstream is not None:
        actual_source = source_tree if source_tree is not None else upstream
        for source, expected_hash in manifest.get('source_sha256', {}).items():
            if hashlib.sha256((upstream / source).read_bytes()).hexdigest() != expected_hash:
                raise ValueError('A user-pin caller-chain source hash changed: ' + source)
            if hashlib.sha256((actual_source / source).read_bytes()).hexdigest() != expected_hash:
                raise ValueError('The actual composed user-pin caller-chain source needs a new review: ' + source)
        inventory = manifest['exact_identifier_occurrences_src_nvidia_C_H_excluding_comments']
        observed = {name: [] for name in inventory}
        pattern = re.compile(r'\b(?:' + '|'.join(map(re.escape, inventory)) + r')\b')
        for source in sorted((actual_source / 'src/nvidia').rglob('*')):
            if source.suffix not in ('.c', '.h'):
                continue
            text = _without_comments(source.read_text())
            for match in pattern.finditer(text):
                observed[match[0]].append({'source': source.relative_to(actual_source).as_posix(),
                                         'line': text.count('\n', 0, match.start()) + 1})
        if observed != inventory:
            raise ValueError('The complete pinned user-pin identifier caller inventory changed.')
    return {'contract': USER_PIN_ROOT_CONTRACT.relative_to(ROOT).as_posix(),
            'sha256': hashlib.sha256(USER_PIN_ROOT_CONTRACT.read_bytes()).hexdigest(),
            'status': 'verified-current-image-and-pinned-source' if upstream is not None else
                      'fixture-image-conditions-only; pinned-source-not-verified',
            'original_source_hashes_verified': upstream is not None,
            'complete_original_identifier_inventory_verified': upstream is not None,
            'actual_composed_source_inventory_verified': upstream is not None and source_tree is not None,
            'project_source_sha256': {path.relative_to(ROOT).as_posix():
                hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(selected)},
            'derived_original_roots_checked': True, 'retained_original_externals_checked': True,
            'compiled_project_symbols_checked': True, 'pin_service_implemented': False,
            'whole_bootstrap_reachability_proven': False, 'kernel_execution': 'not_tested'}


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


def review_profile_contracts(reviewed: dict[str, dict], upstream: Path | None = None) -> tuple[dict, dict]:
    """Keep typed refusals/tripwires distinct from working callback definitions.

    The machine contracts classify source semantics, not runtime reachability.
    The native full-tree audit also verifies every cited original source hash;
    small classifier controls may use the manifest-only path explicitly.
    """
    categories = {
        'unavailable-memory-operation': 'provided_unavailable_memory_operations',
        'unavailable-lifetime-or-scalar-guard': 'provided_memory_lifetime_guards',
        'expected-disabled-platform-branch': 'provided_disabled_profile_callbacks',
        'official-empty-release': 'provided_disabled_profile_callbacks',
        'provided_unavailable_operation': 'provided_unavailable_feature_operations',
        'mixed_disabled_query_and_unavailable_operation': 'provided_partially_available_feature_operations',
        'official_disabled_capability': 'provided_disabled_profile_callbacks',
        'official_disabled_no_owned_resource': 'provided_disabled_profile_callbacks',
        'selected_zero_soc_irq_state': 'provided_profile_state_queries',
        'selected_backend_capability': 'provided_profile_state_queries',
        'unavailable_runtime_pm_operation': 'provided_unavailable_central_operations',
        'unavailable_hot_remove_lifetime_guard': 'provided_central_lifetime_guards',
    }
    rows, provenance = {}, {}
    for path, count in ((MEMORY_PROFILE_CONTRACTS, 40), (FEATURE_PROFILE_CONTRACTS, 30),
                        (CENTRAL_POLICY_CONTRACTS, 8)):
        manifest = json.loads(path.read_text())
        commit = manifest.get('commit', manifest.get('upstream_commit'))
        callbacks = manifest.get('callbacks', [])
        if manifest.get('format') != 1 or commit != original.COMMIT or len(callbacks) != count:
            raise ValueError('The selected callback profile source identity or inventory changed: ' + str(path))
        for callback in callbacks:
            name = callback.get('namespace_symbol')
            original_type = callback.get('original_type', callback.get('type'))
            classification = callback.get('classification')
            if (name != original.PREFIX + callback.get('symbol', '') or name in rows or
                    name not in reviewed or original_type != reviewed[name].get('type') or
                    classification not in categories):
                raise ValueError('A source-classified profile callback has an invalid ABI/category: ' + str(name))
            rows[name] = {'category': categories[classification],
                          'source_classification': classification,
                          'contract': path.relative_to(ROOT).as_posix(),
                          'operational_service_proven': False,
                          'unreachable_entry_proven': False}
        hashes = manifest.get('source_sha256')
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError('A selected callback profile lacks original source hashes: ' + str(path))
        if upstream is not None:
            for source, expected in hashes.items():
                if hashlib.sha256((upstream / source).read_bytes()).hexdigest() != expected:
                    raise ValueError('A selected callback profile original source hash changed: ' + source)
        provenance[path.relative_to(ROOT).as_posix()] = {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'callback_count': count, 'original_source_hashes': len(hashes),
            'original_source_hashes_verified': upstream is not None,
            'runtime_reachability_proven': False}
    if len(rows) != 78:
        raise ValueError('The selected callback profile inventories overlap.')
    return rows, provenance


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
    if remap.get('implementation_status') != 'provided-guarded-device-remap':
        raise ValueError('The DMA-remapping ABI must retain its reviewed bound-device implementation.')
    if not remap.get('admission_requirement'):
        raise ValueError('The DMA-remapping scalar requires its checked bound-device admission policy.')
    remap_original = remap['original_implementation']
    remap_original_text = source_bytes[remap_original['source']].decode()
    if (remap_original_text.splitlines()[remap_original['line'] - 1] != remap_original['anchor'] or
            remap_original['state_anchor'] not in remap_original_text or
            remap_original['policy_anchor'] not in source_bytes[remap_original['policy_source']].decode()):
        raise ValueError('The original DMA-remapping/bounce-buffer policy anchor changed.')
    remap_project = remap['project_implementation']
    remap_bridge = (ROOT / remap_project['bridge']).read_text()
    if (remap_project['bridge_anchor'] not in remap_bridge or
            any(anchor not in remap_bridge for anchor in remap_project['bridge_anchors'])):
        raise ValueError('The reviewed original-ABI DMA-remapping bridge changed.')
    for implementation_file, anchors in (
            (remap_project['backend'], remap_project['backend_anchors']),
            (remap_project['session'], remap_project['session_anchors'])):
        implementation_text = (ROOT / implementation_file).read_text()
        if any(anchor not in implementation_text for anchor in anchors):
            raise ValueError('The reviewed bound-device DMA-remapping policy changed: ' + implementation_file)
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
                                          for path in (project['bridge'], project['backend'],
                                              remap_project['bridge'], remap_project['backend'], remap_project['session'])},
        'nv_requires_dma_remap_backend': 'provided; positively attested bound-device no-bounce mapping',
        'nv_requires_dma_remap_admission_requirement': remap['admission_requirement'],
        'dma_remap_unknown_policy': 'entry blocked; scalar contract violation without Boolean fallback',
        'dma_remap_runtime_admission_verified': False,
        'os_is_queue_flush_ongoing_backend': 'provided; actual guarded queue unload-flush state',
        'os_is_queue_flush_ongoing_admission_requirement': queue['admission_requirement'],
        'queue_unbound_context_policy': 'contract-violation; no scalar fallback',
        'queue_runtime_admission_verified': False}


def _classify(retained: set[str], project_defined: set[str], original_external: set[str],
              reviewed: dict[str, dict], crypto: set[str], profiles: dict | None = None) -> dict:
    unknown = retained - original_external
    compiler = retained & original.COMPILER_MEMORY_IMPORTS
    provided = retained & project_defined
    missing = retained - provided - compiler
    reviewed_missing = missing & reviewed.keys()
    abi_review = missing - reviewed.keys() - crypto
    if profiles is None:
        profiles, _ = review_profile_contracts(reviewed)
    profile_groups = {category: sorted(name for name in provided & profiles.keys()
                                      if profiles[name]['category'] == category)
                      for category in (
                          'provided_unavailable_memory_operations', 'provided_memory_lifetime_guards',
                          'provided_unavailable_feature_operations', 'provided_partially_available_feature_operations',
                          'provided_unavailable_central_operations', 'provided_central_lifetime_guards',
                          'provided_disabled_profile_callbacks', 'provided_profile_state_queries')}
    return {
        'provided_project_callbacks': sorted(provided - crypto - compiler - UNAVAILABLE_ACPI - profiles.keys()),
        'provided_unavailable_crypto': sorted(provided & crypto),
        'provided_unavailable_acpi_methods': sorted(provided & UNAVAILABLE_ACPI),
        **profile_groups,
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


IMPLEMENTATION_BLOCKERS = (
    'unmet_reviewed_callbacks', 'unmet_crypto_definitions', 'unmet_abi_review',
    'provided_without_selected_abi_contract', 'provided_unavailable_acpi_methods',
    'provided_unavailable_crypto', 'provided_unavailable_memory_operations',
    'provided_memory_lifetime_guards', 'provided_unavailable_feature_operations',
    'provided_partially_available_feature_operations', 'provided_unavailable_central_operations',
    'provided_central_lifetime_guards', 'unreviewed_retained_imports')


def implementation_complete(classified: dict) -> bool:
    """An absent raw linker import is not evidence an operation is implemented."""
    return not any(classified[key] for key in IMPLEMENTATION_BLOCKERS)


def analyze_execution_closure(linked_project: Path, original_objects: list[Path],
                              compiled: dict, output: Path, *,
                              linker: list[str] | None = None,
                              cross_probe: bool = False,
                              upstream: Path | None = None,
                              user_pin_source_tree: Path | None = None,
                              metaclass_reference: Path | None = None) -> dict:
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
              'closure_scope': 'current-compiled-bridges-and-source-gated-global-lifecycle',
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
        profiles, profile_review = review_profile_contracts(reviewed, upstream)
        record['selected_callback_profile_review'] = profile_review
        record['coordinator_contract_review'] = supplemental_review
        provenance['packages/nvidia-global-rm/COORDINATOR-CONTRACTS.json'] = supplemental_review['manifest_sha256']
        if metaclass_reference is not None:
            record['project_metaclass_audit'] = metaclass.verify_metaclass_initializers(
                linked_project, metaclass_reference)
        project_defined, project_undefined, _ = original.macho_symbols(
            linked_project, reviewed_project_initializers=metaclass_reference is not None)
        overlap = project_defined & original_defined
        record['project_original_definition_overlap'] = sorted(overlap)
        if overlap:
            raise ValueError('Project sources redefine original RM definitions: ' + str(sorted(overlap)))
        compiled_roots = derive_roots(project_defined, project_undefined, original_defined)
        if not compiled_roots:
            raise ValueError('The actual compiled bridge references no original RM definition.')
        # The source-gated wrapper has no original imports in its current
        # kernel object. Audit those exact prospective entries as well: a
        # successful current-bridge link must not conceal their dependencies.
        # This link-only control does not authorize removing the source gate.
        lifecycle = LIFECYCLE_SOURCE.read_text()
        gate = lifecycle.split('#if defined(KERNEL)', 1)
        if (len(gate) != 2 or 'return out->startupStatus = NV_ERR_NOT_READY;' not in
                gate[1].split('#endif', 1)[0]):
            raise ValueError('The documented kernel global-lifecycle refusal needs a new source review.')
        if ('status = coreInitializeRm();' not in lifecycle or
                'RmShutdownRm();' not in lifecycle):
            raise ValueError('The gated global lifecycle entries need a new source review.')
        gated_roots = {original.PREFIX + name for name in GATED_LIFECYCLE_ROOTS}
        if not gated_roots <= original_defined:
            raise ValueError('The original compilation lacks the gated global lifecycle entries.')
        roots = compiled_roots | gated_roots
        filetype = original.MH_BUNDLE if cross_probe else original.MH_KEXT_BUNDLE
        image = output / 'coordinator-original-dependency-control.bundle'
        record.update(
            current_kernel_global_lifecycle_gate='refused-before-original-code',
            lifecycle_source_sha256=hashlib.sha256(LIFECYCLE_SOURCE.read_bytes()).hexdigest(),
            linked_project_sha256=hashlib.sha256(linked_project.read_bytes()).hexdigest(),
            contract_sha256=provenance, original_object_count=len(original_objects),
            original_root_count=len(roots), original_roots=sorted(roots),
            compiled_bridge_original_roots=sorted(compiled_roots),
            source_gated_global_lifecycle_roots=sorted(gated_roots),
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
        record['user_pin_escape_root_review'] = review_user_pin_roots(
            roots, retained, project_defined | project_undefined, upstream, user_pin_source_tree)
        classified = _classify(retained, project_defined, original_external, reviewed, crypto, profiles)
        record.update(classified, retained_original_external_count=len(retained),
                      retained_original_externals=sorted(retained), sections=sections,
                      image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                      image_executed=False, dynamic_libraries_linked=False)
        if original.PREFIX + 'os_is_queue_flush_ongoing' in retained:
            record['runtime_blockers'].append(
                'Queue-state scalar requires an actual bound context/global work queue; '
                'an unbound queue triggers a contract violation instead of a scalar fallback.')
        if original.PREFIX + 'nv_requires_dma_remap' in retained:
            record['runtime_blockers'].append(
                'DMA-remapping scalar requires a checked policy from the exact bound device before entry; '
                'unresolved or revoked mapper metadata cannot select a Boolean bypass.')
        record['runtime_blockers'].append(
            'Original GSP init/disable frees temporary allocations with active interrupts. '
            'Bounded per-allocation retirement now retains pages and IOVA through the actual IRQ drain. '
            'Its 32-slot/128-MiB capacity and the complete original device lifecycle are not yet validated.')
        save()
        if classified['unreviewed_retained_imports']:
            raise ValueError('The retained original imports escape the verified full compilation inventory: ' +
                             str(classified['unreviewed_retained_imports']))
        blocker_categories = ('unmet_reviewed_callbacks', 'unmet_crypto_definitions',
                              'unmet_abi_review', 'provided_without_selected_abi_contract')
        for key in blocker_categories:
            if classified[key]:
                record['runtime_blockers'].append(key + ': ' + str(len(classified[key])))
        if classified['provided_unavailable_acpi_methods']:
            record['runtime_blockers'].append(
                'The selected RM ACPI-events backend has no method execution. Its six typed '
                'refusal definitions are not operational methods; any call records unavailability '
                'and prevents a successful runtime trial.')
        if classified['provided_unavailable_crypto']:
            record['runtime_blockers'].append(
                'The typed crypto boundaries implement no cryptographic operations. A complete '
                'supported profile must independently prove zero requests throughout its actual lifecycle.')
        for key in ('provided_unavailable_memory_operations', 'provided_memory_lifetime_guards',
                    'provided_unavailable_feature_operations', 'provided_partially_available_feature_operations',
                    'provided_unavailable_central_operations', 'provided_central_lifetime_guards'):
            if classified[key]:
                record['runtime_blockers'].append(
                    key + ': ' + str(len(classified[key])) +
                    '; these definitions refuse operations or detect invalid lifetime/state. '
                    'They are not operational implementations or a proved unreachable route.')
        if classified['provided_disabled_profile_callbacks'] or classified['provided_profile_state_queries']:
            record['runtime_blockers'].append(
                'Source-backed disabled feature/query branches require the actual selected device/backend '
                'preflight and sealed request entries. Native fixtures and lexical caller references '
                'do not prove complete original init/interrupt/error/unwind reachability.')
        record['runtime_blockers'].append(
            'Darwin system address-space/stack services require actual target-kernel ABI/export '
            'admission; public pinned XNU/SDK source agreement is development evidence only.')
        record.update(status='blocked', phase='complete', link_control_status='passed',
                      abi_inventory_status='blocked' if (classified['unmet_abi_review'] or
                          classified['provided_without_selected_abi_contract']) else 'reviewed',
                      closure_implementation_complete=implementation_complete(classified))
        save()
        return record
    except Exception as error:
        record.update(status='failed', failure_phase=record['phase'],
                      failure_type=type(error).__name__, failure=str(error))
        save()
        raise
