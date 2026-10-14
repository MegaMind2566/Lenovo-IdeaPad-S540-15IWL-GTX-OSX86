#!/usr/bin/env python3
"""Build the reversible Intel tracing package from pinned upstream assets."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import urllib.request
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def get_asset(asset, cache):
    path = cache / asset['filename']
    if not path.exists():
        failures = []
        for url in (asset['url'], asset['api_url']):
            try:
                request = urllib.request.Request(url, headers={
                    'User-Agent': 'S540-Intel-trace-builder',
                    'Accept': 'application/octet-stream',
                })
                with urllib.request.urlopen(request, timeout=45) as response:
                    data = response.read()
                if digest(data) != asset['sha256']:
                    raise ValueError('Asset SHA-256 mismatch')
                path.write_bytes(data)
                break
            except (OSError, ValueError) as error:
                failures.append(type(error).__name__)
        else:
            raise ValueError('Download failed for ' + asset['filename'] + ': ' + ', '.join(failures))
    data = path.read_bytes()
    if digest(data) != asset['sha256']:
        raise ValueError('Cached asset SHA-256 mismatch: ' + asset['filename'])
    return data


def build(root, cache):
    lock = json.loads((root / 'profiles/trace-intel-assets.lock.json').read_text())
    cache.mkdir(parents=True, exist_ok=True)
    output = root / 'build/intel-trace'
    stage = output / 'package'
    if stage.exists():
        shutil.rmtree(stage)
    payload = stage / 'assets/traccia-intel'
    payload.mkdir(parents=True)
    manifest = {}
    for asset in lock['assets']:
        with zipfile.ZipFile(io.BytesIO(get_asset(asset, cache))) as archive:
            if archive.testzip() is not None:
                raise ValueError('Invalid asset ZIP')
            prefix = asset['name'] + '.kext/'
            selected = 0
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in item.filename:
                    raise ValueError('Unsafe ZIP path')
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('Symlink in asset ZIP')
                if item.is_dir() or not item.filename.startswith(prefix):
                    continue
                data = archive.read(item)
                destination = payload / item.filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                manifest[item.filename] = digest(data)
                selected += 1
            if not selected:
                raise ValueError('Missing kext in asset ZIP')
    (payload / 'manifest.json').write_text(json.dumps({'files': manifest}, indent=2) + '\n')
    for source in (
        'TRACCIA-INTEL.cmd', 'RECOVERY-TRACCIA-INTEL.cmd', 'RIPRISTINA-TRACCIA-INTEL.cmd',
        'RACCOGLI-INTEL.command', 'tools/trace_intel.py', 'tools/collect_gui_logs.sh',
        'docs/TRACCIA-INTEL.md', 'profiles/trace-intel-assets.lock.json',
    ):
        destination = stage / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, destination)
    shutil.copytree(root / 'licenses/intel-trace', stage / 'licenses/intel-trace')
    archive_path = output / 'S540-traccia-Intel.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(stage).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Final ZIP validation failed')
    print(archive_path)
    print('SHA-256:', digest(archive_path.read_bytes()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path)
    options = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    build(root, options.cache or root / 'build/downloads/intel-trace')
