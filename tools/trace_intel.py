#!/usr/bin/env python3
"""Reversible Intel trace using verified Lilu and WhateverGreen DEBUG payloads."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import tempfile

GUID = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
VERSIONS = {'Lilu.kext': '1.7.2', 'WhateverGreen.kext': '1.7.1'}
FLAGS = ('-liludbgall', '-wegdbg', 'liludump=60', '-igfxdump')
BACKUP = 'backup-traccia-intel'
NORMAL = 'config-traccia-normale.plist'
RECOVERY = 'config-traccia-recovery.plist'
TOKENS = re.compile(r'''(?:[^\s"'\\]|\\.|"(?:[^"\\]|\\.)*"|'[^']*')+''')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ordinary(path):
    info = path.lstat()
    if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Link o reparse point non ammesso: ' + path.name)


def tree(path):
    ordinary(path)
    if not path.is_dir():
        raise ValueError('Cartella kext non presente: ' + path.name)
    result = {'files': {}, 'directories': []}
    def walk_error(error):
        raise error
    for folder, dirs, files in os.walk(str(path), followlinks=False, onerror=walk_error):
        for name in sorted(dirs + files):
            child = Path(folder) / name
            ordinary(child)
            relative = child.relative_to(path).as_posix()
            if child.is_dir():
                result['directories'].append(relative)
            elif child.is_file():
                result['files'][relative] = digest(child.read_bytes())
            else:
                raise ValueError('Elemento non regolare nel kext: ' + child.name)
    result['directories'].sort()
    return result


def trees(parent):
    return {name: tree(parent / name) for name in VERSIONS}


def versions(parent):
    for name, expected in VERSIONS.items():
        info = plistlib.loads((parent / name / 'Contents' / 'Info.plist').read_bytes())
        if info.get('CFBundleVersion') != expected:
            raise ValueError('Versione inattesa di ' + name + '; richiesta ' + expected)


def payload(root):
    assets = root / 'assets' / 'traccia-intel'
    ordinary(root / 'assets')
    ordinary(assets)
    manifest_path = assets / 'manifest.json'
    ordinary(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))['files']
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError('Manifesto del payload non valido.')
    for name, sha in manifest.items():
        if not isinstance(name, str):
            raise ValueError('Percorso non valido nel manifesto del payload.')
        parts = name.split('/')
        if '\\' in name or any(part in ('', '.', '..') for part in parts) or parts[0] not in VERSIONS:
            raise ValueError('Percorso non valido nel manifesto del payload.')
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('SHA-256 non valido nel manifesto del payload.')
    snapshot = trees(assets)
    actual = {name + '/' + path: sha for name, state in snapshot.items()
              for path, sha in state['files'].items()}
    if actual != manifest:
        raise ValueError('Payload DEBUG incompleto o modificato. Nessuna modifica alla EFI.')
    versions(assets)
    return assets, snapshot


def validate(config):
    args = config['NVRAM']['Add'][GUID]['boot-args']
    if not isinstance(args, str):
        raise ValueError('boot-args non e una stringa.')
    shlex.split(args)
    if 'boot-args' not in config['NVRAM'].get('Delete', {}).get(GUID, []):
        raise ValueError('Manca NVRAM/Delete/boot-args. Nessuna modifica.')
    for name, enabled in dict(VERSIONS, **{'IntelBTPatcher.kext': False}).items():
        entries = [entry for entry in config['Kernel']['Add'] if entry.get('BundlePath') == name]
        wanted = enabled if isinstance(enabled, bool) else True
        if len(entries) != 1 or entries[0].get('Enabled') is not wanted:
            raise ValueError(name + ' deve essere ' + ('abilitato.' if wanted else 'disabilitato.'))
    return args


def states(original):
    args = validate(original)
    matches = list(TOKENS.finditer(args))
    for match in reversed(matches):
        if match.group() in ('-igfxvesa', '-x') or match.group().startswith('liludump='):
            args = args[:match.start()] + args[match.end():]
    existing = {m.group() for m in TOKENS.finditer(args)}
    missing = [flag for flag in FLAGS if flag not in existing]
    if missing:
        args += ('' if not args or args[-1].isspace() else ' ') + ' '.join(missing)
    normal = copy.deepcopy(original)
    normal['NVRAM']['Add'][GUID]['boot-args'] = args
    recovery = copy.deepcopy(normal)
    for match in reversed(list(TOKENS.finditer(args))):
        if match.group() == '-igfxdump' or match.group().startswith('liludump='):
            args = args[:match.start()] + args[match.end():]
    recovery['NVRAM']['Add'][GUID]['boot-args'] = args + ('' if not args or args[-1].isspace() else ' ') + '-igfxvesa'
    return normal, recovery


def atomic_write(path, raw):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.traccia-config-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def read_backup(backup, debug=None):
    ordinary(backup)
    for name in ('manifest.json', 'config.original.plist', NORMAL, RECOVERY, 'Kexts'):
        ordinary(backup / name)
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    data = {name: (backup / name).read_bytes() for name in
            ('config.original.plist', NORMAL, RECOVERY)}
    saved_debug = manifest.get('debug')
    if (manifest.get('version') != 1 or not isinstance(saved_debug, dict)
            or set(saved_debug) != set(VERSIONS) or (debug is not None and saved_debug != debug)):
        raise ValueError('Backup della traccia incompatibile. Nessuna modifica.')
    if manifest.get('configs') != {name: digest(raw) for name, raw in data.items()}:
        raise ValueError('Configurazioni del backup modificate. Nessuna modifica.')
    original = plistlib.loads(data['config.original.plist'])
    normal, recovery = states(original)
    if plistlib.loads(data[NORMAL]) != normal or plistlib.loads(data[RECOVERY]) != recovery:
        raise ValueError('Stati del backup incoerenti. Nessuna modifica.')
    saved = trees(backup / 'Kexts')
    if saved != manifest.get('original'):
        raise ValueError('Kext del backup modificati. Nessuna modifica.')
    versions(backup / 'Kexts')
    return data, saved, saved_debug


def make_backup(oc, raw, config, original, debug):
    backup = oc / BACKUP
    stage = Path(tempfile.mkdtemp(prefix='.traccia-backup-', dir=oc))
    try:
        (stage / 'Kexts').mkdir()
        for name in VERSIONS:
            shutil.copytree(oc / 'Kexts' / name, stage / 'Kexts' / name)
        normal, recovery = states(config)
        data = {'config.original.plist': raw, NORMAL: plistlib.dumps(normal, sort_keys=False),
                RECOVERY: plistlib.dumps(recovery, sort_keys=False)}
        for name, content in data.items():
            (stage / name).write_bytes(content)
        manifest = {'version': 1, 'original': original, 'debug': debug,
                    'configs': {name: digest(content) for name, content in data.items()}}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        if trees(stage / 'Kexts') != original or trees(oc / 'Kexts') != original or (oc / 'config.plist').read_bytes() != raw:
            raise ValueError('La EFI e cambiata durante il backup. Nessuna sostituzione.')
        if backup.exists():
            raise ValueError('Backup comparso durante la preparazione. Nessuna sostituzione.')
        stage.rename(backup)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def swap(oc, source, wanted, raw, before, target):
    stage = Path(tempfile.mkdtemp(prefix='.traccia-scambio-', dir=oc))
    changed = []
    rollback_ok = True
    try:
        (stage / 'new').mkdir()
        (stage / 'old').mkdir()
        for name in VERSIONS:
            shutil.copytree(source / name, stage / 'new' / name)
        if trees(stage / 'new') != target:
            raise ValueError('Copia di staging non verificata. Nessuna sostituzione.')
        if trees(oc / 'Kexts') != before or (oc / 'config.plist').read_bytes() != raw:
            raise ValueError('La EFI e cambiata durante la preparazione. Nessuna sostituzione.')
        for name in VERSIONS:
            (oc / 'Kexts' / name).rename(stage / 'old' / name)
            changed.append(name)
            (stage / 'new' / name).rename(oc / 'Kexts' / name)
        atomic_write(oc / 'config.plist', wanted)
        if trees(oc / 'Kexts') != target or (oc / 'config.plist').read_bytes() != wanted:
            raise ValueError('Verifica finale della sostituzione fallita.')
    except Exception:
        if changed:
            try:
                if (oc / 'config.plist').read_bytes() != raw:
                    atomic_write(oc / 'config.plist', raw)
                for name in reversed(changed):
                    active = oc / 'Kexts' / name
                    if active.exists():
                        shutil.rmtree(active)
                    (stage / 'old' / name).rename(active)
            except Exception as error:
                rollback_ok = False
                raise RuntimeError('Rollback incompleto; backup conservato e staging in ' + stage.name) from error
        raise
    finally:
        if rollback_ok:
            shutil.rmtree(stage)


def run(root, mode='apply'):
    if mode not in ('apply', 'recover', 'restore'):
        raise ValueError('Operazione non riconosciuta.')
    oc = root / 'EFI' / 'OC'
    ordinary(root / 'EFI')
    ordinary(oc)
    ordinary(oc / 'Kexts')
    path = oc / 'config.plist'
    ordinary(path)
    assets, debug = (None, None) if mode == 'restore' else payload(root)
    raw = path.read_bytes()
    current = plistlib.loads(raw)
    validate(current)
    active = trees(oc / 'Kexts')
    versions(oc / 'Kexts')
    backup = oc / BACKUP
    if not backup.exists():
        if mode != 'apply':
            raise ValueError('Backup della traccia assente. Nessuna modifica.')
        make_backup(oc, raw, current, active, debug)
    data, original, debug = read_backup(backup, debug)
    configs = {name: plistlib.loads(content) for name, content in data.items()}
    is_original = current == configs['config.original.plist'] and active == original
    is_debug = current in (configs[NORMAL], configs[RECOVERY], configs['config.original.plist']) and active == debug
    if not is_original and not is_debug:
        raise ValueError('La EFI contiene modifiche successive. Operazione annullata.')
    if mode == 'restore':
        wanted, source, target = data['config.original.plist'], backup / 'Kexts', original
    else:
        if mode == 'recover' and not is_debug:
            raise ValueError('Prima attiva TRACCIA-INTEL. Nessuna modifica.')
        wanted = data[RECOVERY if mode == 'recover' else NORMAL]
        source, target = assets, debug
    if current == plistlib.loads(wanted) and active == target:
        if mode == 'restore' and raw != wanted:
            atomic_write(path, wanted)
        print('Stato richiesto gia presente; backup conservato.')
        return False
    swap(oc, source, wanted, raw, active, target)
    print({'apply': 'Traccia Intel attiva: seleziona Machintosh SSD al prossimo avvio.',
           'recover': 'Recovery della traccia pronta: seleziona la voce Recovery.',
           'restore': 'Config e due kext originali ripristinati byte per byte.'}[mode])
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
