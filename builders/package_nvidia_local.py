#!/usr/bin/env python3
"""Package pinned project sources for an Intel macOS local build; no binaries."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'S540-nvidia-build-local-v9'
SOURCE_FILES = [
    'builders/build_nvidia_transport.py',
    'builders/check_nvidia_foundations.py',
    'builders/check_nvidia_callers.py',
    'builders/check_nvidia_lifecycle.py',
    'builders/check_nvidia_runtime.py',
    'builders/check_nvidia_transport_preparation.py',
    'builders/check_nvidia_rm_services.py',
    'builders/check_nvidia_firmware_assets.py',
    'builders/reference/nvidia-rm-full-closure.json',
    'tests/test_nvidia_runtime_provenance.py',
    'tests/test_nvidia_rm_consumer_provenance.py',
    'tests/test_nvidia_lifecycle_provenance.py',
    'tests/test_nvidia_caller_provenance.py',
    'tests/test_nvidia_transport_kernel.py',
    'tests/test_nvidia_clock_provenance.py',
    'tests/test_nvidia_memory_provenance.py',
    'tests/test_nvidia_atomic_provenance.py',
    'packages/nvidia-transport/src/S540NvidiaPCIProbe.hpp',
    'packages/nvidia-transport/src/S540NvidiaPCIProbe.cpp',
    'packages/nvidia-transport/src/kmod_start.cpp',
    'packages/nvidia-transport/src/check_nvidia_transport.c',
    'packages/nvidia-transport/Info.plist',
    'packages/nvidia-transport/CHECK-TRANSPORT.command',
    'packages/nvidia-transport/README.md',
    'packages/nvidia-transport/LICENSE',
]
for component in ('nvidia-os-adapter', 'nvidia-caller-integration',
                  'nvidia-nvport-lifecycle', 'nvidia-nvport-runtime',
                  'nvidia-hardware-transport', 'nvidia-resource-server',
                  'nvidia-rm-services', 'nvidia-firmware-assets'):
    SOURCE_FILES.extend(path.relative_to(ROOT).as_posix()
                        for path in sorted((ROOT / 'packages' / component).rglob('*'))
                        if path.is_file() and '__pycache__' not in path.parts
                        and path.suffix != '.pyc')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package(commit: str, destination: Path) -> Path:
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('The source commit must be a full Git SHA.')
    payload = {}
    for name in SOURCE_FILES:
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise ValueError('A regular source file is required: ' + name)
        payload['source/' + name] = source.read_bytes()
    launcher = (ROOT / 'packages/nvidia-transport/BUILD-LOCAL.command').read_text()
    token = 'NVIDIA_LOCAL_SOURCE_COMMIT_PENDING'
    if launcher.count(token) != 1:
        raise ValueError('The launcher source commit placeholder is not unique.')
    payload['BUILD-LOCAL.command'] = launcher.replace(token, commit).encode()
    payload['README.txt'] = (
        'S540 NVIDIA 0.9.0 bundled RM subsystem and host services local native build\n\n'
        'This archive contains source code, not a compiled kext.\n'
        'Intel macOS, Apple Command Line Tools and Python zstandard 0.25.0 are required.\n'
        'The build downloads the pinned NVIDIA archive (about 409 MB), extracts only\n'
        'two unchanged firmware images and their complete matching agreement,\n'
        'and verifies their exact bytes. No installer is executed.\n'
        'Extract the complete folder into Downloads, then run:\n\n'
        'bash "$HOME/Downloads/' + NAME + '/BUILD-LOCAL.command"\n\n'
        'If developer tools are missing, run xcode-select --install, finish the\n'
        'Apple installation, and run the build command again.\n\n'
        'The command fetches the pinned public MacKernelSDK Git revision, runs\n'
        'policy tests, compiles and signs the native package, and runs its\n'
        'decoder self-tests. It never installs or loads the new kext, changes\n'
        'EFI, or requests an administrator password for the build.\n'
        'An already-loaded probe older than 0.9.0 is allowed as outdated;\n'
        'this does not claim that the new 0.9.0 probe has run.\n\n'
        'Outputs are kept in a private NVIDIA-BUILD folder on the Desktop.\n'
        'On success, share output/S540-nvidia-transport-v9.zip for review.\n'
        'On failure, share build.log from that folder.\n\n'
        'Project source commit: ' + commit + '\n'
    ).encode()
    payload['SOURCE-SHA256SUMS'] = ''.join(
        digest(data) + '  ' + name + '\n' for name, data in sorted(payload.items())
    ).encode('ascii')
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / (NAME + '.zip')
    if archive.exists():
        raise ValueError('The output already exists.')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(payload.items()):
            item = zipfile.ZipInfo(NAME + '/' + name, (2026, 10, 15, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | (0o755 if name.endswith('.command') else 0o644)) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(item, data)
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None or len(output.namelist()) != len(payload):
            raise ValueError('The source archive failed verification.')
    archive.with_suffix('.zip.sha256').write_text(
        digest(archive.read_bytes()) + '  ' + archive.name + '\n', encoding='ascii')
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        archive = package(args.source_commit, args.output_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, 'Source package not created: ' + str(error) + '\n')
    print('Local-build source package: ' + str(archive))
    print('ZIP SHA256: ' + digest(archive.read_bytes()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
