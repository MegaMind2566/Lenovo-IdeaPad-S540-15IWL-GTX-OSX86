#!/usr/bin/env python3
"""Offline release-kit guards for the reviewed S540 NVIDIA profile."""

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / 'builders/build_nullmoth_s540_release.py'
LOCK_PATH = ROOT / 'packages/nullmoth-s540/release/sources.lock.json'
PROFILE_PATH = ROOT / 'packages/nullmoth-s540/release/profile/config.plist'
VERSION = 'v0.4.0-nvidia-experimental.1'
PREFIX = f'S540-NVIDIA-release-kit-{VERSION}/'
HEX256 = re.compile(r'^[0-9a-f]{64}$')


def import_builder():
    if not BUILDER_PATH.is_file():
        raise AssertionError(f'Release builder missing: {BUILDER_PATH.relative_to(ROOT)}')
    spec = importlib.util.spec_from_file_location('nullmoth_release_builder', BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError('Cannot load the NullMoth release builder')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NullMothReleaseGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = import_builder()

    def zip_fixture(self, entries):
        """Return a ZIP; entries are (name, data, unix mode) tuples."""
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, data, mode in entries:
                item = zipfile.ZipInfo(name)
                item.create_system = 3
                item.external_attr = mode << 16
                archive.writestr(item, data)
        return stream.getvalue()

    def extract_fixture(self, data, destination):
        archive = destination.parent / 'fixture.zip'
        archive.write_bytes(data)
        return self.builder.safe_extract_zip(archive, destination)

    def tar_fixture(self, entries):
        """Return a TAR; entries are (name, data, type, linkname) tuples."""
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            for name, data, kind, linkname in entries:
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = linkname
                item.mode = 0o755 if name.endswith('.sh') else 0o644
                if kind == tarfile.REGTYPE:
                    item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))
                else:
                    archive.addfile(item)
        return stream.getvalue()

    def extract_tar_fixture(self, data, destination):
        archive = destination.parent / 'fixture.tar'
        archive.write_bytes(data)
        return self.builder.safe_extract_tar(archive, destination)

    def test_source_lock_is_exact_and_fully_pinned(self):
        lock = self.builder.load_source_lock(LOCK_PATH)
        self.assertEqual(lock['schema'], 1)
        self.assertEqual(lock['release']['tag'], VERSION)
        self.assertEqual(lock['release']['package_name'], PREFIX.rstrip('/') + '.zip')
        self.assertEqual(lock['release']['package_prefix'], PREFIX.rstrip('/'))
        self.assertEqual(
            set(lock), {'schema', 'release', 'sources', 'profile', 'device'}
        )
        expected = {
            'stable_efi': (
                'https://github.com/MegaMind2566/Lenovo-IdeaPad-S540-15IWL-GTX-OSX86/'
                'releases/download/v0.3.0/S540-Tahoe-EFI-v0.3.0.zip',
                47092619,
                'f5a9ad08cfa72e14569bc1040728c7480f7966a58a1adb9bf1e4ff84e303e46d',
            ),
            'opencore': (
                'https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.8/'
                'OpenCore-1.0.8-RELEASE.zip',
                10544084,
                '2011e8b7216ecb2645d97ea710df965947edd406846e92050b9bc4190be6d27b',
            ),
            'amfipass': (
                'https://github.com/bluppus20/AMFIPass/releases/download/1.4.1/'
                'AMFIPass-v1.4.1-RELEASE.zip',
                191154,
                '07b266145906db41f4b13a7938fbb173ea28888cc1fa65f84417f8820adc961e',
            ),
            'nullmoth_1401': (
                'https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.7.2/'
                '1401-Mac-2.7.2.zip',
                2635537,
                '008e8bdb88920a17211f07c45b0df2601bdde2d9a41af3ebe393944b74947dfd',
            ),
            'nullmoth_driver': (
                'https://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.7.2/'
                'nullmoth-nvidia-2.7.2.tar.gz',
                264616298,
                '928557fece27637b1184f5655833566e7d516b22708cc341b28d555055d8e50e',
            ),
        }
        self.assertEqual(set(lock['sources']), set(expected))
        for name, (url, size, digest) in expected.items():
            with self.subTest(source=name):
                source = lock['sources'][name]
                self.assertEqual(source['url'], url)
                self.assertEqual(source['size'], size)
                self.assertEqual(source['sha256'], digest)
                self.assertTrue(source['filename'])
                self.assertNotIn('/latest/', source['url'])
                self.assertIsNotNone(HEX256.fullmatch(source['sha256']))
        signatures = {
            'nullmoth_1401': 'aa1cc71060113fddb3bba9985f5c2ed98e1768c2059d7ae0657ceb1f32142156',
            'nullmoth_driver': '378e8d966777538ddb300bf65dea9fec23cfcc704c3843913ca9779a6630ac0f',
        }
        for name, digest in signatures.items():
            source = lock['sources'][name]
            self.assertEqual(source['signature_sha256'], digest)
            self.assertTrue(source['signature_url'].startswith(source['url']))
            self.assertTrue(source['signature_filename'].endswith('.sig'))
            self.assertGreater(source['signature_size'], 0)

        profile = lock['profile']
        self.assertEqual(lock['release']['tested_macos_version'], '26.7.1')
        self.assertEqual(lock['release']['tested_macos_build'], '25G241')
        self.assertEqual(lock['device']['nvidia_compatible'], 'pci10de,1f91')
        self.assertEqual(lock['device']['nvidia_subsystem_compatible'], 'pci17aa,3806')
        self.assertEqual(profile['system_product_name'], 'MacBookPro16,2')
        self.assertEqual(
            self.builder.sha256_file(LOCK_PATH.parent / profile['config_path']),
            profile['config_sha256'],
        )
        sensor_root = LOCK_PATH.parent / profile['sensors_path']
        sensor_files = {
            'info_sha256': sensor_root / 'Contents/Info.plist',
            'executable_sha256': sensor_root / 'Contents/MacOS/S540Sensors',
            'code_resources_sha256': sensor_root / 'Contents/_CodeSignature/CodeResources',
        }
        for key, path in sensor_files.items():
            with self.subTest(sensor_file=key):
                self.assertTrue(path.is_file())
                self.assertEqual(self.builder.sha256_file(path), profile['sensors'][key])
        self.assertEqual(
            profile['nullmoth_patch']['nvrm_installed_executable_sha256'],
            'a434d9c4df143044759b33abba8d012ef9fb499146cd7b63eadaacc5969c8db8',
        )
        self.assertEqual(
            profile['nullmoth_patch']['nvaccel_prepared_executable_sha256'],
            '60c011d938eb58846ffa2081ed730b01f252a2dee292f8ef53f69fc333341940',
        )
        self.assertEqual(
            profile['nullmoth_patch']['nvaccel_installed_executable_sha256'],
            '2293360ee50d917e1056f070bb7a6979adffb4dab3105d6a9b33c92b22219685',
        )
        self.assertEqual(
            profile['nullmoth_patch']['nvaccel15_installed_executable_sha256'],
            '60c011d938eb58846ffa2081ed730b01f252a2dee292f8ef53f69fc333341940',
        )
        self.assertEqual(
            profile['nullmoth_patch']['nvaccel26_installed_executable_sha256'],
            '2293360ee50d917e1056f070bb7a6979adffb4dab3105d6a9b33c92b22219685',
        )

    def test_private_work_directories_are_excluded_from_git(self):
        rules = {
            line.strip()
            for line in (ROOT / '.gitignore').read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')
        }
        self.assertTrue({
            '.DS_Store', '_backups/', '_candidates/', '_captures/',
            '_diagnostics/', '_external/',
        } <= rules)

    def test_malformed_source_lock_is_refused(self):
        original = json.loads(LOCK_PATH.read_text())
        mutations = []
        missing = copy.deepcopy(original)
        del missing['sources']['opencore']
        mutations.append(missing)
        short_hash = copy.deepcopy(original)
        short_hash['sources']['stable_efi']['sha256'] = '0' * 63
        mutations.append(short_hash)
        insecure = copy.deepcopy(original)
        insecure['sources']['amfipass']['url'] = insecure['sources']['amfipass']['url'].replace(
            'https://', 'http://', 1
        )
        mutations.append(insecure)
        missing_installed_hash = copy.deepcopy(original)
        del missing_installed_hash['profile']['nullmoth_patch'][
            'nvrm_installed_executable_sha256'
        ]
        mutations.append(missing_installed_hash)
        short_installed_hash = copy.deepcopy(original)
        short_installed_hash['profile']['nullmoth_patch'][
            'nvaccel_installed_executable_sha256'
        ] = '0' * 63
        mutations.append(short_installed_hash)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'sources.lock.json'
            for index, changed in enumerate(mutations):
                path.write_text(json.dumps(changed))
                with self.subTest(mutation=index), self.assertRaises(ValueError):
                    self.builder.load_source_lock(path)

    def test_public_config_has_only_placeholders_and_reviewed_policy(self):
        lock = self.builder.load_source_lock(LOCK_PATH)
        config = self.builder.validate_public_config(PROFILE_PATH, lock)
        if config is None:
            config = plistlib.loads(PROFILE_PATH.read_bytes())
        generic = config['PlatformInfo']['Generic']
        self.assertEqual(generic['SystemProductName'], 'MacBookPro16,2')
        self.assertEqual(generic['SystemSerialNumber'], '')
        self.assertEqual(generic['MLB'], '')
        self.assertEqual(generic['SystemUUID'], '00000000-0000-0000-0000-000000000000')
        self.assertEqual(generic['ROM'], bytes(6))
        self.assertTrue(all(item['Enabled'] for item in config['ACPI']['Add']))
        self.assertTrue(all(item['Enabled'] for item in config['Kernel']['Add']))
        self.assertEqual(config['Kernel']['Block'], [])
        self.assertEqual(config['Misc']['Security']['SecureBootModel'], 'Disabled')
        self.assertEqual(config['Misc']['Security']['ScanPolicy'], 769)
        args = config['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']['boot-args']
        self.assertEqual(args, lock['profile']['boot_args'])

    def test_private_identity_mutations_are_refused(self):
        lock = self.builder.load_source_lock(LOCK_PATH)
        original = plistlib.loads(PROFILE_PATH.read_bytes())
        cases = {
            'SystemSerialNumber': 'PRIVATE-SERIAL',
            'MLB': 'PRIVATE-MLB',
            'SystemUUID': '11111111-2222-3333-4444-555555555555',
            'ROM': bytes.fromhex('001122334455'),
            'SystemProductName': 'MacBookPro15,2',
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'config.plist'
            for key, value in cases.items():
                changed = copy.deepcopy(original)
                changed['PlatformInfo']['Generic'][key] = value
                path.write_bytes(plistlib.dumps(changed, sort_keys=False))
                with self.subTest(field=key), self.assertRaises(ValueError):
                    self.builder.validate_public_config(path, lock)

    def test_hash_helpers_are_byte_exact(self):
        data = b'S540 NullMoth release fixture\x00\xff'
        expected = hashlib.sha256(data).hexdigest()
        self.assertEqual(self.builder.sha256_data(data), expected)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture.bin'
            path.write_bytes(data)
            self.assertEqual(self.builder.sha256_file(path), expected)

    def test_safe_zip_extract_accepts_regular_files(self):
        data = self.zip_fixture([
            ('EFI/OC/config.plist', b'reviewed', stat.S_IFREG | 0o644),
            ('EFI/OC/OpenCore.efi', b'efi', stat.S_IFREG | 0o755),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extracted = self.extract_fixture(data, root / 'out')
            self.assertEqual((root / 'out/EFI/OC/config.plist').read_bytes(), b'reviewed')
            self.assertEqual(len(extracted), 2)

    def test_safe_zip_extract_refuses_traversal_and_backslashes(self):
        unsafe = ('../escape', '/absolute', 'EFI/../../escape', 'EFI\\OC\\config.plist')
        for name in unsafe:
            data = self.zip_fixture([(name, b'bad', stat.S_IFREG | 0o644)])
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    self.extract_fixture(data, root / 'out')
                self.assertFalse((root / 'escape').exists())

    def test_safe_zip_extract_refuses_symlinks_and_duplicates(self):
        link = self.zip_fixture([
            ('EFI/link', b'../../escape', stat.S_IFLNK | 0o777),
        ])
        duplicate = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(duplicate, 'w') as archive:
                archive.writestr('EFI/OC/config.plist', b'one')
                archive.writestr('EFI/OC/config.plist', b'two')
        for label, data in (('symlink', link), ('duplicate', duplicate.getvalue())):
            with tempfile.TemporaryDirectory() as temporary:
                with self.subTest(kind=label), self.assertRaises(ValueError):
                    self.extract_fixture(data, Path(temporary) / 'out')

    def test_safe_tar_extract_accepts_regular_files(self):
        data = self.tar_fixture([
            ('pkgroot/install.sh', b'#!/bin/sh\n', tarfile.REGTYPE, ''),
            ('pkgroot/Library/fixture', b'reviewed', tarfile.REGTYPE, ''),
            (
                'pkgroot/lib/libvulkan.1.4.362.dylib', b'vulkan',
                tarfile.REGTYPE, '',
            ),
            (
                'pkgroot/lib/libvulkan.1.dylib', b'', tarfile.SYMTYPE,
                'libvulkan.1.4.362.dylib',
            ),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extracted = self.extract_tar_fixture(data, root / 'out')
            self.assertEqual((root / 'out/pkgroot/Library/fixture').read_bytes(), b'reviewed')
            alias = root / 'out/pkgroot/lib/libvulkan.1.dylib'
            self.assertTrue(alias.is_symlink())
            self.assertEqual(alias.read_bytes(), b'vulkan')
            self.assertEqual(len(extracted), 4)

    def test_safe_tar_extract_refuses_traversal_links_and_duplicates(self):
        cases = {
            'parent traversal': [('../escape', b'bad', tarfile.REGTYPE, '')],
            'absolute path': [('/escape', b'bad', tarfile.REGTYPE, '')],
            'backslashes': [('pkgroot\\escape', b'bad', tarfile.REGTYPE, '')],
            'symbolic link': [('pkgroot/link', b'', tarfile.SYMTYPE, '../../escape')],
            'hard link': [('pkgroot/link', b'', tarfile.LNKTYPE, 'pkgroot/install.sh')],
            'symlink parent': [
                ('pkgroot/real', b'', tarfile.DIRTYPE, ''),
                ('pkgroot/redirect', b'', tarfile.SYMTYPE, 'real'),
                ('pkgroot/redirect/payload', b'bad', tarfile.REGTYPE, ''),
            ],
            'duplicate': [
                ('pkgroot/install.sh', b'one', tarfile.REGTYPE, ''),
                ('pkgroot/install.sh', b'two', tarfile.REGTYPE, ''),
            ],
        }
        for label, entries in cases.items():
            data = self.tar_fixture(entries)
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.subTest(kind=label), self.assertRaises(ValueError):
                    self.extract_tar_fixture(data, root / 'out')
                self.assertFalse((root / 'escape').exists())

    def test_target_host_matrix_is_exact(self):
        module = self.builder._MODULE
        lock = self.builder.load_source_lock(LOCK_PATH)

        def run_with(*, architecture='x86_64', version='26.7.1', build='25G241',
                     registry=None):
            if registry is None:
                registry = '    "compatible" = <"pci17aa,3806" "pci10de,1f91">\n'

            def fake_run(arguments, **_kwargs):
                if arguments == ['/usr/bin/uname', '-m']:
                    output = architecture
                elif arguments == ['/usr/bin/sw_vers', '-productVersion']:
                    output = version
                elif arguments == ['/usr/bin/sw_vers', '-buildVersion']:
                    output = build
                elif arguments == ['/usr/sbin/ioreg', '-l', '-p', 'IOService', '-w0']:
                    output = registry
                else:
                    raise AssertionError(f'unexpected command: {arguments}')
                return subprocess.CompletedProcess(arguments, 0, stdout=output)

            with mock.patch.object(module.sys, 'platform', 'darwin'), \
                    mock.patch.object(module.subprocess, 'run', side_effect=fake_run):
                return module.validate_target_host(lock)

        qualified = run_with()
        self.assertEqual(qualified['architecture'], 'x86_64')
        self.assertEqual(qualified['build_version'], '25G241')
        negative = (
            {'architecture': 'arm64'},
            {'version': '26.7.2'},
            {'build': '25G332'},
            {'registry': '"compatible" = <"pci10de,1f91">'},
            {
                'registry': (
                    '"compatible" = <"pci17aa,3806">\n'
                    '"compatible" = <"pci10de,1f91">'
                ),
            },
        )
        for values in negative:
            with self.subTest(values=values), self.assertRaises(RuntimeError):
                run_with(**values)
        with mock.patch.object(module.sys, 'platform', 'linux'):
            with self.assertRaises(RuntimeError):
                module.validate_target_host(lock)

    def test_install_payload_is_immutable_and_normalized(self):
        module = self.builder._MODULE
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'package'
            root.mkdir()
            install = root / 'install.sh'
            install.write_text('#!/bin/bash\nexit 0\n')
            install.chmod(0o755)
            (root / 'payload').write_bytes(b'reviewed')
            os.symlink('payload', root / 'payload-link')
            payload, digest = module._build_install_payload(root)
            try:
                install.write_text('#!/bin/bash\necho tampered\n')
                (root / 'payload').write_bytes(b'tampered')
                (root / 'evil').write_bytes(b'evil')
                payload.seek(0)
                frozen = payload.read()
                self.assertEqual(hashlib.sha256(frozen).hexdigest(), digest)
                payload.seek(0)
                with tarfile.open(fileobj=payload, mode='r:') as archive:
                    members = {item.name: item for item in archive.getmembers()}
                    self.assertEqual(
                        archive.extractfile('install.sh').read(),
                        b'#!/bin/bash\nexit 0\n',
                    )
                    self.assertEqual(archive.extractfile('payload').read(), b'reviewed')
                    self.assertNotIn('evil', members)
                    self.assertEqual(members['payload-link'].linkname, 'payload')
                    self.assertTrue(all(item.uid == 0 and item.gid == 0 for item in members.values()))
                    self.assertTrue(all(item.mtime == 0 for item in members.values()))
            finally:
                payload.close()

    def test_install_payload_refuses_unsafe_nodes(self):
        module = self.builder._MODULE
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            os.symlink('/etc/passwd', root / 'escape')
            with self.assertRaises(ValueError):
                module._build_install_payload(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'original'
            original.write_bytes(b'x')
            os.link(original, root / 'hardlink')
            with self.assertRaises(ValueError):
                module._build_install_payload(root)
        if hasattr(os, 'mkfifo'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                os.mkfifo(root / 'fifo')
                with self.assertRaises(ValueError):
                    module._build_install_payload(root)

    def test_privileged_install_uses_only_anonymous_payload(self):
        module = self.builder._MODULE
        self.assertEqual(
            subprocess.run(
                ['/bin/bash', '-n', '-c', module.ROOT_INSTALL_SCRIPT],
                check=False,
            ).returncode,
            0,
        )
        with tempfile.TemporaryFile() as payload:
            payload.write(b'fixture')
            digest = hashlib.sha256(b'fixture').hexdigest()
            with mock.patch.object(module.subprocess, 'run') as run:
                module._run_privileged_install(payload, digest)
            arguments = run.call_args.args[0]
            self.assertEqual(arguments[:3], ['/usr/bin/sudo', '/bin/bash', '-c'])
            self.assertEqual(arguments[-1], digest)
            self.assertNotIn('./install.sh', arguments)
            self.assertIs(run.call_args.kwargs['stdin'], payload)
            self.assertNotIn('cwd', run.call_args.kwargs)

    def test_verify_installation_cannot_pass_unqualified_host(self):
        module = self.builder._MODULE
        failure = RuntimeError('unqualified test host')
        process = subprocess.CompletedProcess([], 1, stdout='')
        with mock.patch.object(module, 'validate_target_host', side_effect=failure), \
                mock.patch.object(module.subprocess, 'run', return_value=process):
            result = module.verify_installation(LOCK_PATH.parent)
        self.assertFalse(result['passed'])
        host = next(item for item in result['checks'] if item['name'] == 'Qualified target host')
        self.assertFalse(host['passed'])
        self.assertIn('unqualified test host', host['detail'])

    def test_release_kit_has_only_the_reviewed_structure_and_valid_manifest(self):
        expected = {
            'README.md',
            'sources.lock.json',
            'profile/config.plist',
            'profile/efi-manifest.json',
            'profile/S540Sensors.kext/Contents/Info.plist',
            'profile/S540Sensors.kext/Contents/MacOS/S540Sensors',
            'profile/S540Sensors.kext/Contents/_CodeSignature/CodeResources',
            'bin/s540_release.py',
            'bin/nullmoth_release_sig.py',
            'ASSEMBLA-EFI-NVIDIA.command',
            'INSTALLA-NULLMOTH-S540.command',
            'VERIFICA-INSTALLAZIONE.command',
            'LICENSES/S540Sensors-MIT.txt',
            'LICENSES/S540Sensors-THIRD-PARTY-NOTICES.txt',
            'LICENSES/MacKernelSDK-APSL-2.0.txt',
            'LICENSES/Lilu-BSD-3-Clause.txt',
            'LICENSES/VirtualSMC-BSD-3-Clause.txt',
            'LICENSES/NullMoth-PolyForm-Noncommercial-1.0.0.txt',
            'MANIFEST.json',
        }
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = self.builder.build_release(Path(temporary))
            self.assertTrue(archive_path.is_file())
            sidecar = archive_path.with_suffix(archive_path.suffix + '.sha256')
            self.assertEqual(
                sidecar.read_text(),
                f'{self.builder.sha256_file(archive_path)}  {archive_path.name}\n',
            )
            with zipfile.ZipFile(archive_path) as archive:
                members = {item.filename for item in archive.infolist() if not item.is_dir()}
                self.assertEqual(members, {PREFIX + name for name in expected})
                payload = {
                    name.removeprefix(PREFIX): archive.read(name)
                    for name in members
                }
            manifest = json.loads(payload['MANIFEST.json'])
            self.assertEqual(manifest['schema'], 1)
            self.assertEqual(manifest['version'], VERSION)
            self.assertEqual(set(manifest['files']), expected - {'MANIFEST.json'})
            self.assertEqual(
                manifest['files'],
                {
                    name: hashlib.sha256(data).hexdigest()
                    for name, data in sorted(payload.items())
                    if name != 'MANIFEST.json'
                },
            )
            public = plistlib.loads(payload['profile/config.plist'])
            self.assertEqual(public['PlatformInfo']['Generic']['SystemSerialNumber'], '')
            self.assertNotIn(b'PRIVATE-', archive_path.read_bytes())
            sensor = payload['profile/S540Sensors.kext/Contents/MacOS/S540Sensors']
            self.assertIn(
                b'Copyright (c) 2000 Apple Computer, Inc. All rights reserved.',
                sensor,
            )
            self.assertIn(b'Source Code is available under the Apple Public Source', sensor)
            notice = payload['LICENSES/S540Sensors-THIRD-PARTY-NOTICES.txt']
            self.assertIn(b'Copyright (c) 2000 Apple Computer, Inc.', notice)


if __name__ == '__main__':
    unittest.main()
