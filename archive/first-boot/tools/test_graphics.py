#!/usr/bin/env python3
"""Reversible, offline Intel VESA diagnostic for an existing OpenCore EFI."""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import plistlib

GUID = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
FLAG = '-igfxvesa'


def modified(original):
    result = copy.deepcopy(original)
    args = result['NVRAM']['Add'][GUID]['boot-args']
    if not isinstance(args, str):
        raise ValueError('boot-args must be a string.')
    if FLAG not in args.split():
        result['NVRAM']['Add'][GUID]['boot-args'] = (args + ' ' + FLAG).strip()
    if 'boot-args' not in result['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('The NVRAM boot-args rewrite is missing. Use the project EFI.')
    return result


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.graphics-test.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def apply_test(path):
    raw = path.read_bytes()
    config = plistlib.loads(raw)
    args = config['NVRAM']['Add'][GUID]['boot-args']
    if FLAG in args.split():
        print('Graphics trial already enabled. No changes.')
        return False
    new = modified(config)
    backup = path.with_name('config.before-graphics-test.plist')
    if backup.exists() and backup.read_bytes() != raw:
        raise ValueError('A backup from another configuration state exists. No changes.')
    if not backup.exists():
        backup.write_bytes(raw)
    atomic_write(path, plistlib.dumps(new, sort_keys=False))
    print('Graphics trial enabled: Intel acceleration temporarily disabled.')
    print('Backup saved beside config.plist. Reboot into Recovery for the trial.')
    return True


def restore(path):
    backup = path.with_name('config.before-graphics-test.plist')
    raw = backup.read_bytes()
    original = plistlib.loads(raw)
    current = plistlib.loads(path.read_bytes())
    if current != original and current != modified(original):
        raise ValueError('The configuration contains other changes. Automatic restore cancelled.')
    atomic_write(path, raw)
    print('Previous configuration restored. Backup retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'EFI/OC/config.plist')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if not args.config.is_file():
        raise SystemExit('EFI/OC/config.plist not found. Extract the trial to the boot disk root.')
    try:
        if args.restore:
            restore(args.config)
        else:
            apply_test(args.config)
    except (OSError, ValueError, KeyError, plistlib.InvalidFileException) as error:
        raise SystemExit('Trial not applied: ' + str(error))


if __name__ == '__main__':
    main()
