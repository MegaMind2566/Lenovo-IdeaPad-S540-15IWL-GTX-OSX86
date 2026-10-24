#!/usr/bin/env python3
"""Prepare, compile, link and package one manual retained first-init trial.

Preparation is portable and source-only. Native phases require an actual Intel
Apple toolchain and do not load any code or change system security settings.
"""
from __future__ import annotations
import argparse
from copy import copy
import json
from pathlib import Path

import compose_nvidia_first_transaction as composer
import prepare_nvidia_public_callback_rebuild as closed
import prepare_nvidia_integrated_successor as integrated
import prepare_nvidia_operational_successor as operational
import prepare_nvidia_shutdown_successor as shutdown
import prepare_nvidia_retained_trial as retained

ROOT = Path(__file__).resolve().parents[1]
GSP = ROOT / 'packages/nvidia-gsp-bootstrap'
HISTORICAL_V3 = '/workspace/scratch/9046a5958dfd/nvidia-integrated-recovery/project/build/integrated-inputs/v3/source'
CANONICAL_SHA = '1392052eda0733713e345e938033a06c539669d4b443ba5c3104c70ae171e298'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def layout(work):
    return dict(canonical_parent=work / 'inputs/closed/compose-check-public',
        integrated_base=work / 'inputs/integrated', operational_base=work / 'inputs/operational',
        base=work / 'inputs/shutdown', observation_base=work / 'inputs/preparation-observation-base',
        irq_source_base=work / 'inputs/irq-source-selection-base',
        gsp_memory_base=work / 'inputs/gsp-memory-base',
        composition=work / 'inputs/retained',
        native_compilation=work / 'native', image=work / 'image', package=work / 'package')


def restore_canonical_location(canonical):
    """Preserve one historical location string without moving any source bytes.

The old parent hash contains a GPU source-manifest digest which itself contains
the historical absolute V3 source location. All 4005 original files, 186 project
files and namespace are first checked by the unchanged composer. Preserve the
complete actual-location documents, change only that metadata string, and demand
the unchanged full canonical SHA. This is not a source-hash exception.
"""
    value = composer.verify_composition(canonical)
    manifest = canonical / 'inputs/work-gpu/source-manifest.json'
    actual = json.loads(manifest.read_bytes())
    current = str((canonical.parent / 'v3/source').resolve(strict=True))
    require(actual['base_source'] == current, 'Actual generated V3 location differs')
    require(value['inputs']['gpu_source_manifest_sha256'] == composer.sha(manifest),
            'Fresh generated GPU source-manifest binding differs')
    historical = dict(actual, base_source=HISTORICAL_V3)
    require({k for k in actual if actual[k] != historical[k]} <= {'base_source'},
            'Canonical location replay changed another metadata field')
    for scope, field in (('source', 'original_files'), ('project', 'project_files')):
        require(composer.inventory(canonical / scope) == value[field], 'Source bytes changed before location replay')
    actual_document = canonical / 'composition.actual-location.json'
    actual_manifest = canonical / 'inputs/work-gpu/source-manifest.actual-location.json'
    require(not actual_document.exists() and not actual_manifest.exists(), 'Canonical location receipt must be fresh')
    actual_document.write_bytes((canonical / 'composition.json').read_bytes())
    actual_manifest.write_bytes(manifest.read_bytes())
    composer.write_json(manifest, historical)
    value['inputs']['gpu_source_manifest_sha256'] = composer.sha(manifest)
    composer.write_json(canonical / 'composition.json', value)
    require(composer.sha(canonical / 'composition.json') == CANONICAL_SHA,
            'Only the exact immutable canonical parent may be restored')
    composer.verify_composition(canonical)
    composer.write_json(canonical / 'canonical-location-replay.json', dict(format=1,
        scope='historical-metadata-location-only', historical_v3_source=HISTORICAL_V3,
        actual_v3_source=current, actual_composition_sha256=composer.sha(actual_document),
        actual_gpu_manifest_sha256=composer.sha(actual_manifest),
        canonical_composition_sha256=CANONICAL_SHA,
        canonical_gpu_manifest_sha256=composer.sha(manifest),
        original_files_unchanged=len(value['original_files']), project_files_unchanged=len(value['project_files']),
        source_or_namespace_bytes_changed=False, runtime_admission_granted=False))


def verify_canonical_location(canonical):
    value = composer.verify_composition(canonical)
    require(composer.sha(canonical / 'composition.json') == CANONICAL_SHA, 'Canonical parent changed')
    receipt = json.loads((canonical / 'canonical-location-replay.json').read_bytes())
    actual_path = canonical / 'composition.actual-location.json'
    actual_manifest_path = canonical / 'inputs/work-gpu/source-manifest.actual-location.json'
    actual = json.loads(actual_path.read_bytes())
    current = json.loads(actual_manifest_path.read_bytes())
    historical = json.loads((canonical / 'inputs/work-gpu/source-manifest.json').read_bytes())
    require(receipt['actual_composition_sha256'] == composer.sha(actual_path) and
        receipt['actual_gpu_manifest_sha256'] == composer.sha(actual_manifest_path) and
        receipt['canonical_gpu_manifest_sha256'] == composer.sha(canonical / 'inputs/work-gpu/source-manifest.json'),
        'Location replay evidence changed')
    require(current['base_source'] == str((canonical.parent / 'v3/source').resolve(strict=True)) and
        historical == dict(current, base_source=HISTORICAL_V3), 'Historical location-only metadata differs')
    expected = json.loads(json.dumps(actual))
    expected['inputs']['gpu_source_manifest_sha256'] = composer.sha(canonical / 'inputs/work-gpu/source-manifest.json')
    require(expected == value and actual['inputs']['gpu_source_manifest_sha256'] == composer.sha(actual_manifest_path),
            'A non-location canonical field changed')
    return value


def verify(paths):
    verify_canonical_location(paths['canonical_parent'])
    return retained.verify_plan(paths['canonical_parent'], paths['integrated_base'],
        paths['operational_base'], paths['base'], paths['composition'])[1]


def prepare(args, paths):
    require(not args.output.exists(), 'A fresh complete retained work directory is required')
    closed.prepare_inputs(args.cache, args.upstream, args.output / 'inputs/closed', compose_check=True)
    restore_canonical_location(paths['canonical_parent'])
    integrated.prepare(paths['canonical_parent'], paths['integrated_base'])
    operational.prepare(paths['canonical_parent'], paths['integrated_base'], paths['operational_base'],
                        tuple(operational.PROFILE_DIRECTORIES))
    shutdown.prepare(paths['canonical_parent'], paths['integrated_base'], paths['operational_base'],
                     paths['base'], tuple(shutdown.PROFILE_DIRECTORIES))
    # Exact pre-observation source fixture for CPU controls, never native admission.
    names = tuple(retained.PROFILE_DIRECTORIES)
    retained.prepare(paths['canonical_parent'], paths['integrated_base'], paths['operational_base'],
                     paths['base'], paths['observation_base'], names[:names.index('preparation-observation')])
    retained.prepare(paths['canonical_parent'], paths['integrated_base'], paths['operational_base'],
                     paths['base'], paths['irq_source_base'], names[:names.index('irq-source-selection')])
    retained.prepare(paths['canonical_parent'], paths['integrated_base'], paths['operational_base'],
                     paths['base'], paths['gsp_memory_base'], names[:names.index('gsp-base-pages')])
    retained.prepare(paths['canonical_parent'], paths['integrated_base'], paths['operational_base'],
                     paths['base'], paths['composition'], tuple(retained.PROFILE_DIRECTORIES))
    return verify(paths)


def module(directory, name):
    return composer.load('s540_retained_build_' + directory.replace('-', '_') + '_' + name,
        GSP / directory / (name + '.py'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase', choices=('prepare', 'verify', 'native', 'link', 'package', 'all'), required=True)
    for name in ('upstream', 'kernel-sdk', 'cache', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--cc', type=Path, default=Path('/usr/bin/clang'))
    p.add_argument('--cxx', type=Path, default=Path('/usr/bin/clang++'))
    p.add_argument('--llvm-objdump', type=Path)
    p.add_argument('--jobs', type=int, default=4)
    args = p.parse_args()
    require(1 <= args.jobs <= 8, 'Bounded compiler jobs must be between 1 and 8')
    for name in ('upstream', 'kernel_sdk', 'cache'):
        setattr(args, name, getattr(args, name).resolve(strict=True))
    args.output = args.output.absolute()
    paths = layout(args.output)
    if args.phase in ('native', 'link', 'package', 'all'):
        native = module('prospective-native-target-preparation', 'compile_native')
        native.native_environment(args)
    value = prepare(args, paths) if args.phase in ('prepare', 'all') else verify(paths)
    if args.phase in ('prepare', 'verify'):
        print(json.dumps(dict(status='verified-retained-source-only', units=len(value['project_translation_units']),
            composition_sha256=composer.sha(paths['composition'] / 'composition.json'), native_jobs_started=0), sort_keys=True))
        return
    current = copy(args)
    for name in ('canonical_parent', 'integrated_base', 'operational_base', 'base', 'composition', 'native_compilation'):
        setattr(current, name, paths[name])
    current.assets_dir = args.cache / 'firmware'
    includes = value['retained_trial']['include_directories']
    initializers = value['retained_trial']['reviewed_initializer_sources']
    callback = lambda: verify(paths)
    if args.phase in ('native', 'all'):
        current.output = paths['native_compilation']
        native.compile_verified_plan(current, value, callback,
            companion_include_directories=includes, reviewed_initializer_sources=initializers)
    if args.phase in ('link', 'package', 'all'):
        factory = module('prospective-aggregate-stack-closure', 'context_adapter')
        contract = factory.native_context_contract(current, value)
    if args.phase in ('link', 'all'):
        image = module('prospective-experimental-image', 'link_native')
        current.output = paths['image']
        image.link_verified_plan(current, value, callback, companion_include_directories=includes,
            reviewed_initializer_sources=initializers, **contract)
    if args.phase in ('package', 'all'):
        package = module('prospective-experimental-target-package', 'package')
        current.image_report = paths['image'] / 'experimental-image.json'
        current.image_report_sha256 = composer.sha(current.image_report)
        current.output = paths['package']
        package.package_verified_plan(current, value, callback, companion_include_directories=includes,
            reviewed_initializer_sources=initializers, **contract)
    print(json.dumps(dict(status='completed-retained-phase', phase=args.phase,
        composition_sha256=composer.sha(paths['composition'] / 'composition.json'), module_loaded=False), sort_keys=True))


if __name__ == '__main__':
    main()
