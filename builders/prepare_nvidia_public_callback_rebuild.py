#!/usr/bin/env python3
"""Prepare verified cached namespace/source inputs without running a compiler.

The old native report remains failed and immutable. Only subsequent exact
selective compilation plus all current link/package verifiers can produce a
new image. This helper never loads code, starts CI or grants runtime admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import check_nvidia_idle_resume_cache as fetch_cache
import compile_nvidia_global_rm as original
import compose_nvidia_first_transaction as composition
import prepare_nvidia_idle_image_inputs as replay
import restore_nvidia_idle_native as restore

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ('retained_diagnostic', 'rc_participant', 'shutdown_protocol',
         'platform_closure', 'retained_backends', 'global_epoch', 'live_abi_closure')
CHANGED_SOURCES = {
    'packages/nvidia-darwin-services/src/S540NvidiaDarwinTimer.cpp',
    'packages/nvidia-darwin-services/src/S540NvidiaDarwinWork.cpp'}
NEW_HEADER = 'packages/nvidia-darwin-services/src/S540NvidiaPublicCallout.hpp'
CLOSED = {'original_entry_admission': False, 'production_candidate_allowed': False,
          'hardware_admission': False, 'gpu_access': False,
          'kernel_execution': 'not_tested'}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def no_symlink(path: Path) -> None:
    require(not any(p.is_symlink() for p in (path, *path.parents)),
            'Public callback input preparation refuses symlinks: ' + str(path))


def exact(record: dict, expected: dict, label: str) -> None:
    for key, value in expected.items():
        require(type(record.get(key)) is type(value) and record[key] == value,
                'Public callback source preparation ' + label + ' differs: ' + key)


def fresh_path(path: Path, inputs: tuple[Path, ...] = ()) -> Path:
    no_symlink(path)
    path = path.resolve()
    require(not path.exists(), 'A fresh public callback preparation path is required: ' + str(path))
    for item in (*inputs, ROOT):
        item = item.resolve(strict=True)
        require(not item.is_relative_to(path) and not path.is_relative_to(item)
                or item == ROOT and path.is_relative_to(ROOT / 'build'),
                'Public callback preparation output overlaps an input: ' + str(item))
    return path


def download_cache(destination: Path) -> dict:
    """Read-only GitHub metadata/archive fetch, using the existing overlap guard."""
    require(os.environ.get('GITHUB_REPOSITORY') == fetch_cache.REPO,
            'Unexpected repository for pinned native cache download')
    destination = fresh_path(destination)
    archive = destination.parent / (destination.name + '.zip')
    no_symlink(archive)
    require(not archive.exists(), 'Pinned archive download requires a fresh file')
    fetch_cache.refuse_overlap()
    run = fetch_cache.api('actions/runs/' + str(fetch_cache.RUN))
    require(run['head_sha'] == fetch_cache.COMMIT and run['status'] == 'completed' and
            run['conclusion'] == 'failure' and
            run['path'] == '.github/workflows/build-nvidia-idle-image.yml',
            'Pinned native cache workflow provenance changed')
    artifact = fetch_cache.api('actions/artifacts/' + str(fetch_cache.ARTIFACT))
    require(artifact['name'] == 'NVIDIA-idle-image-native-validation' and
            artifact['workflow_run']['id'] == fetch_cache.RUN and
            artifact['workflow_run']['head_sha'] == fetch_cache.COMMIT and
            artifact['size_in_bytes'] == 113859952 and artifact['expired'] is False and
            artifact.get('digest') == 'sha256:' + fetch_cache.ARCHIVE_SHA,
            'Pinned native cache artifact provenance changed')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open('xb') as stream:
        subprocess.run(['gh', 'api', 'repos/' + fetch_cache.REPO + '/actions/artifacts/' +
                        str(fetch_cache.ARTIFACT) + '/zip'], stdout=stream, check=True)
    require(sha(archive) == fetch_cache.ARCHIVE_SHA, 'Downloaded pinned native archive SHA256 differs')
    fetch_cache.extract_pinned(archive, destination)
    return {'format': 1, 'status': 'downloaded-pinned-native-cache',
        'artifact_root': str(destination), 'archive': str(archive),
        'workflow_run_id': fetch_cache.RUN, 'artifact_id': fetch_cache.ARTIFACT,
        'source_commit': fetch_cache.COMMIT, 'archive_sha256': fetch_cache.ARCHIVE_SHA,
        'historical_report_sha256': fetch_cache.REPORT_SHA,
        'native_jobs_started_by_helper': 0, 'compilation_performed': False,
        'link_performed': False, 'module_loaded': False, **CLOSED}


def verify_composition_difference(baseline: dict, public: dict) -> dict:
    """Admit exactly the two callback source replacements and one new header."""
    for label, record in (('baseline', baseline), ('public callback', public)):
        exact(record, {'format': 1, 'status': 'materialized-source-only',
                       'original_file_count': 4005, **CLOSED}, label + ' composition')
        require(len(record['original_files']) == 4005 and
                len(record['project_translation_units']) == 60 and
                len({row['source'] for row in record['project_translation_units']}) == 60,
                'Source replay changed its exact original/project inventory')
        for flag in FLAGS:
            require(record['fixed_source_profiles'].get(flag) is True,
                    'Source replay lost a required closed source profile: ' + flag)
    require(baseline['fixed_source_profiles'].get('public_callback_closure', False) is False and
            public['fixed_source_profiles'].get('public_callback_closure') is True,
            'Composition comparison did not select the exact public callback successor')
    for key in ('original_files', 'original_tree_sha256', 'namespace_sha256',
                'baseline_namespace_sha256', 'namespace'):
        require(baseline[key] == public[key],
                'Public callback successor changed the original source or namespace: ' + key)
    before, after = baseline['project_files'], public['project_files']
    added = set(after) - set(before)
    removed = set(before) - set(after)
    changed = {name for name in set(before) & set(after) if before[name] != after[name]}
    require(added == {NEW_HEADER} and not removed and changed == CHANGED_SOURCES,
            'Public callback successor changed an unreviewed project input')
    old_units = {row['source']: row for row in baseline['project_translation_units']}
    new_units = {row['source']: row for row in public['project_translation_units']}
    require(set(old_units) == set(new_units) and
            all(old_units[name]['kind'] == new_units[name]['kind'] for name in old_units),
            'Public callback successor changed the translation-unit plan')
    changed_units = {name for name in old_units if old_units[name]['sha256'] != new_units[name]['sha256']}
    require(changed_units == CHANGED_SOURCES and
            all(new_units[name]['kind'] == 'cpp' for name in CHANGED_SOURCES),
            'Public callback successor must replace exactly two existing C++ translation units')
    return {'status': 'verified-two-source-public-callback-successor',
        'original_files_unchanged': 4005, 'project_translation_units': 60,
        'changed_project_sources': sorted(changed), 'added_project_headers': sorted(added),
        'new_translation_units': 0, 'namespace_unchanged': True,
        'compilation_performed': False, 'link_performed': False, **CLOSED}


def prepare_inputs(artifact: Path, upstream: Path, output: Path, *, compose_check: bool = False) -> dict:
    """Verify all old objects, regenerate namespace and replay the frozen V3."""
    no_symlink(artifact)
    artifact = artifact.resolve(strict=True)
    upstream = original._pinned_upstream(upstream)
    output = fresh_path(output, (artifact, upstream))
    evidence = restore.verify_cache(artifact, fetch_cache.REPORT_SHA, allow_failed=True)
    require(evidence['report']['status'] == 'failed', 'The independently pinned historical link must remain failed')
    output.mkdir(parents=True)
    namespace = output / 'baseline/contract/S540GlobalRmNamespace.h'
    baseline_objects = sorted((artifact / 'inputs/baseline').glob('*.o'))
    require(len(baseline_objects) == 1100, 'A complete cached raw-original namespace matrix is required')
    original.namespace_contract(baseline_objects, namespace.parent)
    require(sha(namespace) == replay.BASELINE_SHA == restore.BASELINE_SHA,
            'Regenerated baseline namespace differs from the independently pinned header')
    contract = namespace.parent / 'SOURCE-CONTRACT.json'
    cached_contract = artifact / 'inputs/baseline/contract/SOURCE-CONTRACT.json'
    require(contract.read_bytes() == cached_contract.read_bytes() and
            json.loads(contract.read_bytes()) == evidence['baseline']['namespace_contract'],
            'Regenerated baseline namespace contract changed')
    v3 = output / 'v3'
    replayed = replay.materialize_v3(upstream, namespace, v3)
    exact(replayed, {'status': 'materialized-source-only', 'source_only': True,
        'compiled': False, 'compile_report_issued': False, 'objects_reused': False,
        'original_file_count': 4005, 'hardware_admission': False,
        'original_entry_admission': False, 'production_candidate_allowed': False}, 'frozen V3 replay')
    comparison = None
    if compose_check:
        flags = dict.fromkeys(FLAGS, True)
        before = composition.materialize(upstream, v3, namespace, output / 'compose-check-baseline', **flags)
        after = composition.materialize(upstream, v3, namespace, output / 'compose-check-public',
                                        **flags, public_callback_closure=True)
        comparison = verify_composition_difference(before, after)
        composition.verify_composition(output / 'compose-check-baseline')
        composition.verify_composition(output / 'compose-check-public')
    receipt = {'format': 1, 'status': 'prepared-source-only-public-callback-inputs',
        'artifact_root': str(artifact), 'workflow_run_id': fetch_cache.RUN,
        'artifact_id': fetch_cache.ARTIFACT, 'source_commit': fetch_cache.COMMIT,
        'historical_report_sha256': fetch_cache.REPORT_SHA,
        'historical_status': evidence['report']['status'],
        'cached_complete_link_inputs_verified': len(evidence['report']['input_object_sha256']),
        'cached_baseline_objects_verified': len(baseline_objects),
        'namespace': str(namespace), 'namespace_sha256': sha(namespace),
        'namespace_contract_sha256': sha(contract),
        'v3_root': str(v3), 'v3_report_sha256': sha(v3 / 'materialized-source.json'),
        'original_source_files': replayed['original_file_count'],
        'v3_original_tree_sha256': replayed['original_tree_sha256'],
        'v3_project_tree_sha256': replayed['project_tree_sha256'],
        'composition_difference': comparison, 'helper_sha256': sha(Path(__file__)),
        'native_jobs_started_by_helper': 0, 'fresh_native_compilations': 0,
        'compilation_performed': False, 'link_performed': False,
        'module_loaded': False, 'package_allowed': False, **CLOSED}
    (output / 'public-callback-rebuild-inputs.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-cache', action='store_true')
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compose-check', action='store_true')
    args = parser.parse_args()
    if (args.upstream is None) != (args.output is None):
        parser.error('--upstream and --output must be supplied together')
    if args.upstream is None and (not args.download_cache or args.compose_check):
        parser.error('Source preparation requires --upstream and --output')
    download = download_cache(args.artifact_root) if args.download_cache else None
    receipt = (prepare_inputs(args.artifact_root, args.upstream, args.output, compose_check=args.compose_check)
               if args.upstream is not None else download)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
