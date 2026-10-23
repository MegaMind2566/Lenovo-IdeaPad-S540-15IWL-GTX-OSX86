#!/usr/bin/env python3
"""Replay a separate retained first-initialization source candidate.

The immutable ancestors remain historical closed profiles. This child supplies
an explicit manual experiment and never changes their production admission.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil

import compose_nvidia_first_transaction as composer
import compile_nvidia_integrated_successor as previous
import prepare_nvidia_shutdown_successor as shutdown
import prepare_nvidia_operational_successor as operational

ROOT = Path(__file__).resolve().parents[1]
GSP = 'packages/nvidia-gsp-bootstrap/'
BASE_SHA256 = '72b7d5a5d93504218e8a7953d79c90c1609e4580c55922deb2ec5dab13de24d8'
PROFILE_DIRECTORIES = {
    'pm-event': 'prospective-pm-event-closure',
    'dma-stop': 'prospective-dma-stop-closure',
    'checked-context': 'prospective-checked-context-teardown',
    'first-lock-observation': 'prospective-first-lock-observation',
    'runtime-coordinator': 'prospective-runtime-coordinator',
    'retained-stop': 'prospective-retained-stop',
    'experimental-target-control': 'prospective-experimental-target-control',
}
PROFILE_DEPENDENCIES = {
    'runtime-coordinator': tuple(list(PROFILE_DIRECTORIES)[:4]),
    'retained-stop': ('runtime-coordinator',),
    'experimental-target-control': tuple(list(PROFILE_DIRECTORIES)[:6]),
}
OLD_KERNEL = GSP + 'prospective-loader/S540ProspectiveLoaderKernel.cpp'
OLD_STATE = GSP + 'prospective-loader/S540ProspectiveLoaderState.c'
OLD_KMOD = GSP + 'prospective-loader/S540ProspectiveLoaderKmod.cpp'
IDENTITY = GSP + 'prospective-retained-build-identity/S540ExperimentalBuildIdentity.c'
PROTOCOL = GSP + 'prospective-experimental-target-control/S540ExperimentalTargetProtocol.h'
POWER = GSP + 'platform/S540NvidiaGspPower.cpp'
TARGET = GSP + 'prospective-experimental-target-control/S540ExperimentalTargetKernel.cpp'
EXPERIMENTAL_POLICY = {
    'format': 1, 'scope': 'manual-once-per-boot-retained-first-initialization',
    'target_build': '25G241', 'darwin_release': '25.6.0', 'architecture': 'x86_64',
    'minimum_observed_kernel_stack_bytes': 16384,
    'assumed_irq_stack_bytes': 16384, 'irq_capacity_observed_on_target': False,
    'framework_reserve_bytes': 2048, 'unknown_subtree_reserve_bytes': 4096,
    'recursion_reserve_bytes': 1024, 'exception_reserve_bytes': 1024,
    'require_current_native_compilation_and_final_link': True,
    'reject_known_stack_demand_above_capacity': True,
    'retain_owner_module_and_pci_until_reboot': True,
    'retain_all_uncertain_or_original_visible_buffers_iovas_until_reboot': True,
    'checked_pre_original_cleanup_permitted': True,
    'physical_reclamation_authorized': False, 'ordinary_unload_after_request': False,
    'production_candidate_allowed': False, 'whole_dma_stop_proven': False,
    'kernel_stack_bound_proven': False, 'pm_30_second_shutdown_bound_proven': False,
    'pm_acknowledgement_authorized': False, 'acceleration_test': False,
}
DENIED = dict(shutdown.DENIED, production_candidate_allowed=False,
    physical_reclamation_authorized=False, kernel_stack_bound_proven=False,
    pm_30_second_shutdown_bound_proven=False, whole_dma_stop_proven=False,
    target_package_ready=False, native_ci_requested=False)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def selected_profiles(names):
    names = tuple(names)
    require(names and len(names) == len(set(names)) and set(names) <= set(PROFILE_DIRECTORIES),
            'Select unique reviewed retained trial profiles')
    for name in names:
        require(set(PROFILE_DEPENDENCIES.get(name, ())) <= set(names),
                'Missing retained trial prerequisite: ' + name)
    return tuple(name for name in PROFILE_DIRECTORIES if name in names)


def modules_for(names):
    return {name: composer.load('s540_retained_' + name.replace('-', '_'),
        ROOT / GSP / PROFILE_DIRECTORIES[name] / 'prepare.py')
        for name in selected_profiles(names)}


def companion_paths(module):
    return shutdown.companion_paths(module)


def helper_hashes(modules):
    paths = {Path(__file__), ROOT / 'builders/build_nvidia_retained_trial.py'}
    for module in modules.values():
        here = previous.ordinary(module.HERE)
        for path in [here / 'prepare.py', *sorted(here.glob('*.inc')),
                     *companion_paths(module).values(), *getattr(module, 'SOURCE_FILES', ())]:
            path = Path(path)
            path = previous.ordinary(path if path.is_absolute() else here / path)
            require(path.is_relative_to(here) and path.is_file(),
                    'Retained profile helper escaped its namespace')
            paths.add(path)
    # Bind the code which will validate the compiler/link/package evidence.
    for directory in ('prospective-aggregate-stack-closure', 'prospective-native-target-preparation',
                      'prospective-experimental-image', 'prospective-experimental-target-package'):
        here = ROOT / GSP / directory
        for path in here.rglob('*') if here.exists() else ():
            if path.is_file() and path.suffix in ('.py', '.h', '.hpp', '.c', '.cpp', '.sh'):
                paths.add(previous.ordinary(path))
    stack_contract = ROOT / GSP / 'prospective-aggregate-stack-closure/SOURCE-CONTRACT.json'
    if stack_contract.exists():
        paths.add(previous.ordinary(stack_contract))
    return {path.relative_to(ROOT).as_posix(): composer.sha(path) for path in sorted(paths)}


def verify_base(canonical_parent, integrated_base, operational_base, base):
    base = previous.ordinary(base)
    require(composer.sha(base / 'composition.json') == BASE_SHA256,
            'The exact reviewed 72b7 shutdown parent is required')
    value = shutdown.verify(canonical_parent, integrated_base, operational_base, base)
    require('retained_trial' not in value and len(value['project_translation_units']) == 62,
            'Retained experiment requires the unchanged closed 62-unit parent')
    return value


def identity_source(source_sha, policy_sha):
    def array(h):
        return ','.join('0x' + h[i:i+2] for i in range(0, len(h), 2))
    return ('/* Generated from the complete retained source plan; inventoried normally. */\n'
        '#include "../prospective-experimental-target-control/S540ExperimentalTargetProtocol.h"\n'
        'static const S540ExperimentalBuildIdentity identity = {1U,80U,{'+array(source_sha)+'},{'+
        array(policy_sha)+'},16384ULL};\n'
        'typedef char s540_identity_size[(sizeof(S540ExperimentalBuildIdentity)==80)?1:-1];\n'
        'const S540ExperimentalBuildIdentity *s540ExperimentalGetBuildIdentity(void) { return &identity; }\n')


def build_plan(base, before, names, modules, hashes):
    names = selected_profiles(names)
    require(tuple(modules) == names, 'Retained profile ordering differs')
    value = copy.deepcopy(before)
    replay = previous.OrderedSourceReplay(base, before)
    rows = {row['source']: row for row in value['project_translation_units']}
    profile = value['fixed_source_profiles']
    includes = list(before['shutdown_successor']['include_directories'])
    exports, original_exports, definitions, new_units, retired = {}, {}, {}, [], []
    initializers = set(previous.REVIEWED_INITIALIZERS)
    gate_owners = {operational.BOOT: {'pm-event', 'runtime-coordinator', 'retained-stop'},
        operational.LIFECYCLE: {'runtime-coordinator'}, OLD_KMOD: {'experimental-target-control'},
        OLD_STATE: set(), OLD_KERNEL: set()}
    for name, module in modules.items():
        for scope, inputs, transform in (
            ('project', getattr(module, 'INPUTS', ()), getattr(module, 'transforms', None)),
            ('source', getattr(module, 'ORIGINAL_INPUTS', ()), getattr(module, 'original_transforms', None))):
            require(len(inputs) == len(set(inputs)), 'Duplicate transform input')
            if not inputs:
                continue
            require(callable(transform), 'Missing declared source transform')
            require(all(path in replay.inventories[scope] for path in inputs), 'Uninventoried transform input')
            if scope == 'project':
                for path in inputs:
                    require(path not in gate_owners or name in gate_owners[path],
                            'Retained profile cannot replace this gate: ' + path)
            current = {path: replay.current(scope, path) for path in inputs}
            result = transform(current)
            require(set(result) == set(current), 'Transform changed declared input set')
            for path, text in result.items():
                require(isinstance(text, str), 'Transform must return UTF-8 source')
                replay.replace(scope, path, text, name)
        for path, source in companion_paths(module).items():
            require(path not in replay.inventories['project'], 'Companion cannot overwrite existing source')
            replay.replace('project', path, source.read_text(), name + '-companion')
        for source in getattr(module, 'RETIRED_PROJECT_UNITS', ()):
            require(name == 'experimental-target-control' and source == OLD_KERNEL and source in rows,
                    'Only the replaced old control kernel TU may be retired')
            del rows[source]
            retired.append(source)
            initializers.discard(source)
            for key in ('additional_project_exports', 'source_row_requirements', 'per_source_compile_definitions'):
                mapping = profile.get(key, {})
                for key2 in list(mapping):
                    if key2 == source or key == 'additional_project_exports' and mapping[key2] == source:
                        del mapping[key2]
        for row in getattr(module, 'PROJECT_UNITS', ()):
            require(set(row) == {'source', 'kind'} and row['kind'] in ('plain-c', 'original-c', 'cpp'),
                    'New project unit needs exact supported language')
            source = composer.checked_relative(row['source']).as_posix()
            require(source not in rows and source in replay.inventories['project'], 'Duplicate or missing new TU')
            require(Path(source).suffix == ('.cpp' if row['kind'] == 'cpp' else '.c'), 'Wrong TU language suffix')
            rows[source] = dict(row)
            new_units.append(dict(row))
            if source == TARGET:
                initializers.add(source)
        for source, symbols in getattr(module, 'EXPORTS', {}).items():
            source = composer.checked_relative(source).as_posix()
            require(source in rows or source in replay.inventories['source'] and source.endswith('.c'),
                    'New export has no compiled owner')
            require(len(symbols) == len(set(symbols)), 'Duplicate new export inventory')
            for symbol in symbols:
                require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', symbol) and
                    symbol not in profile['additional_project_exports'] and
                    symbol not in profile.get('additional_private_original_exports', {}) and
                    symbol not in exports and symbol not in original_exports, 'Duplicate or invalid new export')
                if source in rows:
                    exports[symbol] = source
                else:
                    require(symbol.startswith(composer.original.PREFIX), 'Original export lost private namespace')
                    original_exports[symbol] = source
        for source, macros in getattr(module, 'COMPILE_DEFINITIONS', {}).items():
            require(source in rows and macros and isinstance(macros, dict), 'Macro owner is not a project unit')
            merged = dict(rows[source].get('compile_definitions', {}))
            for macro, definition in macros.items():
                require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', macro) and isinstance(definition, str),
                        'Invalid compile macro')
                require(macro not in merged or merged[macro] == definition, 'Conflicting compile macro')
                merged[macro] = definition
            rows[source]['compile_definitions'] = merged
            definitions[source] = merged
        for directory in getattr(module, 'INCLUDE_DIRECTORIES', ()):
            directory = composer.checked_relative(directory).as_posix()
            require(directory.startswith('packages/') and any(p.startswith(directory + '/')
                for p in replay.inventories['project']), 'Include directory has no inventoried files')
            if directory not in includes:
                includes.append(directory)
    for path in (OLD_STATE, OLD_KERNEL):
        require(replay.current('project', path) == (base / 'project' / path).read_text(),
                'The historical idle control was changed')
    for key in ('original_entry_admission', 'hardware_admission', 'final_release_issued', 'stop_receipt_issued'):
        require(profile.get(key) is False, 'A retained source profile cannot grant ' + key)
    profile['additional_project_exports'].update(exports)
    profile.setdefault('additional_private_original_exports', {}).update(original_exports)
    for source, macros in definitions.items():
        required = dict(profile['source_row_requirements'].get(source, {}))
        required['compile_definitions'] = macros
        profile['source_row_requirements'][source] = required
        profile['per_source_compile_definitions'][source] = macros
    for row in rows.values():
        row['sha256'] = replay.inventories['project'][row['source']]['sha256']
    policy_sha = digest(EXPERIMENTAL_POLICY)
    basis = dict(format=1, original_files=replay.inventories['source'],
        project_files=replay.inventories['project'], project_translation_units=[rows[k] for k in sorted(rows)],
        helper_source_sha256=hashes, selected_profiles=list(names), policy=EXPERIMENTAL_POLICY,
        exports=exports, original_exports=original_exports, includes=includes, retired_project_units=retired)
    source_sha = digest(basis)
    if 'experimental-target-control' in names:
        require(IDENTITY not in replay.inventories['project'], 'Build identity unit must be new')
        replay.replace('project', IDENTITY, identity_source(source_sha, policy_sha), 'generated-build-identity')
        row = dict(source=IDENTITY, kind='plain-c', sha256=replay.inventories['project'][IDENTITY]['sha256'])
        rows[IDENTITY] = row
        new_units.append({'source': IDENTITY, 'kind': 'plain-c'})
        exports['s540ExperimentalGetBuildIdentity'] = IDENTITY
        profile['additional_project_exports']['s540ExperimentalGetBuildIdentity'] = IDENTITY
    profile['exact_source_replacements'].extend(replay.edits)
    value['original_files'] = replay.inventories['source']
    value['original_tree_sha256'] = composer.tree_sha(value['original_files'])
    value['project_files'] = replay.inventories['project']
    value['project_translation_units'] = [rows[k] for k in sorted(rows)]
    value['final_link'] = value['original_full_compilation'] = 'not_performed'
    value['retained_trial'] = dict(format=1, status='manual-retained-experimental-source-only',
        base_composition_sha256=BASE_SHA256, selected_profiles=list(names),
        helper_source_sha256=hashes, changes=replay.edits, added_project_translation_units=new_units,
        retired_project_units=retired, new_project_exports=exports, new_original_exports=original_exports,
        per_source_compile_definitions=definitions, include_directories=includes,
        reviewed_initializer_sources=sorted(initializers), experimental_policy=EXPERIMENTAL_POLICY,
        build_identity=dict(format=1, source_sha256=source_sha, policy_sha256=policy_sha,
            generated_source=IDENTITY, required_kernel_stack_bytes=16384,
            source_identity_excludes_only_generated_identity_source=True), **DENIED)
    for key in ('integrated_successor', 'operational_successor', 'shutdown_successor'):
        require(value[key] == before[key], 'A historical ancestor record was altered')
    return value, replay


def verify_plan(canonical_parent, integrated_base, operational_base, base, output):
    canonical_parent, integrated_base, operational_base, base, output = map(previous.ordinary,
        (canonical_parent, integrated_base, operational_base, base, output))
    require(all(output != p and not output.is_relative_to(p) and not p.is_relative_to(output)
        for p in (canonical_parent, integrated_base, operational_base, base)), 'Candidate overlaps ancestor')
    before = verify_base(canonical_parent, integrated_base, operational_base, base)
    actual = composer.verify_composition(output)
    names = selected_profiles(actual.get('retained_trial', {}).get('selected_profiles', ()))
    modules = modules_for(names)
    hashes = helper_hashes(modules)
    expected, replay = build_plan(base, before, names, modules, hashes)
    replay.verify_final(output)
    require(actual == expected, 'Retained composition differs from exact full ordered replay')
    require((output / actual['namespace']).read_bytes() == (base / before['namespace']).read_bytes(),
            'Private namespace changed')
    require(helper_hashes(modules) == hashes, 'Retained transform dependencies changed during replay')
    return before, actual


def prepare(canonical_parent, integrated_base, operational_base, base, output, names):
    names = selected_profiles(names)
    base = previous.ordinary(base)
    before = verify_base(canonical_parent, integrated_base, operational_base, base)
    modules = modules_for(names)
    hashes = helper_hashes(modules)
    value, replay = build_plan(base, before, names, modules, hashes)
    output = composer.new_output(output, [base, canonical_parent, integrated_base, operational_base])
    output.mkdir(parents=True)
    for scope in ('source', 'project'):
        shutil.copytree(base / scope, output / scope)
    shutil.copyfile(base / before['namespace'], output / before['namespace'])
    for (scope, relative), text in replay.overlays.items():
        path = output / scope / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    composer.write_json(output / 'composition.json', value)
    verify_plan(canonical_parent, integrated_base, operational_base, base, output)
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('canonical-parent', 'integrated-base', 'operational-base', 'base', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--profile', action='append', choices=tuple(PROFILE_DIRECTORIES))
    p.add_argument('--verify-only', action='store_true')
    a = p.parse_args()
    value = verify_plan(a.canonical_parent, a.integrated_base, a.operational_base, a.base, a.output)[1] if a.verify_only else prepare(
        a.canonical_parent, a.integrated_base, a.operational_base, a.base, a.output, a.profile or tuple(PROFILE_DIRECTORIES))
    print(json.dumps({'status': value['retained_trial']['status'],
        'units': len(value['project_translation_units']), 'composition_sha256': composer.sha(a.output / 'composition.json')}, sort_keys=True))


if __name__ == '__main__':
    main()
