#!/usr/bin/env python3
"""Assemble a first-test EFI from pinned upstream releases; never modify disks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import stat
import struct
import subprocess
import urllib.request
import uuid
import zipfile

# Historical template kept below archive/efi-iniziale. Hardware sources,
# USB mapping and pinned assets remain shared at the repository root.
ROOT = Path(__file__).resolve().parents[3]
MODEL = 'MacBookPro16,2'
NVRAM_GUID = '7C436110-AB2A-4BBB-A880-FE41995C9F82'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_plist(path):
    return plistlib.loads(path.read_bytes())


def write_plist(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=False))


def download(asset, cache):
    dest = cache / asset['filename']
    if not dest.is_file():
        req = urllib.request.Request(asset['url'], headers={'User-Agent': 'S540-EFI-Builder/1.0'})
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read()
        dest.write_bytes(raw)
    raw = dest.read_bytes()
    if len(raw) != asset['size']:
        raise ValueError(f"Unexpected download size: {asset['id']}")
    digest = sha256(raw)
    if asset['sha256'] and digest != asset['sha256']:
        raise ValueError(f"SHA-256 mismatch: {asset['id']}")
    print(f"ASSET {asset['id']} {digest}")
    return dest, digest


def extract_zip(archive, dest):
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            parts = PurePosixPath(info.filename).parts
            if info.filename.startswith('/') or '..' in parts:
                raise ValueError('Unsafe ZIP path')
            if '__MACOSX' in parts:
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Unexpected symlink in release ZIP')
            z.extract(info, dest)


def unique_file(root, suffix):
    hits = [p for p in root.rglob('*') if p.is_file() and p.as_posix().endswith(suffix)]
    if len(hits) != 1:
        raise ValueError(f'Expected one {suffix}, got {len(hits)}')
    return hits[0]


def copy_kext(source, name, dest):
    hits = [p for p in source.rglob(name) if p.is_dir() and (p/'Contents/Info.plist').is_file()]
    if len(hits) != 1:
        raise ValueError(f'Expected one {name}, got {len(hits)}')
    shutil.copytree(hits[0], dest / name)


def identity_for(macserial, identity_path):
    if identity_path:
        ident = json.loads(identity_path.read_text())
        if ident['SystemProductName'] != MODEL:
            raise ValueError('Identity belongs to another SMBIOS model')
        return ident
    macserial.chmod(0o755)
    result = subprocess.run([str(macserial), '--model', MODEL, '--num', '1'],
                            check=True, text=True, capture_output=True)
    pairs = [line.split('|') for line in result.stdout.splitlines() if '|' in line]
    if len(pairs) != 1 or len(pairs[0]) != 2:
        raise ValueError('Cannot parse macserial output')
    serial, mlb = [p.strip() for p in pairs[0]]
    rom = bytearray(os.urandom(6))
    rom[0] = (rom[0] & 0xFC) | 0x02
    return {'SystemProductName': MODEL, 'SystemSerialNumber': serial, 'MLB': mlb,
            'SystemUUID': str(uuid.uuid4()).upper(), 'ROM': rom.hex()}


def kernel_entries(kext_dir):
    paths = [p for p in kext_dir.rglob('*.kext') if (p/'Contents/Info.plist').is_file()]
    by_id = {}
    for path in paths:
        info = read_plist(path/'Contents/Info.plist')
        identifier = info['CFBundleIdentifier']
        if identifier in by_id:
            raise ValueError(f'Duplicate kext identifier: {identifier}')
        by_id[identifier] = (path, info)
    ordered, active, finished = [], set(), set()

    def visit(identifier):
        if identifier in finished:
            return
        if identifier in active:
            raise ValueError('Kext dependency cycle')
        active.add(identifier)
        path, info = by_id[identifier]
        for dependency in sorted(info.get('OSBundleLibraries', {})):
            if dependency in by_id:
                visit(dependency)
        active.remove(identifier)
        finished.add(identifier)
        executable = info.get('CFBundleExecutable', '')
        executable_path = 'Contents/MacOS/' + executable if executable else ''
        if executable_path and not (path/executable_path).is_file():
            raise ValueError(f'Missing executable: {path.name}')
        # The pinned 2.4 patcher predates the Sequoia USB-memory fix and has
        # appeared in a Tahoe panic. Keep its files for a later controlled test.
        enabled = path.name != 'IntelBTPatcher.kext'
        ordered.append({'Arch': 'x86_64', 'BundlePath': path.relative_to(kext_dir).as_posix(),
                        'Comment': '' if enabled else 'Old Bluetooth patcher: excluded after USB panic',
                        'Enabled': enabled, 'ExecutablePath': executable_path,
                        'MaxKernel': '24.99.99' if path.name == 'AppleALC.kext' else '25.99.99',
                        'MinKernel': '24.0.0', 'PlistPath': 'Contents/Info.plist'})

    # These service providers have runtime clients in addition to their link
    # dependencies. Preserve their recommended order before the satellite kexts.
    preferred = ['Lilu.kext', 'VirtualSMC.kext', 'SMCProcessor.kext', 'SMCBatteryManager.kext',
                 'WhateverGreen.kext', 'RestrictEvents.kext', 'AppleALC.kext',
                 'USBToolBox.kext', 'UTBMap.kext', 'VoodooInput.kext', 'VoodooI2CServices.kext',
                 'VoodooGPIO.kext', 'VoodooI2C.kext', 'VoodooI2CHID.kext',
                 'VoodooPS2Controller.kext', 'VoodooPS2Keyboard.kext',
                 'IntelBluetoothFirmware.kext', 'IntelBTPatcher.kext', 'BlueToolFixup.kext', 'itlwm.kext']
    priority = {name: index for index, name in enumerate(preferred)}
    for identifier in sorted(by_id, key=lambda k: (priority.get(by_id[k][0].name, 100), k)):
        visit(identifier)
    return ordered


def make_config(sample, profile, entries, identity):
    cfg = read_plist(sample)
    # Remove disabled examples and sample devices before adding this machine.
    for section, keys in {'ACPI': ['Add', 'Delete', 'Patch'],
                          'Booter': ['MmioWhitelist', 'Patch'],
                          'Kernel': ['Add', 'Block', 'Force', 'Patch'],
                          'Misc': ['BlessOverride', 'Entries', 'Tools'],
                          'UEFI': ['Drivers', 'ReservedMemory', 'Unload']}.items():
        for key in keys:
            cfg[section][key] = []
    cfg['ACPI']['Add'] = [{'Comment': 'Optional power-off; enable only after first boot'
                          if not table['enabled'] else '', 'Enabled': table['enabled'],
                          'Path': table['path']} for table in profile['acpi_add']]
    cfg['ACPI']['Patch'] = [{'Base': '', 'BaseSkip': 0, 'Comment': 'OEM _OSI to XOSI',
                            'Count': 0, 'Enabled': True, 'Find': bytes.fromhex('5f4f5349'),
                            'Limit': 0, 'Mask': b'', 'OemTableId': b'',
                            'Replace': bytes.fromhex('584f5349'), 'ReplaceMask': b'',
                            'Skip': 0, 'TableLength': 0, 'TableSignature': b''}]
    cfg['Booter']['Quirks'].update(EnableWriteUnprotector=False,
                                  RebuildAppleMemoryMap=True, SyncRuntimePermissions=True)
    igpu = profile['initial_igpu_properties']
    cfg['DeviceProperties']['Add'] = {igpu['pci_path']: {
        'AAPL,ig-platform-id': bytes.fromhex(igpu['AAPL,ig-platform-id_hex']),
        'device-id': bytes.fromhex(igpu['device-id_hex'])}}
    cfg['DeviceProperties']['Delete'] = {}
    cfg['Kernel']['Add'] = entries
    # The only native NVMe here is the unsupported PM981a. USB storage uses a
    # different driver. Disable its driver startup, keeping dependency metadata.
    cfg['Kernel']['Block'] = [{'Arch': 'x86_64', 'Comment': 'USB-only install: block internal PM981a',
                              'Enabled': True, 'Identifier': 'com.apple.iokit.IONVMeFamily',
                              'MaxKernel': '25.99.99', 'MinKernel': '24.0.0', 'Strategy': 'Disable'}]
    cfg['Kernel']['Quirks'].update(AppleXcpmCfgLock=True, DisableIoMapper=True,
                                  PanicNoKextDump=True, PowerTimeoutKernelPanic=True,
                                  XhciPortLimit=False)
    cfg['Misc']['Boot'].update(HideAuxiliary=False, Timeout=10, LauncherOption='Disabled')
    cfg['Misc']['Debug'].update(AppleDebug=True, ApplePanic=True, DisableWatchDog=True,
                               Target=67, SysReport=False)
    cfg['Misc']['Security'].update(ScanPolicy=0, SecureBootModel='Disabled',
                                  Vault='Optional', DmgLoading='Signed')
    cfg['NVRAM']['Add'] = {NVRAM_GUID: {
        'boot-args': '-v keepsyms=1 debug=0x100 -wegnoegpu revpatch=sbvmm alcid=11',
        'csr-active-config': bytes(4), 'prev-lang:kbd': b'', 'run-efi-updater': 'No'}}
    cfg['NVRAM']['Delete'] = {NVRAM_GUID: ['boot-args', 'prev-lang:kbd']}
    cfg['NVRAM']['LegacySchema'] = {}
    generic = cfg['PlatformInfo']['Generic']
    generic.update({k: v for k, v in identity.items() if k != 'ROM'})
    generic['ROM'] = bytes.fromhex(identity['ROM'])
    cfg['UEFI']['Drivers'] = [{'Arguments': '', 'Comment': '', 'Enabled': True,
                              'HideVerbose': False, 'LoadEarly': False, 'Path': path}
                             for path in ['OpenRuntime.efi', 'HfsPlus.efi']]
    return cfg


def verify_bundle(bundle, config, profile):
    oc = bundle/'EFI/OC'
    for table in config['ACPI']['Add']:
        raw = (oc/'ACPI'/table['Path']).read_bytes()
        if raw[:4] != b'SSDT' or struct.unpack_from('<I', raw, 4)[0] != len(raw) or sum(raw) % 256:
            raise ValueError(f"Invalid ACPI table: {table['Path']}")
    ports = read_plist(oc/'Kexts/UTBMap.kext/Contents/Info.plist')['IOKitPersonalities']['XHC']['IOProviderMergeProperties']['ports']
    observed = {int.from_bytes(v['port'], 'little'): v['UsbConnector'] for v in ports.values()}
    expected = {p['port']: p['connector'] for p in profile['usb_map']['ports']}
    if observed != expected or len(ports) > 15:
        raise ValueError('USB map differs from verified hardware profile')
    if not config['Kernel']['Block'][0]['Enabled'] or config['Kernel']['Quirks']['XhciPortLimit']:
        raise ValueError('Unsafe storage/USB configuration for this profile')
    if config['ACPI']['Add'][-1]['Enabled']:
        raise ValueError('dGPU power-off must remain optional until tested')
    for entry in config['UEFI']['Drivers']:
        if not (oc/'Drivers'/entry['Path']).is_file():
            raise ValueError('Missing UEFI driver')
    for path in [bundle/'EFI/BOOT/BOOTx64.efi', oc/'OpenCore.efi']:
        if path.read_bytes()[:2] != b'MZ':
            raise ValueError('Invalid UEFI executable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'build/efi')
    parser.add_argument('--identity', type=Path, help='Reuse identity saved from a previous build')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bundle = out/'bundle'
    if bundle.exists():
        raise SystemExit('Output bundle exists; use a new output directory')
    cache, source = out/'downloads', out/'upstream'
    cache.mkdir(exist_ok=True)
    source.mkdir(exist_ok=True)
    lock = json.loads((ROOT/'profiles/assets.lock.json').read_text())
    profile = json.loads((ROOT/'profiles/s540-81sw.json').read_text())
    downloads, extracted, manifests = {}, {}, []
    for asset in lock['assets']:
        archive, digest = download(asset, cache)
        downloads[asset['id']] = archive
        if archive.suffix == '.zip':
            dest = source/asset['id']
            extract_zip(archive, dest)
            extracted[asset['id']] = dest
        manifests.append({**asset, 'sha256': digest})
    oc_source = extracted['OpenCore']
    boot = bundle/'EFI/BOOT'
    oc = bundle/'EFI/OC'
    for directory in [boot, oc/'Drivers', oc/'Kexts', oc/'ACPI']:
        directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(unique_file(oc_source, 'X64/EFI/BOOT/BOOTx64.efi'), boot/'BOOTx64.efi')
    shutil.copy2(unique_file(oc_source, 'X64/EFI/OC/OpenCore.efi'), oc/'OpenCore.efi')
    shutil.copy2(unique_file(oc_source, 'X64/EFI/OC/Drivers/OpenRuntime.efi'), oc/'Drivers/OpenRuntime.efi')
    shutil.copy2(downloads['HfsPlus'], oc/'Drivers/HfsPlus.efi')
    for source_id, names in {
        'Lilu': ['Lilu.kext'], 'VirtualSMC': ['VirtualSMC.kext', 'SMCProcessor.kext', 'SMCBatteryManager.kext'],
        'WhateverGreen': ['WhateverGreen.kext'], 'RestrictEvents': ['RestrictEvents.kext'],
        'VoodooPS2': ['VoodooPS2Controller.kext'], 'VoodooI2C': ['VoodooI2C.kext', 'VoodooI2CHID.kext'],
        'USBToolBox': ['USBToolBox.kext'], 'itlwm': ['itlwm.kext'],
        'IntelBluetooth': ['IntelBluetoothFirmware.kext', 'IntelBTPatcher.kext'],
        'BrcmPatchRAM': ['BlueToolFixup.kext'], 'AppleALC': ['AppleALC.kext']}.items():
        for name in names:
            copy_kext(extracted[source_id], name, oc/'Kexts')
    # The ELAN touchpad is I2C. Keep only the PS/2 keyboard plugin and a single
    # VoodooInput implementation supplied with VoodooI2C.
    ps2_plugins = oc/'Kexts/VoodooPS2Controller.kext/Contents/PlugIns'
    for name in ['VoodooPS2Mouse.kext', 'VoodooPS2Trackpad.kext', 'VoodooInput.kext']:
        path = ps2_plugins/name
        if path.exists():
            shutil.rmtree(path)
    shutil.copytree(ROOT/'usb/UTBMap.kext', oc/'Kexts/UTBMap.kext')
    wifi_path = oc/'Kexts/itlwm.kext/Contents/Info.plist'
    wifi = read_plist(wifi_path)
    wifi['IOKitPersonalities']['itlwm']['WiFiConfig'] = {}
    write_plist(wifi_path, wifi)
    for table in profile['acpi_add']:
        shutil.copy2(ROOT/'acpi/compiled'/table['path'], oc/'ACPI'/table['path'])
    identity = identity_for(unique_file(oc_source, 'macserial.linux'), args.identity)
    config = make_config(unique_file(oc_source, 'Docs/Sample.plist'), profile,
                         kernel_entries(oc/'Kexts'), identity)
    write_plist(oc/'config.plist', config)
    verify_bundle(bundle, config, profile)
    validator = unique_file(oc_source, 'ocvalidate.linux')
    validator.chmod(0o755)
    validation = subprocess.run([str(validator), str(oc/'config.plist')], text=True, capture_output=True)
    log = validation.stdout + validation.stderr
    (out/'ocvalidate.txt').write_text(log)
    print(log)
    if validation.returncode:
        raise SystemExit('ocvalidate rejected the configuration')
    # Save generated identity outside source control, so later rebuilds can keep it.
    (bundle/'IDENTITA-SMBIOS.json').write_text(json.dumps(identity, indent=2)+'\n')
    utilities = bundle/'tools/macrecovery'
    utilities.mkdir(parents=True)
    recovery_source = unique_file(oc_source, 'macrecovery.py').parent
    for path in recovery_source.iterdir():
        if path.is_file():
            shutil.copy2(path, utilities/path.name)
    shutil.copy2(ROOT/'tools/configure_wifi.py', bundle/'tools/configure_wifi.py')
    shutil.copy2(ROOT/'tools/SCARICA-RECOVERY.cmd', bundle/'SCARICA-RECOVERY.cmd')
    shutil.copy2(ROOT/'tools/CONFIGURA-WIFI.cmd', bundle/'CONFIGURA-WIFI.cmd')
    shutil.copy2(ROOT/'docs/PRIMO-AVVIO.md', bundle/'LEGGIMI.md')
    shutil.copy2(out/'ocvalidate.txt', bundle/'ocvalidate.txt')
    manifest = {'schema': 1, 'status': 'validated configuration; hardware boot not tested',
                'commit': os.environ.get('GITHUB_SHA'), 'opencore': '1.0.8 DEBUG',
                'smbios': MODEL, 'target': 'Samsung 960 EVO over USB-C',
                'assets': manifests, 'files': {}}
    for path in sorted((bundle/'EFI').rglob('*')):
        if path.is_file():
            manifest['files'][path.relative_to(bundle).as_posix()] = sha256(path.read_bytes())
    (bundle/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    credits = ['# Componenti e sorgenti', '', 'Build iniziale da release ufficiali:', '']
    for asset in manifests:
        credits.append(f"- {asset['repository']} {asset['version']}: https://github.com/{asset['repository']}")
    (bundle/'CREDITI.md').write_text('\n'.join(credits)+'\n')
    archive_path = out/'S540-81SW-Tahoe-prima-prova.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(bundle))
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'BUNDLE {archive_path.name} {sha256(archive_path.read_bytes())}')
    print(f"Verified {len(config['Kernel']['Add'])} kext entries and {len(config['ACPI']['Add'])} ACPI tables")


if __name__ == '__main__':
    main()

