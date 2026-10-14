#!/usr/bin/env python3
"""Exclude only IntelBTPatcher from the current EFI, with a guarded rollback."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import plistlib

KEXT = 'IntelBTPatcher.kext'
BACKUP = 'config.before-bt-test.plist'


def modified(original):
    result = copy.deepcopy(original)
    entries = result['Kernel']['Add']
    if not isinstance(entries, list):
        raise ValueError('Kernel/Add must be a list.')
    matches = [entry for entry in entries if entry.get('BundlePath') == KEXT]
    if len(matches) != 1:
        raise ValueError('Exactly one IntelBTPatcher.kext entry is required. No changes made.')
    entry = matches[0]
    if not isinstance(entry.get('Enabled'), bool):
        raise ValueError('Enabled must be a boolean. No changes made.')
    entry['Enabled'] = False
    return result


def atomic_write(path, raw):
    temporary = path.with_name(path.name + '.bt-test.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def apply_test(path):
    raw = path.read_bytes()
    original = plistlib.loads(raw)
    new = modified(original)
    if new == original:
        print('IntelBTPatcher is already excluded from this configuration. No changes made.')
        return False
    backup = path.with_name(BACKUP)
    if backup.exists() and backup.read_bytes() != raw:
        raise ValueError('A backup from another configuration state already exists. No changes made.')
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(raw)
    atomic_write(path, plistlib.dumps(new, sort_keys=False))
    print('Test enabled: only IntelBTPatcher.kext was excluded from Kernel/Add.')
    print('Backup: EFI/OC/' + BACKUP)
    print('Shut down the laptop, boot from the same OpenCore and select Machintosh SSD.')
    return True


def restore(path):
    backup = path.with_name(BACKUP)
    raw = backup.read_bytes()
    original = plistlib.loads(raw)
    expected = modified(original)
    current = plistlib.loads(path.read_bytes())
    if current != original and current != expected:
        raise ValueError('Additional changes are present. Reverse tests applied after TEST-BT first.')
    atomic_write(path, raw)
    print('The previous configuration was restored. The backup is preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parents[1]/'EFI/OC/config.plist')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if not args.config.is_file():
        raise SystemExit("EFI/OC/config.plist not found. Extract the package to the boot HDD root.")
    try:
        if args.restore:
            restore(args.config)
        else:
            apply_test(args.config)
    except (OSError, ValueError, KeyError, TypeError, AttributeError,
            plistlib.InvalidFileException) as error:
        raise SystemExit('Operation not performed: ' + str(error))


if __name__ == '__main__':
    main()
