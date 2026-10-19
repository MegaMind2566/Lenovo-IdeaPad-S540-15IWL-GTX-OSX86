#!/usr/bin/env python3
"""Compose only isolated getters; validate every frozen V3 source file first."""
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

def sha(data): return hashlib.sha256(data).hexdigest()
def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('Source symlinks are not admitted')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                'sha256': sha(path.read_bytes()),
                'mode': '100755' if path.stat().st_mode & 0o111 else '100644'}
    return result

def body(text, name, result):
    first, last = function_span(text, name)
    return result + '\n' + text[first:last] + '\n'

def structure(text, name):
    end = text.index('} ' + name + ';') + len('} ' + name + ';')
    first = text.rfind('typedef struct', 0, end)
    if first < 0: raise ValueError('Exact private type missing: ' + name)
    return text[first:end] + '\n'

def verify_bindings(root, expected):
    root = root.resolve(strict=True)
    for relative, digest in expected.items():
        path = root / relative
        if not path.resolve(strict=True).is_relative_to(root) or any(
                parent.is_symlink() for parent in [path, *path.parents]
                if parent != root and parent.is_relative_to(root)):
            raise ValueError('Pinned source symlinks are not admitted: ' + relative)
        if sha(path.read_bytes()) != digest:
            raise ValueError('Pinned source changed: ' + relative)

def validate_output(upstream, v3, output):
    """Refuse source overlap before the standalone preparer writes anything."""
    output = output.resolve()
    if output.exists():
        raise ValueError('Fresh output directory required')
    for tree in [HERE, upstream, v3, v3.parent / 'project-overlay']:
        tree = tree.resolve(strict=True)
        if output.is_relative_to(tree) or tree.is_relative_to(output):
            raise ValueError('Output overlaps source input')
    if output.is_relative_to(REPO) and not output.is_relative_to(REPO / 'build'):
        raise ValueError('Repo output allowed only under build/')
    return output

def verify_inventory(observed, expected):
    if len(observed) != 4005 or sha(json.dumps(observed, sort_keys=True,
            separators=(',', ':')).encode()) != expected:
        raise ValueError('Full immutable V3 source inventory changed')

def prepare(upstream, v3, output):
    upstream = upstream.resolve(strict=True)
    v3 = v3.resolve(strict=True)
    output = validate_output(upstream, v3, output)
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_text())
    observed = inventory(v3)
    verify_inventory(observed,contract['v3_tree_sha256'])
    project=inventory(v3.parent/'project-overlay')
    if len(project)!=contract['v3_project_files'] or sha(json.dumps(project,sort_keys=True,
            separators=(',',':')).encode())!=contract['v3_project_tree_sha256']:
        raise ValueError('Exact V3 project companion changed')
    for group, root in [('original_sources', upstream), ('v3_sources', v3)]:
        verify_bindings(root,contract[group])
    verify_bindings(HERE,contract['candidate_sources'])
    verify_bindings(REPO,contract['project_dependencies'])
    output.mkdir(parents=True)
    proposals = {}
    for relative, addition in [('src/nvidia/src/kernel/core/locks.c', 'original-gpu-query.inc'),
            ('src/nvidia/src/kernel/rmapi/rmapi.c', 'original-api-query.inc')]:
        text = (v3 / relative).read_text() + '\n' + (HERE / addition).read_text()
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        proposals[relative] = sha(text.encode())
    locks = (v3 / 'src/nvidia/src/kernel/core/locks.c').read_text()
    api = (v3 / 'src/nvidia/src/kernel/rmapi/rmapi.c').read_text()
    os = (v3 / 'src/nvidia/arch/nvalloc/unix/src/os.c').read_text()
    constants = '\n'.join(re.findall(r'^static const NvU32 GPU_INST_(?:INVALID|ALLOC_LOCK).*$', locks, re.M))
    extracted = constants + '\n' + structure(locks, 'GPULOCK') + structure(locks, 'GPULOCKINFO')
    extracted += '\nstatic GPULOCKINFO rmGpuLockInfo;\n'
    for name, result in [('_gpuInstLoopHead', 'static inline NvU32'),
            ('_gpuInstLoopNext', 'static inline NvU32'),
            ('_gpuInstLoopShouldContinue', 'static inline NvBool'),
            ('_rmGpuAllocLockIsOwner', 'static NvBool'), ('rmGpuLocksGetOwnedMask', 'NvU32')]:
        extracted += body(locks, name, result)
    extracted += structure(api, 'RMAPI_LOCK') + '\nstatic RMAPI_LOCK g_RmApiLock;\nstatic NvBool g_bResServInit;\n'
    extracted += body(api, 'rmapiLockIsOwner', 'NvBool')
    for name, result in [('osGetCurrentThread', 'NV_STATUS'), ('osAcquireRmSema', 'NV_STATUS'),
            ('osCondAcquireRmSema', 'NV_STATUS'), ('osReleaseRmSema', 'void')]:
        extracted += body(os, name, result)
    extracted += (HERE / 'original-api-query.inc').read_text() + '\n' + (HERE / 'original-gpu-query.inc').read_text()
    (output / 'actual-original-lock-bodies.inc').write_text(extracted)
    report = {'format': 1, 'v3_tree_sha256': contract['v3_tree_sha256'],
        'v3_files_verified': len(observed), 'composed_original_sources': proposals,
        'v3_project_files_verified':len(project),'v3_project_tree_sha256':contract['v3_project_tree_sha256'],
        'complete_original_bodies': 10, 'exact_original_private_types': ['GPULOCK', 'GPULOCKINFO', 'RMAPI_LOCK'],
        'extracted_fixture_sha256': sha(extracted.encode()),
        'source_contract_sha256': sha((HERE / 'SOURCE-CONTRACT.json').read_bytes()),
        'final_image_binding_proved': False, 'original_entry_admission': False}
    (output / 'prepared-source.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report
