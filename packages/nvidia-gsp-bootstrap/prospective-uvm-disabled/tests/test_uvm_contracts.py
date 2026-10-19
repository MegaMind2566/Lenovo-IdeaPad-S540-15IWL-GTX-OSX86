#!/usr/bin/env python3
"""Provenance and explicit disabled-profile controls; never admit execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from prepare_original_controls import SOURCES, prepare
UPSTREAM = None

class UvmContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract = json.loads((HERE / 'UVM-DISABLED-CONTRACTS.json').read_text())
    def test_source_identity(self):
        for name, expected in self.contract['source_sha256'].items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), expected, name)
    def test_exact_original_abi_and_branch_sources(self):
        self.assertEqual(self.contract['original_source_sha256'], SOURCES)
        self.assertEqual([r['return_type'] for r in self.contract['callbacks']], ['void', 'NV_STATUS', 'void'])
        if UPSTREAM:
            for name, expected in SOURCES.items():
                self.assertEqual(hashlib.sha256((UPSTREAM / name).read_bytes()).hexdigest(), expected, name)
    def test_candidate_has_no_production_default_or_operation_claim(self):
        self.assertFalse(self.contract['uvm_integration_implemented'])
        self.assertFalse(self.contract['p2p_drain_implemented'])
        self.assertFalse(self.contract['production_candidate_allowed'])
        self.assertFalse(self.contract['production_default_changed'])
        self.assertEqual(self.contract['configuration']['required'], 'S540_NVIDIA_NO_UVM_BACKEND=1')
        self.assertTrue(self.contract['configuration']['reject_NV_UVM_ENABLE_even_if_zero'])
    def test_actual_production_sources_exclude_candidate(self):
        sys.path.insert(0, str(ROOT / 'builders'))
        import build_nvidia_execution
        paths = [p for group in build_nvidia_execution.project_sources() for p in group]
        self.assertFalse(any(p.is_relative_to(HERE) for p in paths))
    def test_tampered_original_refused(self):
        if not UPSTREAM: self.skipTest('Pinned upstream required')
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / 'tree'
            for name in SOURCES:
                target = tree / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((UPSTREAM / name).read_bytes())
            path = tree / 'kernel-open/nvidia/nv.c'
            path.write_bytes(path.read_bytes() + b'\n/* unreviewed */\n')
            with self.assertRaisesRegex(ValueError, 'Pinned original source changed'):
                prepare(tree, Path(tmp) / 'out')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--upstream', type=Path)
    args, rest = parser.parse_known_args(); UPSTREAM = args.upstream
    unittest.main(argv=[sys.argv[0], *rest])
