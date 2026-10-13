#!/usr/bin/env python3
"""Reversible safe-boot diagnostic for the existing OpenCore configuration."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import plistlib

GUID = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
FLAG = '-x'
BACKUP = 'config.before-safe-boot.plist'


def modified(original):
    result = copy.deepcopy(original)
    args = result['NVRAM']['Add'][GUID]['boot-args']
    if not isinstance(args, str):
        raise ValueError('boot-args deve essere una stringa.')
    if 'boot-args' not in result['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('Manca la riscrittura NVRAM di boot-args. Nessuna modifica.')
    if result['Booter']['Quirks'].get('EnableSafeModeSlide') is not True:
        raise ValueError('EnableSafeModeSlide non e attivo. Raccogli la configurazione prima della prova.')
    if FLAG not in args.split():
        result['NVRAM']['Add'][GUID]['boot-args'] = (args + ' ' + FLAG).strip()
    return result


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.safe-boot.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def apply_test(path):
    raw = path.read_bytes()
    original = plistlib.loads(raw)
    new = modified(original)
    if new == original:
        print('Avvio sicuro gia richiesto. Nessuna modifica.')
        return False
    backup = path.with_name(BACKUP)
    if backup.exists() and backup.read_bytes() != raw:
        raise ValueError('Esiste un backup di un altro stato della configurazione. Nessuna modifica.')
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(raw)
    atomic_write(path, plistlib.dumps(new, sort_keys=False))
    print('Prova attivata: aggiunto solo -x ai boot-args.')
    print('Boot-args: ' + new['NVRAM']['Add'][GUID]['boot-args'])
    print('Backup: EFI/OC/' + BACKUP)
    print('Riavvia dallo stesso OpenCore e scegli Macintosh SSD.')
    return True


def restore(path):
    backup = path.with_name(BACKUP)
    raw = backup.read_bytes()
    original = plistlib.loads(raw)
    current = plistlib.loads(path.read_bytes())
    if current != original and current != modified(original):
        raise ValueError('La configurazione contiene altre modifiche. Ripristino automatico annullato.')
    atomic_write(path, raw)
    print('Configurazione precedente ripristinata. Backup conservato.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parents[1]/'EFI/OC/config.plist')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if not args.config.is_file():
        raise SystemExit('EFI/OC/config.plist non trovato. Estrai il pacchetto nella radice dell\'HDD di avvio.')
    try:
        if args.restore:
            restore(args.config)
        else:
            apply_test(args.config)
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException) as error:
        raise SystemExit('Operazione non eseguita: ' + str(error))


if __name__ == '__main__':
    main()
