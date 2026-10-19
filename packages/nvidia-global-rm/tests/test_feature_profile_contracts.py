#!/usr/bin/env python3
"""Verify feature classifications against the pinned, unmodified upstream files.

These checks validate source evidence, not a runtime reachability or device test.
The separate C harness compiles every definition against actual original headers.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = ROOT / 'build-src/nvidia-upstream'
CONTRACT = ROOT / 'packages/nvidia-global-rm/FEATURE-PROFILE-CONTRACTS.json'


def verify_sources(upstream, contract):
    if not upstream.is_dir():
        raise ValueError('pinned upstream tree is required')
    result = {}
    for source, expected in contract['source_sha256'].items():
        path = upstream / source
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('source hash changed: ' + source)
        result[source] = path.read_text().splitlines()
    return result


class FeatureProfileContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text())

    def pinned_sources(self):
        if not UPSTREAM.is_dir():
            self.skipTest('Pass --upstream to verify the pinned source bytes.')
        return verify_sources(UPSTREAM, self.contract)

    def test_exact_callback_partition_and_original_abis(self):
        external = json.loads((ROOT / 'packages/nvidia-global-rm/EXTERNAL-CONTRACTS.json').read_text())
        original = {row['symbol']: row for row in external['contracts']}
        callbacks = self.contract['callbacks']
        self.assertEqual(len(callbacks), 30)
        self.assertEqual(len({row['symbol'] for row in callbacks}), 30)
        self.assertEqual(dict(Counter(row['classification'] for row in callbacks)),
                         self.contract['classification_counts'])
        for row in callbacks:
            with self.subTest(symbol=row['symbol']):
                self.assertEqual(row['original_type'], original[row['symbol']]['type'])
                self.assertEqual(row['original_declaration'], original[row['symbol']]['declaration'])
                self.assertEqual(row['namespace_symbol'], original[row['symbol']]['namespace_symbol'])
                self.assertFalse(row['operational_service_proven'])
                self.assertFalse(row['unreachable_entry_proven'])
                self.assertTrue(row['implementation_evidence'])
                self.assertTrue(row['original_caller_evidence'])
        self.assertFalse(self.contract['validation']['production_admission'])
        self.assertFalse(self.contract['unchanged_original_profile']['modified_by_this_feature_backend'])

    def test_pinned_source_bytes_and_evidence_ranges(self):
        sources = self.pinned_sources()
        for row in self.contract['callbacks']:
            for evidence in ([row['declaration_evidence']] + row['implementation_evidence'] +
                             row['original_caller_evidence']):
                with self.subTest(symbol=row['symbol'], evidence=evidence):
                    low, high = evidence['lines']
                    self.assertGreater(low, 0)
                    self.assertGreaterEqual(high, low)
                    self.assertLessEqual(high, len(sources[evidence['source']]))
            for evidence in row['original_caller_evidence']:
                low, high = evidence['lines']
                self.assertIn(row['symbol'], '\n'.join(sources[evidence['source']][low-1:high]))

    def test_command_discriminator_and_disabled_imex_are_original_contracts(self):
        sources = self.pinned_sources()
        command_source = '\n'.join(sources['kernel-open/common/inc/nv-hypervisor.h'])
        for name, value in [('CMD_VFIO_WAKE_REMOVE_GPU', 1), ('CMD_VGPU_VFIO_PRESENT', 2),
                            ('CMD_VFIO_PCI_CORE_PRESENT', 3)]:
            self.assertRegex(command_source, r'#define\s+' + name + r'\s+' + str(value) + r'\b')
        imex = '\n'.join(sources['kernel-open/nvidia/nv-caps-imex.c'])
        self.assertRegex(imex, r'if\s*\(NVreg_ImexChannelCount\s*==\s*0\)\s*\{[^}]*return 0;')
        self.assertIn("0 - Disable IMEX using CUDA driver's fabric handles.",
                      '\n'.join(sources['kernel-open/nvidia/nv-reg.h'][922:960]))
        self.assertEqual(self.contract['immutable_backend_choices']['imex_channel_count'], 0)
        rows = {row['symbol']: row for row in self.contract['callbacks']}
        self.assertEqual(rows['os_call_vgpu_vfio']['classification'],
                         'mixed_disabled_query_and_unavailable_operation')
        for symbol in ('os_nv_cap_create_dir_entry', 'os_nv_cap_create_file_entry',
                       'os_nv_cap_destroy_entry'):
            self.assertEqual(rows[symbol]['classification'], 'provided_unavailable_operation')

    def test_changed_upstream_is_refused_before_any_feature_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            upstream = Path(directory)
            first = next(iter(self.contract['source_sha256']))
            path = upstream / first
            path.parent.mkdir(parents=True)
            path.write_text('/* explicit changed source fixture */\n')
            with self.assertRaisesRegex(ValueError, 'source hash changed'):
                verify_sources(upstream, self.contract)

    def test_unavailable_operations_remain_failures_and_caps_minor_is_not_hidden(self):
        self.assertEqual(self.contract['classification_counts']['provided_unavailable_operation'], 11)
        for row in self.contract['callbacks']:
            if row['classification'] == 'provided_unavailable_operation':
                self.assertEqual(row['unavailable_observer'], 'increment-and-refuse')
        self.assertIn('before original nvidia_caps_root guard',
                      self.contract['related_unresolved_boundary'])
        self.assertFalse(self.contract['validation']['native_user_space_fixture']['kernel_execution'])
        self.assertFalse(self.contract['validation']['native_user_space_fixture']['gpu_access'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, default=UPSTREAM)
    arguments, remaining = parser.parse_known_args()
    UPSTREAM = arguments.upstream
    unittest.main(argv=[__file__, *remaining])
