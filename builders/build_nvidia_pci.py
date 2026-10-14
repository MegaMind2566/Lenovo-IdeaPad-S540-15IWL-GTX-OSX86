#!/usr/bin/env python3
"""Build and package the native read-only Intel NVIDIA PCI inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-pci'
PACKAGE = 'S540-nvidia-pci-v1'
VERSION = '1.0.0'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90)


def plain(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('A required plain source file is missing: ' + path.name)


def validate_report(data: object) -> None:
    if not isinstance(data, dict) or data.get('format') != 1:
        raise ValueError('The native inventory returned an invalid report format.')
    if data.get('status') not in ('found', 'device_tree_only', 'not_visible') or data.get('complete') is not True:
        raise ValueError('The native inventory did not complete successfully.')
    if not isinstance(data.get('matches'), list):
        raise ValueError('The native inventory omitted its target list.')


def build(output: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('Build this package on Intel macOS.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the build commit.')
    output = output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('The output path contains a symbolic link.')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (PACKAGE + '.zip')
    sidecar = output / (archive.name + '.sha256')
    if archive.exists() or sidecar.exists():
        raise ValueError('The package destination already exists.')
    source = SOURCE / 'src/nvidia_pci_inventory.c'
    launcher = SOURCE / 'CHECK-NVIDIA.command'
    readme = SOURCE / 'README.md'
    for path in (source, launcher, readme):
        plain(path)
    with tempfile.TemporaryDirectory(prefix='s540-nvidia-pci-', dir=output) as temporary:
        binary = Path(temporary) / 'nvidia-pci-inventory'
        run('/usr/bin/xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-O2', '-fstack-protector-strong', '-arch', 'x86_64',
            '-mmacosx-version-min=15.0', '-framework', 'IOKit',
            '-framework', 'CoreFoundation', str(source), '-o', str(binary))
        header = binary.read_bytes()[:16]
        if len(header) != 16 or struct.unpack('<IIII', header)[0:2] != (0xFEEDFACF, 0x01000007) or struct.unpack('<IIII', header)[3] != 2:
            raise ValueError('The result is not a thin Intel Mach-O executable.')
        run('/usr/bin/codesign', '--force', '--sign', '-', str(binary))
        run('/usr/bin/codesign', '--verify', '--strict', str(binary))
        version = run(str(binary), '--version').stdout.strip()
        if VERSION not in version:
            raise ValueError('The executable version does not match the package.')
        run(str(binary), '--help')
        live = run(str(binary))
        validate_report(json.loads(live.stdout))
        # Check imported APIs, not just source spelling. No hardware user-client
        # opening, memory mapping or property writes belong in this inventory.
        imports = run('/usr/bin/nm', '-u', str(binary)).stdout
        forbidden = ('IOServiceOpen', 'IOConnectCall', 'IOConnectMapMemory',
                     'IORegistryEntrySetCFProperty', 'IORegistryEntrySetCFProperties')
        if any(name in imports for name in forbidden):
            raise ValueError('The inventory imports a forbidden hardware or write API.')
        launcher_text = launcher.read_text()
        if launcher_text.count('NVIDIA_PCI_BINARY_SHA_PENDING') != 1:
            raise ValueError('The executable hash placeholder is not unique.')
        payload = {
            'bin/nvidia-pci-inventory': binary.read_bytes(),
            'CHECK-NVIDIA.command': launcher_text.replace(
                'NVIDIA_PCI_BINARY_SHA_PENDING', digest(binary.read_bytes())).encode(),
            'README.md': readme.read_text().replace(
                '](../../',
                '](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/'
                + commit + '/').encode(),
        }
        record = {'format': 1, 'package': PACKAGE, 'version': VERSION,
                  'github_sha': commit, 'architecture': 'x86_64',
                  'minimum_macos': '15.0', 'target': '10de:1f91',
                  'source_sha256': digest(source.read_bytes()),
                  'package_file_sha256_excluding_BUILD': {
                      name: digest(data) for name, data in payload.items()},
                  'validation': ['native Intel compile and link',
                                 'ad-hoc signature and thin Mach-O',
                                 'native read-only IORegistry enumeration',
                                 'report schema and imported API checks'],
                  'hardware_status': 'Laptop PCI visibility pending; no GPU initialization or acceleration.'}
        payload['BUILD.json'] = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
        payload['SHA256SUMS'] = ''.join(digest(data) + '  ' + name + '\n'
                                         for name, data in sorted(payload.items())).encode('ascii')
        pending = Path(temporary) / archive.name
        with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, data in sorted(payload.items()):
                entry = zipfile.ZipInfo(PACKAGE + '/' + name, (2026, 10, 15, 0, 0, 0))
                entry.create_system = 3
                executable = name.endswith('.command') or name.startswith('bin/')
                entry.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(entry, data)
        with zipfile.ZipFile(pending) as bundle:
            if bundle.testzip() is not None or len(bundle.namelist()) != len(payload):
                raise ValueError('The package failed its archive check.')
            for name, data in payload.items():
                if bundle.read(PACKAGE + '/' + name) != data:
                    raise ValueError('The ZIP differs from the verified build.')
        os.replace(pending, archive)
    sidecar.write_text(digest(archive.read_bytes()) + '  ' + archive.name + '\n', encoding='ascii')
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build(args.output_dir)
        print('Verified NVIDIA PCI package: ' + str(result))
        print('ZIP SHA256: ' + digest(result.read_bytes()))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print('NVIDIA PCI package not created: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr[-4000:] if error.stderr else '', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
