#!/usr/bin/env python3
"""Exercise deduplication and end-of-phase filesystem identity controls."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('s540_phase_cache', ROOT / 'builders/nvidia_selective_native_cache.py')
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class PhaseByteSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.parent = self.root / 'headers'
        self.parent.mkdir()
        self.header = self.parent / 'public.h'
        self.data = b'/* exact public header */\n'
        self.header.write_bytes(self.data)
        self.sha = digest(self.data)

    def test_repeated_edges_read_each_unique_file_only_once_then_recheck_at_finish(self):
        snapshot = cache.PhaseByteSnapshot()
        second = self.parent / 'other.h'
        second.write_bytes(b'other header')
        with patch.object(snapshot, '_read', wraps=snapshot._read) as read:
            for _ in range(10000):
                snapshot.check(self.header, self.sha)
                snapshot.check(second, digest(b'other header'))
            self.assertEqual(read.call_count, 2)
            snapshot.finish()
            self.assertEqual(read.call_count, 4)
        self.assertTrue(snapshot.finished)
        with self.assertRaisesRegex(ValueError, 'completed native byte snapshot'):
            snapshot.check(self.header, self.sha)

    def test_conflicting_cross_row_sha_is_rejected_without_another_read(self):
        snapshot = cache.PhaseByteSnapshot()
        with patch.object(snapshot, '_read', wraps=snapshot._read) as read:
            snapshot.check(self.header, self.sha)
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                snapshot.check(self.header, 'f' * 64)
            self.assertEqual(read.call_count, 1)

    def test_header_changed_after_duplicate_hit_is_caught_at_phase_end(self):
        snapshot = cache.PhaseByteSnapshot()
        snapshot.check(self.header, self.sha)
        snapshot.check(self.header, self.sha)
        self.header.write_bytes(b'changed after cached edge')
        snapshot.check(self.header, self.sha)  # duplicate edges deliberately do no I/O
        with self.assertRaisesRegex(ValueError, 'input changed'):
            snapshot.finish()

    def test_change_and_restore_bytes_and_mtime_still_changes_ctime_identity(self):
        snapshot = cache.PhaseByteSnapshot()
        snapshot.check(self.header, self.sha)
        before = self.header.stat()
        self.header.write_bytes(b'temporary changed bytes')
        self.header.write_bytes(self.data)
        os.utime(self.header, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(digest(self.header.read_bytes()), self.sha)
        self.assertEqual(self.header.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertNotEqual(self.header.stat().st_ctime_ns, before.st_ctime_ns)
        with self.assertRaisesRegex(ValueError, 'input changed'):
            snapshot.finish()

    def test_file_symlink_swap_to_identical_bytes_is_rejected(self):
        snapshot = cache.PhaseByteSnapshot()
        snapshot.check(self.header, self.sha)
        original = self.header.with_suffix('.original')
        self.header.rename(original)
        self.header.symlink_to(original.name)
        with self.assertRaisesRegex(ValueError, 'regular no-follow file'):
            snapshot.finish()

    def test_directory_symlink_swap_is_rejected(self):
        snapshot = cache.PhaseByteSnapshot()
        snapshot.check(self.header, self.sha)
        original = self.root / 'original-headers'
        self.parent.rename(original)
        self.parent.symlink_to(original.name, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'parent directory changed'):
            snapshot.finish()

    def test_plain_directory_replacement_with_identical_file_bytes_is_rejected(self):
        snapshot = cache.PhaseByteSnapshot()
        snapshot.check(self.header, self.sha)
        original = self.root / 'original-headers'
        self.parent.rename(original)
        self.parent.mkdir()
        shutil.copyfile(original / self.header.name, self.header)
        with self.assertRaisesRegex(ValueError, 'parent directory changed'):
            snapshot.finish()

    def test_leaf_replacement_between_lstat_and_open_is_rejected(self):
        snapshot = cache.PhaseByteSnapshot()
        original_open = cache.os.open
        replaced = False
        def replace_at_open(path, flags, *args, **kwargs):
            nonlocal replaced
            if path == self.header.name and not replaced:
                replaced = True
                self.header.rename(self.header.with_suffix('.original'))
                self.header.write_bytes(self.data)
            return original_open(path, flags, *args, **kwargs)
        with patch.object(cache.os, 'open', side_effect=replace_at_open):
            with self.assertRaisesRegex(ValueError, 'input changed before read'):
                snapshot.check(self.header, self.sha)
        self.assertTrue(replaced)

    def test_mutation_while_open_bytes_are_read_is_rejected(self):
        snapshot = cache.PhaseByteSnapshot()
        original_read = cache.os.read
        changed = False
        def mutate(fd, size):
            nonlocal changed
            data = original_read(fd, size)
            if not changed:
                changed = True
                self.header.write_bytes(self.data + b'new bytes')
            return data
        with patch.object(cache.os, 'read', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'input changed during read'):
                snapshot.check(self.header, self.sha)

    def test_new_phase_does_not_reuse_a_prior_snapshot(self):
        first = cache.PhaseByteSnapshot()
        first.check(self.header, self.sha)
        first.finish()
        self.header.write_bytes(b'changed before independent package verification')
        second = cache.PhaseByteSnapshot()
        with self.assertRaisesRegex(ValueError, 'input changed'):
            second.check(self.header, self.sha)


if __name__ == '__main__':
    unittest.main()
