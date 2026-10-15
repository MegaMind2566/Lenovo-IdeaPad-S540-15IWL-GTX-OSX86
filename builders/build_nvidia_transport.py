#!/usr/bin/env python3
"""Build the bounded Intel PCI attachment probe; never load or install it."""
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

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'packages/nvidia-transport'
PACKAGE = 'S540-nvidia-transport-v1'
VERSION = '0.1.0'
SDK_COMMIT = '3f750085caa17ec3a7880f11c11bf4f48cd6a164'
BUNDLE = 'S540NvidiaPCIProbe.kext'
EXECUTABLE = 'S540NvidiaPCIProbe'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=90)


def plain(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError('A required regular file is missing: ' + path.name)


def macho(path: Path, expected_type: int) -> None:
    header = path.read_bytes()[:16]
    if len(header) != 16 or struct.unpack('<IIII', header)[0:2] != (0xFEEDFACF, 0x01000007) or struct.unpack('<IIII', header)[3] != expected_type:
        raise ValueError('The output has the wrong Intel Mach-O type: ' + path.name)
    if run('/usr/bin/lipo', '-archs', str(path)).stdout.strip() != 'x86_64':
        raise ValueError('The build must contain only x86_64.')


def build(sdk: Path, output: Path) -> Path:
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('An Intel macOS build host is required.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('GITHUB_SHA must identify the build commit.')
    sdk = sdk.resolve(strict=True)
    if run('/usr/bin/git', '-C', str(sdk), 'rev-parse', 'HEAD').stdout.strip() != SDK_COMMIT:
        raise ValueError('The kernel SDK does not match its pinned commit.')
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (PACKAGE + '.zip')
    sidecar = output / (archive.name + '.sha256')
    if archive.exists() or sidecar.exists():
        raise ValueError('The output already exists.')
    kernel_sources = [SOURCE / 'src/S540NvidiaPCIProbe.cpp', SOURCE / 'src/kmod_start.cpp']
    required = [*kernel_sources, SOURCE / 'src/S540NvidiaPCIProbe.hpp',
                SOURCE / 'src/check_nvidia_transport.c', SOURCE / 'Info.plist',
                SOURCE / 'CHECK-TRANSPORT.command', SOURCE / 'README.md',
                SOURCE / 'LICENSE', sdk / 'LICENSE.txt', sdk / 'Library/x86_64/libkmod.a']
    for item in required:
        plain(item)
    info = plistlib.loads((SOURCE / 'Info.plist').read_bytes())
    if info.get('CFBundleExecutable') != EXECUTABLE or info.get('CFBundleVersion') != VERSION:
        raise ValueError('The kernel bundle version or executable is inconsistent.')
    with tempfile.TemporaryDirectory(prefix='s540-nvidia-transport-', dir=output) as temporary:
        work = Path(temporary)
        bundle = work / BUNDLE
        (bundle / 'Contents/MacOS').mkdir(parents=True)
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info, sort_keys=False))
        flags = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-mkernel',
                 '-fapple-kext', '-fno-exceptions', '-fno-rtti', '-fno-builtin',
                 '-fno-common', '-fno-stack-protector', '-fno-threadsafe-statics',
                 '-fno-asynchronous-unwind-tables', '-fno-unwind-tables',
                 '-mno-red-zone', '-DKERNEL', '-D__KERNEL__', '-O2',
                 '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
                 '-std=c++17', '-nostdinc', '-nostdinc++',
                 '-isystem', str(sdk / 'Headers'), '-I', str(SOURCE / 'src')]
        objects = []
        for source in kernel_sources:
            obj = work / (source.stem + '.o')
            run('/usr/bin/xcrun', 'clang++', *flags, '-c', str(source), '-o', str(obj))
            objects.append(str(obj))
        binary = bundle / 'Contents/MacOS' / EXECUTABLE
        run('/usr/bin/xcrun', 'clang++', '-arch', 'x86_64',
            '-mmacosx-version-min=15.0', '-mkernel', '-nostdlib',
            '-Wl,-kext', '-Wl,-no_source_version', *objects,
            str(sdk / 'Library/x86_64/libkmod.a'), '-o', str(binary))
        macho(binary, 11)
        symbols = run('/usr/bin/nm', '-g', str(binary)).stdout
        for symbol in ('_kmod_info', '__realmain', '__antimain'):
            if not re.search(r'\b[SD] ' + re.escape(symbol) + r'$', symbols, re.M):
                raise ValueError('The kext entry metadata is missing: ' + symbol)
        if b'S540NvidiaPCIProbeSnapshot' not in binary.read_bytes():
            raise ValueError('The kernel snapshot marker is absent.')
        if b'Source available under APSL 2.0:' not in binary.read_bytes():
            raise ValueError('The linked module runtime source notice is absent.')
        run('/usr/bin/codesign', '--force', '--sign', '-', str(bundle))
        run('/usr/bin/codesign', '--verify', '--strict', str(bundle))
        checker = work / 'check-nvidia-transport'
        run('/usr/bin/xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
            '-O2', '-fstack-protector-strong', '-arch', 'x86_64',
            '-mmacosx-version-min=15.0', '-framework', 'IOKit', '-framework', 'CoreFoundation',
            str(SOURCE / 'src/check_nvidia_transport.c'), '-o', str(checker))
        macho(checker, 2)
        run('/usr/bin/codesign', '--force', '--sign', '-', str(checker))
        run('/usr/bin/codesign', '--verify', '--strict', str(checker))
        run(str(checker), '--self-test')
        live = json.loads(run(str(checker)).stdout)
        if live.get('format') != 1 or live.get('complete') is not True or live.get('status') != 'not_attached':
            raise ValueError('The native runner must complete without a loaded probe.')
        imports = run('/usr/bin/nm', '-u', str(checker)).stdout
        if any(name in imports for name in ('IOServiceOpen', 'IOConnectCall', 'IOConnectMapMemory', 'IORegistryEntrySetCFProperty', 'IORegistryEntrySetCFProperties')):
            raise ValueError('The reporter imports a hardware-client or write API.')
        launcher = (SOURCE / 'CHECK-TRANSPORT.command').read_text()
        placeholder = 'NVIDIA_TRANSPORT_BINARY_SHA_PENDING'
        if launcher.count(placeholder) != 1:
            raise ValueError('The report executable checksum placeholder is not unique.')
        payload = {
            'bin/check-nvidia-transport': checker.read_bytes(),
            'CHECK-TRANSPORT.command': launcher.replace(placeholder, digest(checker.read_bytes())).encode(),
            'README.md': (SOURCE / 'README.md').read_bytes(),
            'LICENSE': (SOURCE / 'LICENSE').read_bytes(),
            'licenses/MacKernelSDK-APSL-2.0.txt': (sdk / 'LICENSE.txt').read_bytes(),
            'THIRD-PARTY-NOTICES.txt': (
                'The unmodified kernel module runtime is from MacKernelSDK.\n'
                'Portions Copyright (c) 2000, 2008-2012 Apple Inc. All rights reserved.\n'
                'Source code is available under the Apple Public Source License 2.0 at:\n'
                'https://github.com/acidanthera/MacKernelSDK/tree/' + SDK_COMMIT + '/Library/kmod\n'
                'The corresponding license is included in licenses/MacKernelSDK-APSL-2.0.txt.\n').encode(),
            'Kernel-Add-entry.plist': plistlib.dumps({
                'Arch': 'x86_64', 'BundlePath': BUNDLE,
                'Comment': 'S540 NVIDIA PCI attachment experiment', 'Enabled': True,
                'ExecutablePath': 'Contents/MacOS/' + EXECUTABLE,
                'MaxKernel': '25.99.99', 'MinKernel': '25.0.0',
                'PlistPath': 'Contents/Info.plist'}, sort_keys=False),
        }
        for item in sorted(bundle.rglob('*')):
            if item.is_symlink():
                raise ValueError('The signed bundle contains a symbolic link.')
            if item.is_file():
                payload[BUNDLE + '/' + item.relative_to(bundle).as_posix()] = item.read_bytes()
        record = {'format': 1, 'package': PACKAGE, 'version': VERSION,
                  'github_sha': commit, 'architecture': 'x86_64',
                  'kernel_sdk_repository': 'acidanthera/MacKernelSDK', 'kernel_sdk_commit': SDK_COMMIT,
                  'target': {'vendor_id': '0x10de', 'device_id': '0x1f91',
                             'subsystem_vendor_id': '0x17aa', 'subsystem_device_id': '0x3806'},
                  'source_sha256': {item.relative_to(ROOT).as_posix(): digest(item.read_bytes())
                                    for item in required if item.is_relative_to(ROOT)},
                  'package_file_sha256_excluding_BUILD': {name: digest(data) for name, data in payload.items()},
                  'validation': ['native Intel kernel compile and link', 'thin x86_64 Mach-O and module entry metadata',
                                 'ad-hoc signature verification', 'native report decoder self-test',
                                 'native live enumeration without a loaded probe'],
                  'hardware_status': 'Laptop PCI visibility confirmed; probe attachment awaits the experimental boot.'}
        payload['BUILD.json'] = (json.dumps(record, indent=2, sort_keys=True) + '\n').encode()
        payload['SHA256SUMS'] = ''.join(digest(data) + '  ' + name + '\n' for name, data in sorted(payload.items())).encode('ascii')
        pending = work / archive.name
        with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle_zip:
            for name, data in sorted(payload.items()):
                entry = zipfile.ZipInfo(PACKAGE + '/' + name, (2026, 10, 15, 0, 0, 0))
                entry.create_system = 3
                executable = name.endswith('.command') or name.startswith('bin/') or name.endswith('/MacOS/' + EXECUTABLE)
                entry.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                bundle_zip.writestr(entry, data)
        with zipfile.ZipFile(pending) as bundle_zip:
            if bundle_zip.testzip() is not None or len(bundle_zip.namelist()) != len(payload):
                raise ValueError('The package archive failed verification.')
        os.replace(pending, archive)
    sidecar.write_text(digest(archive.read_bytes()) + '  ' + archive.name + '\n', encoding='ascii')
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-sdk', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        archive = build(args.kernel_sdk, args.output_dir)
        print('Verified NVIDIA PCI attachment package: ' + str(archive))
        print('ZIP SHA256: ' + digest(archive.read_bytes()))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print('NVIDIA transport package not created: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-6000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
