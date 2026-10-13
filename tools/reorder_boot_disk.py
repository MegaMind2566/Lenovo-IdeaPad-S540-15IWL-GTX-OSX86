#!/usr/bin/env python3
"""Archive recognized boot-disk diagnostics; leave EFI and Recovery untouched."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
from datetime import datetime
import uuid

COMMANDS = {name.casefold() for name in (
    'TEST-INTEL.cmd', 'TEST-BT.cmd', 'TEST-GRAFICA.cmd', 'AVVIO-SICURO.cmd',
    'RIPRISTINA-INTEL.cmd', 'RIPRISTINA-BT.cmd', 'RIPRISTINA-GRAFICA.cmd',
    'RIPRISTINA-AVVIO.cmd', 'RACCOGLI-LOG-MACOS.command')}
LOG = re.compile(r'opencore-\d{4}-\d{2}-\d{2}-\d{6}\.txt', re.I)
DIAGNOSTIC = re.compile(r'(?:DIAGNOSI-MACOS-|LOG-UNIFICATI-)[A-Za-z0-9]{6}(\.zip)?', re.I)
PACKAGE = re.compile(r'S540-(?:test-|diagnosi-).+\.zip', re.I)


def is_reparse(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def recognized(path):
    if is_reparse(path):
        return False
    name = path.name
    match = DIAGNOSTIC.fullmatch(name)
    if match:
        return path.is_file() if match.group(1) else path.is_dir()
    return path.is_file() and (name.casefold() in COMMANDS or LOG.fullmatch(name)
        or PACKAGE.fullmatch(name) or name.casefold() == 's540-81sw-tahoe-prima-prova.zip')


def digest(path):
    if is_reparse(path):
        raise ValueError('Collegamento o reparse point: non seguito.')
    before = path.stat()
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('File cambiato durante la lettura.')
    return value.hexdigest()


def snapshot(path):
    result = {}
    pending = [(path, '.')]
    while pending:
        item, relative = pending.pop()
        if is_reparse(item):
            raise ValueError('La voce contiene un collegamento: archivio automatico annullato.')
        if item.is_dir():
            result[relative] = {'type': 'directory'}
            pending.extend((child, child.relative_to(path).as_posix()) for child in item.iterdir())
        elif item.is_file():
            result[relative] = {'type': 'file', 'size': item.stat().st_size, 'sha256': digest(item)}
        else:
            raise ValueError('Tipo di file non supportato.')
    return result


def copy_snapshot(source, destination, expected):
    for relative, info in sorted(expected.items(), key=lambda pair: (pair[0].count('/'), pair[0])):
        src = source if relative == '.' else source / relative
        dst = destination if relative == '.' else destination / relative
        if is_reparse(src):
            raise ValueError('Origine cambiata in un collegamento.')
        if info['type'] == 'directory':
            dst.mkdir(parents=True, exist_ok=False)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)


def archive_item(source, destination):
    expected = snapshot(source)
    copy_snapshot(source, destination, expected)
    if snapshot(destination) != expected:
        raise ValueError('Verifica della copia fallita: origine conservata.')
    if snapshot(source) != expected:
        raise ValueError('Origine cambiata dopo la copia: origine conservata.')
    # Remove only verified files. New or modified files are never removed.
    for relative, info in expected.items():
        if info['type'] == 'file':
            item = source if relative == '.' else source / relative
            if digest(item) != info['sha256']:
                raise ValueError('Origine cambiata prima dello spostamento; voci residue conservate.')
            item.unlink()
    directories = [relative for relative, info in expected.items() if info['type'] == 'directory']
    for relative in sorted(directories, key=lambda value: 0 if value == '.' else value.count('/') + 1, reverse=True):
        (source if relative == '.' else source / relative).rmdir()
    return expected


def inventory(root):
    rows = []
    for item in sorted(root.iterdir(), key=lambda value: value.name.casefold()):
        info = item.lstat()
        rows.append({'name': item.name, 'size': info.st_size if stat.S_ISREG(info.st_mode) else None,
                     'attributes': getattr(info, 'st_file_attributes', 0), 'reparse': is_reparse(item),
                     'directory': stat.S_ISDIR(info.st_mode)})
    return rows


def reorder(root, archive):
    if archive.resolve() == root.resolve() or root.resolve() in archive.resolve().parents:
        raise ValueError('L archivio deve trovarsi fuori dal disco di avvio.')
    archive.mkdir(parents=True, exist_ok=False)
    report = {'root_before': inventory(root), 'moved': [], 'errors': []}
    for item in sorted(root.iterdir(), key=lambda value: value.name.casefold()):
        try:
            if recognized(item):
                manifest = archive_item(item, archive / item.name)
                report['moved'].append({'name': item.name, 'manifest': manifest})
        except (OSError, ValueError) as error:
            report['errors'].append({'name': item.name, 'error': str(error)})
    report['root_after'] = inventory(root)
    (archive / 'RAPPORTO.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (archive / 'RIPRISTINO.txt').write_text(
        'EFI, Recovery, strumenti correnti e file non riconosciuti restano sul disco di avvio.\n'
        'Per ripristinare una voce spostata, copiala da questa cartella nella radice dello stesso HDD.\n'
        'Se esiste gia una voce con lo stesso nome, confrontala e non sovrascriverla automaticamente.\n'
        'RAPPORTO.json elenca le voci spostate e gli eventuali errori. In caso di errore, verifica\n'
        'sia la copia qui sia la voce rimasta sull HDD prima di ripetere lo spostamento.\n', encoding='utf-8')
    return report


def main():
    if os.name != 'nt':
        raise ValueError('Esegui RIORDINA-AVVIO.cmd da Windows.')
    root = Path(__file__).resolve().parent.parent
    if root != Path(root.anchor) or (root / 'Windows').exists() or (root / 'Users').exists():
        raise ValueError('Il pacchetto deve essere nella radice dell HDD esterno di OpenCore.')
    for name in ('EFI/OC/config.plist', 'EFI/BOOT/BOOTx64.efi'):
        if not (root / name).is_file():
            raise ValueError('La EFI attesa non e presente: nessuno spostamento eseguito.')
    buffer = ctypes.create_unicode_buffer(32768)
    get_desktop = ctypes.windll.shell32.SHGetFolderPathW
    get_desktop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p]
    get_desktop.restype = ctypes.c_long
    if get_desktop(None, 0x10, None, 0, buffer) != 0:
        raise ValueError('Impossibile individuare il Desktop di Windows.')
    desktop = Path(buffer.value).resolve()
    if os.path.normcase(desktop.anchor) == os.path.normcase(root.anchor):
        raise ValueError('Il Desktop deve trovarsi su un volume diverso dal disco di avvio.')
    drive_type = ctypes.windll.kernel32.GetDriveTypeW
    drive_type.argtypes = [ctypes.c_wchar_p]
    drive_type.restype = ctypes.c_uint32
    if any(drive_type(anchor) not in (2, 3) for anchor in (root.anchor, desktop.anchor)):
        raise ValueError('Usa dischi locali. Nessun percorso di rete viene utilizzato.')
    archive = desktop / ('S540-archivio-avvio-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    print('Archivio e verifica dei vecchi file di prova. EFI e Recovery restano sul disco.')
    report = reorder(root, archive)
    print('Voci archiviate:', len(report['moved']), '- errori:', len(report['errors']))
    print('Archivio sul Desktop:', archive)
    print('Controlla RAPPORTO.json e RIPRISTINO.txt nell archivio.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print('Riordino non completato:', error)
        raise SystemExit(1)
