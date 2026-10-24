import copy
import importlib.util
import io
from pathlib import Path
import plistlib
import stat
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_builder', ROOT / 'builders/build_non_nvidia_release.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReleaseGuards(unittest.TestCase):
    def archive(self, names, symlink=False):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for name in names:
                item = zipfile.ZipInfo(name)
                if symlink:
                    item.create_system = 3
                    item.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(item, b'payload')
        return stream.getvalue()

    def payload(self):
        c = plistlib.loads((ROOT / 'config/efi/releases/v0.3.0/config.plist').read_bytes())
        files = {}
        for item in c['Kernel']['Add']:
            prefix = 'EFI/OC/Kexts/' + item['BundlePath'] + '/'
            for key in ('ExecutablePath', 'PlistPath'):
                if item[key]:
                    files[prefix + item[key]] = plistlib.dumps({}) if key == 'PlistPath' else b'fixture'
        for item in c['ACPI']['Add']:
            files['EFI/OC/ACPI/' + item['Path']] = b'fixture'
        for item in c['UEFI']['Drivers']:
            if item['Enabled']:
                files['EFI/OC/Drivers/' + item['Path']] = b'fixture'
        files['EFI/OC/config.plist'] = plistlib.dumps(c)
        return c, files

    def test_unsafe_zip_paths(self):
        for name in ('../config', '/EFI/config', 'EFI/../../x', 'EFI\\config'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.unpack(self.archive([name]))

    def test_zip_duplicates_and_links(self):
        with self.assertWarns(UserWarning):
            duplicate = self.archive(['same', 'same'])
        with self.assertRaises(ValueError):
            builder.unpack(duplicate)
        with self.assertRaises(ValueError):
            builder.unpack(self.archive(['EFI/link'], True))

    def test_input_tampering(self):
        with self.assertRaises(ValueError):
            builder.checked(b'tampered', builder.sha(b'reviewed'), 'fixture')

    def test_public_boot_policy(self):
        c, files = self.payload()
        builder.validate_payload(files)
        for field in ('gpu', 'windows'):
            changed = copy.deepcopy(c)
            if field == 'gpu':
                changed['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args'] = ''
            else:
                changed['Misc']['Security']['ScanPolicy'] = 0
            files['EFI/OC/config.plist'] = plistlib.dumps(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                builder.validate_payload(files)

    def test_identity_and_saved_wifi_refusal(self):
        c, files = self.payload()
        c['PlatformInfo']['Generic']['SystemSerialNumber'] = 'PRIVATE-TEST-SERIAL'
        files['EFI/OC/config.plist'] = plistlib.dumps(c)
        with self.assertRaises(ValueError):
            builder.validate_payload(files)
        c, files = self.payload()
        files['EFI/OC/Kexts/AirportItlwm.kext/Contents/Info.plist'] = plistlib.dumps({'WiFiConfig': {'private': 'fixture'}})
        with self.assertRaises(ValueError):
            builder.validate_payload(files)

    def test_extra_bootloaders_and_metadata_refusal(self):
        for name in ('EFI/Microsoft/Boot/bootmgfw.efi', 'EFI/BOOT/BOOTx64.efi', 'EFI/OC/._config.plist'):
            _, files = self.payload()
            files[name] = b'fixture'
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.validate_payload(files)

    def test_missing_driver_refusal(self):
        _, files = self.payload()
        del files['EFI/OC/Kexts/BigSurSDXC.kext/Contents/MacOS/BigSurSDXC']
        with self.assertRaises(ValueError):
            builder.validate_payload(files)


if __name__ == '__main__':
    unittest.main()
