#!/usr/bin/env python3
"""Check exact pinned NVIDIA allocation/mutex bodies and their narrow ABI."""
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
UPSTREAM = ROOT / 'packages/nvidia-caller-integration/upstream'
ADAPTER = '../../nvidia-os-adapter/upstream/'
COMMIT = '1a82fbfda8f321b056eb3568850f9316c5e465c5'
PINNED = {
    ADAPTER + 'include/nvtypes.h': ('src/common/sdk/nvidia/inc/nvtypes.h', 'cb6d906a34cf6ace3d852657cf8dde4a587d7721'),
    ADAPTER + 'include/cpuopsys.h': ('src/common/sdk/nvidia/inc/cpuopsys.h', '6467b396a696a47fa71d4ad41e32d27f344fcdce'),
    ADAPTER + 'include/nvstatus.h': ('src/common/sdk/nvidia/inc/nvstatus.h', '4f5284db2b1e6af1c2c0c85bc39dfc14daccc9fd'),
    ADAPTER + 'include/nvstatuscodes.h': ('src/common/sdk/nvidia/inc/nvstatuscodes.h', '430eed77a03f2f15bf058d3c49931a9f89ace08e'),
    ADAPTER + 'include/nv-kernel-interface-api.h': ('kernel-open/common/inc/nv-kernel-interface-api.h', '183f9b4312eb0913c0a0a97e4db1f62a50b442c5'),
    ADAPTER + 'reference/os-interface.h': ('src/nvidia/arch/nvalloc/unix/include/os-interface.h', '03de89a28a2611bca2fb2a3d85c7f617a681a20a'),
    ADAPTER + 'reference/memory_unix_kernel_os.c': ('src/nvidia/src/libraries/nvport/memory/memory_unix_kernel_os.c', '06e5504a6556d2107d41cf614063737a92ad57c0'),
    ADAPTER + 'reference/memory.h': ('src/nvidia/inc/libraries/nvport/memory.h', '595eafee880dccd54ca2f382fb77afc918793e1d'),
    ADAPTER + 'reference/debug.h': ('src/nvidia/inc/libraries/nvport/debug.h', 'c2929200e628022149e6c2fb1581469946ffe05a'),
    'reference/memory_tracking.h': ('src/nvidia/inc/libraries/nvport/inline/memory_tracking.h', '37f11e95b6d6d4a02eefe1d66a0567a6baaed070'),
    'reference/sync_unix_kernel_os.c': ('src/nvidia/src/libraries/nvport/sync/sync_unix_kernel_os.c', '9a545779dda38f261977a0da6b130ab62cf67f41'),
    'reference/sync_unix_kernel_os_def.h': ('src/nvidia/src/libraries/nvport/sync/inc/sync_unix_kernel_os_def.h', 'b12c4ad3506d39de835d3bce5e45bb8c8eeafe70'),
    'reference/sync.h': ('src/nvidia/inc/libraries/nvport/sync.h', '29e472dedf677501e11c22cb043431750c9f8f30'),
}
ALLOCATORS = ['_portMemAllocPagedUntracked', '_portMemAllocNonPagedUntracked', '_portMemFreeUntracked']
MUTEX = ['portSyncMutexInitialize', 'portSyncMutexDestroy', 'portSyncMutexAcquire',
         'portSyncMutexAcquireConditional', 'portSyncMutexRelease']
ALLOC_DECLS = {
    'os_alloc_mem': ('NV_STATUS', ['void **', 'NvU64']),
    'os_free_mem': ('void', ['void *']),
    '_portMemAllocPagedUntracked': ('void *', ['NvLength']),
    '_portMemAllocNonPagedUntracked': ('void *', ['NvLength']),
    '_portMemFreeUntracked': ('void', ['void *']),
}
MUTEX_DECLS = {
    'os_alloc_mutex': ('NV_STATUS', ['void **']),
    'os_free_mutex': ('void', ['void *']),
    'os_acquire_mutex': ('NV_STATUS', ['void *']),
    'os_cond_acquire_mutex': ('NV_STATUS', ['void *']),
    'os_release_mutex': ('void', ['void *']),
    'portSyncMutexInitialize': ('NV_STATUS', ['PORT_MUTEX *']),
    'portSyncMutexDestroy': ('void', ['PORT_MUTEX *']),
    'portSyncMutexAcquire': ('void', ['PORT_MUTEX *']),
    'portSyncMutexAcquireConditional': ('NvBool', ['PORT_MUTEX *']),
    'portSyncMutexRelease': ('void', ['PORT_MUTEX *']),
}
SCOPE = {'allocation': 'three untracked caller functions only', 'tracked_allocator': False,
         'global_allocator': False, 'user_copy': False, 'mmio': False, 'dma': False,
         'resource_manager': False, 'gpu_initialization': False,
         'mutex': 'five caller-owned mutex operations only', 'mutex_create': False,
         'spinlock': False, 'semaphore': False, 'rwlock': False}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def regular_bytes(root: Path, name: str) -> bytes:
    target = root / name
    require(target.is_file() and not target.is_symlink(), 'Not a regular input: ' + name)
    return target.read_bytes()


def strip_comments(data: bytes) -> str:
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', data.decode(), flags=re.S)


def compact(text: str) -> str:
    return re.sub(r'\s+', '', text)


def declaration_shape(data: bytes, name: str) -> tuple[str, list[str]]:
    expression = (r'\b(void\s*\*|void|NV_STATUS|NvBool)\s*'
                  r'(?:(?:NV_API_CALL|NV_FORCERESULTCHECK)\s+)*' + re.escape(name)
                  + r'\s*\(([^;{}]*)\)\s*;')
    matches = re.findall(expression, strip_comments(data))
    require(len(matches) == 1, 'Missing or ambiguous declaration: ' + name)
    result, args = matches[0]
    shapes = []
    for argument in args.split(','):
        match = re.fullmatch(r'(void\s*\*\s*\*|void\s*\*|PORT_MUTEX\s*\*|NvU64|NvLength)\s*(?:[A-Za-z_]\w*)?', argument.strip())
        require(match is not None, 'Unexpected argument type: ' + name)
        shapes.append(compact(match.group(1)))
    return compact(result), shapes


def verify_upstream(root: Path = UPSTREAM) -> dict:
    manifest = json.loads(regular_bytes(root, 'PROVENANCE.json'))
    require(manifest.get('format') == 1 and manifest.get('repository') == 'NVIDIA/open-gpu-kernel-modules'
            and manifest.get('release') == '615.78.08' and manifest.get('commit') == COMMIT,
            'Unexpected caller provenance identity.')
    entries = manifest.get('upstream_files', [])
    require(len(entries) == len(PINNED) and {entry.get('path') for entry in entries} == set(PINNED),
            'Unexpected caller input list.')
    for entry in entries:
        name = entry['path']
        source, blob = PINNED[name]
        data = regular_bytes(root, name)
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        require(actual == blob, 'A pinned caller reference was modified: ' + name)
        require(entry.get('source_path') == source and entry.get('git_blob_sha1') == blob
                and entry.get('sha256') == sha256(data) and entry.get('bytes') == len(data)
                and entry.get('modified') is False and entry.get('license') == 'MIT',
                'A caller reference identity changed: ' + name)
        require(b'SPDX-License-Identifier: MIT' in data, 'Missing original MIT notice.')

    specifications = [
        ('adapted_caller', 'nvport_allocator_callers.c', ADAPTER + 'reference/memory_unix_kernel_os.c',
         b'void *\n_portMemAllocPagedUntracked\n', b'void *\nportMemCopy\n', [43, 78], ALLOCATORS,
         'upstream-release-only', '6d69e7353b615f85469d7d64ba4f7d2b1e596ee51d916a4df43f184496f29273'),
        ('adapted_mutex_caller', 'nvport_mutex_callers.c', 'reference/sync_unix_kernel_os.c',
         b'NV_STATUS\nportSyncMutexInitialize\n', b'NV_STATUS\nportSyncSemaphoreInitialize\n', [95, 158], MUTEX,
         'upstream-release-checked-assertions-with-fatal-mandatory-assertions',
         'eee3e9ef4f52fffd4c799c87bb4eea4488a43a18a76baf58559fca6dbd50e745'),
    ]
    for key, path, reference, marker, end_marker, lines, names, profile, prefix_hash in specifications:
        source = regular_bytes(root, reference)
        body = source[source.index(marker):source.index(end_marker, source.index(marker))]
        caller = regular_bytes(root, path)
        adapted = manifest.get(key, {})
        require(adapted.get('path') == path and adapted.get('source_reference') == reference
                and adapted.get('source_lines') == lines and adapted.get('functions') == names
                and adapted.get('changes') == {} and adapted.get('complete_upstream_translation_unit') is False
                and adapted.get('assertion_profile') == profile and adapted.get('checked_profile_supported') is False,
                'The caller adaptation is mislabeled: ' + path)
        require(adapted.get('sha256') == sha256(caller) and adapted.get('source_body_sha256') == sha256(body),
                'A caller adaptation checksum changed: ' + path)
        require(caller[caller.index(marker):] == body, 'An exact caller body contains an unrecorded change: ' + path)
        require(sha256(caller[:caller.index(marker)]) == prefix_hash,
                'The license, scope or assertion profile changed: ' + path)
        require(re.findall(rb'^#include\s+(.+)$', caller, re.M) == [b'"' + path.replace('.c', '.h').encode() + b'"'],
                'Unexpected caller include closure: ' + path)

    debug = regular_bytes(root, ADAPTER + 'reference/debug.h')
    require(b'#else // PORT_IS_CHECKED_BUILD\n#define PORT_BREAKPOINT_CHECKED()\n#define PORT_ASSERT_CHECKED(x)\n#endif // PORT_IS_CHECKED_BUILD' in debug,
            'The upstream release assertion contract changed.')
    require(manifest['adapted_mutex_caller'].get('tracked_allocator_free') == 'fatal unsupported contract',
            'The mutex allocator boundary was mislabeled.')
    os_reference = regular_bytes(root, ADAPTER + 'reference/os-interface.h')
    for key, header_name, declarations, caller_reference in [
        ('interface', 'nvport_allocator_callers.h', ALLOC_DECLS, 'reference/memory_tracking.h'),
        ('mutex_interface', 'nvport_mutex_callers.h', MUTEX_DECLS, 'reference/sync.h'),
    ]:
        header = regular_bytes(root, header_name)
        interface = manifest.get(key, {})
        require(interface.get('path') == header_name and interface.get('sha256') == sha256(header)
                and interface.get('declarations_reference') == ADAPTER + 'reference/os-interface.h'
                and interface.get('caller_declarations_reference') == caller_reference
                and interface.get('hooks') == [name for name in declarations if name.startswith('os_')],
                'The narrow caller interface identity changed: ' + header_name)
        reference = regular_bytes(root, caller_reference)
        for name, (result, parameters) in declarations.items():
            expected = compact(result), [compact(arg) for arg in parameters]
            require(declaration_shape(header, name) == expected, 'The narrow caller ABI changed: ' + name)
            require(declaration_shape(os_reference if name.startswith('os_') else reference, name) == expected,
                    'The original caller ABI changed: ' + name)
            if name.startswith('os_'):
                require(re.search(r'\bNV_API_CALL\s+' + re.escape(name) + r'\s*\(', strip_comments(header)) is not None,
                        'The OS calling convention was removed: ' + name)
        includes = re.findall(rb'^#include\s+(.+)$', header, re.M)
        expected_includes = [b'"' + (ADAPTER + 'include/' + name).encode() + b'"'
                             for name in ['nvtypes.h', 'nvstatus.h', 'nv-kernel-interface-api.h']] + [b'<stddef.h>']
        require(includes == expected_includes and b'extern "C" {' in header,
                'The caller header lost shared NVIDIA types or C linkage.')
        require(not re.search(r'^\s*#\s*define\s+(?:os_|_port|portSync|NvLength|NvU64|NV_API_CALL)', header.decode(), re.M),
                'The caller ABI must not be rewritten by a macro.')
    require(manifest['interface'].get('length_abi') == {'NvLength_bits': 64, 'os_hook_length_bits': 64},
            'The caller allocation length ABI changed.')
    mutex_header = regular_bytes(root, 'nvport_mutex_callers.h')
    structure_reference = regular_bytes(root, 'reference/sync_unix_kernel_os_def.h')
    for data in [mutex_header, structure_reference]:
        fields = re.findall(r'struct\s+PORT_MUTEX\s*\{([^}]*)\}\s*;', strip_comments(data))
        require(len(fields) == 1 and compact(fields[0]) == 'void*mutex;PORT_MEM_ALLOCATOR*pAllocator;',
                'The exact upstream mutex structure changed.')
    require(manifest['mutex_interface'].get('structure_reference') == 'reference/sync_unix_kernel_os_def.h'
            and re.search(r'void\s+__attribute__\s*\(\(noreturn\)\)\s+s540NvidiaCallerAssertionFailed\s*\(\s*const char \*,\s*const char \*,\s*int\s*\)\s*;', strip_comments(mutex_header)) is not None,
            'The mandatory assertion hook lost its non-returning ABI.')
    require(manifest.get('scope') == SCOPE, 'The caller integration scope changed.')
    return {'commit': COMMIT, 'release': manifest['release'], 'unmodified_inputs': len(PINNED),
            'adapted_allocator_functions': len(ALLOCATORS), 'adapted_mutex_functions': len(MUTEX),
            'complete_upstream_memory_module': False, 'complete_upstream_sync_module': False,
            'assertion_profile': 'release-only with fatal mandatory assertions', 'tracked_allocator': False,
            'allocator_caller_sha256': sha256(regular_bytes(root, 'nvport_allocator_callers.c')),
            'mutex_caller_sha256': sha256(regular_bytes(root, 'nvport_mutex_callers.c'))}


class CallerProvenanceTests(unittest.TestCase):
    def copy_inputs(self, temporary: str) -> Path:
        target = Path(temporary) / 'packages/nvidia-caller-integration/upstream'
        shutil.copytree(UPSTREAM, target)
        shutil.copytree(UPSTREAM / ADAPTER, target / ADAPTER)
        return target

    def test_pinned_callers_and_narrow_abi(self) -> None:
        result = verify_upstream()
        self.assertEqual(result['adapted_allocator_functions'], 3)
        self.assertEqual(result['adapted_mutex_functions'], 5)

    def test_reference_change_rejected_even_with_updated_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_inputs(temporary)
            path = root / 'reference/memory_tracking.h'
            path.write_bytes(path.read_bytes() + b'\n')
            manifest = json.loads((root / 'PROVENANCE.json').read_bytes())
            for entry in manifest['upstream_files']:
                if entry['path'] == 'reference/memory_tracking.h':
                    data = path.read_bytes()
                    entry.update(sha256=sha256(data), bytes=len(data), git_blob_sha1=hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest())
            (root / 'PROVENANCE.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'pinned caller reference was modified'):
                verify_upstream(root)

    def test_body_change_rejected_even_with_updated_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_inputs(temporary)
            path = root / 'nvport_allocator_callers.c'
            path.write_bytes(path.read_bytes().replace(b'if (lengthBytes > 0)', b'if (lengthBytes > 1)'))
            manifest = json.loads((root / 'PROVENANCE.json').read_bytes())
            manifest['adapted_caller']['sha256'] = sha256(path.read_bytes())
            (root / 'PROVENANCE.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'exact caller body contains an unrecorded change'):
                verify_upstream(root)

    def test_mandatory_assertion_removal_rejected_even_with_updated_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_inputs(temporary)
            path = root / 'nvport_mutex_callers.c'
            path.write_bytes(path.read_bytes().replace(b'if (!(condition))', b'if (0)'))
            manifest = json.loads((root / 'PROVENANCE.json').read_bytes())
            manifest['adapted_mutex_caller']['sha256'] = sha256(path.read_bytes())
            (root / 'PROVENANCE.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'assertion profile changed'):
                verify_upstream(root)

    def test_narrowed_length_rejected_even_with_updated_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_inputs(temporary)
            path = root / 'nvport_allocator_callers.h'
            path.write_bytes(path.read_bytes().replace(b'NvLength', b'NvU32'))
            manifest = json.loads((root / 'PROVENANCE.json').read_bytes())
            manifest['interface']['sha256'] = sha256(path.read_bytes())
            (root / 'PROVENANCE.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Unexpected argument type|narrow caller ABI changed'):
                verify_upstream(root)

    def test_changed_mutex_structure_rejected_even_with_updated_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_inputs(temporary)
            path = root / 'nvport_mutex_callers.h'
            path.write_bytes(path.read_bytes().replace(b'void *mutex;', b'void *mutex; void *extra;'))
            manifest = json.loads((root / 'PROVENANCE.json').read_bytes())
            manifest['mutex_interface']['sha256'] = sha256(path.read_bytes())
            (root / 'PROVENANCE.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'mutex structure changed'):
                verify_upstream(root)

    def test_checked_profile_rejected_at_compile_time(self) -> None:
        compiler = shutil.which('clang') or shutil.which('cc')
        self.assertIsNotNone(compiler, 'A C compiler is required for the targeted profile check.')
        with tempfile.TemporaryDirectory() as temporary:
            for name in ['nvport_allocator_callers.c', 'nvport_mutex_callers.c']:
                result = subprocess.run([compiler, '-std=c11', '-DPORT_IS_CHECKED_BUILD=1', '-c',
                                         str(UPSTREAM / name), '-o', str(Path(temporary) / 'checked.o')],
                                        text=True, capture_output=True, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('release assertion profile only', result.stderr)


if __name__ == '__main__':
    unittest.main()
