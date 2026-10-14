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
        raise ValueError('boot-args deve essere una stringa.')
    if FLAG not in args.split():
        result['NVRAM']['Add'][GUID]['boot-args'] = (args + ' ' + FLAG).strip()
    if 'boot-args' not in result['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('Manca la riscrittura NVRAM di boot-args. Usa la EFI del progetto.')
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
        print('Test grafica gia attivo. Nessuna modifica.')
        return False
    new = modified(config)
    backup = path.with_name('config.before-graphics-test.plist')
    if backup.exists() and backup.read_bytes() != raw:
        raise ValueError('Esiste un backup di un altro stato della configurazione. Nessuna modifica.')
    if not backup.exists():
        backup.write_bytes(raw)
    atomic_write(path, plistlib.dumps(new, sort_keys=False))
    print('Test grafica attivato: accelerazione Intel temporaneamente disabilitata.')
    print('Backup salvato accanto a config.plist. Riavvia la Recovery per la prova.')
    return True


def restore(path):
    backup = path.with_name('config.before-graphics-test.plist')
    raw = backup.read_bytes()
    original = plistlib.loads(raw)
    current = plistlib.loads(path.read_bytes())
    if current != original and current != modified(original):
        raise ValueError('La configurazione contiene altre modifiche. Ripristino automatico annullato.')
    atomic_write(path, raw)
    print('Configurazione precedente ripristinata. Backup conservato.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'EFI/OC/config.plist')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if not args.config.is_file():
        raise SystemExit('EFI/OC/config.plist non trovato. Estrai il test nella radice del disco di avvio.')
    try:
        if args.restore:
            restore(args.config)
        else:
            apply_test(args.config)
    except (OSError, ValueError, KeyError, plistlib.InvalidFileException) as error:
        raise SystemExit('Test non applicato: ' + str(error))


if __name__ == '__main__':
    main()
