#!/usr/bin/env python3
"""Temporarily add VESA for Recovery without replacing the current Intel EFI."""
import argparse
import copy
import os
from pathlib import Path
import plistlib
import re
import shlex
import tempfile

GUID = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
FLAG = '-igfxvesa'
BACKUP = 'config.before-runtime-logs.plist'


def validate(config):
    args = config['NVRAM']['Add'][GUID]['boot-args']
    if not isinstance(args, str):
        raise ValueError('boot-args must be a string.')
    shlex.split(args)
    if 'boot-args' not in config['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('NVRAM/Delete/boot-args is missing. No changes.')
    patchers = [entry for entry in config['Kernel']['Add']
                if entry.get('BundlePath', '').replace('\\', '/').split('/')[-1].casefold() == 'intelbtpatcher.kext']
    if len(patchers) != 1 or patchers[0].get('Enabled') is not False:
        raise ValueError('IntelBTPatcher must remain disabled. No changes.')
    return args


def has_vesa(args):
    return any(token.group() == FLAG for token in re.finditer(
        r'''(?:[^\s"'\\]|\\.|"(?:[^"\\]|\\.)*"|'[^']*')+''', args))


def modified(original):
    args = validate(original)
    result = copy.deepcopy(original)
    if not has_vesa(args):
        separator = '' if not args or args[-1].isspace() else ' '
        result['NVRAM']['Add'][GUID]['boot-args'] = args + separator + FLAG
    return result


def atomic_write(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.runtime-logs-',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def backup_state(path):
    raw = path.read_bytes()
    original = plistlib.loads(raw)
    if has_vesa(validate(original)):
        raise ValueError('The backup already contains VESA and does not identify the preceding trial. No changes.')
    return raw, original


def prepare(path):
    raw = path.read_bytes()
    current = plistlib.loads(raw)
    args = validate(current)
    backup = path.with_name(BACKUP)
    if backup.exists():
        _, original = backup_state(backup)
        expected = modified(original)
        if current == expected:
            print('Recovery already prepared. Previous backup retained.')
            return False
        if current != original:
            raise ValueError('The backup belongs to another EFI state. No changes.')
    elif has_vesa(args):
        raise ValueError('VESA is already present without this trial backup. No changes.')
    else:
        with backup.open('xb') as stream:
            stream.write(raw)
    if path.read_bytes() != raw:
        raise ValueError('The configuration changed during preparation. Configuration unchanged.')
    atomic_write(path, plistlib.dumps(modified(current), sort_keys=False))
    print('Recovery prepared: only -igfxvesa added.')
    print('Previous configuration retained in EFI/OC/' + BACKUP)
    print('Intel properties, Bluetooth, and other settings are preserved.')
    return True


def restore(path):
    backup = path.with_name(BACKUP)
    if not backup.exists():
        raise ValueError('Trial backup missing. No changes.')
    original_raw, original = backup_state(backup)
    current_raw = path.read_bytes()
    current = plistlib.loads(current_raw)
    validate(current)
    if current != original and current != modified(original):
        raise ValueError('The EFI contains other changes. Automatic restore cancelled.')
    if path.read_bytes() != current_raw:
        raise ValueError('The configuration changed during the check. Restore cancelled.')
    atomic_write(path, original_raw)
    print('Configuration preceding collection restored byte for byte.')
    print('Intel properties and the disabled IntelBTPatcher state are preserved.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true')
    options = parser.parse_args()
    path = Path(__file__).resolve().parent.parent / 'EFI' / 'OC' / 'config.plist'
    if not path.is_file():
        raise ValueError('Extract the package to the OpenCore HDD root, alongside EFI.')
    return restore(path) if options.restore else prepare(path)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException) as error:
        print('Operation not performed:', error)
        raise SystemExit(1)
