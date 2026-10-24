#!/usr/bin/env python3
"""Publish only the reviewed v0.3.0 assets, retaining all previous releases."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import subprocess
import tempfile
from urllib.parse import urljoin, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86'
TAG = 'v0.3.0'
BRANCH = 'release/non-nvidia-efi-v0.3.0'
TITLE = 'v0.3.0 — Non-NVIDIA EFI and updated hardware status'
REQUEST = '.github/release-requests/non-nvidia-v0.3.0.json'
RECIPE = ROOT / 'config/efi/releases/v0.3.0'
EFI_NAME = 'S540-Tahoe-EFI-v0.3.0.zip'
BOUND_FILES = (
    'builders/build_non_nvidia_release.py', 'builders/publish_non_nvidia_release.py',
    'tests/test_non_nvidia_publication.py',
    '.github/workflows/publish-non-nvidia-efi.yml',
    *('config/efi/releases/v0.3.0/' + n for n in (
        'config.plist', 'sources.lock.json', 'payload-manifest.json',
        'package-manifest.json', 'package.sha256', 'companions.lock.json', 'refind.conf')),
    *('docs/releases/v0.3.0/' + n for n in (
        'RELEASE-NOTES.md', 'INSTALL.md', 'SOURCE-PROVENANCE.md')),
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def api(endpoint, method='GET', body=None, missing_ok=False):
    command = ['gh', 'api', f'repos/{REPOSITORY}/' + endpoint, '--method', method]
    if body is not None:
        command += ['--input', '-']
    p = subprocess.run(command, input=None if body is None else json.dumps(body),
                       capture_output=True, text=True)
    if p.returncode:
        if missing_ok and 'HTTP 404' in p.stderr:
            return None
        raise RuntimeError('GitHub API request failed: ' + endpoint)
    return json.loads(p.stdout)


def unpack(data):
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        require(sum(i.file_size for i in z.infolist()) <= 512 * 1024 * 1024,
                'Archive exceeds extraction bound')
        seen = set()
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            require(item.filename and item.filename not in seen and not p.is_absolute()
                    and '..' not in p.parts and '\\' not in item.filename
                    and '\x00' not in item.filename
                    and not stat.S_ISLNK(item.external_attr >> 16),
                    'Unsafe or duplicate archive member')
            seen.add(item.filename)
            if not item.is_dir():
                result[item.filename] = z.read(item)
    return result


def lock():
    value = json.loads((RECIPE / 'companions.lock.json').read_text())
    require(value['version'] == TAG and value['repository'] == REPOSITORY,
            'Unexpected companion lock identity')
    for name in ('audio', 'hotkeys'):
        x = value[name]
        require(re.fullmatch(r'[0-9a-f]{64}', x['sha256']) and x['size'] > 0
                and x['asset_name'] == Path(x['asset_name']).name,
                'Invalid companion lock')
    return value


def check_bytes(data, item):
    require(len(data) == item['size'] and sha(data) == item['sha256'],
            'Asset differs from reviewed bytes: ' + item['asset_name'])


def release():
    values = api('releases?per_page=100')
    matches = [r for r in values if r['tag_name'] == TAG]
    require(len(matches) <= 1, 'Ambiguous release identity')
    return matches[0] if matches else None


def download_asset(asset_id):
    return subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/releases/assets/{asset_id}',
                                    '-H', 'Accept: application/octet-stream'])


def prepare_assets(directory):
    items = lock()
    directory.mkdir(parents=True, exist_ok=True)
    audio = items['audio']
    old = api('releases/tags/' + audio['source_tag'])
    found = [a for a in old['assets'] if a['name'] == audio['asset_name']]
    require(len(found) == 1 and found[0]['id'] == audio['source_asset_id'],
            'Unexpected original audio asset')
    data = download_asset(found[0]['id'])
    check_bytes(data, audio)
    (directory / audio['asset_name']).write_bytes(data)

    hotkeys = items['hotkeys']
    # Prefer the permanent asset after publication; bootstrap from the recorded CI artifact.
    current = release()
    existing = [] if current is None else [a for a in current['assets']
                                           if a['name'] == hotkeys['asset_name']]
    require(len(existing) <= 1, 'Ambiguous hotkey asset')
    if existing:
        data = download_asset(existing[0]['id'])
    else:
        native = hotkeys['native_artifact']
        meta = api('actions/artifacts/' + str(native['id']))
        run = api('actions/runs/' + str(native['run_id']))
        require(not meta['expired'] and meta['id'] == native['id']
                and meta['name'] == native['name'] and meta['size_in_bytes'] == native['size']
                and meta['digest'] == 'sha256:' + native['sha256']
                and meta['workflow_run']['id'] == native['run_id']
                and meta['workflow_run']['head_sha'] == native['source_commit']
                and run['head_sha'] == native['source_commit']
                and run['path'] == native['workflow_path']
                and run['status'] == 'completed' and run['conclusion'] == 'success',
                'Native hotkey artifact provenance differs or expired')
        outer = subprocess.check_output(['gh', 'api',
            f'repos/{REPOSITORY}/actions/artifacts/{native["id"]}/zip'])
        require(len(outer) == native['size'] and sha(outer) == native['sha256'],
                'Native artifact bytes differ')
        data = unpack(outer)[native['inner_path']]
    check_bytes(data, hotkeys)
    (directory / hotkeys['asset_name']).write_bytes(data)
    for item in (audio, hotkeys):
        name = item['asset_name']
        (directory / (name + '.sha256')).write_text(f'{item["sha256"]}  {name}\n')


def validate_assets(directory):
    companions = lock()
    efi_sha, efi_name = (RECIPE / 'package.sha256').read_text().split()
    require(efi_name == EFI_NAME and re.fullmatch(r'[0-9a-f]{64}', efi_sha),
            'Invalid reviewed EFI checksum')
    expected = {EFI_NAME: efi_sha,
                **{companions[k]['asset_name']: companions[k]['sha256']
                   for k in ('audio', 'hotkeys')}}
    names = set(expected) | {n + '.sha256' for n in expected}
    actual = {p.name for p in directory.iterdir() if p.is_file()}
    require(actual == names, 'Release directory must contain exactly the six reviewed assets')
    for name, checksum in expected.items():
        path = directory / name
        require(not path.is_symlink() and sha(path.read_bytes()) == checksum,
                'Local ZIP checksum differs: ' + name)
        sidecar = directory / (name + '.sha256')
        require(not sidecar.is_symlink()
                and sidecar.read_bytes() == f'{checksum}  {name}\n'.encode(),
                'Local checksum sidecar differs: ' + name)
        unpack(path.read_bytes())
    for key in ('audio', 'hotkeys'):
        check_bytes((directory / companions[key]['asset_name']).read_bytes(), companions[key])
    files = unpack((directory / EFI_NAME).read_bytes())
    manifest = json.loads(files['manifest.json'])
    require(manifest['version'] == TAG and set(files) == set(manifest['files']) | {'manifest.json'},
            'EFI manifest paths differ')
    require(all(sha(files[n]) == h for n, h in manifest['files'].items()),
            'EFI manifest checksum differs')
    config = plistlib.loads(files['EFI/OC/config.plist'])
    generic = config['PlatformInfo']['Generic']
    require(generic['SystemSerialNumber'] == generic['MLB'] == '' and generic['ROM'] == bytes(6)
            and generic['SystemUUID'] == '00000000-0000-0000-0000-000000000000',
            'Personal SMBIOS identity in public archive')
    require('-wegnoegpu' in config['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args'].split()
            and config['Misc']['Security']['ScanPolicy'] == 769,
            'Non-NVIDIA/native-Windows boot policy changed')
    require(all(n.startswith('EFI/OC/') for n in files if n.startswith('EFI/')),
            'Unexpected Microsoft/fallback boot files in archive')
    return {p.name: p for p in sorted(directory.iterdir()) if p.name in names}


def validate_request():
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH,
            'Publication is restricted to the explicit repository/release branch')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    parent = subprocess.check_output(['git', 'rev-parse', 'HEAD^'], cwd=ROOT, text=True).strip()
    require(head == os.environ.get('GITHUB_SHA'), 'Checkout/source commit differs')
    changed = subprocess.check_output(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', head],
                                      cwd=ROOT, text=True).splitlines()
    require(changed == [REQUEST], 'Publication request commit must change only its request file')
    request = json.loads((ROOT / REQUEST).read_text())
    require(request['schema'] == 1 and request['version'] == TAG
            and request['source_parent'] == parent
            and re.fullmatch(r'[A-Za-z0-9._-]{8,100}', request['batch'])
            and set(request['files']) == set(BOUND_FILES), 'Invalid publication request binding')
    require(all(sha((ROOT / n).read_bytes()) == request['files'][n] for n in BOUND_FILES),
            'Publication source binding differs')
    return head


def release_notes():
    text = (ROOT / 'docs/releases/v0.3.0/RELEASE-NOTES.md').read_text()
    require('development' in text.lower(), 'Release must retain ongoing development status')
    base = f'https://github.com/{REPOSITORY}/blob/{TAG}/docs/releases/v0.3.0/'
    def replace(match):
        target = match.group(2)
        if target.startswith('#') or urlsplit(target).scheme:
            return match.group(0)
        return match.group(1) + urljoin(base, target) + match.group(3)
    return re.sub(r'(\]\()([^\s)]+)(\))', replace, text).strip()


def validate_remote(value, head, notes, assets, complete=False, download=False):
    require(value['tag_name'] == TAG and value['target_commitish'] == head
            and value['name'] == TITLE and not value['prerelease']
            and value['body'].replace('\r\n', '\n').strip() == notes,
            'Existing release identity/body differs; refusing replacement')
    remote = {a['name']: a for a in value['assets']}
    require(len(remote) == len(value['assets']) and set(remote) <= set(assets),
            'Unexpected or duplicate existing release assets')
    if complete:
        require(set(remote) == set(assets), 'Uploaded asset set incomplete')
    for name, a in remote.items():
        data = assets[name].read_bytes()
        require(a['state'] == 'uploaded' and a['size'] == len(data)
                and a['digest'] == 'sha256:' + sha(data), 'Remote digest differs: ' + name)
        if download:
            require(download_asset(a['id']) == data, 'Downloaded remote bytes differ: ' + name)


def publish(directory):
    head = validate_request()
    assets = validate_assets(directory)
    notes = release_notes()
    tag = api('git/ref/tags/' + TAG, missing_ok=True)
    if tag is not None:
        require(tag['object']['type'] == 'commit' and tag['object']['sha'] == head,
                'Existing tag points elsewhere; refusing replacement')
    value = release()
    if value is None:
        with tempfile.TemporaryDirectory(prefix='efi-release-notes-') as temp:
            path = Path(temp) / 'notes.md'
            path.write_text(notes + '\n')
            subprocess.run(['gh', 'release', 'create', TAG, '--repo', REPOSITORY,
                            '--target', head, '--draft', '--title', TITLE,
                            '--notes-file', str(path)], check=True)
        value = release()
    require(value is not None, 'Draft creation not found')
    validate_remote(value, head, notes, assets)
    if not value['draft']:
        validate_remote(value, head, notes, assets, complete=True, download=True)
        require(tag is not None, 'Published release tag missing')
        print(value['html_url'])
        return
    release_id = value['id']
    for name, path in assets.items():
        current = release()
        require(current['id'] == release_id and current['draft'], 'Draft changed during upload')
        validate_remote(current, head, notes, assets)
        if name not in {a['name'] for a in current['assets']}:
            subprocess.run(['gh', 'release', 'upload', TAG, str(path), '--repo', REPOSITORY], check=True)
    current = release()
    require(current['id'] == release_id and current['draft'], 'Draft changed before publication')
    validate_remote(current, head, notes, assets, complete=True, download=True)
    published = api('releases/' + str(release_id), 'PATCH', {'draft': False, 'make_latest': 'true'})
    require(not published['draft'] and published['id'] == release_id, 'Publication not confirmed')
    validate_remote(published, head, notes, assets, complete=True)
    tag = api('git/ref/tags/' + TAG)
    require(tag['object']['type'] == 'commit' and tag['object']['sha'] == head,
            'Published tag differs from the source request')
    print(published['html_url'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-assets', action='store_true')
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--publish', action='store_true')
    parser.add_argument('--assets-directory', type=Path, default=ROOT / 'build/non-nvidia-release')
    args = parser.parse_args()
    if args.prepare_assets:
        prepare_assets(args.assets_directory)
    elif args.check_only:
        validate_assets(args.assets_directory)
        print('All six reviewed release assets verified; no publication performed.')
    else:
        publish(args.assets_directory)


if __name__ == '__main__':
    main()
