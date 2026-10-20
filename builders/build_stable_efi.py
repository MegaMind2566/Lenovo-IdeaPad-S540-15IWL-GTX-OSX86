#!/usr/bin/env python3
"""Repackage the reviewed v0.2.0 EFI without compiling or upgrading drivers."""
import argparse
import hashlib
import io
import json
import os
import plistlib
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'config/efi/releases/v0.2.0'
DOCS = ROOT / 'docs/releases/v0.2.0'
VERSION = 'v0.2.0'
REPOSITORY = 'MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(data, expected, label):
    if digest(data) != expected:
        raise ValueError(f'SHA256 mismatch: {label}')
    return data


def archive(data):
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set()
        if sum(i.file_size for i in z.infolist()) > 512 * 1024 * 1024:
            raise ValueError('Archive exceeds size limit')
        for item in z.infolist():
            name = item.filename
            path = PurePosixPath(name)
            if (name in names or not name or path.is_absolute() or '..' in path.parts
                    or '\\' in name or '\x00' in name
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('Unsafe or duplicate archive path')
            names.add(name)
            if not item.is_dir():
                result[name] = z.read(item)
    return result


def gh_json(endpoint, missing_ok=False):
    p = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if p.returncode:
        if missing_ok and '(HTTP 404)' in p.stderr:
            return None
        raise RuntimeError(f'GitHub API request failed: {endpoint}')
    return json.loads(p.stdout)


def download_inputs(lock, directory):
    directory.mkdir(parents=True, exist_ok=True)
    for key in ('base', 'wifi'):
        item = lock[key]
        endpoint = f'repos/{REPOSITORY}/actions/artifacts/{item["artifact_id"]}'
        metadata = gh_json(endpoint)
        run = gh_json(f'repos/{REPOSITORY}/actions/runs/{item["run_id"]}')
        if not (metadata['id'] == item['artifact_id'] and not metadata['expired']
                and metadata['name'] == item['name']
                and metadata['workflow_run']['id'] == item['run_id']
                and metadata['workflow_run']['head_sha'] == item['source_commit']
                and metadata['digest'] == 'sha256:' + item['sha256']
                and metadata['size_in_bytes'] == item['size']
                and run['head_sha'] == item['source_commit']
                and run['path'] == item['workflow_path']
                and run['status'] == 'completed' and run['conclusion'] == 'success'):
            raise ValueError(f'Artifact provenance mismatch: {key}')
        destination = directory / item['filename']
        with destination.open('wb') as output:
            subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=output, check=True)
    for key in ('brightness', 'validator'):
        item = lock[key]
        with urllib.request.urlopen(item['url'], timeout=90) as response:
            (directory / item['filename']).write_bytes(response.read())


def load_inputs(lock, directory):
    inputs = {}
    for key in ('base', 'wifi', 'brightness', 'validator'):
        item = lock[key]
        data = (directory / item['filename']).read_bytes()
        if len(data) != item['size']:
            raise ValueError(f'Archive size mismatch: {key}')
        checked(data, item['sha256'], key)
        contents = archive(data)
        if 'inner_path' in item:
            inner = checked(contents[item['inner_path']], item['inner_sha256'], key + ' inner ZIP')
            contents = archive(inner)
        inputs[key] = contents
    return inputs


def validate_payload(payload):
    c = plistlib.loads(payload['EFI/OC/config.plist'])
    g = c['PlatformInfo']['Generic']
    if not (g['MLB'] == g['SystemSerialNumber'] == '' and g['ROM'] == bytes(6)
            and g['SystemUUID'] == '00000000-0000-0000-0000-000000000000'
            and g['SystemProductName'] == 'MacBookPro16,2'):
        raise ValueError('Public SMBIOS identity must contain placeholders')
    if c['Kernel']['Block']:
        raise ValueError('Obsolete NVMe block is present')
    args = c['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args']
    if '-wegnoegpu' not in args.split():
        raise ValueError('Stable Intel graphics policy changed')
    for path, data in payload.items():
        if any(p.startswith('._') or p == '.DS_Store' for p in path.split('/')):
            raise ValueError('Finder metadata in payload')
        if any(n in path for n in ('/itlwm.kext/', '/AppleALC.kext/', '/IntelBTPatcher.kext/', 'SSDT-DGPU-OFF.aml')):
            raise ValueError('Inactive payload in public package')
        if path.endswith('.plist') and 'WiFiConfig' in plistlib.loads(data):
            raise ValueError('Saved Wi-Fi configuration in package')
    bundles = []
    for item in c['Kernel']['Add']:
        if not item['Enabled']:
            raise ValueError('Disabled kernel entry in stable recipe')
        bundle = 'EFI/OC/Kexts/' + item['BundlePath']
        bundles.append(item['BundlePath'])
        for key in ('PlistPath', 'ExecutablePath'):
            if item[key] and bundle + '/' + item[key] not in payload:
                raise ValueError(f'Unresolved {key}: {item["BundlePath"]}')
    if 'AirportItlwm.kext' not in bundles:
        raise ValueError('Native Wi-Fi is missing')
    for item in c['ACPI']['Add']:
        if not item['Enabled'] or 'EFI/OC/ACPI/' + item['Path'] not in payload:
            raise ValueError('Unresolved ACPI entry')
    for item in c['UEFI']['Drivers']:
        if item['Enabled'] and 'EFI/OC/Drivers/' + item['Path'] not in payload:
            raise ValueError('Unresolved UEFI driver')


def compose(inputs, lock):
    expected = json.loads((RECIPE / 'payload-manifest.json').read_text())
    if expected['version'] != VERSION or len(expected['files']) != 53:
        raise ValueError('Unexpected payload manifest')
    payload = {}
    for name, checksum in expected['files'].items():
        if name == 'EFI/OC/config.plist':
            data = (RECIPE / 'config.plist').read_bytes()
        elif '/AirportItlwm.kext/' in name:
            data = inputs['wifi']['S540-wifi-native-v1/payload/' + name.removeprefix('EFI/OC/Kexts/')]
        elif '/BrightnessKeys.kext/' in name:
            data = inputs['brightness'][name.removeprefix('EFI/OC/Kexts/')]
        else:
            data = inputs['base'][name]
        payload[name] = checked(data, checksum, name)
    validate_payload(payload)
    files = dict(payload)
    files.update({n: b for n, b in inputs['base'].items() if n.startswith('LICENSES/')})
    files['LICENSES/BrightnessKeys-LICENSE.txt'] = (ROOT / 'licenses/efi/BrightnessKeys-LICENSE.txt').read_bytes()
    for old, new in [('LICENSE', 'AirportItlwm-LICENSE'), ('iwlwifi-firmware-license', 'AirportItlwm-iwlwifi-firmware-license')]:
        files['LICENSES/' + new] = inputs['wifi']['S540-wifi-native-v1/licenses/' + old]
    files['LICENSES/NOTICE.md'] += b'\n## v0.2.0 additions\n\nAirportItlwm replaces the inactive itlwm bundle. Its exact laobamac/itlwm source and build SDK are included under source/wifi; see SOURCE-PROVENANCE.md. BrightnessKeys 1.0.3 is from acidanthera/BrightnessKeys and its BSD license is included. All active EFI binary bytes are preserved from the working source EFI. OpenCore remains the original 1.0.8 DEBUG build; the validator is from the matching RELEASE tools archive.\n'
    for name in ('itlwm.tar.gz', 'MacKernelSDK.tar.gz', 'build_wifi_native.py'):
        files['source/wifi/' + name] = inputs['wifi']['S540-wifi-native-v1/source/' + name]
    files['source/wifi/sources.lock.json'] = inputs['wifi']['S540-wifi-native-v1/sources.lock.json']
    files['source/base-v0.1.0-manifest.json'] = inputs['base']['manifest.json']
    for name in ('RELEASE-NOTES.md', 'INSTALL.md', 'SOURCE-PROVENANCE.md'):
        files[name] = (DOCS / name).read_bytes()
    files['README.md'] = b'# S540 stable EFI v0.2.0\n\nIntel UHD 620 and native Wi-Fi for Lenovo IdeaPad S540-15IWL GTX (81SW).\n\nStart with INSTALL.md: the public SMBIOS identity MUST be personalized. Keep your working private EFI backup. VoodooHDA audio is installed separately on macOS. Read RELEASE-NOTES.md for confirmed features and unresolved F4-F10, SD and NVIDIA/HDMI.\n\nValidate an edited config on macOS with: ./tools/ocvalidate EFI/OC/config.plist\n\nOnly the EFI directory belongs on the EFI partition. The other files are documentation, licenses, validation tools and reproducible Wi-Fi sources.\n'
    files['sources.lock.json'] = (RECIPE / 'sources.lock.json').read_bytes()
    for name in ('ocvalidate', 'ocvalidate.linux'):
        files['tools/' + name] = inputs['validator']['Utilities/ocvalidate/' + name]
    files['VALIDATION.md'] = b'# Package validation\n\nAll 53 EFI file hashes match the reviewed public payload manifest. The 52 non-config files match the working source EFI byte for byte and are recovered from pinned existing artifacts. OpenCore 1.0.8 ocvalidate passed for the public config. Active kext, ACPI and UEFI paths resolve; inactive bundles and Finder metadata are excluded. SMBIOS fields contain public placeholders and no saved Wi-Fi configuration is included.\n\nThis is packaging/static validation, not a new boot, hardware test, native compilation or NVIDIA GPU initialization. The existing laptop observations are listed in RELEASE-NOTES.md.\n'
    return files


def run_validator(files):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        tool = root / 'ocvalidate.linux'
        tool.write_bytes(files['tools/ocvalidate.linux'])
        tool.chmod(0o755)
        config = root / 'config.plist'
        config.write_bytes(files['EFI/OC/config.plist'])
        subprocess.run([str(tool), str(config)], check=True)


def write_package(files, directory):
    files = dict(files)
    manifest = {'schema': 1, 'version': VERSION,
                'files': {n: digest(b) for n, b in sorted(files.items())}}
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / 'S540-Tahoe-EFI-v0.2.0.zip'
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(2026, 10, 20, 0, 0, 0))
            executable = '/MacOS/' in name or name.endswith('.efi') or name.startswith('tools/')
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, data, compresslevel=9)
    checksum = digest(destination.read_bytes())
    destination.with_suffix('.zip.sha256').write_text(f'{checksum}  {destination.name}\n')
    print(f'Built {destination.name}: {destination.stat().st_size} bytes; SHA256 {checksum}')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs-directory', type=Path, default=ROOT / 'build/stable-inputs')
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'build/stable-release')
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    lock = json.loads((RECIPE / 'sources.lock.json').read_text())
    if lock['version'] != VERSION or lock['repository'] != REPOSITORY:
        raise ValueError('Unexpected release identity')
    if args.download:
        if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
            raise ValueError('Publication download requires the expected repository')
        for endpoint in (f'repos/{REPOSITORY}/releases/tags/{VERSION}', f'repos/{REPOSITORY}/git/ref/tags/{VERSION}'):
            if gh_json(endpoint, missing_ok=True) is not None:
                raise ValueError('Release or tag already exists; refusing to overwrite')
        download_inputs(lock, args.inputs_directory)
    inputs = load_inputs(lock, args.inputs_directory)
    files = compose(inputs, lock)
    expected_manifest = RECIPE / 'package-manifest.json'
    if expected_manifest.exists():
        actual = {n: digest(b) for n, b in sorted(files.items())}
        if actual != json.loads(expected_manifest.read_text())['files']:
            raise ValueError('Full package content differs from reviewed manifest')
    run_validator(files)
    destination = write_package(files, args.output_directory)
    expected_path = RECIPE / 'package.sha256'
    if expected_path.exists():
        expected = expected_path.read_text().split()[0]
        checked(destination.read_bytes(), expected, 'final release ZIP')


if __name__ == '__main__':
    main()
