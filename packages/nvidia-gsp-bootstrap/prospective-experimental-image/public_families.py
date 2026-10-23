#!/usr/bin/env python3
"""Two source-derived public family metaclasses for this experiment only.

SDK declarations remain independently required by the linker. These pinned
Apple implementation/build/Info.plist sources establish ordinary public global
definitions and their declared providers, not exports observed on the Lenovo.
The historical KPI inventory and idle package profile are unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import plistlib
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'builders'))
import nvidia_public_kpi_exports as public

DATA = HERE / 'data/public-family-metaclasses'
MANIFEST_SHA256 = 'db00d149652e33686d63b3597c1d715135774291c9374b291a7b9e3cd89a645f'
FAMILIES = {
    'IOGraphics': ('IOFramebuffer', 'IOGraphicsDevice', 'Abstract',
                   'com.apple.iokit.IOGraphicsFamily', '1.0.0b1',
                   ('A68335960D450E6600307FE3', 'A68335970D450E6600307FE3', 'A68335980D450E6600307FE3')),
    'IOACPIFamily': ('IOACPIPlatformDevice', 'IOPlatformDevice', '',
                     'com.apple.iokit.IOACPIFamily', '1.0.0d1',
                     ('A6B29F7A0D4982AE001D2E80', 'A6B29F7B0D4982AE001D2E80', 'A6B29F7C0D4982AE001D2E80')),
}
LIBRARIES = {**public.IDLE_LIBRARIES,
             **{row[3]: row[4] for row in FAMILIES.values()}}


def require(value, message):
    if not value:
        raise ValueError(message)


def load_inventory(directory=DATA):
    directory = Path(directory)
    manifest_path = directory / 'manifest.json'
    require(manifest_path.is_file() and not manifest_path.is_symlink(), 'Family proof manifest must be ordinary')
    raw = manifest_path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256, 'Reviewed family proof manifest changed')
    manifest = json.loads(raw)
    rows = manifest['sources']
    require({p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()} ==
            {'manifest.json', *[row['file'] for row in rows]}, 'Family proof source inventory changed')
    texts, proof = {}, []
    for row in rows:
        path = directory / row['file']
        require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
                'Family proof source must be ordinary')
        content = path.read_bytes()
        require(len(content) == row['bytes'] and hashlib.sha256(content).hexdigest() == row['sha256'],
                'Pinned Apple family proof source changed: ' + row['file'])
        texts[(row['repository'].split('/')[-1], row['role'])] = content.decode('utf-8')
        proof.append(dict(row, immutable_url='https://github.com/' + row['repository'] + '/blob/' +
                          row['commit'] + '/' + row['source_path']))
    macro = texts[('xnu', 'macro')].replace('\\\n', ' ')
    require(re.search(r'const\s+OSMetaClass\s*\*\s*const\s+className\s*::metaClass\s*=\s*&\s*className\s*::gMetaClass', macro),
            'The pinned public metaclass global definition changed')
    owners = {}
    for repository, (name, parent, abstract, bundle, compatible, configurations) in FAMILIES.items():
        implementation = texts[(repository, 'implementation')]
        header = texts[(repository, 'header')]
        project = texts[(repository, 'project')]
        info = plistlib.loads(texts[(repository, 'info')].encode('utf-8'))
        require(re.search(r'OSDefineMetaClassAnd' + abstract + r'Structors\s*\(\s*' + name + r'\s*,\s*' + parent + r'\s*\)', implementation)
                and re.search(r'OSDeclareDefaultStructors\s*\(\s*' + name + r'\s*\)', header),
                'The exact public family metaclass declaration/definition changed')
        require(info['CFBundleIdentifier'] == bundle and info['OSBundleCompatibleVersion'] == compatible,
                'The pinned family provider identity/compatibility boundary changed')
        require(name + '.cpp in Sources' in project and
                not re.search(r'(?:UN)?EXPORTED_SYMBOLS_FILE|(?:-exported|-unexported)_symbols_list|LD_EXPORT_SYMBOLS', project),
                'The reviewed family source inclusion/export build policy changed')
        for identifier in configurations:
            block = re.search(r'\n\t\t' + identifier + r' /\*[^\n]+\*/ = \{(.*?)\n\t\t\};', project, re.S)
            require(block is not None and 'GCC_SYMBOLS_PRIVATE_EXTERN = NO;' in block[1],
                    'The exact family target no longer builds ordinary public globals')
        # Linker names omit exactly one Mach-O underscore. Derive the sole
        # member spelling from the source class name; authorize no family API.
        symbol = '_ZN' + str(len(name)) + name + '9metaClassE'
        owners[symbol] = dict(bundle_id=bundle, compatible_version=compatible,
                              source_class=name, member='metaClass',
                              definition='OSDefineMetaClassAnd' + abstract + 'Structors',
                              public_global_build_setting='GCC_SYMBOLS_PRIVATE_EXTERN=NO')
    return dict(owners=owners, manifest_sha256=MANIFEST_SHA256, sources=proof,
                limitations=manifest['limitations'])


def audit_imports(imports, declared_libraries=LIBRARIES, *, inventory_dir=DATA):
    report = public.inspect_imports(imports, declared_libraries)
    inventory = load_inventory(inventory_dir)
    rejected = []
    for row in report['rejected']:
        owner = inventory['owners'].get(row['symbol'])
        if owner is None or row['reason'] != 'unknown-export':
            rejected.append(row)
        elif owner['bundle_id'] not in declared_libraries:
            rejected.append(dict(row, reason='public-export-owner-not-declared',
                                 public_export_owners=[owner['bundle_id']]))
        elif declared_libraries[owner['bundle_id']] != owner['compatible_version']:
            rejected.append(dict(row, reason='reviewed-family-compatibility-boundary-changed'))
        else:
            report['matched'].append(dict(symbol=row['symbol'],
                declared_public_export_owners=[owner['bundle_id']], source_metaclass_definition=owner,
                source_files=[source['file'] for source in inventory['sources'] if
                    source['repository'].endswith('/' + ('IOGraphics' if owner['source_class'] == 'IOFramebuffer' else 'IOACPIFamily'))
                    or source['role'] == 'macro']))
    report.update(status='failed' if rejected else 'passed', rejected=rejected,
                  matched_count=len(report['matched']), family_metaclass_source_proof=inventory)
    report['matched'].sort(key=lambda row: row['symbol'])
    if rejected:
        raise public.ExportAuditError(report)
    return report
