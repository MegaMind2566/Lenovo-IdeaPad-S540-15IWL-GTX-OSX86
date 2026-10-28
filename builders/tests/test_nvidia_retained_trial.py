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
    profiles = tuple(retained.PROFILE_DIRECTORIES)
    gsp_base = profiles[:profiles.index('gsp-base-pages') + 1]
    unprotected = profiles[:profiles.index('unprotected-host-memory') + 1]
    attach_witness = profiles[:profiles.index('attach-failure-witness') + 1]
    fresh_counters = profiles[:profiles.index('fresh-failure-counters') + 1]
    optional_nvlink = profiles[:profiles.index('optional-nvlink-absence') + 1]
    unavailable_witness = profiles[:profiles.index('unavailable-service-witness') + 1]
    optional_acpi = profiles[:profiles.index('optional-acpi-capability-absence') + 1]
    host_allocation = profiles[:profiles.index('host-allocation-witness') + 1]
    pci_topology = profiles[:profiles.index('pci-topology-facts') + 1]
    gsp_boot = profiles[:profiles.index('gsp-boot-contracts') + 1]
    assert retained.PROFILE_DEPENDENCIES['experimental-target-control'] == profiles[
        :profiles.index('experimental-target-control')]
    for names in (profiles, gsp_base, unprotected, attach_witness, fresh_counters,
                  optional_nvlink, unavailable_witness, optional_acpi, host_allocation,
                  pci_topology, gsp_boot):
        assert retained.selected_profiles(reversed(names)) == names
    for names in (('unknown',), ('pm-event', 'pm-event'), ('retained-stop',),
                  ('experimental-target-control',), ('runtime-coordinator',), ('preparation-observation',),
                  ('pci-memory-bars',), ('irq-source-selection',), ('gsp-base-pages',),
                  ('unprotected-host-memory',), ('attach-failure-witness',),
                  ('fresh-failure-counters',),
                  ('optional-nvlink-absence',), ('unavailable-service-witness',),
                  ('optional-acpi-capability-absence',), ('host-allocation-witness',),
                  ('pci-topology-facts',), ('gsp-boot-contracts',),
                  tuple(name for name in retained.PROFILE_DIRECTORIES if name != 'preparation-observation'),
                  tuple(name for name in retained.PROFILE_DIRECTORIES if name != 'pci-memory-bars'),
                  tuple(name for name in retained.PROFILE_DIRECTORIES if name != 'irq-source-selection'),
                  tuple(name for name in profiles if name != 'gsp-base-pages'),
                  tuple(name for name in profiles if name != 'unprotected-host-memory'),
                  tuple(name for name in profiles if name != 'attach-failure-witness'),
                  tuple(name for name in profiles if name != 'fresh-failure-counters'),
                  tuple(name for name in profiles if name != 'optional-nvlink-absence'),
                  tuple(name for name in profiles if name != 'unavailable-service-witness'),
                  tuple(name for name in profiles if name != 'optional-acpi-capability-absence'),
                  tuple(name for name in profiles if name != 'host-allocation-witness'),
                  tuple(name for name in profiles if name != 'pci-topology-facts'),
                  tuple(name for name in profiles if name != 'gsp-boot-contracts'),
                  # Omit the frontend so its prerequisites cannot mask a
                  # missing direct dependency in the memory/diagnostic chain.
                  tuple(name for name in gsp_base if name != 'irq-source-selection'),
                  tuple(name for name in unprotected if name != 'gsp-base-pages'),
                  tuple(name for name in attach_witness if name != 'unprotected-host-memory'),
                  tuple(name for name in fresh_counters if name != 'attach-failure-witness'),
                  tuple(name for name in optional_nvlink if name != 'fresh-failure-counters'),
                  tuple(name for name in unavailable_witness if name != 'optional-nvlink-absence'),
                  tuple(name for name in optional_acpi if name != 'unavailable-service-witness'),
                  tuple(name for name in host_allocation if name != 'optional-acpi-capability-absence'),
                  tuple(name for name in pci_topology if name != 'host-allocation-witness'),
                  tuple(name for name in gsp_boot if name != 'pci-topology-facts')):
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
    changed_manifest('remove-shared-function-parser-binding', lambda v: v['retained_trial']['helper_source_sha256'].pop(
        'packages/nvidia-gsp-bootstrap/cancellation/prepare_wait_candidates.py'))
    for directory in ('prospective-attach-failure-witness', 'prospective-fresh-failure-counters',
                      'prospective-optional-nvlink-absence', 'prospective-unavailable-service-witness',
                      'prospective-optional-acpi-capability-absence', 'prospective-host-allocation-witness',
                      'prospective-pci-topology-facts', 'prospective-gsp-boot-contracts'):
        changed_manifest('remove-diagnostic-transform-binding-' + directory,
            lambda v, directory=directory: v['retained_trial']['helper_source_sha256'].pop(
                retained.GSP + directory + '/prepare.py'))
    # Rehash the changed file as an attacker could. The generic inventory now
    # agrees, but the exact independent source replay must still refuse it.
    for scope, relative in (
            ('project', retained.IDENTITY), ('project', retained.OLD_STATE),
            ('project', retained.PLATFORM), ('project', retained.DARWIN_DEVICE),
            ('project', retained.GSP + 'prospective-runtime-coordinator/S540ExperimentalRuntime.h'),
            ('project', 'packages/nvidia-device-transport/src/S540NvidiaDeviceServices.cpp'),
            ('project', 'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.cpp'),
            ('project', 'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp'),
            ('project', retained.GSP + 'src/S540NvidiaGspContext.c'),
            ('project', retained.GSP + 'prospective-attach-failure-witness/S540AttachFailureWitness.c'),
            ('project', retained.GSP + 'prospective-optional-nvlink-absence/S540OptionalNvlinkAbsence.c'),
            ('project', retained.GSP + 'prospective-optional-acpi-capability-absence/S540OptionalAcpiAbsence.c'),
            ('project', retained.GSP + 'prospective-optional-acpi-capability-absence/S540OptionalAcpiAbsence.h'),
            ('project', retained.GSP + 'prospective-host-allocation-witness/S540HostAllocationDiagnostics.h'),
            ('project', retained.GSP + 'prospective-pci-topology-facts/S540PciTopology.cpp'),
            ('project', retained.GSP + 'prospective-pci-topology-facts/S540PciTopology.hpp'),
            ('project', retained.GSP + 'prospective-pci-topology-facts/S540PciTopologyFacts.h'),
            ('project', retained.GSP + 'prospective-pci-topology-facts/sdk_import_reference.cpp'),
            ('project', retained.GSP + 'prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'),
            ('project', retained.GSP + 'prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'),
            ('project', 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp'),
            ('project', 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmOs.c'),
            ('project', 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmAcpi.c'),
            ('source', 'src/nvidia/src/kernel/gpu/gsp/message_queue_cpu.c'),
            ('source', 'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c'),
            ('source', 'src/nvidia/src/kernel/gpu/gpu.c'),
            ('source', 'src/nvidia/src/kernel/platform/acpi_common.c'),
            ('source', 'src/nvidia/src/kernel/platform/chipset/chipset.c'),
            ('source', 'src/nvidia/src/kernel/platform/chipset/chipset_pcie.c'),
            ('source', 'src/nvidia/arch/nvalloc/unix/src/os.c'),
            ('source', 'src/nvidia/arch/nvalloc/unix/src/osinit.c'),
            ('source', 'src/nvidia/src/kernel/gpu_mgr/gpu_mgr.c')):
        source = paths['composition'] / scope / relative
        saved = source.read_bytes()
        modified = deepcopy(value)
        altered = saved + b'\n/* unauthorized source replacement */\n'
        source_sha = hashlib.sha256(altered).hexdigest()
        inventory = 'project_files' if scope == 'project' else 'original_files'
        modified[inventory][relative]['sha256'] = source_sha
        if scope == 'project':
            for row in modified['project_translation_units']:
                if row['source'] == relative:
                    row['sha256'] = source_sha
        else:
            modified['original_tree_sha256'] = composer.tree_sha(modified['original_files'])
        try:
            source.write_bytes(altered)
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
