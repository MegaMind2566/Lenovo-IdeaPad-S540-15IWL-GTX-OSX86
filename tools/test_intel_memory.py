#!/usr/bin/env python3
"""Apply the diagnosed Intel framebuffer memory adjustment reversibly."""
import argparse
import copy
import json
import os
from pathlib import Path
import plistlib

import trace_intel as trace

GPU = 'PciRoot(0x0)/Pci(0x2,0x0)'
PAIR = {'AAPL,ig-platform-id': bytes.fromhex('0900A53E'), 'device-id': bytes.fromhex('A53E0000')}
MEMORY = {'framebuffer-patch-enable': bytes.fromhex('01000000'),
          'framebuffer-stolenmem': bytes.fromhex('00003001'),
          'framebuffer-fbmem': bytes.fromhex('00009000')}
BACKUP = 'config.before-intel-memory.plist'
META = 'config.before-intel-memory.json'
NORMAL = 'config.intel-memory.normal.plist'
RECOVERY = 'config.intel-memory.recovery.plist'
FILES = (BACKUP, META, NORMAL, RECOVERY)


def validate(config):
    args = trace.validate(config)
    props = config['DeviceProperties']['Add'][GPU]
    if any(type(props.get(name)) is not bytes or props[name] != value for name, value in PAIR.items()):
        raise ValueError('La coppia Intel non coincide con la prova Whiskey Lake verificata. Nessuna modifica.')
    if any(name in props and props[name] != value for name, value in MEMORY.items()):
        raise ValueError('Sono presenti altri valori di memoria Intel. Nessuna modifica.')
    return args


def states(original):
    args = validate(original)
    for match in reversed(list(trace.TOKENS.finditer(args))):
        if match.group() in ('-igfxvesa', '-x'):
            args = args[:match.start()] + args[match.end():]
    normal = copy.deepcopy(original)
    normal['DeviceProperties']['Add'][GPU].update(MEMORY)
    normal['NVRAM']['Add'][trace.GUID]['boot-args'] = args
    recovery = copy.deepcopy(normal)
    recovery['NVRAM']['Add'][trace.GUID]['boot-args'] = args + ('' if not args or args[-1].isspace() else ' ') + '-igfxvesa'
    return normal, recovery


def metadata(raw, original, kexts):
    normal, recovery = states(original)
    return {'version': 1, 'original_sha256': trace.digest(raw), 'kexts': kexts,
            'normal_sha256': trace.digest(plistlib.dumps(normal, sort_keys=False)),
            'recovery_sha256': trace.digest(plistlib.dumps(recovery, sort_keys=False))}


def saved_state(oc):
    for name in FILES:
        trace.ordinary(oc / name)
    raw = (oc / BACKUP).read_bytes()
    original = plistlib.loads(raw)
    saved = json.loads((oc / META).read_text(encoding='utf-8'))
    if not isinstance(saved, dict) or saved != metadata(raw, original, saved.get('kexts')):
        raise ValueError('Backup memoria modificato o incompatibile. Nessuna modifica.')
    if (trace.digest((oc / NORMAL).read_bytes()) != saved['normal_sha256']
            or trace.digest((oc / RECOVERY).read_bytes()) != saved['recovery_sha256']):
        raise ValueError('Snapshot della prova memoria modificati. Nessuna modifica.')
    return raw, original, saved['kexts']


def trace_baseline(root, current, active):
    backup = root / 'EFI' / 'OC' / trace.BACKUP
    data, original_kexts, debug = trace.read_backup(backup)
    original = plistlib.loads(data['config.original.plist'])
    validate(original)
    known = [plistlib.loads(data[name]) for name in ('config.original.plist', trace.NORMAL, trace.RECOVERY)]
    if not ((current == original and active == original_kexts) or (current in known and active == debug)):
        raise ValueError('La traccia contiene modifiche successive. Nessuna modifica.')
    return data['config.original.plist'], original, original_kexts


def make_backup(oc, raw, original, kexts):
    created = []
    normal, recovery = states(original)
    contents = {BACKUP: raw, NORMAL: plistlib.dumps(normal, sort_keys=False),
                RECOVERY: plistlib.dumps(recovery, sort_keys=False),
                META: json.dumps(metadata(raw, original, kexts), indent=2).encode('utf-8')}
    try:
        for name, data in contents.items():
            path = oc / name
            with path.open('xb') as stream:
                created.append(path)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        saved_state(oc)
    except Exception:
        for path in reversed(created):
            path.unlink()
        raise


def run(root, mode='apply'):
    if mode not in ('apply', 'recover', 'restore'):
        raise ValueError('Operazione non riconosciuta.')
    oc = root / 'EFI' / 'OC'
    for path in (root / 'EFI', oc, oc / 'Kexts', oc / 'config.plist'):
        trace.ordinary(path)
    path = oc / 'config.plist'
    current_raw = path.read_bytes()
    current = plistlib.loads(current_raw)
    validate(current)
    active = trace.trees(oc / 'Kexts')
    trace.versions(oc / 'Kexts')
    exists = [os.path.lexists(oc / name) for name in FILES]
    for name, present in zip(FILES, exists):
        if present:
            trace.ordinary(oc / name)
    if any(exists) and not all(exists):
        raise ValueError('Backup memoria incompleto. Nessuna modifica.')
    if all(exists):
        original_raw, original, expected_kexts = saved_state(oc)
    else:
        if mode != 'apply':
            raise ValueError('Backup memoria assente. Avvia prima TEST-MEMORIA-INTEL.')
        original_raw, original, expected_kexts = current_raw, current, active
        tracing = os.path.lexists(oc / trace.BACKUP)
        if tracing:
            original_raw, original, expected_kexts = trace_baseline(root, current, active)
        # Derive and validate the entire future state before restoring the trace.
        states(original)
        if path.read_bytes() != current_raw or trace.trees(oc / 'Kexts') != active:
            raise ValueError('La EFI e cambiata durante i controlli. Nessuna modifica.')
        if tracing:
            trace.run(root, 'restore')
        if path.read_bytes() != original_raw or trace.trees(oc / 'Kexts') != expected_kexts:
            raise ValueError('Lo stato precedente alla prova memoria non e verificato.')
        make_backup(oc, original_raw, original, expected_kexts)
        current_raw, current, active = original_raw, original, expected_kexts
    normal, recovery = states(original)
    if current not in (original, normal, recovery) or active != expected_kexts:
        raise ValueError('La EFI contiene altre modifiche. Operazione annullata.')
    wanted = original_raw if mode == 'restore' else plistlib.dumps(recovery if mode == 'recover' else normal, sort_keys=False)
    if path.read_bytes() != current_raw or trace.trees(oc / 'Kexts') != active:
        raise ValueError('La EFI e cambiata durante i controlli. Nessuna modifica al config.')
    if current_raw == wanted:
        print('Stato della prova memoria gia presente; backup conservato.')
        return False
    try:
        trace.atomic_write(path, wanted)
        if path.read_bytes() != wanted:
            raise OSError('Verifica della scrittura del config fallita.')
    except Exception:
        if path.read_bytes() != current_raw:
            trace.atomic_write(path, current_raw)
        raise
    print({'apply': 'Prova memoria Intel pronta: seleziona Machintosh SSD al prossimo avvio.',
           'recover': 'Recovery pronta con la prova memoria conservata e VESA attivo.',
           'restore': 'Config precedente alla prova memoria ripristinato byte per byte.'}[mode])
    print('Backup conservato in EFI/OC/' + BACKUP)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--recover', action='store_true')
    group.add_argument('--restore', action='store_true')
    options = parser.parse_args()
    try:
        run(Path(__file__).resolve().parent.parent, 'restore' if options.restore else 'recover' if options.recover else 'apply')
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, plistlib.InvalidFileException) as error:
        print('Operazione non completata:', error)
        raise SystemExit(1)
