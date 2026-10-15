#!/usr/bin/env python3
"""Verify the pinned complete ResourceServer/NVOC source closure and adaptations."""
from pathlib import Path
import hashlib
import json
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
UPSTREAM = PACKAGE / 'upstream'
TREE = UPSTREAM / 'tree'
PIN = '1a82fbfda8f321b056eb3568850f9316c5e465c5'


def function(text, name, next_name):
    start = text.index('NV_STATUS\n' + name + '\n')
    end = text.index('\nNV_STATUS\n' + next_name, start)
    return start, end


def derive_server():
    source = (TREE / 'src/nvidia/src/libraries/resserv/src/rs_server.c').read_text()
    a = source.index('NV_STATUS\nserverConstruct\n')
    b = source.index('\n\nNV_STATUS\nserverDestruct', a)
    constructor = (UPSTREAM / 'adapted/server_construct.c.inc').read_text().rstrip('\n')
    source = source[:a] + constructor + source[b:]
    policy_source = (TREE / 'src/nvidia/src/kernel/rmapi/sharing.c').read_text()
    a = policy_source.index('NV_STATUS\nserverInitGlobalSharePolicies\n')
    b = policy_source.index('\nstatic OBJGPU *', a)
    policy = policy_source[a:b].strip()
    empty = 'NV_STATUS\nserverInitGlobalSharePolicies\n(\n    RsServer *pServer\n)\n{\n    return NV_OK;\n}'
    assert source.count(empty) == 1
    source = source.replace(empty, policy)
    a, b = function(source, 'serverFreeResourceTree', 'serverControl')
    body = source[a:b]
    body = body.replace('LOCK_ACCESS_TYPE    topLockAccess;',
                        'LOCK_ACCESS_TYPE    topLockAccess = LOCK_ACCESS_WRITE;')
    body = body.replace('LOCK_ACCESS_TYPE    firstTopLockAccess;',
                        'LOCK_ACCESS_TYPE    firstTopLockAccess = LOCK_ACCESS_WRITE;')
    before = '            status = serverFreeResourceTreeLockAndFindResource(pServer, pParams, topLockAccess,'
    assert body.count(before) == 1
    body = body.replace(before, '            firstTopLockAccess = topLockAccess;\n' + before)
    before = 'serverTopLock_Epilogue(pServer, topLockAccess, pLockInfo, &releaseFlags);'
    assert body.count(before) == 2
    last = body.rindex(before)
    body = body[:last] + body[last:].replace(before,
        'serverTopLock_Epilogue(pServer, firstTopLockAccess, pLockInfo, &releaseFlags);', 1)
    return source[:a] + body + source[b:]


class Provenance(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((UPSTREAM / 'PROVENANCE.json').read_text())
        self.build = json.loads((UPSTREAM / 'BUILD.json').read_text())

    def test_commit_and_release(self):
        self.assertEqual(self.manifest['commit'], PIN)
        self.assertEqual(self.manifest['release'], '615.78.08')
        self.assertEqual(self.manifest['repository'], 'https://github.com/NVIDIA/open-gpu-kernel-modules')

    def test_exact_reference_files(self):
        files = self.manifest['files']
        self.assertEqual(len(files), 90)
        self.assertEqual(len({x['path'] for x in files}), len(files))
        for entry in files:
            with self.subTest(path=entry['path']):
                data = (TREE / entry['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
                blob = b'blob ' + str(len(data)).encode() + b'\0' + data
                self.assertEqual(hashlib.sha1(blob).hexdigest(), entry['git_blob'])

    def test_no_unrecorded_reference(self):
        recorded = {entry['path'] for entry in self.manifest['files']}
        actual = {str(path.relative_to(TREE)) for path in TREE.rglob('*') if path.is_file()}
        self.assertEqual(actual, recorded)

    def test_complete_source_closure(self):
        self.assertEqual(len(self.build['sources']), 13)
        self.assertEqual(len(set(self.build['sources'])), 13)
        self.assertEqual(len(self.build['shared_sources']), 1)
        for path in self.build['sources']:
            self.assertTrue((TREE / path).is_file())
        source = self.build['shared_sources'][0]
        self.assertEqual((TREE / source['upstream']).read_bytes(),
                         (PACKAGE / source['compiled']).read_bytes())

    def test_exact_derived_server(self):
        self.assertEqual(derive_server(), (UPSTREAM / 'adapted/rs_server.c').read_text())

    def test_exact_typed_iterator_overlay(self):
        original = (TREE / 'src/nvidia/inc/libraries/containers/type_safety.h').read_text()
        a = original.index('//\n// The dummy contId prevents compilers')
        b = original.index('\n#else\n', a)
        replacement = (UPSTREAM / 'adapted/iterator_macros.h.inc').read_text()
        derived = original[:a] + replacement + original[b:]
        self.assertEqual(derived,
            (UPSTREAM / 'adapted/include/containers/type_safety.h').read_text())
        self.assertEqual(self.build['adapter_include_dirs'], ['upstream/adapted/include'])
        self.assertEqual(self.build['header_overrides'], {
            'containers/type_safety.h': 'upstream/adapted/include/containers/type_safety.h'})
        self.assertNotIn('contId(pFunc)', replacement)
        self.assertIn('s540_typed_iterator.iter = (pFunc)', replacement)
        self.assertEqual(self.manifest['adaptations'][2]['macros'],
                         ['CONT_ITER_RANGE', 'CONT_ITER_RANGE_INDEX'])

    def test_exact_policy_extraction(self):
        original = (TREE / 'src/nvidia/src/kernel/rmapi/sharing.c').read_text()
        a = original.index('NV_STATUS\nserverInitGlobalSharePolicies\n')
        b = original.index('\nstatic OBJGPU *', a)
        extracted = original[:original.index('#include')] + '#include "resserv/rs_server.h"\n\n' + original[a:b]
        self.assertEqual(extracted, (UPSTREAM / 'adapted/share_policies.c').read_text())
        self.assertNotIn('upstream/adapted/share_policies.c', self.build['adapter_c_sources'])

    def test_profile_and_production_binding(self):
        expected = {'RS_STANDALONE': 1, 'RS_COMPATABILITY_MODE': 1,
                    'RS_PROVIDES_API_STATE': 0, 'LOCK_VAL_ENABLED': 0,
                    'PORT_IS_KERNEL_BUILD': 1, 'PORT_IS_CHECKED_BUILD': 0, 'NV_UNIX': 1}
        self.assertEqual(self.manifest['profile'], expected)
        for key, value in expected.items():
            self.assertIn(key + '=' + str(value), self.build['defines'])
        self.assertEqual(self.build['source_substitutions'], {
            'src/nvidia/src/libraries/resserv/src/rs_server.c': 'upstream/adapted/rs_server.c'})
        self.assertIn('-ffreestanding', self.build['c_flags'])
        for path in self.build['adapter_c_sources'] + self.build['adapter_cpp_sources']:
            self.assertTrue((PACKAGE / path).is_file())

    def test_shared_list_header_abi(self):
        self.assertEqual((TREE / 'src/nvidia/inc/libraries/containers/list.h').read_bytes(),
            (PACKAGE.parent / 'nvidia-nvport-runtime/upstream/consumer/include/containers/list.h').read_bytes())
        self.assertIn('_Static_assert(sizeof(PORT_MEM_ALLOCATOR) == 40',
                      (PACKAGE / 'src/S540NvidiaResourceExercise.c').read_text())

    def test_explicit_adaptation_inventory(self):
        adaptation = self.manifest['adaptations'][0]
        self.assertEqual(adaptation['function'], 'serverConstruct')
        self.assertEqual(adaptation['additional_replacement']['function'], 'serverInitGlobalSharePolicies')
        self.assertEqual(adaptation['failure_lock_fix']['function'], 'serverFreeResourceTree')
        self.assertFalse(self.manifest['adaptations'][1]['compiled'])


if __name__ == '__main__':
    unittest.main()
