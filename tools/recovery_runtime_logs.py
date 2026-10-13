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
        raise ValueError('boot-args deve essere una stringa.')
    shlex.split(args)
    if 'boot-args' not in config['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('Manca NVRAM/Delete/boot-args. Nessuna modifica.')
    patchers = [entry for entry in config['Kernel']['Add']
                if entry.get('BundlePath', '').replace('\\', '/').split('/')[-1].casefold() == 'intelbtpatcher.kext']
    if len(patchers) != 1 or patchers[0].get('Enabled') is not False:
        raise ValueError('IntelBTPatcher deve restare disabilitato. Nessuna modifica.')
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
        raise ValueError('Il backup contiene gia VESA e non identifica la prova precedente. Nessuna modifica.')
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
            print('Recovery gia preparata. Backup precedente conservato.')
            return False
        if current != original:
            raise ValueError('Il backup appartiene a un altro stato della EFI. Nessuna modifica.')
    elif has_vesa(args):
        raise ValueError('VESA e gia presente senza il backup di questa prova. Nessuna modifica.')
    else:
        with backup.open('xb') as stream:
            stream.write(raw)
    if path.read_bytes() != raw:
        raise ValueError('Il config e cambiato durante la preparazione. Nessuna modifica al config.')
    atomic_write(path, plistlib.dumps(modified(current), sort_keys=False))
    print('Recovery preparata: aggiunto soltanto -igfxvesa.')
    print('Configurazione precedente conservata in EFI/OC/' + BACKUP)
    print('Le proprieta Intel, Bluetooth e le altre impostazioni sono conservati.')
    return True


def restore(path):
    backup = path.with_name(BACKUP)
    if not backup.exists():
        raise ValueError('Backup della prova non presente. Nessuna modifica.')
    original_raw, original = backup_state(backup)
    current_raw = path.read_bytes()
    current = plistlib.loads(current_raw)
    validate(current)
    if current != original and current != modified(original):
        raise ValueError('La EFI contiene altre modifiche. Ripristino automatico annullato.')
    if path.read_bytes() != current_raw:
        raise ValueError('Il config e cambiato durante il controllo. Ripristino annullato.')
    atomic_write(path, original_raw)
    print('Ripristinata byte per byte la configurazione precedente alla raccolta.')
    print('Le proprieta Intel e IntelBTPatcher disabilitato sono conservati.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true')
    options = parser.parse_args()
    path = Path(__file__).resolve().parent.parent / 'EFI' / 'OC' / 'config.plist'
    if not path.is_file():
        raise ValueError('Estrai il pacchetto nella radice dell HDD di OpenCore, accanto a EFI.')
    return restore(path) if options.restore else prepare(path)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException) as error:
        print('Operazione non eseguita:', error)
        raise SystemExit(1)
