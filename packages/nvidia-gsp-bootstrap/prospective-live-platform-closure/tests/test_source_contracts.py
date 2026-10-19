#!/usr/bin/env python3
"""Live ABI policy is explicit and original/provider source identities stay fixed."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
from prepare_original_controls import prepare
UPSTREAM = None


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.contract = json.loads((HERE/'SOURCE-CONTRACT.json').read_text())

    def test_exact_inputs(self):
        for name, expected in self.contract['source_sha256'].items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(), expected, name)
        for name, expected in self.contract['repository_dependency_sha256'].items():
            self.assertEqual(hashlib.sha256((REPO/name).read_bytes()).hexdigest(), expected, name)
        if UPSTREAM:
            for name, expected in self.contract['original_source_sha256'].items():
                self.assertEqual(hashlib.sha256((UPSTREAM/name).read_bytes()).hexdigest(), expected, name)

    def test_callback_contract(self):
        self.assertEqual(len(self.contract['callbacks']), 7)
        self.assertTrue(self.contract['file_failure_preserves_output'])
        self.assertTrue(self.contract['nonnull_close_and_console_calls_fail_stop'])
        self.assertEqual(self.contract['bif_identity_policy'], 'manual adapter start only; exact retained transaction nv')
        self.assertFalse(self.contract['bif_hardware_reset_safety_proved'])
        self.assertFalse(self.contract['file_operations_implemented'])
        self.assertFalse(self.contract['console_backend_implemented'])
        self.assertFalse(self.contract['production_default_changed'])
        self.assertFalse(self.contract['production_candidate_allowed'])

    def test_tampered_original(self):
        if not UPSTREAM: self.skipTest('Pinned upstream required.')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'upstream'
            for name in self.contract['original_source_sha256']:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes((UPSTREAM/name).read_bytes())
            path = root/'kernel-open/nvidia/os-interface.c'; path.write_bytes(path.read_bytes()+b'\n/* changed */\n')
            with self.assertRaisesRegex(ValueError, 'Pinned original source changed'):
                prepare(root, Path(directory)/'output')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False); parser.add_argument('--upstream', type=Path)
    args, rest = parser.parse_known_args(); UPSTREAM = args.upstream
    unittest.main(argv=[sys.argv[0], *rest])
