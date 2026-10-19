#!/usr/bin/env python3
"""Verify original ABI/source evidence; no target runtime or reachability claim."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = ROOT / 'build-src/nvidia-upstream'
PACKAGE = ROOT / 'packages/nvidia-global-rm'
class CentralSystemContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.external = {r['symbol']:r for r in json.loads((PACKAGE/'EXTERNAL-CONTRACTS.json').read_text())['contracts']}
        cls.policy = json.loads((PACKAGE/'CENTRAL-POLICY-CONTRACTS.json').read_text())
        cls.firmware = json.loads((PACKAGE/'FIRMWARE-TABLE-CONTRACTS.json').read_text())
    def test_exact_policy_partition_and_original_abi(self):
        rows=self.policy['callbacks']
        self.assertEqual(len(rows),8)
        self.assertEqual(len({r['symbol'] for r in rows}),8)
        self.assertEqual(dict(Counter(r['classification'] for r in rows)),self.policy['classification_counts'])
        for r in rows:
            e=self.external[r['symbol']]
            self.assertEqual(r['original_type'],e['type'])
            self.assertEqual(r['original_declaration'],e['declaration'])
            self.assertEqual(r['namespace_symbol'],e['namespace_symbol'])
            self.assertFalse(r['operational_service_proven'])
            self.assertFalse(r['unreachable_entry_proven'])
        self.assertFalse(self.policy['validation']['production_admission'])
        self.assertFalse(self.policy['original_source_profile_modified'])
    def test_unavailable_operation_is_not_capability_completion(self):
        rows={r['symbol']:r for r in self.policy['callbacks']}
        for name in ('nv_indicate_idle','nv_indicate_not_idle'):
            self.assertEqual(rows[name]['classification'],'unavailable_runtime_pm_operation')
            self.assertEqual(rows[name]['unavailable_observer'],'increment-and-refuse')
        self.assertEqual(rows['os_pci_remove']['classification'],'unavailable_hot_remove_lifetime_guard')
        self.assertEqual(rows['os_pci_remove']['unavailable_observer'],'increment-and-fail-stop')
        self.assertEqual(rows['os_pci_remove_supported']['classification'],'selected_backend_capability')
        self.assertFalse(any(self.policy['immutable_backend_choices'].values()))
    def test_firmware_exact_abi_and_true_platform_boundary(self):
        r=self.firmware['callback'];e=self.external[r['symbol']]
        self.assertEqual(r['original_type'],e['type'])
        self.assertEqual(r['original_declaration'],e['declaration'])
        self.assertEqual(r['namespace_symbol'],e['namespace_symbol'])
        self.assertTrue(r['valid_output_initialized_to_zero_before_lookup'])
        self.assertFalse(r['actual_target_execution_proven'])
        self.assertFalse(self.firmware['validation']['physical_firmware_read_in_native_fixture'])
        self.assertFalse(self.firmware['validation']['production_admission'])
        self.assertEqual(self.firmware['bounds']['physical_end_exclusive'],1<<32)
        self.assertEqual(self.firmware['bounds']['maximum_read_chunk_bytes'],64)
        self.assertTrue(self.firmware['remaining_requirements'])
        self.assertEqual(len(self.firmware['primary_apple_sources']),3)
    def test_original_source_bytes_and_evidence_ranges(self):
        if not UPSTREAM.is_dir(): self.skipTest('Pass --upstream for pinned source verification.')
        for manifest in (self.policy,self.firmware):
            data={}
            for name,digest in manifest['source_sha256'].items():
                raw=(UPSTREAM/name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),digest,name)
                data[name]=raw.decode().splitlines()
            for r in manifest.get('callbacks',[manifest.get('callback')]):
                for e in [r['declaration_evidence'],*r['source_evidence']]:
                    low,high=e['lines'];self.assertGreater(low,0);self.assertGreaterEqual(high,low)
                    self.assertLessEqual(high,len(data[e['source']]))
    def test_firmware_read_errors_are_not_missing_feature_success(self):
        r=self.firmware['callback']
        self.assertEqual(r['null_output_status'],'NV_ERR_INVALID_STATE')
        self.assertEqual(r['absent_supported_efi_publication_status'],'NV_ERR_NOT_SUPPORTED')
        self.assertEqual(r['observed_efi_table_missing_acpi_status'],'NV_ERR_OPERATING_SYSTEM')
        self.assertIn('os_map_kernel_space',' '.join(self.firmware['remaining_requirements']))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--upstream',type=Path,default=UPSTREAM)
    args,remaining=parser.parse_known_args();UPSTREAM=args.upstream
    unittest.main(argv=[__file__,*remaining])
