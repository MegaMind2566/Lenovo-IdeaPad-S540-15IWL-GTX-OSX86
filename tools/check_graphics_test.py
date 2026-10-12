#!/usr/bin/env python3
"""Check diagnostic scope, idempotence, restore, and refusal of stale backups."""
import argparse
import copy
from pathlib import Path
import plistlib
import subprocess
import tempfile
import test_graphics as graphics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=Path)
    parser.add_argument('--ocvalidate', type=Path)
    args = parser.parse_args()
    original_raw = args.config.read_bytes()
    original = plistlib.loads(original_raw)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'config.plist'
        path.write_bytes(original_raw)
        assert graphics.apply_test(path)
        backup = path.with_name('config.before-graphics-test.plist')
        assert backup.read_bytes() == original_raw
        changed = plistlib.loads(path.read_bytes())
        expected = copy.deepcopy(original)
        expected['NVRAM']['Add'][graphics.GUID]['boot-args'] += ' ' + graphics.FLAG
        assert changed == expected, 'Only the diagnostic boot argument may change'
        first_raw = path.read_bytes()
        assert not graphics.apply_test(path)
        assert path.read_bytes() == first_raw and backup.read_bytes() == original_raw
        if args.ocvalidate:
            subprocess.run([str(args.ocvalidate.resolve()), str(path)], check=True)
        graphics.restore(path)
        assert path.read_bytes() == original_raw
        edited = copy.deepcopy(original)
        edited['Misc']['Boot']['Timeout'] += 1
        path.write_bytes(plistlib.dumps(edited))
        before = path.read_bytes()
        try:
            graphics.apply_test(path)
        except ValueError:
            pass
        else:
            raise AssertionError('Stale backup must not be overwritten')
        assert path.read_bytes() == before and backup.read_bytes() == original_raw
    print('Graphics diagnostic scope, backup, repeat and restore checks passed')


if __name__ == '__main__':
    main()
