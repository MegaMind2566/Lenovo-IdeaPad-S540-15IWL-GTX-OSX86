#!/usr/bin/env python3
"""Verify pinned NVIDIA input bytes and the explicitly adapted uptime caller."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'packages/nvidia-os-adapter/upstream'
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
PINNED = {
    'include/nvtypes.h': (
        'src/common/sdk/nvidia/inc/nvtypes.h',
        'cb6d906a34cf6ace3d852657cf8dde4a587d7721'),
    'include/cpuopsys.h': (
        'src/common/sdk/nvidia/inc/cpuopsys.h',
        '6467b396a696a47fa71d4ad41e32d27f344fcdce'),
    'include/nv-kernel-interface-api.h': (
        'kernel-open/common/inc/nv-kernel-interface-api.h',
        '183f9b4312eb0913c0a0a97e4db1f62a50b442c5'),
    'reference/time_unix_kernel_os.c': (
        'src/nvidia/src/libraries/nvport/time/time_unix_kernel_os.c',
        'abfec8d3aa0b94a9d53e18134a66655dc7179e43'),
    'reference/os-interface.h': (
        'src/nvidia/arch/nvalloc/unix/include/os-interface.h',
        '03de89a28a2611bca2fb2a3d85c7f617a681a20a'),
}
CALLERS = [
    'portTimeGetUptimeMicroseconds',
    'portTimeGetUptimeNanoseconds',
    'portTimeGetUptimeNanosecondsHighPrecision',
    'portTimeGetUptimeResolution',
]
HOOKS = [
    'os_get_monotonic_time_ns',
    'os_get_monotonic_time_ns_hr',
    'os_get_monotonic_tick_resolution_ns',
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_bytes(root: Path, name: str) -> bytes:
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('A provenance input is not a regular file: ' + name)
    return path.read_bytes()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_upstream(root: Path = UPSTREAM) -> dict:
    """Read and verify only; return provenance for the native build record."""
    manifest = json.loads(regular_bytes(root, 'PROVENANCE.json'))
    require(manifest.get('format') == 1, 'Unexpected provenance format.')
    require(manifest.get('repository') == 'NVIDIA/open-gpu-kernel-modules',
            'Unexpected upstream repository.')
    require(manifest.get('release') == '615.78.08' and manifest.get('commit') == COMMIT,
            'The upstream release or commit changed.')
    entries = manifest.get('upstream_files', [])
    require(isinstance(entries, list) and len(entries) == len(PINNED),
            'The unmodified input list is incomplete.')
    require({item.get('path') for item in entries} == set(PINNED),
            'Unexpected unmodified input paths.')
    for item in entries:
        path = item['path']
        origin, blob_sha1 = PINNED[path]
        data = regular_bytes(root, path)
        actual_blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        require(item.get('source_path') == origin and item.get('git_blob_sha1') == blob_sha1,
                'An upstream input identity changed: ' + path)
        require(actual_blob == blob_sha1, 'An upstream input was modified: ' + path)
        require(item.get('sha256') == sha256(data) and item.get('bytes') == len(data),
                'An upstream checksum or size changed: ' + path)
        require(item.get('modified') is False and item.get('license') == 'MIT',
                'An upstream input is not recorded as unmodified MIT source.')
        require(b'SPDX-License-Identifier: MIT' in data,
                'An upstream input lost its license notice: ' + path)

    original = regular_bytes(root, 'reference/time_unix_kernel_os.c')
    # The pinned source's exact contiguous four-function block, including newline.
    body = b''.join(original.splitlines(keepends=True)[62:81])
    require(body.startswith(b'NvU64 portTimeGetUptimeMicroseconds(void)\n'),
            'The pinned caller source range no longer begins as expected.')
    require(original[original.index(b'NvU64 portTimeGetUptimeMicroseconds'):] == body,
            'The pinned caller range is no longer the complete uptime tail.')
    adapted = manifest.get('adapted_caller', {})
    require(adapted.get('path') == 'nvport_time_uptime.c'
            and adapted.get('source_reference') == 'reference/time_unix_kernel_os.c'
            and adapted.get('source_lines') == [63, 81]
            and adapted.get('functions') == CALLERS
            and adapted.get('complete_upstream_translation_unit') is False,
            'The adapted extraction is mislabeled.')
    caller = regular_bytes(root, 'nvport_time_uptime.c')
    require(adapted.get('sha256') == sha256(caller)
            and adapted.get('source_body_sha256') == sha256(body),
            'An adapted caller checksum changed.')
    notice = original[:original.index(b'/**')]
    require(caller.startswith(notice), 'The original full MIT notice was not retained.')
    require(b'Adapted extraction' in caller and b'not the unmodified complete upstream time module' in caller,
            'The caller is not explicitly labeled as an adapted extraction.')
    require(caller[caller.index(b'NvU64 portTimeGetUptimeMicroseconds'):] == body,
            'The extracted uptime signatures or bodies changed.')
    require(re.findall(rb'\bNvU64\s+(portTime\w+)\(void\)\s*\{', caller)
            == [name.encode() for name in CALLERS],
            'The adapted file contains an unexpected caller implementation.')
    require(re.findall(rb'^#include\s+(.+)$', caller, re.M)
            == [b'"nvport_time_uptime.h"'], 'The adapted include closure changed.')
    require(b'os_get_system_time' not in caller,
            'The adapted caller acquired a wall-clock dependency.')

    interface = manifest.get('interface', {})
    require(interface.get('path') == 'nvport_time_uptime.h'
            and interface.get('declarations_reference') == 'reference/os-interface.h'
            and interface.get('declaration_lines') == [81, 83]
            and interface.get('hooks') == HOOKS, 'The interface provenance changed.')
    header = regular_bytes(root, 'nvport_time_uptime.h')
    require(interface.get('sha256') == sha256(header), 'The narrow interface checksum changed.')
    reference = regular_bytes(root, 'reference/os-interface.h')
    for hook in HOOKS:
        declaration = rb'\bNvU64\s+NV_API_CALL\s+' + hook.encode() + rb'\s*\(\s*void\s*\)\s*;'
        require(len(re.findall(declaration, reference)) == 1
                and len(re.findall(declaration, header)) == 1,
                'A hook declaration differs from the actual NVIDIA ABI: ' + hook)
    require(b'#include "include/nvtypes.h"' in header
            and b'#include "include/nv-kernel-interface-api.h"' in header
            and b'extern "C" {' in header,
            'The narrow header lost the actual NVIDIA types, convention, or C linkage.')
    require(re.findall(rb'\bNvU64\s+(?:NV_API_CALL\s+)?(\w+)\s*\(\s*void\s*\)\s*;', header)
            == [name.encode() for name in HOOKS + CALLERS],
            'The narrow interface contains unexpected or missing declarations.')
    return {'commit': COMMIT, 'release': manifest['release'],
            'unmodified_inputs': len(PINNED), 'adapted_uptime_functions': len(CALLERS),
            'compiled_caller_sha256': sha256(caller),
            'complete_upstream_time_module': False}


class ProvenanceTests(unittest.TestCase):
    def test_checked_in_source_matches_pinned_blobs_and_extraction(self) -> None:
        result = verify_upstream()
        self.assertEqual(result['adapted_uptime_functions'], 4)
        self.assertFalse(result['complete_upstream_time_module'])

    def test_changed_original_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, copy)
            target = copy / 'include/nvtypes.h'
            target.write_bytes(target.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'input was modified'):
                verify_upstream(copy)

    def test_changed_caller_is_rejected_even_if_its_manifest_hash_is_updated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, copy)
            target = copy / 'nvport_time_uptime.c'
            target.write_bytes(target.read_bytes().replace(b'/ 1000;', b'/ 999;', 1))
            manifest_path = copy / 'PROVENANCE.json'
            manifest = json.loads(manifest_path.read_bytes())
            manifest['adapted_caller']['sha256'] = sha256(target.read_bytes())
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'signatures or bodies changed'):
                verify_upstream(copy)

    def test_changed_hook_abi_is_rejected_even_if_header_hash_is_updated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, copy)
            target = copy / 'nvport_time_uptime.h'
            target.write_bytes(target.read_bytes().replace(
                b'NvU64 NV_API_CALL os_get_monotonic_time_ns(void);',
                b'NvU32 NV_API_CALL os_get_monotonic_time_ns(void);'))
            manifest_path = copy / 'PROVENANCE.json'
            manifest = json.loads(manifest_path.read_bytes())
            manifest['interface']['sha256'] = sha256(target.read_bytes())
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'actual NVIDIA ABI'):
                verify_upstream(copy)


if __name__ == '__main__':
    unittest.main()
