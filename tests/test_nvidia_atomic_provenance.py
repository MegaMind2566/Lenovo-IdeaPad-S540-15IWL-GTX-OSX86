#!/usr/bin/env python3
"""Verify the original NVIDIA atomic header closure and its LLVM license."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'packages/nvidia-os-adapter/upstream'
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
EXPECTED = {
    "include/nvport/nvport.h": [
        "src/nvidia/inc/libraries/nvport/nvport.h",
        "f9cd603d3a920534a1c4ddec10b8ebb4ad7e526b"
    ],
    "include/nvport/atomic.h": [
        "src/nvidia/inc/libraries/nvport/atomic.h",
        "2ad6f6a7e353f174f16ffbfb80b9ee8f9fb269ac"
    ],
    "include/nvport/inline/atomic_c11.h": [
        "src/nvidia/inc/libraries/nvport/inline/atomic_c11.h",
        "a1dffba035f155a42db28d1ae6dc3ecd93bf5cef"
    ],
    "include/nvport/inline/atomic_clang.h": [
        "src/nvidia/inc/libraries/nvport/inline/atomic_clang.h",
        "57e5dd67a4aa5941e1361681b57f9ad06751bfd0"
    ],
    "include/nvport/clang/stdatomic.h": [
        "src/nvidia/inc/libraries/nvport/clang/stdatomic.h",
        "e796a36c02a751780724696a28220195e451378c"
    ],
    "include/nvstatus.h": [
        "src/common/sdk/nvidia/inc/nvstatus.h",
        "4f5284db2b1e6af1c2c0c85bc39dfc14daccc9fd"
    ],
    "include/nvstatuscodes.h": [
        "src/common/sdk/nvidia/inc/nvstatuscodes.h",
        "430eed77a03f2f15bf058d3c49931a9f89ace08e"
    ],
    "include/nv_stddef.h": [
        "src/common/sdk/nvidia/inc/nv_stddef.h",
        "a69b28c023b06cd98f49dccfadf1097f762a83ab"
    ],
    "include/nvtypes.h": [
        "src/common/sdk/nvidia/inc/nvtypes.h",
        "cb6d906a34cf6ace3d852657cf8dde4a587d7721"
    ],
    "include/cpuopsys.h": [
        "src/common/sdk/nvidia/inc/cpuopsys.h",
        "6467b396a696a47fa71d4ad41e32d27f344fcdce"
    ]
}
LLVM_BLOB = 'fa6ac540007032cbd0ec772a1c72e6cb5527a4fe'


def blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + bytes([0]) + data).hexdigest()


def verify_upstream(root: Path = UPSTREAM) -> dict:
    root = Path(root)
    manifest = json.loads((root / 'ATOMIC-PROVENANCE.json').read_text())
    if (manifest.get('format') != 1 or
            manifest.get('repository') != 'NVIDIA/open-gpu-kernel-modules' or
            manifest.get('commit') != COMMIT or
            manifest.get('component') != 'nvport-atomic' or
            manifest.get('adapted_upstream_code') is not False):
        raise ValueError('Unexpected atomic source identity.')
    entries = manifest.get('source_files')
    if (not isinstance(entries, list) or len(entries) != len(EXPECTED) or
            {e.get('path') for e in entries} != set(EXPECTED)):
        raise ValueError('The atomic header closure is incomplete or duplicated.')
    hashes = {}
    for entry in entries:
        local = entry['path']
        upstream_path, pinned_blob = EXPECTED[local]
        if (entry.get('upstream_path') != upstream_path or
                entry.get('git_blob_sha1') != pinned_blob):
            raise ValueError('The atomic source path or pinned blob differs: ' + local)
        data = (root / local).read_bytes()
        if blob_sha1(data) != pinned_blob:
            raise ValueError('An original atomic dependency was modified: ' + local)
        if local == 'include/nvport/clang/stdatomic.h':
            if b'SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception' not in data:
                raise ValueError('The original LLVM license notice is missing.')
        elif b'SPDX-License-Identifier: MIT' not in data:
            raise ValueError('The original NVIDIA license notice is missing.')
        hashes[local] = hashlib.sha256(data).hexdigest()
    license_record = manifest.get('llvm_license', {})
    if license_record != {
            'path': 'LLVM-LICENSE.txt', 'repository': 'llvm/llvm-project',
            'upstream_path': 'llvm/LICENSE.TXT', 'ref': 'llvmorg-18.1.8',
            'git_blob_sha1': LLVM_BLOB}:
        raise ValueError('Unexpected LLVM license identity.')
    data = (root / 'LLVM-LICENSE.txt').read_bytes()
    if blob_sha1(data) != LLVM_BLOB or b'LLVM Exceptions' not in data:
        raise ValueError('The LLVM license or exception text differs.')
    hashes['LLVM-LICENSE.txt'] = hashlib.sha256(data).hexdigest()
    return {
        'repository': manifest['repository'], 'commit': COMMIT,
        'component': 'nvport-atomic', 'unchanged_headers': len(EXPECTED),
        'adapted_upstream_code': False,
        'source_sha256': hashes,
        'llvm_license': license_record,
        'selection': {
            'c': 'original C11 branch in GNU C11 freestanding kernel-build profile',
            'cpp': 'original Clang intrinsic branch in C++17 kernel-build profile'},
        'scope': 'CPU-only atomic integration; no RM or GPU access',
    }


class AtomicProvenanceTests(unittest.TestCase):
    def test_original_header_closure_and_licenses(self) -> None:
        result = verify_upstream()
        self.assertEqual(result['unchanged_headers'], 10)
        self.assertFalse(result['adapted_upstream_code'])

    def test_modified_header_rejected_even_with_modified_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix='atomic-provenance-') as temporary:
            root = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, root)
            path = root / 'include/nvport/inline/atomic_c11.h'
            path.write_bytes(path.read_bytes().replace(
                b'memory_order_seq_cst', b'memory_order_relaxed', 1))
            manifest_path = root / 'ATOMIC-PROVENANCE.json'
            manifest = json.loads(manifest_path.read_text())
            entry = next(e for e in manifest['source_files']
                         if e['path'] == 'include/nvport/inline/atomic_c11.h')
            entry['git_blob_sha1'] = blob_sha1(path.read_bytes())
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'pinned blob differs'):
                verify_upstream(root)

    def test_missing_header_and_license_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix='atomic-provenance-') as temporary:
            root = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, root)
            manifest_path = root / 'ATOMIC-PROVENANCE.json'
            original = manifest_path.read_text()
            manifest = json.loads(original)
            manifest['source_files'].pop()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'closure is incomplete'):
                verify_upstream(root)
            manifest_path.write_text(original)
            (root / 'LLVM-LICENSE.txt').write_text('Apache license omitted')
            with self.assertRaisesRegex(ValueError, 'LLVM license or exception'):
                verify_upstream(root)


if __name__ == '__main__':
    unittest.main()
