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
        raise ValueError('Link or reparse point; not followed.')
    before = path.stat()
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('File changed during reading.')
    return value.hexdigest()


def snapshot(path):
    result = {}
    pending = [(path, '.')]
    while pending:
        item, relative = pending.pop()
        if is_reparse(item):
            raise ValueError('The entry contains a link; automatic archiving cancelled.')
        if item.is_dir():
            result[relative] = {'type': 'directory'}
            pending.extend((child, child.relative_to(path).as_posix()) for child in item.iterdir())
        elif item.is_file():
            result[relative] = {'type': 'file', 'size': item.stat().st_size, 'sha256': digest(item)}
        else:
            raise ValueError('Unsupported file type.')
    return result


def copy_snapshot(source, destination, expected):
    for relative, info in sorted(expected.items(), key=lambda pair: (pair[0].count('/'), pair[0])):
        src = source if relative == '.' else source / relative
        dst = destination if relative == '.' else destination / relative
        if is_reparse(src):
            raise ValueError('The source became a link.')
        if info['type'] == 'directory':
            dst.mkdir(parents=True, exist_ok=False)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)


def archive_item(source, destination):
    expected = snapshot(source)
    copy_snapshot(source, destination, expected)
    if snapshot(destination) != expected:
        raise ValueError('Copy verification failed; the source is preserved.')
    if snapshot(source) != expected:
        raise ValueError('The source changed after copying; it is preserved.')
    # Remove only verified files. New or modified files are never removed.
    for relative, info in expected.items():
        if info['type'] == 'file':
            item = source if relative == '.' else source / relative
            if digest(item) != info['sha256']:
                raise ValueError('The source changed before moving; remaining entries are preserved.')
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
        raise ValueError('The archive must be outside the boot disk.')
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
        'EFI, Recovery, current tools and unrecognized files remain on the boot disk.\n'
        'To restore a moved entry, copy it from this directory to the root of the same HDD.\n'
        'If an entry with the same name already exists, compare it and do not overwrite it automatically.\n'
        'RAPPORTO.json lists moved entries and any errors. If an error occurs, check\n'
        'both this copy and the entry remaining on the HDD before trying the move again.\n', encoding='utf-8')
    return report


def main():
    if os.name != 'nt':
        raise ValueError('Run RIORDINA-AVVIO.cmd from Windows.')
    root = Path(__file__).resolve().parent.parent
    if root != Path(root.anchor) or (root / 'Windows').exists() or (root / 'Users').exists():
        raise ValueError('The package must be in the root of the external OpenCore HDD.')
    for name in ('EFI/OC/config.plist', 'EFI/BOOT/BOOTx64.efi'):
        if not (root / name).is_file():
            raise ValueError('The expected EFI is missing; no files moved.')
    buffer = ctypes.create_unicode_buffer(32768)
    get_desktop = ctypes.windll.shell32.SHGetFolderPathW
    get_desktop.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p]
    get_desktop.restype = ctypes.c_long
    if get_desktop(None, 0x10, None, 0, buffer) != 0:
        raise ValueError('Cannot locate the Windows Desktop.')
    desktop = Path(buffer.value).resolve()
    if os.path.normcase(desktop.anchor) == os.path.normcase(root.anchor):
        raise ValueError('The Desktop must be on a volume other than the boot disk.')
    drive_type = ctypes.windll.kernel32.GetDriveTypeW
    drive_type.argtypes = [ctypes.c_wchar_p]
    drive_type.restype = ctypes.c_uint32
    if any(drive_type(anchor) not in (2, 3) for anchor in (root.anchor, desktop.anchor)):
        raise ValueError('Use local disks. No network paths are used.')
    archive = desktop / ('S540-archivio-avvio-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    print('Archiving and verifying old trial files. EFI and Recovery remain on the disk.')
    report = reorder(root, archive)
    print('Entries archived:', len(report['moved']), '- errors:', len(report['errors']))
    print('Archive on the Desktop:', archive)
    print('Check RAPPORTO.json and RIPRISTINO.txt in the archive.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print('Reorganization did not complete:', error)
        raise SystemExit(1)
