#!/usr/bin/env python3
"""Adversarial controls for the actual retained source replay and identity."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compose_nvidia_first_transaction as composer
import prepare_nvidia_retained_trial as retained
import build_nvidia_retained_trial as build


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    a = p.parse_args()
    paths = build.layout(a.work.resolve(strict=True))
    value = build.verify(paths)
    manifest = paths['composition'] / 'composition.json'
    original = manifest.read_bytes()
    cases = []
    def refused(label, action):
        try:
            action()
        except (ValueError, KeyError):
            cases.append(label)
            return
        raise AssertionError('Mutation was not refused: ' + label)
    for names in (('unknown',), ('pm-event', 'pm-event'), ('retained-stop',),
                  ('experimental-target-control',), ('runtime-coordinator',)):
        refused('profile-selection-' + '-'.join(names), lambda names=names: retained.selected_profiles(names))
    def changed_manifest(label, mutate):
        modified = deepcopy(value)
        mutate(modified)
        try:
            composer.write_json(manifest, modified)
            refused(label, lambda: build.verify(paths))
        finally:
            manifest.write_bytes(original)
    changed_manifest('forged-native-admission', lambda v: v['retained_trial'].update(target_package_ready=True))
    changed_manifest('missing-compiled-unit', lambda v: v['project_translation_units'].pop())
    changed_manifest('resurrect-obsolete-kernel', lambda v: v['project_translation_units'].append(
        dict(source=retained.OLD_KERNEL, kind='cpp', sha256=v['project_files'][retained.OLD_KERNEL]['sha256'])))
    changed_manifest('forged-native-stack-proof', lambda v: v['retained_trial'].update(kernel_stack_bound_proven=True))
    changed_manifest('forged-source-identity', lambda v: v['retained_trial']['build_identity'].update(source_sha256='00'*32))
    changed_manifest('remove-transform-helper-binding', lambda v: v['retained_trial']['helper_source_sha256'].pop(
        'builders/build_nvidia_retained_trial.py'))
    # Rehash the changed file as an attacker could. The generic inventory now
    # agrees, but the exact independent source replay must still refuse it.
    for relative in (retained.IDENTITY, retained.OLD_STATE):
        source = paths['composition'] / 'project' / relative
        saved = source.read_bytes()
        modified = deepcopy(value)
        altered = saved + b'\n/* unauthorized source replacement */\n'
        source.write_bytes(altered)
        modified['project_files'][relative]['sha256'] = hashlib.sha256(altered).hexdigest()
        for row in modified['project_translation_units']:
            if row['source'] == relative:
                row['sha256'] = hashlib.sha256(altered).hexdigest()
        try:
            composer.write_json(manifest, modified)
            composer.verify_composition(paths['composition'])
            refused('rehash-source-and-manifest-' + Path(relative).name, lambda: build.verify(paths))
        finally:
            source.write_bytes(saved)
            manifest.write_bytes(original)
    assert build.verify(paths) == value
    identity = value['retained_trial']['build_identity']
    assert (paths['composition'] / 'project' / retained.IDENTITY).read_text() == retained.identity_source(
        identity['source_sha256'], identity['policy_sha256'])
    assert identity['policy_sha256'] == retained.digest(retained.EXPERIMENTAL_POLICY)
    assert value['retained_trial']['retired_project_units'] == [retained.OLD_KERNEL]
    assert value['retained_trial']['reviewed_initializer_sources'] == sorted((retained.POWER, retained.TARGET))
    print(json.dumps({'status': 'passed-actual-retained-source-replay-mutation-controls',
        'negative_controls': len(cases), 'mutations': cases,
        'source_and_manifest_restored': True, 'native_or_target_execution': False}, sort_keys=True))


if __name__ == '__main__':
    main()
