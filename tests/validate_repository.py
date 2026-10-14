#!/usr/bin/env python3
"""Check source syntax, metadata and local documentation links without device access."""
import ast
import hashlib
import json
from pathlib import Path
import plistlib
import re
import subprocess
from urllib.parse import unquote, urlsplit


PACKAGE_INPUTS = {
    'microphone': ('INSTALLA-MICROFONO.command', 'ANNULLA-MICROFONO.command',
                   'VERIFICA-MICROFONO.command', 'tools/microphone_driver_test.sh',
                   'tools/verify_microphone_driver.sh'),
    'audio': ('PREPARA-AUDIO.command', 'INSTALLA-AUDIO.command',
              'VERIFICA-AUDIO.command', 'RIPRISTINA-AUDIO.command',
              'VOLUME-AUDIO.command', 'ANNULLA-VOLUME-AUDIO.command', 'tools/audio_tahoe.sh'),
    'backlight': ('TEST-SCHERMO-AVVIO.command', 'ANNULLA-SCHERMO-AVVIO.command',
                  'tools/backlight_boot_test.sh'),
    'boot-network': ('RACCOGLI-AVVIO-RETE.command', 'tools/collect_boot_network.sh'),
    'hardware-inventory': ('RACCOGLI-DATI.cmd', 'tools/Raccogli-Dati.ps1'),
    'boot-maintenance': ('RIORDINA-AVVIO.cmd', 'tools/reorder_boot_disk.py'),
    'bluetooth': ('TEST-BT.cmd', 'RIPRISTINA-BT.cmd', 'tools/test_bluetooth.py'),
    'recovery': ('SCARICA-RECOVERY.cmd', 'CONFIGURA-WIFI.cmd', 'tools/configure_wifi.py'),
    'microphone-diagnostics': ('RACCOGLI-MICROFONO.command', 'tools/collect_microphone.sh',
                               'src/hda_mixer_snapshot.c'),
}
AUDIO_ZIP_PATHS = {
    'PREPARA-AUDIO.command', 'INSTALLA-AUDIO.command', 'VERIFICA-AUDIO.command',
    'RIPRISTINA-AUDIO.command', 'VOLUME-AUDIO.command', 'ANNULLA-VOLUME-AUDIO.command',
    'tools/audio_tahoe.sh', 'profiles/audio-tahoe-assets.lock.json', 'docs/AUDIO-TAHOE.md',
    'licenses/audio-tahoe/VoodooHDA-LICENSE.txt',
    'licenses/audio-tahoe/VoodooHDA-third-party-LICENSE.txt',
    'licenses/audio-tahoe/AppleALC-LICENSE.txt',
}


def check_structure(root, failures):
    for name in ('tools', 'acpi', 'profiles', 'usb'):
        if (root / name).exists():
            failures.append(f'Unexpected directory at the repository root: {name}')
    for path in root.iterdir():
        if path.is_file() and path.suffix in ('.command', '.cmd', '.sh', '.ps1', '.py', '.c', '.aml'):
            failures.append(f'Unexpected launcher or source file at the repository root: {path.name}')
    required = [
        'builders/build_audio_microphone.py', 'builders/build_audio_tahoe.py',
        'builders/build_acpi.py', 'tests/test_audio_microphone_patch.py',
        'tests/test_microphone_installer.py', 'tests/test_microphone_driver.sh',
        'tests/validate_repository.py', 'patches/audio-microphone/input-gain.patch',
        'config/profiles/audio-tahoe-assets.lock.json', 'config/profiles/assets.lock.json',
        'config/profiles/s540-81sw.json', 'config/acpi/compiled/manifest.json',
        'config/usb/ports.json', 'config/usb/UTBMap.kext/Contents/Info.plist',
        'docs/guides/microphone-fix.md', 'docs/guides/microphone-diagnostics.md',
        'docs/guides/tahoe-audio.md', 'archive/README.md', 'docs/README.md',
        'packages/README.md',
        'licenses/audio-tahoe/VoodooHDA-LICENSE.txt',
        'licenses/audio-tahoe/VoodooHDA-third-party-LICENSE.txt',
        'licenses/audio-tahoe/AppleALC-LICENSE.txt',
    ]
    for package, inputs in PACKAGE_INPUTS.items():
        required.extend(f'packages/{package}/{item}' for item in inputs)
    for relative in required:
        if not (root / relative).is_file():
            failures.append(f'Required active input missing: {relative}')
    for path in (root / 'packages').glob('*/*'):
        if path.suffix not in ('.command', '.cmd'):
            continue
        for helper in re.findall(r'tools[\\/]+([A-Za-z0-9_.-]+\.(?:sh|py|ps1))', path.read_text()):
            if not (path.parent / 'tools' / helper).is_file():
                failures.append(f'{path.relative_to(root)}: helper missing tools/{helper}')
    # Package source paths may change, but the existing distributed ZIP paths
    # must not. Read the builder's literal source map without importing code.
    builder = root / 'builders/build_audio_tahoe.py'
    if builder.is_file():
        tree = ast.parse(builder.read_text())
        source_map = None
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'SOURCE_FILES'
                for target in statement.targets
            ):
                source_map = ast.literal_eval(statement.value)
        if not isinstance(source_map, dict) or set(source_map) != AUDIO_ZIP_PATHS:
            failures.append('The audio builder does not preserve the existing package paths.')
        else:
            for relative in source_map.values():
                if not (root / relative).is_file():
                    failures.append(f'Audio package source missing: {relative}')
    # Check literal workflow inputs, while leaving generated build paths alone.
    pattern = r'(?<![\w./-])(?:builders|tests|packages|config|docs|licenses|patches)/[A-Za-z0-9_./-]+\.(?:command|patch|json|ps1|cmd|py|sh|md|c)(?![\w.-])'
    for workflow in (root / '.github/workflows').glob('*.yml'):
        text = workflow.read_text().replace('\\', '/')
        for relative in re.findall(pattern, text):
            if not (root / relative).is_file():
                failures.append(f'{workflow.relative_to(root)}: input missing {relative}')


def check_archive(root, failures):
    manifest = root / 'archive/manifest.json'
    if not manifest.is_file():
        failures.append('Archive manifest missing.')
        return
    try:
        data = json.loads(manifest.read_text())
        hash_basis = data.get('hash_basis')
        if 'hash_basis' in data and hash_basis != 'cmd-lf-canonical':
            failures.append(f'Unrecognized archive checksum basis: {hash_basis}')
            return
        old_paths, new_paths = set(), set()
        for move in data['moves']:
            old, new = move['from'], move['to']
            if old in old_paths or new in new_paths:
                failures.append(f'Duplicate move in the archive manifest: {old}')
            old_paths.add(old)
            new_paths.add(new)
            if (root / old).exists():
                failures.append(f'Archived original path still present: {old}')
            target = (root / new).resolve()
            if not target.is_relative_to(root / 'archive') or not target.is_file():
                failures.append(f'Archive destination missing or outside the archive: {new}')
                continue
            contents = target.read_bytes()
            if hash_basis == 'cmd-lf-canonical' and target.suffix == '.cmd':
                # Git checks out *.cmd with CRLF through .gitattributes. Only
                # this declared basis permits that equivalent representation;
                # all other files retain byte-exact checksum verification.
                contents = contents.replace(b'\r\n', b'\n')
            digest = hashlib.sha256(contents).hexdigest()
            if digest != move['archived_sha256']:
                failures.append(f'Archive checksum mismatch: {new}')
    except (KeyError, ValueError, OSError, TypeError) as error:
        failures.append(f'Invalid archive manifest: {error}')


def main():
    root = Path(__file__).resolve().parents[1]
    failures = []
    count = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(part in ('build', '.git', '__pycache__') for part in path.relative_to(root).parts):
            continue
        count += 1
        try:
            if path.suffix == '.py':
                ast.parse(path.read_text(), filename=str(path))
            elif path.suffix == '.json':
                json.loads(path.read_text())
            elif path.suffix == '.plist':
                plistlib.loads(path.read_bytes())
            elif path.suffix in ('.sh', '.command'):
                subprocess.run(['bash', '-n', str(path)], check=True, capture_output=True)
            elif path.suffix == '.md':
                text = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
                for target in re.findall(r'\]\(([^\n)]+)\)', text):
                    target = target.split(' "', 1)[0].strip('<>')
                    parsed = urlsplit(target)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    destination = (path.parent / unquote(parsed.path)).resolve()
                    if not destination.exists():
                        failures.append(f'{path.relative_to(root)}: missing link {target}')
        except (SyntaxError, ValueError, OSError, subprocess.CalledProcessError) as error:
            failures.append(f'{path.relative_to(root)}: {error}')
    check_structure(root, failures)
    check_archive(root, failures)
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'PASS: {count} files; structure, package inputs, syntax, archive and local links verified.')


if __name__ == '__main__':
    main()
