#!/usr/bin/env python3
"""Verify pinned NVIDIA memory inputs and the explicitly adapted RAM callers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'packages/nvidia-os-adapter/upstream'
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
PINNED = {
    'include/nvtypes.h': ('src/common/sdk/nvidia/inc/nvtypes.h',
                         'cb6d906a34cf6ace3d852657cf8dde4a587d7721'),
    'include/cpuopsys.h': ('src/common/sdk/nvidia/inc/cpuopsys.h',
                          '6467b396a696a47fa71d4ad41e32d27f344fcdce'),
    'include/nv-kernel-interface-api.h': ('kernel-open/common/inc/nv-kernel-interface-api.h',
                                       '183f9b4312eb0913c0a0a97e4db1f62a50b442c5'),
    'reference/os-interface.h': ('src/nvidia/arch/nvalloc/unix/include/os-interface.h',
                                 '03de89a28a2611bca2fb2a3d85c7f617a681a20a'),
    'reference/memory_unix_kernel_os.c': (
        'src/nvidia/src/libraries/nvport/memory/memory_unix_kernel_os.c',
        '06e5504a6556d2107d41cf614063737a92ad57c0'),
    'reference/memory.h': ('src/nvidia/inc/libraries/nvport/memory.h',
                            '595eafee880dccd54ca2f382fb77afc918793e1d'),
    'reference/debug.h': ('src/nvidia/inc/libraries/nvport/debug.h',
                           'c2929200e628022149e6c2fb1581469946ffe05a'),
}
CALLERS = ['portMemCopy', 'portMemCopyAligned', 'portMemSet', 'portMemCmp']
CHANGES = {'os_mem_copy': 's540NvidiaMemoryCopy',
           'os_mem_set': 's540NvidiaMemorySet',
           'os_mem_cmp': 's540NvidiaMemoryCompare'}
DECLARATIONS = [
    ('void *', 'os_mem_copy', ['void *', 'const void *', 'NvU32']),
    ('void *', 'os_mem_set', ['void *', 'NvU8', 'NvU32']),
    ('NvS32', 'os_mem_cmp', ['const NvU8 *', 'const NvU8 *', 'NvU32']),
    ('void *', 'portMemCopy', ['void *', 'NvLength', 'const void *', 'NvLength']),
    ('void *', 'portMemCopyAligned', ['void *', 'NvLength', 'const void *', 'NvLength']),
    ('void *', 'portMemSet', ['void *', 'NvU8', 'NvLength']),
    ('NvS32', 'portMemCmp', ['const void *', 'const void *', 'NvLength']),
    ('void *', 's540NvidiaMemoryCopy', ['void *', 'const void *', 'NvLength']),
    ('void *', 's540NvidiaMemorySet', ['void *', 'NvU8', 'NvLength']),
    ('NvS32', 's540NvidiaMemoryCompare', ['const NvU8 *', 'const NvU8 *', 'NvLength']),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def regular_bytes(root: Path, name: str) -> bytes:
    target = root / name
    require(target.is_file() and not target.is_symlink(), 'Not a regular input: ' + name)
    return target.read_bytes()


def compact(value: str) -> str:
    return re.sub(r'\s+', '', value)


def declaration_shape(data: bytes, name: str) -> tuple[str, list[str]]:
    # Strip comments before finding exactly one function declaration. Parameter
    # names are removed only after a complete known type, preserving ABI width.
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', data.decode(), flags=re.S)
    expression = (r'\b(void\s*\*|NvS32)\s*(?:NV_API_CALL\s+)?' + re.escape(name)
                  + r'\s*\(([^;{}]*)\)\s*;')
    matches = re.findall(expression, source)
    require(len(matches) == 1, 'Missing or ambiguous declaration: ' + name)
    result, arguments = matches[0]
    shapes = []
    for argument in arguments.split(','):
        argument = argument.strip()
        match = re.fullmatch(r'((?:const\s+)?void\s*\*|(?:const\s+)?NvU8\s*\*|NvU8|NvU32|NvLength)\s*(?:[A-Za-z_]\w*)?', argument)
        require(match is not None, 'Unexpected argument type: ' + name)
        shapes.append(compact(match.group(1)))
    return compact(result), shapes


def verify_upstream(root: Path = UPSTREAM) -> dict:
    manifest = json.loads(regular_bytes(root, 'MEMORY-PROVENANCE.json'))
    require(manifest.get('format') == 1
            and manifest.get('repository') == 'NVIDIA/open-gpu-kernel-modules'
            and manifest.get('release') == '615.78.08'
            and manifest.get('commit') == COMMIT, 'Unexpected pinned memory provenance.')
    entries = manifest.get('upstream_files', [])
    require(len(entries) == len(PINNED)
            and {item.get('path') for item in entries} == set(PINNED),
            'Unexpected memory input list.')
    for entry in entries:
        name = entry['path']
        source, blob = PINNED[name]
        data = regular_bytes(root, name)
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        require(actual == blob, 'A pinned memory input was modified: ' + name)
        require(entry.get('source_path') == source and entry.get('git_blob_sha1') == blob
                and entry.get('sha256') == sha256(data) and entry.get('bytes') == len(data)
                and entry.get('modified') is False and entry.get('license') == 'MIT',
                'A pinned memory input identity changed: ' + name)
        require(b'SPDX-License-Identifier: MIT' in data, 'Missing original MIT notice.')

    original = regular_bytes(root, 'reference/memory_unix_kernel_os.c')
    start = original.index(b'void *\nportMemCopy\n')
    end = original.index(b'\n\n\n#define PORT_MEM_USE_GENERIC_portMemSetPattern', start)
    body = original[start:end]
    adapted = manifest.get('adapted_caller', {})
    require(adapted.get('path') == 'nvport_memory_primitives.c'
            and adapted.get('source_reference') == 'reference/memory_unix_kernel_os.c'
            and adapted.get('source_lines') == [79, 156]
            and adapted.get('functions') == CALLERS and adapted.get('changes') == CHANGES
            and adapted.get('complete_upstream_translation_unit') is False
            and adapted.get('assertion_profile') == 'upstream-release-only'
            and adapted.get('checked_profile_supported') is False,
            'The memory adaptation is mislabeled.')
    caller = regular_bytes(root, 'nvport_memory_primitives.c')
    require(adapted.get('sha256') == sha256(caller)
            and adapted.get('source_body_sha256') == sha256(body),
            'A memory adaptation checksum changed.')
    transformed = body
    for old, new in CHANGES.items():
        require(transformed.count(old.encode() + b'(') == 1, 'Unexpected upstream hook usage.')
        transformed = transformed.replace(old.encode() + b'(', new.encode() + b'(')
    require(caller[caller.index(b'void *\nportMemCopy\n'):].rstrip(b'\n') == transformed.rstrip(b'\n'),
            'The adapted memory bodies contain an unrecorded change.')
    notice = original[:original.index(b'/**')]
    require(caller.startswith(notice) and b'Adapted extraction' in caller
            and b'not the unmodified' in caller and b'complete upstream memory module' in caller,
            'The adaptation lost its license or explicit scope.')
    require(re.findall(rb'^#include\s+(.+)$', caller, re.M)
            == [b'"nvport_memory_primitives.h"'], 'Unexpected memory caller include closure.')
    debug = regular_bytes(root, 'reference/debug.h')
    require(b'#else // PORT_IS_CHECKED_BUILD\n#define PORT_BREAKPOINT_CHECKED()\n#define PORT_ASSERT_CHECKED(x)\n#endif // PORT_IS_CHECKED_BUILD' in debug,
            'The upstream release assertion contract changed.')
    require(b'#if defined(PORT_IS_CHECKED_BUILD) && PORT_IS_CHECKED_BUILD\n#error ' in caller
            and re.findall(rb'^#define PORT_ASSERT_CHECKED\(x\)([^\n]*)$', caller, re.M) == [b'']
            and b'upstream release assertion profile' in caller,
            'The explicit release-only assertion profile changed.')

    interface = manifest.get('interface', {})
    header = regular_bytes(root, 'nvport_memory_primitives.h')
    require(interface.get('path') == 'nvport_memory_primitives.h'
            and interface.get('declarations_reference') == 'reference/os-interface.h'
            and interface.get('caller_declarations_reference') == 'reference/memory.h'
            and interface.get('hooks') == list(CHANGES)
            and interface.get('length_abi') == {'NvLength_bits': 64, 'os_hook_length_bits': 32}
            and interface.get('sha256') == sha256(header), 'The memory interface identity changed.')
    os_reference = regular_bytes(root, 'reference/os-interface.h')
    memory_reference = regular_bytes(root, 'reference/memory.h')
    for result, name, parameters in DECLARATIONS:
        expected = compact(result), [compact(parameter) for parameter in parameters]
        require(declaration_shape(header, name) == expected, 'The narrow memory ABI changed: ' + name)
        if name in CHANGES:
            require(declaration_shape(os_reference, name) == expected, 'The OS-hook ABI changed: ' + name)
        elif name in CALLERS:
            require(declaration_shape(memory_reference, name) == expected, 'The NvPort ABI changed: ' + name)
    require(b'#include "include/nvtypes.h"' in header
            and b'#include "include/nv-kernel-interface-api.h"' in header
            and b'extern "C" {' in header, 'The narrow memory interface lost real NVIDIA types or linkage.')
    require(manifest.get('scope') == {'memory': 'ordinary RAM only', 'allocation': False,
                                     'user_copy': False, 'mmio': False, 'dma': False,
                                     'generic_move_pattern': False}, 'The memory scope changed.')
    return {'commit': COMMIT, 'release': manifest['release'], 'unmodified_inputs': len(PINNED),
            'adapted_memory_functions': len(CALLERS), 'assertion_profile': 'upstream-release-only',
            'complete_upstream_memory_module': False, 'compiled_caller_sha256': sha256(caller),
            'length_abi': interface['length_abi']}


class MemoryProvenanceTests(unittest.TestCase):
    def test_pinned_memory_inputs_and_adaptation(self) -> None:
        self.assertEqual(verify_upstream()['adapted_memory_functions'], 4)

    def test_modified_reference_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, target)
            path = target / 'reference/memory_unix_kernel_os.c'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'pinned memory input was modified'):
                verify_upstream(target)

    def test_unrecorded_caller_change_is_rejected_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, target)
            path = target / 'nvport_memory_primitives.c'
            path.write_bytes(path.read_bytes().replace(b'return -1;', b'return 0;'))
            manifest = json.loads((target / 'MEMORY-PROVENANCE.json').read_bytes())
            manifest['adapted_caller']['sha256'] = sha256(path.read_bytes())
            (target / 'MEMORY-PROVENANCE.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'unrecorded change'):
                verify_upstream(target)

    def test_narrowed_length_is_rejected_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'upstream'
            shutil.copytree(UPSTREAM, target)
            path = target / 'nvport_memory_primitives.h'
            path.write_bytes(path.read_bytes().replace(b'NvLength', b'NvU32'))
            manifest = json.loads((target / 'MEMORY-PROVENANCE.json').read_bytes())
            manifest['interface']['sha256'] = sha256(path.read_bytes())
            (target / 'MEMORY-PROVENANCE.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'narrow memory ABI changed'):
                verify_upstream(target)

    def test_checked_profile_is_rejected_at_compile_time(self) -> None:
        compiler = shutil.which('clang') or shutil.which('cc')
        self.assertIsNotNone(compiler, 'A C compiler is needed for the targeted assertion-profile check.')
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([compiler, '-std=c11', '-DPORT_IS_CHECKED_BUILD=1',
                                     '-c', str(UPSTREAM / 'nvport_memory_primitives.c'),
                                     '-o', str(Path(temporary) / 'checked.o')],
                                    text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('release assertion profile only', result.stderr)


if __name__ == '__main__':
    unittest.main()
