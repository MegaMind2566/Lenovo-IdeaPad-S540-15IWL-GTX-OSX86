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
        raise ValueError('boot-args deve essere una stringa.')
    if 'boot-args' not in result['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('Manca la riscrittura NVRAM di boot-args. Nessuna modifica.')
    if intel:
        result['NVRAM']['Add'][GUID]['boot-args'] = clear_intel_args(args)[0]
    else:
        if result['Booter']['Quirks'].get('EnableSafeModeSlide') is not True:
            raise ValueError('EnableSafeModeSlide non e attivo. Raccogli la configurazione prima della prova.')
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
            print('I parametri -x e -igfxvesa non sono presenti in questo file. Nessuna modifica.')
            print('Boot-args: ' + original['NVRAM']['Add'][GUID]['boot-args'])
        else:
            print('Avvio sicuro gia richiesto. Nessuna modifica.')
        return False
    backup_name = INTEL_BACKUP if intel else BACKUP
    backup = path.with_name(backup_name)
    if backup.exists() and backup.read_bytes() != raw:
        raise ValueError('Esiste un backup di un altro stato della configurazione. Nessuna modifica.')
    if not backup.exists():
        with backup.open('xb') as stream:
            stream.write(raw)
    atomic_write(path, plistlib.dumps(new, sort_keys=False))
    if intel:
        removed = clear_intel_args(original['NVRAM']['Add'][GUID]['boot-args'])[1]
        print('Prova Intel attivata. Parametri rimossi: ' + ' '.join(removed))
    else:
        print('Prova attivata: aggiunto solo -x ai boot-args.')
    print('Boot-args: ' + new['NVRAM']['Add'][GUID]['boot-args'])
    print('Backup: EFI/OC/' + backup_name)
    print('Riavvia dallo stesso OpenCore e scegli Macintosh SSD.')
    return True


def restore(path, intel=False):
    backup = path.with_name(INTEL_BACKUP if intel else BACKUP)
    raw = backup.read_bytes()
    original = plistlib.loads(raw)
    current = plistlib.loads(path.read_bytes())
    if current != original and current != modified(original, intel=intel):
        raise ValueError('La configurazione contiene altre modifiche. Ripristino automatico annullato.')
    atomic_write(path, raw)
    print('Configurazione precedente ripristinata. Backup conservato.')


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
        raise SystemExit('EFI/OC/config.plist non trovato. Estrai il pacchetto nella radice dell\'HDD di avvio.')
    try:
        if args.restore or args.restore_intel:
            restore(args.config, intel=args.restore_intel)
        else:
            apply_test(args.config, intel=args.intel)
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException) as error:
        raise SystemExit('Operazione non eseguita: ' + str(error))


if __name__ == '__main__':
    main()
