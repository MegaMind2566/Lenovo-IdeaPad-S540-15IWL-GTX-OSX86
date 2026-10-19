#!/usr/bin/env python3
"""Source-only loader invariants; no kernel loading or target-link inference."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import unittest
PACKAGE=Path(__file__).resolve().parents[1]
ROOT=PACKAGE.parents[2]
UPSTREAM=None
class LoaderContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract=json.loads((PACKAGE/'LOADER-PROTOTYPE-CONTRACTS.json').read_text())
    def test_exact_reviewed_source_bytes(self):
        for name,sha in self.contract['source_sha256'].items():
            self.assertEqual(hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest(),sha,name)
    def test_request_cannot_supply_privilege_or_admission(self):
        self.assertEqual(self.contract['protocol']['request_fields'],['format','bytes','generation'])
        self.assertEqual(self.contract['protocol']['request_bytes'],16)
        self.assertEqual(self.contract['protocol']['snapshot_bytes'],64)
        self.assertFalse(self.contract['target_loader_admission_proven'])
        self.assertTrue(self.contract['entry_policy_closed'])
        self.assertFalse(self.contract['original_rm_entry_implemented'])
        self.assertFalse(self.contract['production_candidate_allowed'])
    def test_personality_has_no_pci_or_executable(self):
        info=plistlib.loads((PACKAGE/'Info.prototype.plist').read_bytes())
        self.assertTrue(info['S540SourceOnly'])
        self.assertNotIn('CFBundleExecutable',info)
        personality=info['IOKitPersonalities']['IdleControlOnly']
        self.assertEqual(personality['IOProviderClass'],'IOResources')
        self.assertNotIn('IOPCIPrimaryMatch',personality)
        self.assertNotIn('IOPCIMatch',personality)
    def test_actual_production_builder_excludes_every_prototype_source(self):
        sys.path.insert(0,str(ROOT/'builders'))
        import build_nvidia_execution
        paths=[p for group in build_nvidia_execution.project_sources() for p in group]
        self.assertFalse(any(p.is_relative_to(PACKAGE) for p in paths))
    def test_exact_original_root_and_namespace_inventory(self):
        roots=self.contract['same_image_original_roots']
        self.assertEqual(roots['count'],25)
        self.assertEqual(len(set(roots['symbols'])),25)
        self.assertFalse(roots['final_image_retention_verified'])
        self.assertNotIn('s540Global_rm_ioctl',roots['symbols'])
        self.assertNotIn('s540Global_RmIoctl',roots['symbols'])
        self.assertTrue(roots['typed_actual_header_fields'])
        if UPSTREAM:
            for name,sha in self.contract['original_header_sha256'].items():
                self.assertEqual(hashlib.sha256((UPSTREAM/name).read_bytes()).hexdigest(),sha,name)
    def test_actual_callbacks_are_not_loader_started_attestation(self):
        state=self.contract['observations']
        self.assertEqual(state['module_entry_accepted'],'actual project module-entry callback only')
        self.assertEqual(state['control_service_started'],'actual IOResources control-service start callback only')
        self.assertFalse(state['either_callback_proves_loader_command_returned_success'])
        self.assertFalse(self.contract['runtime']['legacy_cplus_runtime_used'])
        self.assertEqual(self.contract['validation']['state_checks_per_variant'],46)
if __name__=='__main__':
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--upstream',type=Path)
    args,remaining=parser.parse_known_args();UPSTREAM=args.upstream
    unittest.main(argv=[sys.argv[0],*remaining])
