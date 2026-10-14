#!/usr/bin/env python3
"""Package the native EFI-copy visibility experiment without changing a disk."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

import build_efi_release as efi

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-visibility'
PACKAGE = 'S540-nvidia-visibility-v1'
VERSION = '1.0.0'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=120)


def verify_intel(path: Path) -> None:
    header = path.read_bytes()[:16]
    if len(header) != 16:
        raise ValueError('A compiled executable is truncated.')
    words = struct.unpack('<IIII', header)
    if words[:2] != (0xFEEDFACF, 0x01000007) or words[3] != 2:
        raise ValueError('A compiled executable is not thin Intel Mach-O.')


def build(output: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('Build this package on Intel macOS.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the build commit.')
    output = efi.ordinary_path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (PACKAGE + '.zip')
    sidecar = output / (archive.name + '.sha256')
    if archive.exists() or sidecar.exists():
        raise ValueError('The package destination already exists.')
    lock = json.loads((ROOT / 'config/profiles/assets.lock.json').read_text())
    asset = next(a for a in lock['assets'] if a['id'] == 'OpenCore')
    if asset['version'] != '1.0.8' or asset['sha256'] != '3f5f42b85703cf2c08e8dcd9245a52fb4326c9f4ef335c75b49f516cbbe131c6':
        raise ValueError('The OpenCore 1.0.8 validator lock changed.')
    with tempfile.TemporaryDirectory(prefix='nvidia-visibility-build-', dir=output) as temporary:
        work = Path(temporary)
        cache = work / 'assets'
        cache.mkdir()
        source_archive = efi.download(asset, cache)
        validator = efi.validator_from({'OpenCore': source_archive}, work)
        original_validator_sha = sha(validator.read_bytes())
        architectures = run('/usr/bin/lipo', '-archs', str(validator)).stdout.split()
        if architectures != ['x86_64']:
            thin = work / 'ocvalidate-intel'
            run('/usr/bin/lipo', str(validator), '-thin', 'x86_64', '-output', str(thin))
            validator = thin
        binaries = {'ocvalidate': validator}
        for name, source_name in (('locate-efi', 'locate_efi.swift'),
                                  ('prepare-nvidia-visibility', 'prepare_nvidia_visibility.swift')):
            source = SOURCE / 'src' / source_name
            efi.ordinary_file(source)
            destination = work / name
            run('/usr/bin/xcrun', 'swiftc', '-O', '-target',
                'x86_64-apple-macos15.0', str(source), '-o', str(destination))
            run(str(destination), '--self-test')
            binaries[name] = destination
        pci_source = ROOT / 'packages/nvidia-pci/src/nvidia_pci_inventory.c'
        inventory = work / 'nvidia-pci-inventory'
        run('/usr/bin/xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-O2', '-arch', 'x86_64', '-mmacosx-version-min=15.0',
            '-framework', 'IOKit', '-framework', 'CoreFoundation',
            str(pci_source), '-o', str(inventory))
        binaries['nvidia-pci-inventory'] = inventory
        for executable in binaries.values():
            executable.chmod(0o755)
            verify_intel(executable)
            run('/usr/bin/codesign', '--force', '--sign', '-', str(executable))
            run('/usr/bin/codesign', '--verify', '--strict', str(executable))
        run(sys.executable, str(ROOT / 'tests/test_nvidia_visibility.py'),
            '--tool', str(binaries['prepare-nvidia-visibility']))

        # Exercise the real validator and full staging flow against public
        # repository configuration and upstream boot files in a private fixture.
        fixture_source = work / 'fixture-source/EFI'
        fixture_parent = work / 'fixture-desktop'
        fixture_parent.mkdir()
        for relative in ('BOOT', 'OC'):
            (fixture_source / relative).mkdir(parents=True)
        with zipfile.ZipFile(source_archive) as upstream:
            for relative in ('BOOT/BOOTx64.efi', 'OC/OpenCore.efi'):
                member = 'X64/EFI/' + relative
                (fixture_source / relative).write_bytes(upstream.read(member))
        config = ROOT / 'config/efi/current/config.plist'
        baseline = config.read_bytes()
        (fixture_source / 'OC/config.plist').write_bytes(baseline)
        run(str(validator), str(config))
        run(str(binaries['prepare-nvidia-visibility']), str(fixture_source),
            str(fixture_parent), str(validator))
        candidates = list(fixture_parent.glob('NVIDIA-VISIBILITY.*/EFI/OC/config.plist'))
        if len(candidates) != 1 or (fixture_source / 'OC/config.plist').read_bytes() != baseline:
            raise ValueError('The native staging integration fixture failed.')
        old = plistlib.loads(baseline)
        expected = plistlib.loads(candidates[0].read_bytes())
        guid = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
        new_args = expected['NVRAM']['Add'][guid]['boot-args']
        if '-wegnoegpu' in new_args.split() or '-igfxblr' not in new_args.split():
            raise ValueError('The staged arguments failed their integration check.')
        expected['NVRAM']['Add'][guid]['boot-args'] = old['NVRAM']['Add'][guid]['boot-args']
        if old != expected:
            raise ValueError('The stage changed another configuration value.')

        payload = {'bin/' + name: path.read_bytes() for name, path in binaries.items()}
        prepare = (SOURCE / 'PREPARE-NVIDIA.command').read_text()
        for marker, name in (('NVIDIA_LOCATOR_SHA_PENDING', 'locate-efi'),
                             ('NVIDIA_STAGER_SHA_PENDING', 'prepare-nvidia-visibility'),
                             ('NVIDIA_OCVALIDATE_SHA_PENDING', 'ocvalidate')):
            if prepare.count(marker) != 1:
                raise ValueError('A prepare executable hash placeholder is not unique.')
            prepare = prepare.replace(marker, sha(payload['bin/' + name]))
        report = (ROOT / 'packages/nvidia-pci/CHECK-NVIDIA.command').read_text()
        if report.count('NVIDIA_PCI_BINARY_SHA_PENDING') != 1:
            raise ValueError('The report executable hash placeholder is not unique.')
        payload['PREPARE-NVIDIA.command'] = prepare.encode()
        payload['CHECK-NVIDIA.command'] = report.replace(
            'NVIDIA_PCI_BINARY_SHA_PENDING', sha(inventory.read_bytes())).encode()
        payload['README.md'] = (SOURCE / 'README.md').read_text().replace(
            '](../../', '](https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/blob/'
            + commit + '/').encode()
        payload['licenses/OpenCore-LICENSE.txt'] = (ROOT / 'licenses/efi/OpenCore-LICENSE.txt').read_bytes()
        payload['BUILD.json'] = (json.dumps({
            'format': 1, 'package': PACKAGE, 'version': VERSION, 'github_sha': commit,
            'architecture': 'x86_64', 'minimum_macos': '15.0',
            'opencore_archive_sha256': asset['sha256'],
            'original_validator_sha256': original_validator_sha,
            'source_sha256': {name: sha((SOURCE / 'src' / name).read_bytes())
                              for name in ('locate_efi.swift', 'prepare_nvidia_visibility.swift')},
            'package_file_sha256_excluding_BUILD': {name: sha(raw) for name, raw in payload.items()},
            'validation': ['native Intel build and signatures', 'locator and transformation fixtures',
                           'filesystem staging/ownership and unchanged source fixtures',
                           'pinned ocvalidate baseline/candidate integration'],
            'hardware_status': 'Experimental EFI is created only on the laptop; visibility boot result pending.'
        }, indent=2, sort_keys=True) + '\n').encode()
        payload['SHA256SUMS'] = ''.join(sha(raw) + '  ' + name + '\n'
                                         for name, raw in sorted(payload.items())).encode('ascii')
        pending = work / archive.name
        with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, raw in sorted(payload.items()):
                item = zipfile.ZipInfo(PACKAGE + '/' + name, (2026, 10, 15, 0, 0, 0))
                item.create_system = 3
                item.external_attr = (stat.S_IFREG | (0o755 if name.startswith('bin/') or name.endswith('.command') else 0o644)) << 16
                item.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(item, raw)
        with zipfile.ZipFile(pending) as bundle:
            if bundle.testzip() is not None or len(bundle.namelist()) != len(payload):
                raise ValueError('The archive failed its structure check.')
            for name, raw in payload.items():
                if bundle.read(PACKAGE + '/' + name) != raw:
                    raise ValueError('The ZIP differs from the verified build.')
        os.replace(pending, archive)
    sidecar.write_text(sha(archive.read_bytes()) + '  ' + archive.name + '\n', encoding='ascii')
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build(args.output_dir)
        print('Verified NVIDIA visibility package: ' + str(result))
        print('ZIP SHA256: ' + sha(result.read_bytes()))
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print('NVIDIA visibility package not created: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-5000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
