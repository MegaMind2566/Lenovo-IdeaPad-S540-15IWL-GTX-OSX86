#!/usr/bin/env python3
"""Compose the integrated preparation successor, with runtime admission closed.

This is source preparation only. It neither requests native CI nor produces a
target package. Every input, overlapping source edit and extra translation unit
is recorded; the closed idle composition remains unchanged.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil

import compose_nvidia_first_transaction as composer

ROOT = Path(__file__).resolve().parents[1]
GSP = 'packages/nvidia-gsp-bootstrap/'
PROFILES = ('retained-construction', 'session-lifetime', 'irq-callback')
REQUIRED = ('retained_diagnostic', 'rc_participant', 'shutdown_protocol',
            'platform_closure', 'retained_backends', 'global_epoch',
            'live_abi_closure', 'public_callback_closure')
IRQ = GSP+'prospective-irq-callback-closure/'
IRQ_ORIGINAL = IRQ+'rc/S540NvidiaIrqOriginal.c'
RECORD = GSP+'prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
GATE_FILES = (GSP+'prospective-loader/S540ProspectiveLoaderState.c',
              'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c')
# This exact portable, relative-path manifest was independently regenerated
# from source checkpoint 06237ad9 and the authenticated closed native inputs.
# Selecting a different parent requires a separate source-contract review.
PARENT_COMPOSITION_SHA256 = '1392052eda0733713e345e938033a06c539669d4b443ba5c3104c70ae171e298'
PARENT_GATE_SHA256 = {
    GATE_FILES[0]: 'f1d95ec85bf22f10108b0245e5a24156afb2a66fda557fe269c149a0335f8204',
    GATE_FILES[1]: 'ccf6483a792dd9b0b22624ffb86e509199ebb971c9273408a7c6d9e931555f44'}
REFUSAL = '''        state.initializationStatus = NV_ERR_NOT_SUPPORTED;
        // Persistent ownership and PM revocation do not prove native ABI
        // closure, sufficient allocation capacity, original-entry cancellation
        // within the PM deadline, or a genuine kernel stack boundary for the
        // original Resource Manager. Never enter it here.
        return NV_ERR_NOT_SUPPORTED;'''


def helpers():
    result = {}
    for name in PROFILES:
        directory = ROOT/GSP/('prospective-'+name+'-closure')
        result[name] = composer.load('s540_integrated_'+name.replace('-', '_'), directory/'prepare.py')
    return result


def helper_hashes(modules):
    result = {Path(__file__).relative_to(ROOT).as_posix(): composer.sha(Path(__file__))}
    for module in modules.values():
        # Runtime control programs are separate evidence, not transform inputs.
        for path in [module.HERE/'prepare.py', *sorted(module.HERE.glob('*.inc'))]:
            result[path.relative_to(ROOT).as_posix()] = composer.sha(path)
    for relative in (GSP+'prospective-public-callback-closure/S540NvidiaPublicCallout.hpp',
                     IRQ+'S540NvidiaIrqClosure.h', IRQ+'rc/S540NvidiaIrqOriginal.h', IRQ_ORIGINAL):
        result[relative] = composer.sha(ROOT/relative)
    contract = ROOT/IRQ/'SOURCE-CONTRACT.json'
    result[contract.relative_to(ROOT).as_posix()] = composer.sha(contract)
    for name in json.loads(contract.read_text())['candidate_sha256']:
        path = contract.parent/composer.checked_relative(name)
        result[path.relative_to(ROOT).as_posix()] = composer.sha(path)
    return result


def verify_parent(parent):
    value = composer.verify_composition(parent)
    if composer.sha(parent/'composition.json') != PARENT_COMPOSITION_SHA256:
        raise ValueError('The exact reviewed closed parent composition is required')
    if value.get('integrated_successor') or not all(
            value['fixed_source_profiles'].get(name) is True for name in REQUIRED):
        raise ValueError('All eight closed public-callback parent profiles are required')
    return value


def prepare(parent: Path, output: Path) -> dict:
    parent = parent.resolve(strict=True)
    if parent.is_file():
        parent = parent.parent
    before = verify_parent(parent)
    modules = helpers()
    source_helpers = helper_hashes(modules)
    public = GSP+'prospective-public-callback-closure/S540NvidiaPublicCallout.hpp'
    output = composer.new_output(output, [parent, *(m.HERE for m in modules.values())])
    output.mkdir(parents=True)
    for directory in ('source', 'project'):
        shutil.copytree(parent/directory, output/directory)
    shutil.copyfile(parent/before['namespace'], output/before['namespace'])
    value = copy.deepcopy(before)
    edits = []

    def replace(scope, relative, text, profile):
        path = output/scope/composer.checked_relative(relative)
        old = composer.sha(path) if path.exists() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        edits.append(dict(scope=scope, source=relative, profile=profile,
                          input_sha256=old, output_sha256=composer.sha(path)))

    for name, module in modules.items():
        for scope, inputs, transform in [
                ('project', module.INPUTS, module.transforms),
                *([('source', module.ORIGINAL_INPUTS, module.original_transforms)]
                  if hasattr(module, 'ORIGINAL_INPUTS') else [])]:
            values = {path: (output/scope/path).read_text() for path in inputs}
            changed = transform(values)
            if set(changed) != set(values):
                raise ValueError('Successor changed its declared input set: '+name)
            for relative, text in changed.items():
                replace(scope, relative, text, name)
    lifetime = modules['session-lifetime']
    replace('project', lifetime.LOADER,
            lifetime.loader_transform((output/'project'/lifetime.LOADER).read_text()), 'session-lifetime-loader')
    for relative in (public, IRQ+'S540NvidiaIrqClosure.h',
                     IRQ+'rc/S540NvidiaIrqOriginal.h', IRQ_ORIGINAL):
        replace('project', relative, (ROOT/relative).read_text(), 'irq-companion')

    # Source preparation cannot install a runtime coordinator or open either
    # entry gate. Retain the exact operational and global refusal paths.
    for relative in GATE_FILES:
        if composer.sha(output/'project'/relative) != before['project_files'][relative]['sha256']:
            raise ValueError('Integrated preparation changed a runtime gate: '+relative)
    if REFUSAL not in (output/'project'/lifetime.BOOT).read_text():
        raise ValueError('Operational initialization refusal must remain intact')
    profile = value['fixed_source_profiles']
    for name in PROFILES:
        profile[name.replace('-', '_')+'_preparation'] = True
    profile['exact_source_replacements'].extend(edits)
    owners = profile['additional_project_exports']
    owners.update({name: RECORD for name in modules['retained-construction'].EXPORTS})
    for unit, symbols in modules['irq-callback'].EXPORTS.items():
        for symbol in symbols:
            if symbol in owners:
                raise ValueError('IRQ successor duplicates an existing export: '+symbol)
            owners[symbol] = unit
    owners['s540GspDiagnosticLifetimePinCount'] = lifetime.BOOT
    rows = {row['source']: row for row in value['project_translation_units']}
    if IRQ_ORIGINAL in rows:
        raise ValueError('Additional IRQ original source duplicates an existing unit')
    rows[IRQ_ORIGINAL] = dict(source=IRQ_ORIGINAL, kind='original-c')
    for relative in (modules['irq-callback'].DEVICE, IRQ_ORIGINAL):
        definitions = dict(rows[relative].get('compile_definitions', {}))
        definitions['S540_NVIDIA_IRQ_CALLBACK_CLOSURE'] = '1'
        requirements = dict(profile['source_row_requirements'].get(relative, {}))
        requirements['compile_definitions'] = definitions
        profile['source_row_requirements'][relative] = requirements
        profile['per_source_compile_definitions'][relative] = definitions
        rows[relative].update(requirements)
    for relative, row in rows.items():
        row['sha256'] = composer.sha(output/'project'/relative)
    value['project_translation_units'] = [rows[name] for name in sorted(rows)]
    value['original_files'] = composer.inventory(output/'source')
    value['original_tree_sha256'] = composer.tree_sha(value['original_files'])
    value['project_files'] = composer.inventory(output/'project')
    value['integrated_successor'] = {
        'format': 1, 'status': 'preparation-only-runtime-admission-closed',
        'parent_composition_sha256': composer.sha(parent/'composition.json'),
        'helper_source_sha256': source_helpers, 'ordered_profiles': list(PROFILES),
        'changes': edits, 'unchanged_runtime_gates': {name: before['project_files'][name]['sha256'] for name in GATE_FILES},
        'original_entry_admission': False, 'hardware_admission': False,
        'kernel_stack_bound_proven': False, 'pm_30_second_shutdown_bound_proven': False,
        'runtime_coordinator_installed': False, 'target_package_ready': False,
        'native_ci_requested': False, 'physical_reclamation_authorized': False}
    value['final_link'] = value['original_full_compilation'] = 'not_performed'
    composer.write_json(output/'composition.json', value)
    verify(output)
    if composer.verify_composition(parent) != before:
        raise ValueError('Parent composition changed during integration')
    for relative, digest in source_helpers.items():
        if composer.sha(ROOT/relative) != digest:
            raise ValueError('Successor helper changed during integration: '+relative)
    return value


def verify(output: Path) -> dict:
    value = composer.verify_composition(output)
    for name in ('original_entry_admission', 'hardware_admission', 'final_release_issued', 'stop_receipt_issued'):
        if value['fixed_source_profiles'].get(name) is not False:
            raise ValueError('Integrated source profiles cannot grant '+name)
    record = value.get('integrated_successor', {})
    if record.get('status') != 'preparation-only-runtime-admission-closed':
        raise ValueError('Integrated preparation record required')
    for name in ('original_entry_admission', 'hardware_admission', 'kernel_stack_bound_proven',
                 'pm_30_second_shutdown_bound_proven', 'runtime_coordinator_installed',
                 'target_package_ready', 'native_ci_requested', 'physical_reclamation_authorized'):
        if record.get(name) is not False:
            raise ValueError('Integrated source preparation cannot grant '+name)
    if record.get('ordered_profiles') != list(PROFILES):
        raise ValueError('Integrated profile ordering changed')
    if record.get('parent_composition_sha256') != PARENT_COMPOSITION_SHA256:
        raise ValueError('The exact reviewed closed parent composition is required')
    rows = value['project_translation_units']
    names = [row['source'] for row in rows]
    if len(rows) != 61 or len(set(names)) != 61 or names.count(IRQ_ORIGINAL) != 1:
        raise ValueError('Exactly sixty parent units plus one typed IRQ bridge required')
    for row in rows:
        if composer.sha(output/'project'/composer.checked_relative(row['source'])) != row['sha256']:
            raise ValueError('Translation unit source hash differs: '+row['source'])
    for relative in ('packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp', IRQ_ORIGINAL):
        row = next(row for row in rows if row['source'] == relative)
        expected = {'S540_NVIDIA_IRQ_CALLBACK_CLOSURE': '1'}
        definitions = row.get('compile_definitions', {})
        if any(definitions.get(key) != item for key, item in expected.items()):
            raise ValueError('Required integrated IRQ compile profile missing: '+relative)
        profile = value['fixed_source_profiles']
        if (profile['per_source_compile_definitions'].get(relative) != definitions or
                profile['source_row_requirements'][relative].get('compile_definitions') != definitions):
            raise ValueError('Integrated IRQ compile profile bindings differ: '+relative)
    if record['unchanged_runtime_gates'] != PARENT_GATE_SHA256:
        raise ValueError('Exact runtime gate bindings required')
    for name, digest in record['unchanged_runtime_gates'].items():
        if composer.sha(output/'project'/composer.checked_relative(name)) != digest:
            raise ValueError('A runtime gate changed: '+name)
    if REFUSAL not in (output/'project'/GSP/'src/S540NvidiaGspBootstrap.cpp').read_text():
        raise ValueError('Operational entry gate changed')
    if record['helper_source_sha256'] != helper_hashes(helpers()):
        raise ValueError('Successor helper changed or exact input bindings missing')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        verify(args.output.resolve(strict=True))
    else:
        if not args.composition:
            parser.error('--composition is required unless --verify-only is selected')
        prepare(args.composition, args.output)
    print('Integrated source successor verified; runtime admission remains closed.')
