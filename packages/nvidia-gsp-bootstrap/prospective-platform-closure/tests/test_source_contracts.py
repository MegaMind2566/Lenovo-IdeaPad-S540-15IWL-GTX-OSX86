#!/usr/bin/env python3
"""Pinned source identities and bounded, explicitly selected callback policy."""
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
    def setUpClass(cls):
        cls.contract = json.loads((HERE/'SOURCE-CONTRACT.json').read_text())

    def test_exact_source_and_original_identities(self):
        for name, expected in self.contract['source_sha256'].items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(), expected, name)
        for name, expected in self.contract['repository_dependency_sha256'].items():
            self.assertEqual(hashlib.sha256((REPO/name).read_bytes()).hexdigest(), expected, name)
        if UPSTREAM:
            for name, expected in self.contract['original_source_sha256'].items():
                self.assertEqual(hashlib.sha256((UPSTREAM/name).read_bytes()).hexdigest(), expected, name)

    def test_explicit_seven_callback_scope(self):
        self.assertEqual(len(self.contract['callbacks']), 7)
        self.assertFalse(self.contract['runtime_power_implemented'])
        self.assertFalse(self.contract['tegra_platform_implemented'])
        self.assertFalse(self.contract['nvlink_hardware_implemented'])
        self.assertFalse(self.contract['production_candidate_allowed'])
        self.assertFalse(self.contract['production_default_changed'])
        self.assertTrue(self.contract['non_tegra_query_preserves_output'])
        self.assertTrue(self.contract['invalid_identity_output_records_unavailable'])

    def test_original_tampering_rejected(self):
        if not UPSTREAM:
            self.skipTest('Pinned source required.')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'original'
            for name in self.contract['original_source_sha256']:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((UPSTREAM/name).read_bytes())
            path = root/'kernel-open/nvidia/nv.c'; path.write_bytes(path.read_bytes()+b'\n/* changed */\n')
            with self.assertRaisesRegex(ValueError, 'Pinned original source changed'):
                prepare(root, Path(directory)/'output')

    def test_production_compiler_does_not_implicitly_add_candidate(self):
        sys.path.insert(0, str(REPO/'builders'))
        import build_nvidia_execution
        self.assertFalse(any(path.is_relative_to(HERE) for group in build_nvidia_execution.project_sources() for path in group))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--upstream', type=Path)
    args, rest = parser.parse_known_args(); UPSTREAM = args.upstream
    unittest.main(argv=[sys.argv[0], *rest])
