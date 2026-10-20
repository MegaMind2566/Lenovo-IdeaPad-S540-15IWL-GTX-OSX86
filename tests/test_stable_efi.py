import importlib.util
import io
from pathlib import Path
import stat
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('stable_efi', Path(__file__).resolve().parents[1] / 'builders/build_stable_efi.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class StableArchiveTests(unittest.TestCase):
    def make_zip(self, names, symlink=False):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for name in names:
                item = zipfile.ZipInfo(name)
                if symlink:
                    item.create_system = 3
                    item.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(item, b'payload')
        return stream.getvalue()

    def test_paths_are_rejected_before_reading(self):
        for name in ('../config.plist', '/EFI/config.plist', 'EFI/../../x', 'EFI\\config.plist'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.archive(self.make_zip([name]))

    def test_duplicate_paths_and_symlinks_are_rejected(self):
        with self.assertWarns(UserWarning):
            data = self.make_zip(['same', 'same'])
        with self.assertRaises(ValueError):
            builder.archive(data)
        with self.assertRaises(ValueError):
            builder.archive(self.make_zip(['EFI/link'], symlink=True))

    def test_tampered_download_fails_hash_check(self):
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            builder.checked(b'tampered input', builder.digest(b'reviewed input'), 'input')


if __name__ == '__main__':
    unittest.main()
