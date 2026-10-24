#!/usr/bin/env python3
"""Assemble the reviewed v0.3.0 non-NVIDIA EFI from pinned public assets."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import plistlib
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v0.3.0'
REPOSITORY = 'MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(data, expected, label):
    if sha(data) != expected:
        raise ValueError(f'SHA-256 mismatch: {label}')
    return data


def unpack(data):
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > 512 * 1024 * 1024:
            raise ValueError('Archive exceeds size limit')
        seen = set()
        for i in z.infolist():
            p = PurePosixPath(i.filename)
            if (not i.filename or i.filename in seen or p.is_absolute()
                    or '..' in p.parts or '\\' in i.filename or '\x00' in i.filename
                    or stat.S_ISLNK(i.external_attr >> 16)):
                raise ValueError('Unsafe or duplicate ZIP member')
            seen.add(i.filename)
            if not i.is_dir():
                result[i.filename] = z.read(i)
    return result


def load_inputs(lock, directory, download):
    result = {}
    directory.mkdir(parents=True, exist_ok=True)
    for name in ('base', 'opencore', 'sd'):
        item = lock[name]
        path = directory / item['filename']
        if download and not path.exists():
            with urllib.request.urlopen(item['url'], timeout=120) as response:
                path.write_bytes(response.read())
        data = path.read_bytes()
        if len(data) != item['size']:
            raise ValueError(f'Input size mismatch: {name}')
        checked(data, item['sha256'], name)
        result[name] = unpack(data)
    return result


def validate_payload(payload):
    c = plistlib.loads(payload['EFI/OC/config.plist'])
    g = c['PlatformInfo']['Generic']
    if not (g['MLB'] == g['SystemSerialNumber'] == '' and g['ROM'] == bytes(6)
            and g['SystemUUID'] == '00000000-0000-0000-0000-000000000000'
            and g['SystemProductName'] == 'MacBookPro16,2'):
        raise ValueError('Public SMBIOS placeholders changed')
    args = c['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args']
    if '-wegnoegpu' not in args.split() or c['Misc']['Security']['ScanPolicy'] != 769:
        raise ValueError('Non-NVIDIA or native-Windows boot policy changed')
    if c['Kernel']['Block']:
        raise ValueError('Unexpected kernel block')
    bundles = []
    for item in c['Kernel']['Add']:
        if not item['Enabled'] or 'nvidia' in item['BundlePath'].lower():
            raise ValueError('Disabled or NVIDIA kernel entry')
        bundles.append(item['BundlePath'])
        prefix = 'EFI/OC/Kexts/' + item['BundlePath'] + '/'
        for key in ('ExecutablePath', 'PlistPath'):
            if item[key] and prefix + item[key] not in payload:
                raise ValueError(f'Unresolved kext path: {item["BundlePath"]}')
    if not {'AirportItlwm.kext', 'BigSurSDXC.kext'} <= set(bundles):
        raise ValueError('Native Wi-Fi or SD driver missing')
    for item in c['ACPI']['Add']:
        if not item['Enabled'] or 'EFI/OC/ACPI/' + item['Path'] not in payload:
            raise ValueError('Unresolved or disabled ACPI entry')
    for item in c['UEFI']['Drivers']:
        if item['Enabled'] and 'EFI/OC/Drivers/' + item['Path'] not in payload:
            raise ValueError('Unresolved UEFI driver')
    for name, data in payload.items():
        parts = PurePosixPath(name).parts
        if (not name.startswith('EFI/OC/') or any(p.startswith('._') or p == '.DS_Store' for p in parts)
                or any(x in name for x in ('/AppleALC.kext/', '/IntelBTPatcher.kext/', '/itlwm.kext/',
                                           'SSDT-DGPU-OFF.aml', 'Nvidia', 'NVIDIA'))):
            raise ValueError(f'Unexpected boot payload: {name}')
        if name.endswith('.plist') and 'WiFiConfig' in plistlib.loads(data):
            raise ValueError('Saved Wi-Fi configuration')


def compose(inputs, lock, recipe, docs):
    base, oc, sd = (inputs[n] for n in ('base', 'opencore', 'sd'))
    payload = {n: b for n, b in base.items() if n.startswith('EFI/OC/')}
    for name in ('EFI/OC/OpenCore.efi', 'EFI/OC/Drivers/OpenRuntime.efi'):
        payload[name] = oc['X64/' + name]
    payload['EFI/OC/config.plist'] = (recipe / 'config.plist').read_bytes()
    checked(payload['EFI/OC/config.plist'], lock['public_config_sha256'], 'public config')
    original = checked(sd['BigSurSDXC.kext/Contents/Info.plist'],
                       lock['sd']['original_info_sha256'], 'original SD Info.plist')
    if original.count(b'pci14e4,16bc') != 1:
        raise ValueError('SD match substitution is not unique')
    info = original.replace(b'pci14e4,16bc', b'pci1217,8621')
    checked(info, lock['sd']['direct_info_sha256'], 'direct-match SD Info.plist')
    binary = checked(sd['BigSurSDXC.kext/Contents/MacOS/BigSurSDXC'],
                     lock['sd']['unchanged_executable_sha256'], 'unchanged SD executable')
    prefix = 'EFI/OC/Kexts/BigSurSDXC.kext/Contents/'
    payload[prefix + 'Info.plist'] = info
    payload[prefix + 'MacOS/BigSurSDXC'] = binary
    expected = json.loads((recipe / 'payload-manifest.json').read_text())
    if expected['version'] != VERSION or len(expected['files']) != 54:
        raise ValueError('Unexpected reviewed payload manifest')
    if {n: sha(b) for n, b in sorted(payload.items())} != expected['files']:
        raise ValueError('EFI payload differs from the reviewed manifest')
    validate_payload(payload)
    files = dict(payload)
    files.update({n: b for n, b in base.items() if n.startswith(('LICENSES/', 'source/wifi/'))})
    files['source/base-v0.2.0-manifest.json'] = base['manifest.json']
    files['sources.lock.json'] = (recipe / 'sources.lock.json').read_bytes()
    for name in ('RELEASE-NOTES.md', 'INSTALL.md', 'SOURCE-PROVENANCE.md'):
        files[name] = (docs / name).read_bytes()
    files['README.md'] = b'''# S540 non-NVIDIA EFI v0.3.0\n\nAn ongoing development snapshot for Lenovo IdeaPad S540-15IWL GTX (81SW), using Intel UHD 620. Read RELEASE-NOTES.md for working, non-working and unverified hardware.\n\nStart with INSTALL.md. Personalize the public SMBIOS placeholders before booting. Merge EFI/OC while preserving your existing EFI/BOOT, EFI/Microsoft, rEFInd and firmware entries. This archive is not a drop-in USB boot image.\n\nAudio and hotkey support include separately installed macOS components; copying this EFI alone does not install them. The refind.conf under examples is only a reference for the already tested native-Windows route.\n'''
    files['examples/refind.conf'] = (recipe / 'refind.conf').read_bytes()
    for name in ('ocvalidate', 'ocvalidate.linux'):
        files['tools/' + name] = oc['Utilities/ocvalidate/' + name]
    files['LICENSES/NOTICE.md'] += b'''\n\n## v0.3.0 current payload\n\nThe historical notices above describe their earlier snapshots. This version uses OpenCore 1.0.8 RELEASE and its matching OpenRuntime.efi. BigSurSDXC 1.9.0 is the unchanged Apple executable retained in the pinned OpenCore Legacy Patcher payload; only its Info.plist match string is changed for the observed O2Micro 1217:8621. This is not the S18R/3V3 experiment. See SOURCE-PROVENANCE.md and sources.lock.json. Microsoft boot binaries and the rEFInd executable are not distributed in this package.\n'''
    files['LICENSES/BigSurSDXC-NOTICE.md'] = b'''# BigSurSDXC provenance notice\n\nThe driver identifies itself as Apple Inc. 2009-2020, version 1.9.0. It is recovered unchanged from the pinned dortania/OpenCore-Legacy-Patcher payload named in sources.lock.json. The single Info.plist IONameMatch substitution is documented and hash-checked by the builder. The OCLP project's tooling license is not presented as a license grant for Apple's binary. This notice records provenance and attribution.\n'''
    files['VALIDATION.md'] = b'''# Validation boundary\n\nAll 54 EFI file hashes match the reviewed payload manifest. The 53 non-config files match the active tested internal source bytes. The public config differs only in placeholder SMBIOS identity and removal of inactive entries. OpenCore 1.0.8 ocvalidate is run during packaging; active kext, ACPI and UEFI references resolve.\n\nThe boot payload is EFI/OC only: no Microsoft files, fallback BOOT loader, rEFInd binary, personal identifiers, saved Wi-Fi configuration, test probes or Finder metadata are included. Read INSTALL.md before merging files.\n\nPackage checks are separate from hardware evidence. The user's confirmed internal-boot SD reading and previous laptop checks are described in RELEASE-NOTES.md. This is ongoing development, not universal hardware compatibility or project completion. No driver compilation or new NVIDIA initialization is performed.\n'''
    return files


def validate_config(files):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        tool = root / 'ocvalidate.linux'
        tool.write_bytes(files['tools/ocvalidate.linux'])
        tool.chmod(0o755)
        config = root / 'config.plist'
        config.write_bytes(files['EFI/OC/config.plist'])
        subprocess.run([str(tool), str(config)], check=True)


def write_zip(files, directory):
    files = dict(files)
    files['manifest.json'] = (json.dumps({'schema': 1, 'version': VERSION,
        'files': {n: sha(b) for n, b in sorted(files.items())}}, indent=2) + '\n').encode()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / 'S540-Tahoe-EFI-v0.3.0.zip'
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 24, 0, 0, 0))
            executable = '/MacOS/' in name or name.endswith('.efi') or name.startswith('tools/')
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data, compresslevel=9)
    destination.with_suffix('.zip.sha256').write_text(f'{sha(destination.read_bytes())}  {destination.name}\n')
    print(f'Built {destination}: {destination.stat().st_size} bytes; SHA256 {sha(destination.read_bytes())}')
    return destination


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs-directory', type=Path, default=ROOT / 'build/non-nvidia-inputs')
    p.add_argument('--output-directory', type=Path, default=ROOT / 'build/non-nvidia-release')
    p.add_argument('--recipe-directory', type=Path, default=ROOT / 'config/efi/releases/v0.3.0')
    p.add_argument('--docs-directory', type=Path, default=ROOT / 'docs/releases/v0.3.0')
    p.add_argument('--download', action='store_true')
    p.add_argument('--prepare-manifests', action='store_true', help='Local review only; cannot download/publication-build')
    args = p.parse_args()
    if args.prepare_manifests and args.download:
        raise ValueError('Review preparation and publication download cannot be combined')
    lock = json.loads((args.recipe_directory / 'sources.lock.json').read_text())
    if lock['version'] != VERSION or lock['repository'] != REPOSITORY:
        raise ValueError('Unexpected release identity')
    inputs = load_inputs(lock, args.inputs_directory, args.download)
    files = compose(inputs, lock, args.recipe_directory, args.docs_directory)
    package_manifest = args.recipe_directory / 'package-manifest.json'
    actual = {'schema': 1, 'version': VERSION, 'files': {n: sha(b) for n, b in sorted(files.items())}}
    if args.prepare_manifests:
        package_manifest.write_text(json.dumps(actual, indent=2) + '\n')
    elif not package_manifest.exists() or actual != json.loads(package_manifest.read_text()):
        raise ValueError('Full package differs from the reviewed content manifest')
    validate_config(files)
    destination = write_zip(files, args.output_directory)
    expected = args.recipe_directory / 'package.sha256'
    if args.prepare_manifests:
        expected.write_text(f'{sha(destination.read_bytes())}  {destination.name}\n')
    elif not expected.exists() or expected.read_text().split()[0] != sha(destination.read_bytes()):
        raise ValueError('ZIP differs from the reviewed final SHA-256')


if __name__ == '__main__':
    main()
