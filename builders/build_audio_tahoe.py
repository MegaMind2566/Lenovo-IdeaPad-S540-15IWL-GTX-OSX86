#!/usr/bin/env python3
"""Build a pinned audio test package; never package a user's EFI or logs."""
from pathlib import Path
import argparse
import hashlib
import json
import plistlib
import struct
import urllib.request
import zipfile


# Preserve the ZIP's established paths while source files live by feature.
SOURCE_FILES = {
    'PREPARA-AUDIO.command': 'packages/audio/PREPARA-AUDIO.command',
    'INSTALLA-AUDIO.command': 'packages/audio/INSTALLA-AUDIO.command',
    'VERIFICA-AUDIO.command': 'packages/audio/VERIFICA-AUDIO.command',
    'RIPRISTINA-AUDIO.command': 'packages/audio/RIPRISTINA-AUDIO.command',
    'VOLUME-AUDIO.command': 'packages/audio/VOLUME-AUDIO.command',
    'ANNULLA-VOLUME-AUDIO.command': 'packages/audio/ANNULLA-VOLUME-AUDIO.command',
    'tools/audio_tahoe.sh': 'packages/audio/tools/audio_tahoe.sh',
    'profiles/audio-tahoe-assets.lock.json': 'config/profiles/audio-tahoe-assets.lock.json',
    'docs/AUDIO-TAHOE.md': 'docs/guides/AUDIO-TAHOE.md',
    'licenses/audio-tahoe/VoodooHDA-LICENSE.txt': 'licenses/audio-tahoe/VoodooHDA-LICENSE.txt',
    'licenses/audio-tahoe/VoodooHDA-third-party-LICENSE.txt': 'licenses/audio-tahoe/VoodooHDA-third-party-LICENSE.txt',
    'licenses/audio-tahoe/AppleALC-LICENSE.txt': 'licenses/audio-tahoe/AppleALC-LICENSE.txt',
}


def load_payload(archive, lock):
    blob = archive.read_bytes()
    if len(blob) != lock['archive_size'] or hashlib.sha256(blob).hexdigest() != lock['archive_sha256']:
        raise ValueError('Upstream audio archive size/hash mismatch')
    payload = {}
    with zipfile.ZipFile(archive) as source:
        if source.testzip() is not None:
            raise ValueError('Upstream audio ZIP CRC failure')
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate upstream ZIP entries')
        for name, expected in lock['files'].items():
            entry = source.getinfo(name)
            if ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError('Unexpected upstream symlink')
            data = source.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Audio payload hash mismatch: ' + name)
            payload['assets/audio-tahoe/' + name] = data
    info = plistlib.loads(payload['assets/audio-tahoe/VoodooHDA.kext/Contents/Info.plist'])
    if info['CFBundleVersion'] != lock['version'] or info['CFBundleIdentifier'] != 'org.voodoo.driver.VoodooHDA':
        raise ValueError('Wrong VoodooHDA bundle')
    if info['IOKitPersonalities']['VoodooHDA']['IONameMatch'] != 'HDAS':
        raise ValueError('Unexpected audio matching personality')
    binary = payload['assets/audio-tahoe/VoodooHDA.kext/Contents/MacOS/VoodooHDA']
    header = struct.unpack_from('<8I', binary)
    if header[0] != 0xfeedfacf or header[1] != 0x01000007 or header[3] != 11:
        raise ValueError('Expected an x86_64 MH_KEXT_BUNDLE')
    return payload


def write_entry(target, name, data):
    entry = zipfile.ZipInfo('S540-audio-Tahoe-v3/' + name, (1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    mode = 0o755 if name.endswith(('.command', '.sh')) or name.endswith('/MacOS/VoodooHDA') else 0o644
    entry.external_attr = (0o100000 | mode) << 16
    entry.compress_type = zipfile.ZIP_DEFLATED
    target.writestr(entry, data, compresslevel=9)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-zip', type=Path, help='Use an already downloaded pinned upstream ZIP')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    lock = json.loads((root/'config/profiles/audio-tahoe-assets.lock.json').read_text())
    output = root/'build/audio-tahoe'
    output.mkdir(parents=True, exist_ok=True)
    upstream = args.asset_zip
    if upstream is None:
        upstream = output/'VoodooHDA.kext-368.zip'
        if not upstream.exists():
            with urllib.request.urlopen(lock['url'], timeout=30) as response:
                data = response.read(lock['archive_size'] + 1)
            if len(data) != lock['archive_size'] or hashlib.sha256(data).hexdigest() != lock['archive_sha256']:
                raise ValueError('Downloaded audio archive failed validation')
            upstream.write_bytes(data)
    entries = load_payload(upstream, lock)
    for name, source_name in SOURCE_FILES.items():
        source = root/source_name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing or unsafe package source: ' + name)
        entries[name] = source.read_bytes()
    entries['assets/audio-tahoe/SHA256SUMS'] = ''.join(
        digest + '  ' + name + '\n' for name, digest in sorted(lock['files'].items())
    ).encode()
    entries['LEGGIMI.txt'] = (
        'Prova audio ALC257 su Tahoe. Prima conserva la EFI funzionante.\n'
        'Leggi docs/AUDIO-TAHOE.md. Esegui PREPARA-AUDIO.command, poi riavvia.\n'
        'Esegui INSTALLA-AUDIO.command; approva il driver se macOS lo richiede e riavvia.\n'
        'Esegui VERIFICA-AUDIO.command e controlla altoparlanti, cuffie e microfono.\n'
        'RIPRISTINA-AUDIO.command documenta e gestisce il ritorno alla configurazione precedente.\n'
        'Se audio e tasti funzionano ma il volume cambia solo a muto: esegui VOLUME-AUDIO.command.\n'
        'ANNULLA-VOLUME-AUDIO.command ripristina soltanto il driver precedente alla prova volume.\n'
        'Il pacchetto non contiene EFI personali, Wi-Fi, SMBIOS o log.\n'
    ).encode()
    archive = output/'S540-audio-Tahoe-v3.zip'
    with zipfile.ZipFile(archive, 'w') as target:
        for name, data in sorted(entries.items()):
            write_entry(target, name, data)
    with zipfile.ZipFile(archive) as target:
        if target.testzip() is not None:
            raise ValueError('Final ZIP failed CRC validation')
        if len(target.namelist()) != len(entries):
            raise ValueError('Unexpected package entry count')
        for name, data in entries.items():
            if target.read('S540-audio-Tahoe-v3/' + name) != data:
                raise ValueError('Final package differs from verified source: ' + name)
    print(archive)
    print('SHA-256:', hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
