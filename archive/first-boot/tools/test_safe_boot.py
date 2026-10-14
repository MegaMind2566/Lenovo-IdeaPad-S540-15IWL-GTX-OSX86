#!/usr/bin/env python3
"""Reversible safe-boot and normal Intel diagnostics for the existing EFI."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import plistlib
import re
import shlex

GUID = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
FLAG = '-x'
BACKUP = 'config.before-safe-boot.plist'
INTEL_BACKUP = 'config.before-intel-test.plist'


def clear_intel_args(args):
    # Preserve quoted values, escaped spaces and all unrelated arguments.
    shlex.split(args)
    spans = [
        (match.start(), match.end(), match.group())
        for match in re.finditer(
            r'''(?:[^\s"'\\]|\\.|"(?:[^"\\]|\\.)*"|'[^']*')+''', args)
        if match.group() in {'-x', '-igfxvesa'}
    ]
    if not spans:
        return args, []
    pieces = []
    position = 0
    for start, end, _ in spans:
        pieces.append(args[position:start])
        position = end
    pieces.append(args[position:])
    removed = [flag for flag in ['-x', '-igfxvesa']
               if any(span[2] == flag for span in spans)]
    return ''.join(pieces).strip(), removed


def modified(original, intel=False):
    result = copy.deepcopy(original)
    args = result['NVRAM']['Add'][GUID]['boot-args']
    if not isinstance(args, str):
        raise ValueError('boot-args must be a string.')
    if 'boot-args' not in result['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('The NVRAM boot-args rewrite is missing. No changes.')
    if intel:
        result['NVRAM']['Add'][GUID]['boot-args'] = clear_intel_args(args)[0]
    else:
        if result['Booter']['Quirks'].get('EnableSafeModeSlide') is not True:
            raise ValueError('EnableSafeModeSlide is not enabled. Collect the configuration before the trial.')
        if FLAG not in args.split():
            result['NVRAM']['Add'][GUID]['boot-args'] = (args + ' ' + FLAG).strip()
    return result


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.safe-boot.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def apply_test(path, intel=False):
    raw = path.read_bytes()
    original = plistlib.loads(raw)
    new = modified(original, intel=intel)
    if new == original:
        if intel:
            print('Arguments -x and -igfxvesa are absent from this file. No changes.')
            print('Boot-args: ' + original['NVRAM']['Add'][GUID]['boot-args'])
        else:
            print('Safe boot already requested. No changes.')
        return False
    backup_name = INTEL_BACKUP if intel else BACKUP
    backup = path.with_name(backup_name)
    if backup.exists() and backup.read_bytes() != raw:
        raise ValueError('A backup from another configuration state exists. No changes.')
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(raw)
    atomic_write(path, plistlib.dumps(new, sort_keys=False))
    if intel:
        removed = clear_intel_args(original['NVRAM']['Add'][GUID]['boot-args'])[1]
        print('Intel trial enabled. Arguments removed: ' + ' '.join(removed))
    else:
        print('Trial enabled: only -x added to boot arguments.')
    print('Boot-args: ' + new['NVRAM']['Add'][GUID]['boot-args'])
    print('Backup: EFI/OC/' + backup_name)
    print('Reboot from the same OpenCore and select Macintosh SSD.')
    return True


def restore(path, intel=False):
    backup = path.with_name(INTEL_BACKUP if intel else BACKUP)
    raw = backup.read_bytes()
    original = plistlib.loads(raw)
    current = plistlib.loads(path.read_bytes())
    if current != original and current != modified(original, intel=intel):
        raise ValueError('The configuration contains other changes. Automatic restore cancelled.')
    atomic_write(path, raw)
    print('Previous configuration restored. Backup retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parents[1]/'EFI/OC/config.plist')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--restore', action='store_true')
    mode.add_argument('--intel', action='store_true')
    mode.add_argument('--restore-intel', action='store_true')
    args = parser.parse_args()
    if not args.config.is_file():
        raise SystemExit('EFI/OC/config.plist not found. Extract the package to the boot HDD root.')
    try:
        if args.restore or args.restore_intel:
            restore(args.config, intel=args.restore_intel)
        else:
            apply_test(args.config, intel=args.intel)
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException) as error:
        raise SystemExit('Operation not performed: ' + str(error))


if __name__ == '__main__':
    main()
