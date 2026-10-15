#!/usr/bin/env python3
"""Check exact external declarations and the fail-closed generation boundary."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('global_refusals', ROOT / 'generate_refusals.py')
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class ExternalContracts(unittest.TestCase):
    def test_exact_inventory(self):
        record = json.loads((ROOT / 'EXTERNAL-CONTRACTS.json').read_text())
        names = [entry['symbol'] for entry in record['contracts']]
        self.assertEqual(len(names), 244)
        self.assertEqual(len(set(names)), 244)
        self.assertEqual(len(record['source_sha256']), 4)
        for entry in record['contracts']:
            self.assertIn(entry['source'], record['source_sha256'])
            self.assertTrue(entry['declaration'].endswith(';'))
            self.assertGreater(entry['line'], 0)

    def test_only_failure_return_types_are_generated(self):
        source, report = GENERATOR.generate(set())
        self.assertEqual(len(report['failure_bindings']), 113)
        self.assertEqual(len(report['blocked_scalar_or_void']), 119)
        self.assertEqual(len(report['blocked_data']), 12)
        self.assertFalse(report['entry_allowed'])
        self.assertNotIn('return NV_OK;', source)
        self.assertNotIn('return 0;', source)
        self.assertNotIn('return NV_FALSE;', source)
        for name in report['blocked_scalar_or_void']:
            self.assertNotRegex(source, r'\b' + re.escape(name) + r'\s*\(')

    def test_selected_implementation_is_not_redefined(self):
        source, report = GENERATOR.generate({'nv_alloc_pages', 'nv_get_firmware'})
        self.assertNotIn('nv_alloc_pages', report['failure_bindings'])
        self.assertNotIn('nv_get_firmware', report['failure_bindings'])
        self.assertNotRegex(source, r'\bnv_alloc_pages\s*\(')
        self.assertEqual(len(report['failure_bindings']), 111)

    def test_unknown_implementation_is_refused(self):
        with self.assertRaises(ValueError):
            GENERATOR.generate({'invented_successful_gpu_service'})

    def test_complex_parameter_declaration(self):
        self.assertEqual(GENERATOR.parameter('void (*)(void *)', 'p0'), 'void (*p0)(void *)')
        self.assertEqual(GENERATOR.parameter('NvU8 [16]', 'p1'), 'NvU8 p1[16]')


if __name__ == '__main__':
    unittest.main()
