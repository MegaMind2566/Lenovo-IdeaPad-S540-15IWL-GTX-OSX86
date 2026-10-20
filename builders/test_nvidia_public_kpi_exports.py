#!/usr/bin/env python3
"""Source-backed export/dependency preflight regression controls."""
import shutil
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import nvidia_public_kpi_exports as exports


class PublicKpiExportControls(unittest.TestCase):
    def test_header_declared_private_call_is_rejected(self):
        with self.assertRaises(exports.ExportAuditError) as caught:
            exports.audit_imports(['thread_call_cancel_wait'], exports.IDLE_LIBRARIES)
        self.assertEqual(caught.exception.report['rejected'],
                         [{'symbol': 'thread_call_cancel_wait', 'reason': 'private-only-export'}])

    def test_public_cancel_and_free_have_declared_mach_owner(self):
        report = exports.audit_imports(['thread_call_cancel', 'thread_call_free'], ['com.apple.kpi.mach'])
        self.assertEqual(report['status'], 'passed')
        self.assertFalse(report['exact_target_export_proof'])
        self.assertEqual(report['matched_count'], 2)

    def test_undeclared_dependency_and_unknown_rejected_together(self):
        report = exports.inspect_imports(['thread_call_cancel', 's540InventedKernelExport'], [])
        self.assertEqual({r['symbol']: r['reason'] for r in report['rejected']},
                         {'thread_call_cancel': 'public-export-owner-not-declared',
                          's540InventedKernelExport': 'unknown-export'})

    def test_alias_left_side_and_exact_macho_prefix(self):
        self.assertEqual(exports.parse_exports('_task_reference: _task_reference_external\n'
                                               '__ZN8OSObject7releaseEv # comment\n'),
                         {'task_reference', '_ZN8OSObject7releaseEv'})
        self.assertNotIn('task_reference_external', exports.parse_exports(
            '_task_reference:_task_reference_external\n'))

    def test_family_export_requires_family_dependency(self):
        inventory = exports.load_inventory()
        symbol = next(name for name, owners in inventory['public'].items()
                      if set(owners) == {'com.apple.iokit.IOPCIFamily'})
        with self.assertRaises(exports.ExportAuditError):
            exports.audit_imports([symbol], ['com.apple.kpi.iokit'])
        self.assertEqual(exports.audit_imports([symbol], ['com.apple.iokit.IOPCIFamily'])['matched_count'], 1)

    def test_bad_export_syntax_is_not_a_glob_or_alias_admission(self):
        for text in ('_anything*', '_public:_private:bad', 'plain_symbol', '_one _two'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                exports.parse_exports(text)

    def test_private_source_prefix_only_classifies_rejection(self):
        report = exports.inspect_imports(['_ZN16IOPlatformExpert20InventedPrivateThingEv'],
                                         [*filter(None, exports.GROUPS.values())])
        self.assertEqual(report['rejected'][0]['reason'], 'private-only-export')
        self.assertEqual(report['matched_count'], 0)

    def test_source_byte_change_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'exports'
            shutil.copytree(exports.DATA, folder)
            path = folder / 'Mach.exports'
            path.write_bytes(path.read_bytes() + b'_invented_public_export\n')
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                exports.audit_imports(['invented_public_export'], ['com.apple.kpi.mach'], inventory_dir=folder)

    def test_source_inventory_cannot_add_arm_or_private_authorizer(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'exports'
            shutil.copytree(exports.DATA, folder)
            (folder / 'Mach.arm64.exports').write_text('_arm_only\n')
            with self.assertRaisesRegex(ValueError, 'Unexpected or missing'):
                exports.load_inventory(folder)

    def test_coordinated_map_and_manifest_change_cannot_authorize_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'exports'
            shutil.copytree(exports.DATA, folder)
            path = folder / 'Mach.exports'
            forged = path.read_bytes() + b'_invented_public_export\n'
            path.write_bytes(forged)
            manifest_path = folder / 'manifest.json'
            manifest = json.loads(manifest_path.read_bytes())
            row = next(row for row in manifest['sources'] if row['file'] == path.name)
            row.update(bytes=len(forged), sha256=hashlib.sha256(forged).hexdigest())
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
            with self.assertRaisesRegex(ValueError, 'Reviewed export manifest bytes changed'):
                exports.audit_imports(['invented_public_export'], exports.IDLE_LIBRARIES,
                                      inventory_dir=folder)

    def test_idle_dependency_mapping_is_exact(self):
        self.assertEqual(exports.IDLE_LIBRARIES, {
            'com.apple.kpi.bsd': '8.0.0', 'com.apple.kpi.iokit': '8.0.0',
            'com.apple.kpi.libkern': '8.0.0', 'com.apple.kpi.mach': '8.0.0',
            'com.apple.kpi.unsupported': '8.0.0', 'com.apple.iokit.IOPCIFamily': '2.9.0'})


if __name__ == '__main__':
    unittest.main()
