#!/usr/bin/env python3
"""Compose selected local follow-ups to the pinned integrated source checkpoint.

This is a source-only plan. The operational and KERNEL entry refusals remain
closed; selecting a profile does not authorize execution, linking or packaging.
The previous integrated manifest is retained as historical base evidence.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import shutil

import compose_nvidia_first_transaction as composer
import compile_nvidia_integrated_successor as previous
import prepare_nvidia_integrated_successor as integrated

ROOT = Path(__file__).resolve().parents[1]
GSP = 'packages/nvidia-gsp-bootstrap/'
BASE_SHA256 = 'fcf44e804e1308c37b39f2d25c207434d06fd0b60b9fc9624453bcef1b2d8590'
PROFILE_DIRECTORIES = {
    'global-result': 'prospective-global-result-closure',
    'irq-installation': 'prospective-irq-installation',
    'rc-dispatch': 'prospective-rc-dispatch-closure',
    'allocator-stack': 'prospective-allocator-stack-closure'}
LIFECYCLE = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
LOADER_GATE = GSP + 'prospective-loader/S540ProspectiveLoaderState.c'
BOOT = GSP + 'src/S540NvidiaGspBootstrap.cpp'
DENIED = dict(original_entry_admission=False, hardware_admission=False,
              production_candidate_allowed=False, kernel_stack_bound_proven=False,
              pm_30_second_shutdown_bound_proven=False, runtime_coordinator_installed=False,
              target_package_ready=False, native_ci_requested=False,
              physical_reclamation_authorized=False, final_release_issued=False,
              stop_receipt_issued=False, kernel_execution='not_tested', gpu_access=False)


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def selected_profiles(names) -> tuple[str, ...]:
    names = tuple(names)
    require('dma-containment' not in names,
            'DMA containment is blocked: the original BAR0 BME writer bypass remains unresolved')
    require(names and len(names) == len(set(names)) and set(names) <= set(PROFILE_DIRECTORIES),
            'Select a nonempty unique set of reviewed operational profiles')
    return tuple(name for name in PROFILE_DIRECTORIES if name in names)


def modules_for(names) -> dict:
    return {name: composer.load('s540_operational_' + name.replace('-', '_'),
            ROOT / GSP / PROFILE_DIRECTORIES[name] / 'prepare.py') for name in selected_profiles(names)}


def companion_paths(module) -> dict[str, Path]:
    result = {}
    here = previous.ordinary(module.HERE)
    for relative, source in getattr(module, 'COMPANIONS', {}).items():
        composer.checked_relative(relative)
        require(relative.startswith('packages/'), 'A companion must be a project-relative package source')
        source = Path(source)
        source = previous.ordinary(source if source.is_absolute() else here / source)
        require(source.is_relative_to(here) and source.is_file(), 'Companion escaped its selected module')
        result[relative] = source
    return result


def helper_hashes(modules: dict) -> dict:
    result = {Path(__file__).relative_to(ROOT).as_posix(): composer.sha(Path(__file__))}
    for module in modules.values():
        here = previous.ordinary(module.HERE)
        paths = [here / 'prepare.py', *here.glob('*.inc'), *companion_paths(module).values()]
        for source in getattr(module, 'SOURCE_FILES', ()):
            source = Path(source)
            paths.append(source if source.is_absolute() else here / source)
        for path in paths:
            path = previous.ordinary(path)
            require(path.is_relative_to(here), 'Transform dependency escaped its selected module')
            result[path.relative_to(ROOT).as_posix()] = composer.sha(path)
    return result


def verify_base(canonical_parent: Path, base: Path) -> dict:
    canonical_parent, base = previous.ordinary(canonical_parent), previous.ordinary(base)
    require(composer.sha(base / 'composition.json') == BASE_SHA256,
            'The exact reviewed integrated-successor-5 composition is required')
    _, value = previous.verify_provenance(canonical_parent, base)
    require('operational_successor' not in value and len(value['project_translation_units']) == 61,
            'An unchanged 61-unit integrated base is required')
    return value


def lifecycle_guard(before: str, after: str) -> None:
    start = 'NV_STATUS s540GlobalRmInitialize('
    marker = '    status=coreInitializeRm();'
    require(before.count(start) == after.count(start) == 1 and
            before.count(marker) == after.count(marker) == 1, 'Exact global initialization boundary required')
    old = before[before.index(start):before.index(marker) + len(marker)]
    new = after[after.index(start):after.index(marker) + len(marker)]
    require(old == new, 'The pre-original global/KERNEL refusal boundary changed')


def build_plan(base: Path, before: dict, names, modules: dict, hashes: dict) -> tuple[dict, previous.OrderedSourceReplay]:
    """Replay selected modules in memory, then construct their complete manifest."""
    names = selected_profiles(names)
    require(tuple(modules) == names, 'Selected module ordering differs')
    value = copy.deepcopy(before)
    replay = previous.OrderedSourceReplay(base, before)
    rows = {row['source']: row for row in value['project_translation_units']}
    profile = value['fixed_source_profiles']
    exports, original_exports, definitions, includes, new_units = {}, {}, {}, [], []
    for name, module in modules.items():
        for scope, inputs, transform in [
                ('project', getattr(module, 'INPUTS', ()), getattr(module, 'transforms', None)),
                ('source', getattr(module, 'ORIGINAL_INPUTS', ()), getattr(module, 'original_transforms', None))]:
            require(len(inputs) == len(set(inputs)), 'Duplicate transform input: ' + name)
            if not inputs:
                continue
            require(callable(transform), 'A declared source scope requires its exact transform')
            require(scope != 'project' or LIFECYCLE not in inputs or name == 'global-result',
                    'Only the reviewed global-result transform may change the lifecycle gate source')
            require(scope != 'project' or LOADER_GATE not in inputs, 'The loader entry gate is immutable')
            values = {relative: replay.current(scope, relative) for relative in inputs}
            changed = transform(values)
            require(set(changed) == set(values), 'Transform changed its declared input set: ' + name)
            for relative, text in changed.items():
                replay.replace(scope, relative, text, name)
        for relative, path in companion_paths(module).items():
            require(relative not in (LIFECYCLE, LOADER_GATE, BOOT), 'A companion cannot replace a runtime gate')
            replay.replace('project', relative, path.read_text(), name + '-companion')
        for row in getattr(module, 'PROJECT_UNITS', ()):
            require(set(row) == {'source', 'kind'} and row['kind'] in ('plain-c', 'original-c', 'cpp'),
                    'A new translation unit requires exact source and supported kind')
            relative = composer.checked_relative(row['source']).as_posix()
            require(relative not in rows and relative in replay.inventories['project'],
                    'New project translation unit duplicates or lacks a declared source')
            require(Path(relative).suffix == ('.cpp' if row['kind'] == 'cpp' else '.c'),
                    'New translation-unit suffix differs from its language kind')
            rows[relative] = dict(row)
            new_units.append(dict(row))
        for source, symbols in getattr(module, 'EXPORTS', {}).items():
            source = composer.checked_relative(source).as_posix()
            project = source in rows
            require((project or source.endswith('.c') and source in replay.inventories['source']) and
                    len(symbols) == len(set(symbols)), 'Invalid new export owner inventory')
            for symbol in symbols:
                require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', symbol) is not None and
                        symbol not in profile['additional_project_exports'] and
                        symbol not in profile.get('additional_private_original_exports', {}) and
                        symbol not in exports and symbol not in original_exports,
                        'Duplicate or invalid operational export: ' + symbol)
                if project:
                    exports[symbol] = source
                else:
                    require(symbol.startswith(composer.original.PREFIX),
                            'An original operational export must retain the private namespace')
                    original_exports[symbol] = source
        for source, macros in getattr(module, 'COMPILE_DEFINITIONS', {}).items():
            require(source in rows and isinstance(macros, dict) and macros, 'Compile definitions need an exact project unit')
            merged = dict(rows[source].get('compile_definitions', {}))
            for macro, definition in macros.items():
                require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', macro) is not None and isinstance(definition, str),
                        'Invalid operational compile definition')
                require(macro not in merged or merged[macro] == definition, 'Conflicting operational source profile')
                merged[macro] = definition
            rows[source]['compile_definitions'] = merged
            definitions[source] = merged
        for directory in getattr(module, 'INCLUDE_DIRECTORIES', ()):
            directory = composer.checked_relative(directory).as_posix()
            require(directory.startswith('packages/') and any(
                    path.startswith(directory + '/') for path in replay.inventories['project']),
                    'Operational include directory has no declared project files')
            if directory not in includes:
                includes.append(directory)
        profile['operational_' + name.replace('-', '_') + '_preparation'] = True
    lifecycle_guard((base / 'project' / LIFECYCLE).read_text(), replay.current('project', LIFECYCLE))
    require(replay.current('project', LOADER_GATE) == (base / 'project' / LOADER_GATE).read_text(),
            'The exact loader entry gate changed')
    require(integrated.REFUSAL in replay.current('project', BOOT), 'The operational initialization refusal changed')
    for key in ('original_entry_admission', 'hardware_admission', 'final_release_issued', 'stop_receipt_issued'):
        require(profile.get(key) is False, 'Source profiles cannot grant ' + key)
    profile['additional_project_exports'].update(exports)
    if original_exports:
        profile.setdefault('additional_private_original_exports', {}).update(original_exports)
    for source, macros in definitions.items():
        requirements = dict(profile['source_row_requirements'].get(source, {}))
        requirements['compile_definitions'] = macros
        profile['source_row_requirements'][source] = requirements
        profile['per_source_compile_definitions'][source] = macros
    for source, row in rows.items():
        row['sha256'] = replay.inventories['project'][source]['sha256']
    profile['exact_source_replacements'].extend(replay.edits)
    value['original_files'] = replay.inventories['source']
    value['original_tree_sha256'] = composer.tree_sha(value['original_files'])
    value['project_files'] = replay.inventories['project']
    value['project_translation_units'] = [rows[name] for name in sorted(rows)]
    value['final_link'] = value['original_full_compilation'] = 'not_performed'
    value['operational_successor'] = dict(format=1, status='source-plan-only-runtime-admission-closed',
        base_composition_sha256=BASE_SHA256, inherited_integrated_record_scope='historical-base-only',
        selected_profiles=list(names), helper_source_sha256=hashes, changes=replay.edits,
        added_project_translation_units=new_units, new_project_exports=exports,
        new_original_exports=original_exports,
        per_source_compile_definitions=definitions, include_directories=includes,
        pre_original_global_guard_preserved=True, loader_entry_gate_sha256=before['project_files'][LOADER_GATE]['sha256'],
        operational_refusal_preserved=True, **DENIED)
    return value, replay


def verify_plan(canonical_parent: Path, base: Path, output: Path) -> tuple[dict, dict]:
    canonical_parent, base, output = map(previous.ordinary, (canonical_parent, base, output))
    require(all(output != item and not output.is_relative_to(item) and not item.is_relative_to(output)
                for item in (canonical_parent, base)), 'Operational companion must be isolated from both parents')
    before = verify_base(canonical_parent, base)
    actual = composer.verify_composition(output)
    record = actual.get('operational_successor', {})
    names = selected_profiles(record.get('selected_profiles', ()))
    modules = modules_for(names)
    hashes = helper_hashes(modules)
    expected, replay = build_plan(base, before, names, modules, hashes)
    replay.verify_final(output)
    require(actual == expected, 'Operational manifest differs from the complete selected-profile replay')
    require((output / actual['namespace']).read_bytes() == (base / before['namespace']).read_bytes(),
            'The private namespace changed')
    require(helper_hashes(modules) == hashes, 'Selected transform inputs changed during verification')
    return before, actual


def verify(canonical_parent: Path, base: Path, output: Path) -> dict:
    return verify_plan(canonical_parent, base, output)[1]


def prepare(canonical_parent: Path, base: Path, output: Path, names) -> dict:
    names = selected_profiles(names)
    base = previous.ordinary(base)
    before = verify_base(canonical_parent, base)
    modules = modules_for(names)
    hashes = helper_hashes(modules)
    value, replay = build_plan(base, before, names, modules, hashes)
    output = composer.new_output(output, [base, canonical_parent, *(module.HERE for module in modules.values())])
    output.mkdir(parents=True)
    for scope in ('source', 'project'):
        shutil.copytree(base / scope, output / scope)
    shutil.copyfile(base / before['namespace'], output / before['namespace'])
    for (scope, relative), text in replay.overlays.items():
        path = output / scope / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    composer.write_json(output / 'composition.json', value)
    after_base, after = verify_plan(canonical_parent, base, output)
    require(after == value, 'Prepared source plan changed')
    require(after_base == before, 'The pinned base changed during preparation')
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('canonical-parent', 'base', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile', action='append', choices=tuple(PROFILE_DIRECTORIES))
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        value = verify(args.canonical_parent, args.base, args.output)
    else:
        if not args.profile:
            parser.error('At least one explicit --profile is required')
        value = prepare(args.canonical_parent, args.base, args.output, args.profile)
    print(json.dumps({'status': value['operational_successor']['status'],
                      'project_translation_units': len(value['project_translation_units']),
                      'selected_profiles': value['operational_successor']['selected_profiles']}, sort_keys=True))


if __name__ == '__main__':
    main()
