#!/usr/bin/env python3
"""Publish the immutable first EFI artifact after its recorded integrity checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86'
LOCK = ROOT / 'config/efi/releases/v0.1.0.json'
PACKAGE = 'S540-Tahoe-EFI-v0.1.0.zip'


def load_lock():
    lock = json.loads(LOCK.read_text())
    assert lock['tag'] == 'v0.1.0'
    assert lock['repository'] == REPOSITORY
    assert re.fullmatch(r'[0-9a-f]{40}', lock['source_commit'])
    for key in ('zip_sha256', 'artifact_sha256'):
        assert re.fullmatch(r'[0-9a-f]{64}', lock[key])
    for key in ('run_id', 'artifact_id'):
        assert isinstance(lock[key], int) and lock[key] > 0
    return lock


def verify_package(directory, lock):
    package = directory / PACKAGE
    sidecar = directory / (PACKAGE + '.sha256')
    assert package.is_file() and not package.is_symlink()
    assert sidecar.is_file() and not sidecar.is_symlink()
    assert hashlib.sha256(package.read_bytes()).hexdigest() == lock['zip_sha256']
    assert sidecar.read_text().split() == [lock['zip_sha256'], PACKAGE]
    expected = json.loads((ROOT / 'config/efi/current/manifest.json').read_text())['files']
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert all(not name.startswith('/') and '..' not in Path(name).parts for name in names)
        actual = {name: hashlib.sha256(archive.read(name)).hexdigest()
                  for name in names if name.startswith('EFI/')}
        assert actual == expected
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['commit'] == lock['source_commit']
        assert manifest['component_hashes'] == expected
        assert 'No issues found.' in archive.read('ocvalidate.txt').decode()
        config = plistlib.loads(archive.read('EFI/OC/config.plist'))
        identity = config['PlatformInfo']['Generic']
        assert identity['MLB'] == identity['SystemSerialNumber'] == ''
        assert identity['ROM'] == bytes(6)
        assert identity['SystemUUID'] == '00000000-0000-0000-0000-000000000000'
        wifi = plistlib.loads(archive.read('EFI/OC/Kexts/itlwm.kext/Contents/Info.plist'))
        assert wifi['IOKitPersonalities']['itlwm']['WiFiConfig'] == {}
        assert archive.read('EFI/OC/config.plist') == (ROOT / 'config/efi/current/config.plist').read_bytes()
        for path in (ROOT / 'licenses/efi').rglob('*'):
            if path.is_file():
                assert archive.read('LICENSES/' + path.relative_to(ROOT / 'licenses/efi').as_posix()) == path.read_bytes()
    return package, sidecar


def api(path):
    result = subprocess.run(['gh', 'api', 'repos/' + REPOSITORY + '/' + path],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def verify_remote(lock):
    run = api('actions/runs/' + str(lock['run_id']))
    assert run['head_sha'] == lock['source_commit']
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    assert run['path'] == '.github/workflows/build-current-efi.yml'
    artifact = api('actions/artifacts/' + str(lock['artifact_id']))
    assert not artifact['expired']
    assert artifact['name'] == 'S540-Tahoe-EFI-v0.1.0'
    assert artifact['workflow_run']['id'] == lock['run_id']
    assert artifact['workflow_run']['head_sha'] == lock['source_commit']
    assert artifact['digest'] == 'sha256:' + lock['artifact_sha256']
    # Do not replace an existing tag or release during a rerun.
    assert all(item['ref'] != 'refs/tags/v0.1.0' for item in api('git/matching-refs/tags/v0.1.0'))
    assert all(item['tag_name'] != 'v0.1.0' for item in api('releases?per_page=100'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-directory', required=True, type=Path)
    parser.add_argument('--verify-only', action='store_true')
    arguments = parser.parse_args()
    try:
        lock = load_lock()
        assets = verify_package(arguments.artifact_directory, lock)
        if arguments.verify_only:
            print('Verified the immutable EFI package, manifest, privacy and license notices.')
            return 0
        assert os.environ.get('GITHUB_ACTIONS') == 'true'
        assert os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
        verify_remote(lock)
        subprocess.run(['gh', 'release', 'create', lock['tag'], '--repo', REPOSITORY,
                        '--target', lock['source_commit'], '--title',
                        'v0.1.0 — Initial macOS Tahoe EFI', '--notes-file',
                        str(ROOT / 'docs/releases/v0.1.0.md'), '--latest',
                        *map(str, assets)], check=True)
        print('Published the first EFI release.')
        return 0
    except (AssertionError, OSError, ValueError, KeyError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as error:
        print('Release publication stopped: integrity, source or existing-release check failed.')
        if not isinstance(error, subprocess.CalledProcessError):
            print(type(error).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
