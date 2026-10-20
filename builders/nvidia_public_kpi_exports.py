#!/usr/bin/env python3
"""Fail-closed import preflight against pinned Apple public export source maps.

SDK references establish declaration/ABI provenance.  They do not establish that
a symbol is exported.  This independent source-snapshot check establishes the
latter only for the recorded published source profile, never an installed target.
Names accepted by the Python API use the linker's existing spelling: exactly one
Mach-O leading underscore has already been removed, including for C++ manglings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

DATA = Path(__file__).resolve().parent / 'data/nvidia-public-kpi-exports'
MANIFEST_SHA256 = '0784ca8bc579c5ca5d60055b2c4652e0f9a2af8d3dfa3d4947987ed7021c1ee5'
XNU = ('apple-oss-distributions/xnu', 'f6217f891ac0bb64f3d375211650a4c1ff8ca1ea')
PCI = ('apple-oss-distributions/IOPCIFamily', '4822b27a36e2de70e231ecf2bf3021384fab6ec2')
GROUPS = {'BSDKernel': 'com.apple.kpi.bsd', 'IOKit': 'com.apple.kpi.iokit',
          'Libkern': 'com.apple.kpi.libkern', 'Mach': 'com.apple.kpi.mach',
          'Unsupported': 'com.apple.kpi.unsupported', 'Private': None}
IDLE_LIBRARIES = {**{'com.apple.kpi.' + group: '8.0.0' for group in
                    ('bsd', 'iokit', 'libkern', 'mach', 'unsupported')},
                  'com.apple.iokit.IOPCIFamily': '2.9.0'}
FILES = {group + suffix: (group, XNU) for group in GROUPS
         for suffix in ('.exports', '.x86_64.exports', '.x86_64.MacOSX.exports')
         if not (group == 'Mach' and suffix == '.x86_64.MacOSX.exports')}
FILES['IOPCIFamily.exports'] = ('IOPCIFamily', PCI)
SYMBOL = re.compile(r'_[A-Za-z0-9_.$]+')


class ExportAuditError(ValueError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__('Imports lack declared public source exports: ' +
                         ', '.join(row['symbol'] + ' (' + row['reason'] + ')'
                                   for row in report['rejected']))


def parse_exports(text: str, *, private_patterns: bool = False) -> set[str]:
    """Read public names on the LEFT side of export aliases, without globbing."""
    names = set()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(':')]
        if private_patterns and len(parts) == 1 and parts[0].endswith('*') and \
                SYMBOL.fullmatch(parts[0][:-1]) is not None:
            names.add(parts[0][1:])  # Private-only classification; never authorizes.
            continue
        if len(parts) not in (1, 2) or any(SYMBOL.fullmatch(p) is None for p in parts):
            raise ValueError('Malformed export map row %d: %r' % (number, raw))
        names.add(parts[0][1:])  # Strip precisely the Mach-O prefix, not C++ '_'.
    return names


def load_inventory(directory: Path = DATA) -> dict:
    directory = Path(directory)
    manifest_path = directory / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError('Export manifest must be a regular file')
    raw_manifest = manifest_path.read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Reviewed export manifest bytes changed')
    manifest = json.loads(raw_manifest)
    for name, value in {'format': 1, 'architecture': 'x86_64', 'platform': 'MacOSX',
                        'exact_target_export_proof': False}.items():
        if type(manifest.get(name)) is not type(value) or manifest[name] != value:
            raise ValueError('Export manifest profile changed: ' + name)
    rows = manifest.get('sources')
    if not isinstance(rows, list) or len(rows) != len(FILES) or \
            {row.get('file') for row in rows} != set(FILES):
        raise ValueError('Export manifest source inventory changed')
    if {path.name for path in directory.iterdir()} != {*FILES, 'manifest.json'}:
        raise ValueError('Unexpected or missing export inventory files')
    public, private, private_prefixes = {}, set(), set()
    source_proof = []
    for row in rows:
        name = row['file']
        group, (repository, commit) = FILES[name]
        bundle = 'com.apple.iokit.IOPCIFamily' if group == 'IOPCIFamily' else GROUPS[group]
        expected = {'repository': repository, 'commit': commit, 'source_path': 'config/' + name,
                    'classification': 'private' if group == 'Private' else 'public',
                    'bundle_id': bundle,
                    'architecture': 'x86_64' if '.x86_64.' in name else 'source-common',
                    'platform': 'MacOSX' if '.MacOSX.' in name else 'source-common'}
        if any(row.get(key) != value for key, value in expected.items()):
            raise ValueError('Export source identity/profile changed: ' + name)
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Export input must be a regular file: ' + name)
        raw = path.read_bytes()
        if len(raw) != row.get('bytes') or hashlib.sha256(raw).hexdigest() != row.get('sha256'):
            raise ValueError('Export input bytes changed: ' + name)
        names = parse_exports(raw.decode('utf-8'), private_patterns=bundle is None)
        if bundle is None:
            private.update(name for name in names if not name.endswith('*'))
            private_prefixes.update(name[:-1] for name in names if name.endswith('*'))
        else:
            for symbol in names:
                public.setdefault(symbol, {}).setdefault(bundle, []).append(name)
        source_proof.append({**row, 'parsed_export_count': len(names)})
    return {'public': public, 'private': private, 'private_prefixes': private_prefixes, 'sources': source_proof,
            'manifest_sha256': hashlib.sha256(raw_manifest).hexdigest(),
            'limitations': manifest['limitations']}


def inspect_imports(imports, declared_libraries, *, inventory_dir: Path = DATA) -> dict:
    """Classify every final import and retain all failures in one result."""
    if isinstance(imports, (str, bytes)):
        raise ValueError('Imports must be a collection of linker symbol names')
    imports = list(imports)
    if any(not isinstance(name, str) or not name or SYMBOL.fullmatch('_' + name) is None
           for name in imports):
        raise ValueError('Invalid linker import spelling')
    if len(imports) != len(set(imports)):
        raise ValueError('Duplicate final import names')
    if isinstance(declared_libraries, (str, bytes)):
        raise ValueError('Declared libraries must be a collection or mapping')
    libraries = set(declared_libraries)
    inventory = load_inventory(inventory_dir)
    matched, rejected = [], []
    for symbol in sorted(imports):
        owners = inventory['public'].get(symbol, {})
        admitted = sorted(set(owners) & libraries)
        if admitted:
            matched.append({'symbol': symbol, 'declared_public_export_owners': admitted,
                            'source_files': sorted({path for owner in admitted for path in owners[owner]})})
        elif owners:
            rejected.append({'symbol': symbol, 'reason': 'public-export-owner-not-declared',
                             'public_export_owners': sorted(owners)})
        else:
            is_private = symbol in inventory['private'] or \
                any(symbol.startswith(prefix) for prefix in inventory['private_prefixes'])
            rejected.append({'symbol': symbol,
                             'reason': 'private-only-export' if is_private
                                       else 'unknown-export'})
    return {'format': 1, 'scope': 'pinned Apple source export snapshot; preflight only',
            'status': 'passed' if not rejected else 'failed', 'architecture': 'x86_64',
            'platform': 'MacOSX', 'exact_target_export_proof': False,
            'declared_libraries': sorted(libraries), 'import_count': len(imports),
            'matched_count': len(matched), 'rejected': rejected, 'matched': matched,
            'manifest_sha256': inventory['manifest_sha256'], 'sources': inventory['sources'],
            'limitations': inventory['limitations']}


def audit_imports(imports, declared_libraries, *, inventory_dir: Path = DATA) -> dict:
    """Require source-backed public exports from declared dependencies."""
    report = inspect_imports(imports, declared_libraries, inventory_dir=inventory_dir)
    if report['rejected']:
        raise ExportAuditError(report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True,
                        help='Native strict report with final_image.imports')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--libraries-plist', type=Path,
                        help='Actual bundle Info.plist; otherwise use the idle package dependencies')
    args = parser.parse_args(argv)
    libraries = IDLE_LIBRARIES
    if args.libraries_plist:
        import plistlib
        libraries = plistlib.loads(args.libraries_plist.read_bytes())['OSBundleLibraries']
    native = json.loads(args.report.read_bytes())
    report = inspect_imports(native['final_image']['imports'], libraries)
    report['native_report_sha256'] = hashlib.sha256(args.report.read_bytes()).hexdigest()
    encoded = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(encoded)
    print(json.dumps({key: report[key] for key in
                     ('status', 'import_count', 'matched_count', 'rejected', 'exact_target_export_proof')},
                     indent=2, sort_keys=True))
    return int(report['status'] != 'passed')


if __name__ == '__main__':
    sys.exit(main())
