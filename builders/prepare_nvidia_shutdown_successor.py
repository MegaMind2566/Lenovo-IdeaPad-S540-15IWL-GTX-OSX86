#!/usr/bin/env python3
"""Compose reviewed stack/PM/producer follow-ups to the frozen operational base.

Every ancestor is replayed by its unchanged verifier. The operational record is
preserved as historical evidence; this child records only its own ordered edits.
No runtime, DMA-stop, stack-capacity or PM admission is granted by composition.
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
import prepare_nvidia_operational_successor as operational

ROOT = Path(__file__).resolve().parents[1]
GSP = 'packages/nvidia-gsp-bootstrap/'
BASE_SHA256 = '40f0fd1fc279421464c14f9b98f7fa84f6850e6fafb61d46aa60663ce471dd4c'
PROFILE_DIRECTORIES = {
    'stack-context': 'prospective-stack-context-closure',
    'pm-revocation': 'prospective-pm-revocation-closure',
    'dma-producer': 'prospective-dma-producer-closure'}
PROFILE_DEPENDENCIES = {'dma-producer': ('pm-revocation',)}
GATE_FILES = (operational.LIFECYCLE, operational.LOADER_GATE, operational.BOOT)
DENIED = dict(operational.DENIED, whole_dma_stop_proven=False,
              pm_acknowledgement_authorized=False, irreversible_bme_seal_proven=False)


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def selected_profiles(names) -> tuple[str, ...]:
    names = tuple(names)
    require('dma-containment' not in names,
            'Whole DMA containment remains blocked; the narrow producer profile is not a stop receipt')
    require(names and len(names) == len(set(names)) and set(names) <= set(PROFILE_DIRECTORIES),
            'Select a nonempty unique set of reviewed shutdown profiles')
    for name in names:
        require(set(PROFILE_DEPENDENCIES.get(name, ())) <= set(names),
                'Profile dependency missing: ' + name + ' requires pm-revocation')
    return tuple(name for name in PROFILE_DIRECTORIES if name in names)


def modules_for(names) -> dict:
    return {name: composer.load('s540_shutdown_' + name.replace('-', '_'),
            ROOT / GSP / PROFILE_DIRECTORIES[name] / 'prepare.py') for name in selected_profiles(names)}


def companion_paths(module) -> dict[str, Path]:
    """A companion can add only an isolated file in its own new package."""
    result = {}
    here = previous.ordinary(module.HERE)
    prefix = here.relative_to(ROOT).as_posix() + '/'
    for relative, source in getattr(module, 'COMPANIONS', {}).items():
        composer.checked_relative(relative)
        require(relative.startswith(prefix), 'A companion must remain in its owning module namespace')
        source = Path(source)
        source = previous.ordinary(source if source.is_absolute() else here / source)
        require(source.is_relative_to(here) and source.is_file(), 'Companion escaped its selected module')
        result[relative] = source
    return result


def helper_hashes(modules: dict) -> dict:
    paths = [Path(__file__), ROOT / 'builders/prepare_nvidia_operational_successor.py',
        ROOT / 'builders/compile_nvidia_integrated_successor.py',
        ROOT / 'builders/compose_nvidia_first_transaction.py']
    for module in modules.values():
        here = previous.ordinary(module.HERE)
        local = [here / 'prepare.py', *sorted(here.glob('*.inc')), *companion_paths(module).values()]
        for source in getattr(module, 'SOURCE_FILES', ()):
            source = Path(source)
            local.append(source if source.is_absolute() else here / source)
        for path in local:
            path = previous.ordinary(path)
            require(path.is_relative_to(here) and path.is_file(),
                    'Transform dependency escaped its selected module')
            paths.append(path)
    return {previous.ordinary(path).relative_to(ROOT).as_posix(): composer.sha(path) for path in paths}


def verify_base(canonical_parent: Path, integrated_base: Path, base: Path) -> dict:
    canonical_parent, integrated_base, base = map(previous.ordinary, (canonical_parent, integrated_base, base))
    require(composer.sha(base / 'composition.json') == BASE_SHA256,
            'The exact reviewed operational-successor-2 composition is required')
    _, value = operational.verify_plan(canonical_parent, integrated_base, base)
    require('shutdown_successor' not in value and len(value['project_translation_units']) == 62 and
            value['operational_successor']['selected_profiles'] ==
            ['global-result', 'irq-installation', 'rc-dispatch', 'allocator-stack'],
            'The unchanged four-profile 62-unit operational base is required')
    return value


def build_plan(base: Path, before: dict, names, modules: dict, hashes: dict):
    """Replay source edits without modifying any ancestor record or directory."""
    names = selected_profiles(names)
    require(tuple(modules) == names, 'Selected module ordering differs')
    value = copy.deepcopy(before)
    replay = previous.OrderedSourceReplay(base, before)
    rows = {row['source']: row for row in value['project_translation_units']}
    profile = value['fixed_source_profiles']
    exports, original_exports, definitions, new_units = {}, {}, {}, []
    inherited_includes = list(before['operational_successor']['include_directories'])
    require(len(inherited_includes) == len(set(inherited_includes)), 'Inherited include plan duplicates directories')
    includes = list(inherited_includes)
    for name, module in modules.items():
        for scope, inputs, transform in [
                ('project', getattr(module, 'INPUTS', ()), getattr(module, 'transforms', None)),
                ('source', getattr(module, 'ORIGINAL_INPUTS', ()), getattr(module, 'original_transforms', None))]:
            require(len(inputs) == len(set(inputs)), 'Duplicate transform input: ' + name)
            if not inputs:
                continue
            require(callable(transform), 'A declared source scope requires its exact transform')
            require(scope != 'project' or not set(inputs) & set(GATE_FILES),
                    'The global, loader and operational runtime gates are immutable')
            require(all(relative in replay.inventories[scope] for relative in inputs),
                    'A transform input is absent from the authenticated source inventory')
            values = {relative: replay.current(scope, relative) for relative in inputs}
            changed = transform(values)
            require(set(changed) == set(values), 'Transform changed its declared input set: ' + name)
            for relative, text in changed.items():
                require(isinstance(text, str), 'A source transform must return exact UTF-8 text')
                replay.replace(scope, relative, text, name)
        for relative, path in companion_paths(module).items():
            require(relative not in replay.inventories['project'],
                    'A companion cannot replace an existing authenticated file')
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
                        'Duplicate or invalid shutdown export: ' + symbol)
                if project:
                    exports[symbol] = source
                else:
                    require(symbol.startswith(composer.original.PREFIX),
                            'An original shutdown export must retain the private namespace')
                    original_exports[symbol] = source
        for source, macros in getattr(module, 'COMPILE_DEFINITIONS', {}).items():
            require(source in rows and isinstance(macros, dict) and macros,
                    'Compile definitions need an exact project unit')
            merged = dict(rows[source].get('compile_definitions', {}))
            for macro, definition in macros.items():
                require(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', macro) is not None and isinstance(definition, str),
                        'Invalid shutdown compile definition')
                require(macro not in merged or merged[macro] == definition, 'Conflicting shutdown source profile')
                merged[macro] = definition
            rows[source]['compile_definitions'] = merged
            definitions[source] = merged
        for directory in getattr(module, 'INCLUDE_DIRECTORIES', ()):
            directory = composer.checked_relative(directory).as_posix()
            require(directory.startswith('packages/') and any(
                    path.startswith(directory + '/') for path in replay.inventories['project']),
                    'Shutdown include directory has no declared project files')
            if directory not in includes:
                includes.append(directory)
        profile['shutdown_' + name.replace('-', '_') + '_preparation'] = True
    for relative in GATE_FILES:
        require(replay.current('project', relative) == (base / 'project' / relative).read_text(),
                'An exact runtime entry gate changed: ' + relative)
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
    value['shutdown_successor'] = dict(format=1, status='source-plan-only-runtime-admission-closed',
        base_composition_sha256=BASE_SHA256, inherited_operational_record_scope='historical-base-only',
        selected_profiles=list(names), helper_source_sha256=hashes, changes=replay.edits,
        added_project_translation_units=new_units, new_project_exports=exports, new_original_exports=original_exports,
        per_source_compile_definitions=definitions, inherited_include_directories=inherited_includes,
        include_directories=includes, unchanged_runtime_gate_sha256={
            relative: before['project_files'][relative]['sha256'] for relative in GATE_FILES}, **DENIED)
    require(value['operational_successor'] == before['operational_successor'],
            'The historical operational record changed')
    return value, replay


def verify_plan(canonical_parent: Path, integrated_base: Path, base: Path, output: Path) -> tuple[dict, dict]:
    canonical_parent, integrated_base, base, output = map(previous.ordinary,
        (canonical_parent, integrated_base, base, output))
    require(all(output != parent and not output.is_relative_to(parent) and not parent.is_relative_to(output)
                for parent in (canonical_parent, integrated_base, base)),
            'Shutdown companion must be isolated from every ancestor')
    before = verify_base(canonical_parent, integrated_base, base)
    actual = composer.verify_composition(output)
    record = actual.get('shutdown_successor', {})
    names = selected_profiles(record.get('selected_profiles', ()))
    modules = modules_for(names)
    hashes = helper_hashes(modules)
    expected, replay = build_plan(base, before, names, modules, hashes)
    replay.verify_final(output)
    require(actual == expected, 'Shutdown manifest differs from the complete selected-profile replay')
    require((output / actual['namespace']).read_bytes() == (base / before['namespace']).read_bytes(),
            'The private namespace changed')
    require(helper_hashes(modules) == hashes, 'Selected transform inputs changed during verification')
    return before, actual


def verify(canonical_parent: Path, integrated_base: Path, base: Path, output: Path) -> dict:
    return verify_plan(canonical_parent, integrated_base, base, output)[1]


def prepare(canonical_parent: Path, integrated_base: Path, base: Path, output: Path, names) -> dict:
    names = selected_profiles(names)
    base = previous.ordinary(base)
    before = verify_base(canonical_parent, integrated_base, base)
    modules = modules_for(names)
    hashes = helper_hashes(modules)
    value, replay = build_plan(base, before, names, modules, hashes)
    output = composer.new_output(output,
        [base, canonical_parent, integrated_base, *(module.HERE for module in modules.values())])
    output.mkdir(parents=True)
    for scope in ('source', 'project'):
        shutil.copytree(base / scope, output / scope)
    shutil.copyfile(base / before['namespace'], output / before['namespace'])
    for (scope, relative), text in replay.overlays.items():
        path = output / scope / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    composer.write_json(output / 'composition.json', value)
    after_base, after = verify_plan(canonical_parent, integrated_base, base, output)
    require(after == value and after_base == before, 'Prepared child or pinned base changed')
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('canonical-parent', 'integrated-base', 'base', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile', action='append', choices=tuple(PROFILE_DIRECTORIES))
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        value = verify(args.canonical_parent, args.integrated_base, args.base, args.output)
    else:
        if not args.profile:
            parser.error('At least one explicit --profile is required')
        value = prepare(args.canonical_parent, args.integrated_base, args.base, args.output, args.profile)
    print(json.dumps({'status': value['shutdown_successor']['status'],
                      'project_translation_units': len(value['project_translation_units']),
                      'selected_profiles': value['shutdown_successor']['selected_profiles']}, sort_keys=True))


if __name__ == '__main__':
    main()
