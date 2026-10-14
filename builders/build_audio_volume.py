#!/usr/bin/env python3
"""Package the native CI-built S540 full-range output driver without installing it."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

import build_audio_microphone as base

REPO = Path(__file__).resolve().parents[1]
PACKAGE = 'S540-volume-fine-v1'
VERSION = '3.6.10'
BUNDLE_FILES = base.BUNDLE_FILES


def verify_macho(path: Path) -> None:
    base.verify_macho(path)
    if b'S540OutputRangeFixActive' not in path.read_bytes():
        base.fail('The compiled driver lacks the guarded output-range marker.')


def make_package(built_bundle: Path, output: Path) -> Path:
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        base.fail('GITHUB_SHA must identify the CI commit.')
    patches = [REPO / 'patches/audio-microphone/input-gain.patch',
               REPO / 'patches/audio-volume/output-range.patch']
    for patch in patches:
        base.regular_file(patch)
    source_binary = built_bundle / 'Contents/MacOS/VoodooHDA'
    base.absolute_plain_path(str(source_binary))
    verify_macho(source_binary)
    info = base.load_original_info()
    info['CFBundleVersion'] = info['CFBundleShortVersionString'] = VERSION
    personality = info['IOKitPersonalities']['VoodooHDA']
    personality['VoodooHDAEnableVolumeChangeFix'] = True
    personality['S540InputGainFix'] = True
    personality['S540OutputRangeFix'] = True
    personality['MixerValues']['Rec'] = 50
    personality['MixerValues']['iMix'] = 100
    package = output / PACKAGE
    archive_path = output / f'{PACKAGE}.zip'
    checksum_path = output / f'{PACKAGE}.zip.sha256'
    if any(path.exists() or path.is_symlink() for path in (package, archive_path, checksum_path)):
        base.fail('The output already exists and will not be overwritten.')
    with tempfile.TemporaryDirectory(prefix='s540-volume-package-', dir=output) as temporary:
        stage = Path(temporary) / PACKAGE
        stage.mkdir()
        bundle = stage / 'assets/volume/VoodooHDA.kext'
        (bundle / 'Contents/MacOS').mkdir(parents=True)
        base.copy_plain(source_binary, bundle / 'Contents/MacOS/VoodooHDA', executable=True)
        (bundle / 'Contents/Info.plist').write_bytes(plistlib.dumps(info, sort_keys=False))
        (bundle / 'Contents/Info.plist').chmod(0o644)
        base.run('/usr/bin/codesign', '--force', '--sign', '-', str(bundle))
        base.run('/usr/bin/codesign', '--verify', '--strict', str(bundle))
        verify_macho(bundle / 'Contents/MacOS/VoodooHDA')
        manifest, payload_hashes = base.canonical_manifest(bundle)
        manifest_sha = base.digest(manifest)
        sums = stage / 'assets/volume/SHA256SUMS'
        sums.write_bytes(manifest)
        sums.chmod(0o644)
        for name in ('INSTALL-VOLUME.command', 'RESTORE-VOLUME.command', 'VERIFY-VOLUME.command'):
            base.copy_plain(REPO / 'packages/audio-volume' / name, stage / name, executable=True)
        helper_source = REPO / 'packages/audio-volume/tools/volume_driver_test.sh'
        base.regular_file(helper_source)
        helper_text = helper_source.read_text()
        if helper_text.count('VOLUME_MANIFEST_SHA_PENDING') != 1:
            base.fail('The volume manifest placeholder is not unique.')
        helper = stage / 'tools/volume_driver_test.sh'
        helper.parent.mkdir()
        helper.write_text(helper_text.replace('VOLUME_MANIFEST_SHA_PENDING', manifest_sha))
        helper.chmod(0o755)
        base.copy_plain(REPO / 'docs/guides/volume-control.md', stage / 'README.md')
        for name in ('VoodooHDA-LICENSE.txt', 'VoodooHDA-third-party-LICENSE.txt'):
            base.copy_plain(REPO / 'licenses/audio-tahoe' / name,
                            stage / 'licenses/audio-tahoe' / name)
        base.run('/bin/bash', str(helper), 'payload-check')
        patch_hashes = {patch.relative_to(REPO).as_posix(): base.file_digest(patch)
                        for patch in patches}
        lock = {
            'format': 1, 'version': VERSION,
            'source_commit': base.SOURCE_COMMIT, 'kernel_sdk_commit': base.SDK_COMMIT,
            'patch_sha256': patch_hashes,
            'original_release_archive_sha256': base.ARCHIVE_SHA,
            'payload_manifest_sha256': manifest_sha, 'files': payload_hashes,
        }
        base.write_json(stage / 'profiles/audio-volume-assets.lock.json', lock)
        base.write_json(stage / 'BUILD.json', {
            **lock, 'package': PACKAGE, 'github_sha': commit,
            'upstream_repository': 'CloverHackyColor/VoodooHDA',
            'kernel_sdk_repository': 'joevt/MacKernelSDK',
            'compiled_macho_sha256_before_signing': base.file_digest(source_binary),
            'package_file_sha256_excluding_BUILD': {
                item.relative_to(stage).as_posix(): base.file_digest(item)
                for item in sorted(stage.rglob('*')) if item.is_file()
            },
            'validation': ['pinned upstream archive and three source hashes',
                           'thin x86_64 MH_KEXT_BUNDLE',
                           'input and output policy markers',
                           'ad-hoc codesign --verify --strict',
                           'native read-only helper payload-check'],
        })
        staged_zip = Path(temporary) / archive_path.name
        with zipfile.ZipFile(staged_zip, 'w', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=9) as archive:
            for item in sorted(stage.rglob('*')):
                if item.is_symlink() or item.name == '.DS_Store':
                    base.fail('The package contains unsupported files.')
                if not item.is_file():
                    continue
                entry = zipfile.ZipInfo((Path(PACKAGE) / item.relative_to(stage)).as_posix(),
                                        date_time=(2026, 10, 14, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | stat.S_IMODE(item.stat().st_mode)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, item.read_bytes())
        staged_zip.chmod(0o644)
        zip_sha = base.file_digest(staged_zip)
        shutil.move(stage, package)
        shutil.move(staged_zip, archive_path)
        checksum_path.write_text(f'{zip_sha}  {archive_path.name}\n', encoding='ascii')
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--built-bundle', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    try:
        if sys.platform != 'darwin' or platform.machine() != 'x86_64':
            base.fail('Packaging requires Intel macOS and native Apple tools.')
        built = base.absolute_plain_path(args.built_bundle, directory=True)
        output = base.absolute_plain_path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        if not output.is_dir(): base.fail('The destination is not a directory.')
        archive = make_package(built, output)
        print(f'Verified package: {archive}')
        print(f'SHA256: {base.file_digest(archive)}')
        return 0
    except (ValueError, OSError, KeyError, plistlib.InvalidFileException,
            json.JSONDecodeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(f'Package not created: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr[-4000:], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
