#!/usr/bin/env python3
"""Pinned source-pair and immutable optional fatal diagnostic policy controls."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import prepare
UPSTREAM = None


class Contracts(unittest.TestCase):
    def setUp(self):
        if UPSTREAM is None:
            self.skipTest('Pinned original source required; pass --upstream for source-pair controls.')
        self.files = {name: (UPSTREAM/name).read_text() for name in (prepare.HEADER, prepare.SOURCE)}

    def test_exact_successor_and_terminal_helpers(self):
        result = prepare.overlay(self.files)
        for name in prepare.FUNCTIONS:
            start, end, _ = prepare.function_span(result[prepare.SOURCE], name)
            code = result[prepare.SOURCE][start:end]
            self.assertIn('os_bug_check(', code)
            self.assertIn('__builtin_trap();', code)
            self.assertNotIn('NV_JOURNAL_ASSERT_FAILURE', code)
            self.assertNotIn('NV_ASSERT_PRINTF', code)
            self.assertNotIn('NV_ASSERT_LOG', code)
            status = 'status' if 'OkFailed' in name else '0'
            self.assertIn('os_bug_check('+status+', pszExpr ? pszExpr : "RM assertion failed");', code)

    def test_recoverable_check_helpers_remain_byte_identical(self):
        result = prepare.overlay(self.files)
        for name in ('nvCheckFailed', 'nvCheckOkFailed', 'nvCheckFailedNoLog', 'nvCheckOkFailedNoLog'):
            a, b, _ = prepare.function_span(self.files[prepare.SOURCE], name)
            c, d, _ = prepare.function_span(result[prepare.SOURCE], name)
            self.assertEqual(self.files[prepare.SOURCE][a:b], result[prepare.SOURCE][c:d])

    def test_source_drift_refused_for_each_complete_input(self):
        for name in self.files:
            with self.subTest(name=name):
                changed = dict(self.files)
                changed[name] += '\n'
                with self.assertRaisesRegex(ValueError, 'Original complete assertion source changed'):
                    prepare.overlay(changed)

    def test_partial_and_extra_source_pairs_refused(self):
        for pair in ({prepare.SOURCE: self.files[prepare.SOURCE]},
                     {prepare.HEADER: self.files[prepare.HEADER]},
                     {**self.files, 'other.c': ''}):
            with self.assertRaisesRegex(ValueError, 'Exact assertion source/header pair required'):
                prepare.overlay(pair)

    def test_profile_guards_and_header_macro_policy(self):
        result = prepare.overlay(self.files)
        header = result[prepare.HEADER]
        policy = prepare.HEADER_POLICY
        self.assertEqual(header.count(policy), 1)
        self.assertIn('#if !defined('+prepare.PROFILE+') || '+prepare.PROFILE+' != 1', policy)
        for condition in ('!defined(NVRM)', '!NVOS_IS_UNIX', 'NVOS_IS_LIBOS',
                          'defined(GSP_PLUGIN_BUILD)', 'defined(NVWATCH)', 'defined(NV_MODS)'):
            self.assertIn(condition, policy)
        self.assertIn('#if !(NV_PRINTF_ENABLED || NV_JOURNAL_ASSERT_ENABLE)', policy)
        self.assertEqual(policy.count('__attribute__((noreturn))'), 4)
        self.assertNotIn('NV_ASSERT_LOG(', policy)
        self.assertNotIn('NVLOG_PRINTF(', policy)
        self.assertIn('#define NV_ASSERT_FAILED_PRECOMP    NV_ASSERT_FAILED_FUNC', header)
        self.assertLess(header.index(policy), header.index('\n#ifdef __cplusplus\n}\n#endif //__cplusplus\n'))

    def test_prepare_is_fresh_nonmutating_and_deterministic(self):
        original = dict(self.files)
        expected = prepare.overlay(self.files)
        self.assertEqual(self.files, original)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'successor'
            actual = prepare.prepare(UPSTREAM, output)
            self.assertEqual(actual, expected)
            for name, text in actual.items():
                self.assertEqual((output/name).read_text(), text)
            with self.assertRaises(FileExistsError):
                prepare.prepare(UPSTREAM, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path)
    args, rest = parser.parse_known_args()
    UPSTREAM = args.upstream.resolve(strict=True) if args.upstream else None
    unittest.main(argv=[sys.argv[0], *rest])
