# SPDX-License-Identifier: MIT
"""Source and final-root preconditions for unavailable-memory refusal safety."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
UPSTREAM = None
LINK_REPORT = None
COMMENTS = re.compile(r'/\*.*?\*/|//[^\n]*', re.S)


def without_comments(text):
    return COMMENTS.sub(lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


class MemoryFailureSourceTests(unittest.TestCase):
    def test_thirteen_status_rows_cover_all_direct_sites(self):
        contract = json.loads((PACKAGE / 'MEMORY-FAILURE-CONTRACTS.json').read_text())
        self.assertEqual(contract['counts'], {'callbacks': 13, 'direct_original_call_sites': 19})
        rows = contract['callbacks']
        self.assertEqual(len({r['symbol'] for r in rows}), 13)
        self.assertEqual(sum(len(r['direct_original_call_sites']) for r in rows), 19)
        self.assertTrue(all(not r['operation_implemented'] and
                            r['unexpected_refusal_blocks_adapter_success'] for r in rows))

    def test_prospective_patch_bytes_match_audited_inputs(self):
        audit = json.loads((PACKAGE / 'prospective/MEMORY-UNWIND-AUDIT.json').read_text())
        for path, sha in audit['patch_sha256'].items():
            self.assertEqual(hashlib.sha256((PACKAGE / 'prospective' / path).read_bytes()).hexdigest(), sha)
        for key, path in [('generator_sha256', 'generate_memory_unwind.py'),
                          ('fixture_sha256', 'check_memory_unwind_bodies.c')]:
            self.assertEqual(hashlib.sha256((PACKAGE / 'prospective' / path).read_bytes()).hexdigest(),
                             audit['native_fault_controls'][key])
        self.assertFalse(audit['active_ten_overlay_profile_modified'])

    def test_pinned_original_source_hashes(self):
        if UPSTREAM is None:
            self.skipTest('Pass --upstream for original source proof.')
        for filename in ('MEMORY-FAILURE-CONTRACTS.json', 'USER-PIN-ROOT-CONTRACT.json'):
            contract = json.loads((PACKAGE / filename).read_text())
            for source, sha in contract['source_sha256'].items():
                self.assertEqual(hashlib.sha256((UPSTREAM / source).read_bytes()).hexdigest(), sha, source)

    def test_complete_escape_identifier_inventory(self):
        if UPSTREAM is None:
            self.skipTest('Pass --upstream for complete original identifier inventory.')
        contract = json.loads((PACKAGE / 'USER-PIN-ROOT-CONTRACT.json').read_text())
        expected = contract['exact_identifier_occurrences_src_nvidia_C_H_excluding_comments']
        observed = {name: [] for name in expected}
        pattern = re.compile(r'\b(?:' + '|'.join(map(re.escape, expected)) + r')\b')
        for source in sorted((UPSTREAM / 'src/nvidia').rglob('*')):
            if source.suffix not in ('.c', '.h'):
                continue
            text = without_comments(source.read_text())
            for match in pattern.finditer(text):
                observed[match[0]].append({'source': source.relative_to(UPSTREAM).as_posix(),
                    'line': text.count('\n', 0, match.start()) + 1})
        self.assertEqual(observed, expected)

    def test_project_production_has_no_escape_or_pin_reference(self):
        contract = json.loads((PACKAGE / 'USER-PIN-ROOT-CONTRACT.json').read_text())
        names = contract['required_final_link_conditions']['project_production_must_not_reference']
        pattern = re.compile(r'\b(?:s540Global_)?(?:' + '|'.join(map(re.escape, names)) + r')\b')
        for package in sorted((ROOT / 'packages').iterdir()):
            production = package / 'src'
            if not production.is_dir():
                continue
            for source in production.rglob('*'):
                if source.suffix in ('.c', '.cpp', '.h', '.hpp'):
                    self.assertIsNone(pattern.search(without_comments(source.read_text())), str(source))

    def test_final_link_has_no_escape_root_or_pin_import(self):
        if LINK_REPORT is None:
            self.skipTest('Pass --link-report from the final admitted image for the image precondition.')
        report = json.loads(LINK_REPORT.read_text())
        report = report.get('execution_closure', report)
        self.assertIn('original_roots', report)
        self.assertIn('retained_original_externals', report)
        contract = json.loads((PACKAGE / 'USER-PIN-ROOT-CONTRACT.json').read_text())
        conditions = contract['required_final_link_conditions']
        self.assertFalse(set(report['original_roots']) & set(conditions['forbidden_original_roots']))
        self.assertFalse(set(report['retained_original_externals']) &
                         set(conditions['forbidden_retained_original_externals']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--upstream', type=Path)
    parser.add_argument('--link-report', type=Path)
    args, remaining = parser.parse_known_args()
    UPSTREAM, LINK_REPORT = args.upstream, args.link_report
    unittest.main(argv=[sys.argv[0], *remaining])
