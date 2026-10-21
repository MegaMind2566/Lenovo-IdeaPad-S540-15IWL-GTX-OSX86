#!/usr/bin/env python3
"""Focused regression controls for overlapping integrated source replay."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compile_nvidia_integrated_successor import OrderedSourceReplay


class OrderedSourceReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.parent = self.root / 'parent'
        self.output = self.root / 'successor'
        for root in (self.parent, self.output):
            (root / 'project').mkdir(parents=True)
        self.original = 'record: parent\n'
        (self.parent / 'project/record.c').write_text(self.original)
        self.before = {'original_files': {}, 'project_files': {
            'record.c': {'sha256': self.sha(self.original), 'mode': '100644'}}}

    @staticmethod
    def sha(text):
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def replay_two_profiles(self):
        final = self.original + 'retained construction\nirq cancellation\n'
        (self.output / 'project/record.c').write_text(final)
        replay = OrderedSourceReplay(self.parent, self.before)
        # The successor already contains the second edit, so comparing its
        # bytes against this first intermediate value is a regression.
        first = replay.current('project', 'record.c') + 'retained construction\n'
        replay.replace('project', 'record.c', first, 'retained-construction')
        second = replay.current('project', 'record.c') + 'irq cancellation\n'
        replay.replace('project', 'record.c', second, 'irq-callback')
        return replay, first, final

    def test_overlapping_edits_keep_history_and_verify_final_bytes(self):
        replay, first, final = self.replay_two_profiles()
        replay.verify_final(self.output)
        self.assertEqual(replay.edits[0]['input_sha256'], self.sha(self.original))
        self.assertEqual(replay.edits[0]['output_sha256'], self.sha(first))
        self.assertEqual(replay.edits[1]['input_sha256'], self.sha(first))
        self.assertEqual(replay.edits[1]['output_sha256'], self.sha(final))
        self.assertEqual((self.parent / 'project/record.c').read_text(), self.original)
        self.assertEqual(self.before['project_files']['record.c']['sha256'], self.sha(self.original))

    def test_intermediate_or_tampered_bytes_do_not_pass_as_final(self):
        replay, first, _ = self.replay_two_profiles()
        for wrong in (first, 'unreviewed mutation\n'):
            with self.subTest(wrong=wrong):
                (self.output / 'project/record.c').write_text(wrong)
                with self.assertRaisesRegex(ValueError, 'final ordered transform'):
                    replay.verify_final(self.output)


if __name__ == '__main__':
    unittest.main()
