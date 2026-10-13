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
        raise ValueError('Kernel/Add deve essere una lista.')
    matches = [entry for entry in entries if entry.get('BundlePath') == KEXT]
    if len(matches) != 1:
        raise ValueError('Occorre una sola voce IntelBTPatcher.kext. Nessuna modifica.')
    entry = matches[0]
    if not isinstance(entry.get('Enabled'), bool):
        raise ValueError('Enabled deve essere un valore booleano. Nessuna modifica.')
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
        print('IntelBTPatcher e gia escluso da questa configurazione. Nessuna modifica.')
        return False
    backup = path.with_name(BACKUP)
    if backup.exists() and backup.read_bytes() != raw:
        raise ValueError('Esiste un backup di un altro stato della configurazione. Nessuna modifica.')
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(raw)
    atomic_write(path, plistlib.dumps(new, sort_keys=False))
    print('Prova attivata: solo IntelBTPatcher.kext e stato escluso da Kernel/Add.')
    print('Backup: EFI/OC/' + BACKUP)
    print('Spegni il portatile, riaccendilo dallo stesso OpenCore e scegli Machintosh SSD.')
    return True


def restore(path):
    backup = path.with_name(BACKUP)
    raw = backup.read_bytes()
    original = plistlib.loads(raw)
    expected = modified(original)
    current = plistlib.loads(path.read_bytes())
    if current != original and current != expected:
        raise ValueError('Sono presenti altre modifiche. Annulla prima le prove successive a TEST-BT.')
    atomic_write(path, raw)
    print('Configurazione precedente ripristinata. Backup conservato.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parents[1]/'EFI/OC/config.plist')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if not args.config.is_file():
        raise SystemExit("EFI/OC/config.plist non trovato. Estrai il pacchetto nella radice dell'HDD di avvio.")
    try:
        if args.restore:
            restore(args.config)
        else:
            apply_test(args.config)
    except (OSError, ValueError, KeyError, TypeError, AttributeError,
            plistlib.InvalidFileException) as error:
        raise SystemExit('Operazione non eseguita: ' + str(error))


if __name__ == '__main__':
    main()
