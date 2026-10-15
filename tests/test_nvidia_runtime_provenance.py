#!/usr/bin/env python3
"""Audit the selected CPU runtime against independently pinned NVIDIA blobs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'packages/nvidia-nvport-runtime/upstream'
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
PINNED = {
    'reference/string_generic.c': ('src/nvidia/src/libraries/nvport/string/string_generic.c', '4ec73acc292677af93ffa4626fbdc6208fb51740'),
    'reference/crypto_random_xorshift.c': ('src/nvidia/src/libraries/nvport/crypto/crypto_random_xorshift.c', 'f2d34cc81b68300bfc7c588cfa72b4c235a627dc'),
    'reference/core.c': ('src/nvidia/src/libraries/nvport/core/core.c', '8a4f0d371be2d9568c786f07899683a981fd5b51'),
    'reference/string.h': ('src/nvidia/inc/libraries/nvport/string.h', '32ab84eef9dff9cb99a5f8a2a0c4b1d0bb7abaf2'),
    'reference/crypto.h': ('src/nvidia/inc/libraries/nvport/crypto.h', 'adda6c9c7756500787f2beaff674fcc4b7eaa147'),
    'reference/core.h': ('src/nvidia/inc/libraries/nvport/core.h', '26f8ec10f15e0bd4a53c3e899dcde9195b4de0ef'),
    'reference/util.h': ('src/nvidia/inc/libraries/nvport/util.h', '177e5d03b9ff8c4e76aeb02cf83b44983e1a43f5'),
    'reference/util_generic.h': ('src/nvidia/inc/libraries/nvport/inline/util_generic.h', 'c5e6e371e3805bb4e5c24838513339b423fda9b0'),
    'reference/util_gcc_clang.h': ('src/nvidia/inc/libraries/nvport/inline/util_gcc_clang.h', 'be58d89a333b139dd44bd7e94c8dc668cb29cfcb'),
    '../../nvidia-nvport-lifecycle/upstream/reference/safe_generic.h': ('src/nvidia/inc/libraries/nvport/inline/safe_generic.h', 'e701c2cecde7816760291c78b3fea5507acc82a5'),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def function(text: str, name: str) -> str:
    """Find a definition, including single-line and multiline signatures."""
    for match in re.finditer(r'\b' + re.escape(name) + r'\s*\(', text):
        index = text.index('(', match.start()) + 1
        depth = 1
        while depth:
            if text[index] == '(':
                depth += 1
            elif text[index] == ')':
                depth -= 1
            index += 1
        brace = index
        while text[brace].isspace():
            brace += 1
        if text[brace] != '{':
            continue
        start = text.rfind('\n', 0, match.start()) + 1
        if not text[start:match.start()].strip():
            previous = text.rfind('\n', 0, start - 1) + 1
            if text[previous:start].strip():
                start = previous
        index, depth, state = brace, 0, 'normal'
        while index < len(text):
            char, pair = text[index], text[index:index + 2]
            if state == 'normal':
                if pair == '//':
                    state, index = 'line', index + 2
                    continue
                if pair == '/*':
                    state, index = 'comment', index + 2
                    continue
                if char == '"':
                    state = 'string'
                elif char == "'":
                    state = 'char'
                elif char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:index + 1] + '\n'
            elif state == 'line':
                if char == '\n':
                    state = 'normal'
            elif state == 'comment':
                if pair == '*/':
                    state, index = 'normal', index + 2
                    continue
            elif state in ('string', 'char'):
                if char == '\\':
                    index += 2
                    continue
                if (state == 'string' and char == '"') or (state == 'char' and char == "'"):
                    state = 'normal'
            index += 1
    raise ValueError('Missing function definition: ' + name)


def macro(text: str, name: str) -> str:
    lines = text.splitlines(True)
    start = next(index for index, line in enumerate(lines)
                 if re.match(r'#define ' + re.escape(name) + r'(?:\(|\s)', line))
    end = start + 1
    while lines[end - 1].rstrip().endswith('\\'):
        end += 1
    return ''.join(lines[start:end])


class NvidiaRuntimeProvenance(unittest.TestCase):
    def setUp(self) -> None:
        self.report = json.loads((UPSTREAM / 'PROVENANCE.json').read_text())

    def test_independently_pinned_source_inputs(self) -> None:
        self.assertEqual(self.report['commit'], COMMIT)
        self.assertEqual(self.report['release'], '615.78.08')
        self.assertEqual({item['path'] for item in self.report['upstream_files']}, set(PINNED))
        for item in self.report['upstream_files']:
            path = UPSTREAM / item['path']
            self.assertFalse(path.is_symlink())
            data = path.read_bytes()
            self.assertEqual((item['source_path'], item['git_blob_sha1']), PINNED[item['path']])
            git_blob = b'blob ' + str(len(data)).encode() + b'\0' + data
            self.assertEqual(hashlib.sha1(git_blob).hexdigest(), item['git_blob_sha1'])
            self.assertEqual(sha256(data), item['sha256'])
            self.assertEqual(len(data), item['bytes'])
            self.assertFalse(item['modified'])
            self.assertIn(b'Permission is hereby granted', data)

    def test_all_selected_original_bodies_are_unchanged(self) -> None:
        count = 0
        for unit in self.report['adapted_translation_units']:
            text = (UPSTREAM / unit['path']).read_text()
            self.assertEqual(sha256(text.encode()), unit['sha256'])
            self.assertFalse(unit['complete_upstream_translation_unit'])
            for item in unit['functions']:
                original = function((UPSTREAM / item['source_reference']).read_text(), item['source_function'])
                compiled = function(text, item['compiled_function'])
                self.assertEqual(original, compiled)
                self.assertEqual(sha256(original.encode()), item['source_body_sha256'])
                self.assertEqual(sha256(compiled.encode()), item['compiled_body_sha256'])
                self.assertEqual(item['changes'], [])
                count += 1
        self.assertEqual(count, 38)
        self.assertEqual(self.report['unchanged_function_bodies'], 38)

    def test_unsigned_arithmetic_exact_macro_closure(self) -> None:
        profile = self.report['unsigned_arithmetic']
        text = (UPSTREAM / profile['path']).read_text()
        source = (UPSTREAM / profile['source_reference']).read_text()
        self.assertEqual(sha256(text.encode()), profile['sha256'])
        self.assertFalse(profile['signed_arithmetic'])
        self.assertFalse(profile['casts'])
        for item in profile['macros']:
            self.assertEqual(macro(text, item['name']), macro(source, item['name']))
            self.assertEqual(sha256(macro(text, item['name']).encode()), item['sha256'])
        calls = re.findall(r'^PORT_SAFE_DEFINE_MATH_FUNC\((\w+),\s*(U?),\s*(\w+)\)$', text, re.M)
        expected = {(op, sign, size) for size, sign in [('32', 'U'), ('64', 'U'), ('UPtr', ''), ('Length', '')]
                    for op in ('Add', 'Sub', 'Mul', 'Div') if (size, op) != ('Length', 'Add')}
        self.assertEqual(set(calls), expected)
        self.assertEqual(len(calls), 15)
        self.assertEqual(profile['reused_functions'], ['portSafeAddLength'])

    def test_checked_core_failure_and_cleanup_order(self) -> None:
        profile = self.report['checked_core']
        text = (UPSTREAM / profile['path']).read_text()
        self.assertEqual(sha256(text.encode()), profile['sha256'])
        self.assertFalse(profile['complete_upstream_core'])
        self.assertTrue(profile['failure_atomic'])
        init = function(text, 's540NvportRuntimeInitialize')
        self.assertLess(init.index('!s540NvportLifecycleContextAllowed()'), init.index('status = s540NvportMemoryInitialize()'))
        self.assertLess(init.index('status = s540NvportMemoryInitialize()'), init.index('if (status != NV_OK)'))
        self.assertLess(init.index('if (status != NV_OK)'), init.index('portCryptoInitialize()'))
        self.assertLess(init.index('portCryptoInitialize()'), init.index('if (portCryptoDefaultGenerator == NULL)'))
        self.assertLess(init.index('portMemShutdown(NV_TRUE)'), init.index('runtimeInitialized = NV_TRUE'))
        self.assertIn('return NV_ERR_NO_MEMORY;', init)
        shutdown = function(text, 's540NvportRuntimeShutdown')
        refusal = shutdown.index('active.numAllocations != defaultAllocations')
        self.assertLess(refusal, shutdown.index('portCryptoShutdown()'))
        self.assertLess(shutdown.index('s540NvportMemoryAllocatorCount() != baselineAllocators'), shutdown.index('portCryptoShutdown()'))
        self.assertLess(shutdown.index('portCryptoShutdown()'), shutdown.index('portMemShutdown(NV_TRUE)'))
        self.assertIn('return s540NvportRuntimeIsCold() ? NV_OK : NV_ERR_INVALID_STATE;', shutdown)
        self.assertNotRegex(text, r'\bportInitialize\s*\(')
        self.assertNotIn('portSyncInitialize(', text)
        self.assertNotIn('portCpuInitialize(', text)

    def test_excluded_unsafe_or_unimplemented_surface(self) -> None:
        header = (UPSTREAM / 'nvport_runtime.h').read_text()
        strings = (UPSTREAM / 'nvport_runtime_strings.c').read_text()
        self.assertIn('#define NVPORT_STRING_DONT_DEFINE_portStringBufferToHexGroups 1', strings)
        self.assertNotIn('portStringBufferToHexGroups(', header)
        for unsupported in ('portCryptoExTrueRandomGetU32(', 'portCryptoExTrueRandomGetU64(', 'portCryptoHashMD5(', 'portUtilCheckAlignment(', 'portUtilIsPowerOfTwo(', 'portUtilCheckOverlap(', 'portUtilExReadTimestampCounter('):
            self.assertNotIn(unsupported, header)
        utilities = (UPSTREAM / 'nvport_runtime_utilities.h').read_text()
        self.assertNotIn('__asm__', utilities)
        self.assertNotIn('portUtilIsPowerOfTwo(', utilities)
        self.assertFalse(self.report['profile']['true_entropy'])
        self.assertFalse(self.report['profile']['security_cryptography'])
        self.assertFalse(self.report['profile']['full_nvport'])
        self.assertFalse(self.report['profile']['full_rm'])
        self.assertFalse(self.report['profile']['gpu_access'])

    def test_explicit_profile_header_and_contract(self) -> None:
        for item in self.report['profile_headers']:
            self.assertEqual(sha256((UPSTREAM / item['path']).read_bytes()), item['sha256'])
        text = (UPSTREAM / 'nvport_runtime.h').read_text()
        self.assertIn('NV_U64_MAX / 2', text)
        self.assertIn('NV_U64_MAX - 7', text)
        self.assertIn('leaving it NULL', text)
        self.assertIn('not security cryptography', text)
        self.assertIn('portCryptoExTrueRandomGetU64_SUPPORTED 0', text)
        self.assertEqual(self.report['profile']['strings_public_functions'], 11)
        self.assertEqual(self.report['profile']['prng_public_functions'], 11)
        self.assertEqual(self.report['profile']['inline_utility_functions'], 12)


if __name__ == '__main__':
    unittest.main()
