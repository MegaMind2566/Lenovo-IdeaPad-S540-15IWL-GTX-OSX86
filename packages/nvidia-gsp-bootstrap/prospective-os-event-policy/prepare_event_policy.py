#!/usr/bin/env python3
"""Isolated OS-event feature guards on the exact frozen V3 source tree."""
import difflib
import hashlib
import json
from pathlib import Path
import re

V3_TREE = 'fa8498c3958a559a3466ef6dd4e541bfcea9f55d8809d0a422c784cacd703029'
SOURCES = {
    'src/nvidia/src/kernel/rmapi/event_api.c': '3b6eafb223337f534e22afba9adabd4332beda1d868a79fc403061b03720b922',
    'src/nvidia/src/kernel/rmapi/event_buffer.c': '7e0134eea585feace5fcbe0912ea849f5ffd15c965291501db2ef2d4a17c512a',
    'src/nvidia/src/kernel/gpu/mem_mgr/sem_surf.c': '3734a2566643a186b3b497e2c63532a1d3ec73dfea63165ef3421046130fd463',
}
FUNCTIONS = {
    'eventapiConstruct_IMPL': next(iter(SOURCES)),
    'eventbufferConstruct_IMPL': list(SOURCES)[1],
    'semsurfCtrlCmdRegisterWaiter_IMPL': list(SOURCES)[2],
    'semsurfCtrlCmdUnregisterWaiter_IMPL': list(SOURCES)[2],
}
SEAL = ('/* Explicit selected backend: OS event handles are not registered. */\n'
        '#if !defined(S540_NVIDIA_NO_OS_EVENT_BACKEND) || S540_NVIDIA_NO_OS_EVENT_BACKEND != 1\n'
        '#error "This isolated profile requires explicit S540_NVIDIA_NO_OS_EVENT_BACKEND=1"\n'
        '#endif\n\n')

def sha(data): return hashlib.sha256(data).hexdigest()
def function(text, name):
    match = re.search(r'^(?:static )?NV_STATUS\s+' + name + r'\s*\(', text, re.M)
    if match is None: raise ValueError('Missing original function: ' + name)
    opening = text.index('{', match.end()); depth = 1
    token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for item in token.finditer(text, opening + 1):
        depth += (item[0] == '{') - (item[0] == '}')
        if depth == 0: return match.start(), item.end(), text[match.start():item.end()]
    raise ValueError('Unclosed original function: ' + name)

def replace_one(text, old, new):
    if text.count(old) != 1: raise ValueError('Original guard anchor changed: ' + old[:80])
    return text.replace(old, new, 1)

def prepare(v3_source: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for path in sorted(v3_source.rglob('*')):
        if path.is_symlink(): raise ValueError('Source symlink refused')
        if path.is_file():
            files[path.relative_to(v3_source).as_posix()] = {'sha256': sha(path.read_bytes()),
                'mode': '100755' if path.stat().st_mode & 0o111 else '100644'}
    observed = sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
    if len(files) != 4005 or observed != V3_TREE: raise ValueError('Not the exact frozen V3 source composition')
    raw = {name: (v3_source / name).read_text() for name in SOURCES}
    if any(sha(text.encode()) != SOURCES[name] for name, text in raw.items()):
        raise ValueError('Reviewed event source changed')
    proposed = dict(raw)
    api, buf, sem = SOURCES
    anchor = '    NvHandle hParentClient = pNv0050AllocParams->hParentClient;\n'
    proposed[api] = replace_one(proposed[api], anchor, anchor +
        '\n    // This backend has no OS-event handle registry. Keep real kernel callbacks.\n'
        '    if (pResourceRef->externalClassId == NV01_EVENT_OS_EVENT)\n'
        '        return NV_ERR_NOT_SUPPORTED;\n')
    anchor = '    pRmClient = dynamicCast(pCallContext->pClient, RmClient);\n'
    proposed[buf] = replace_one(proposed[buf], anchor,
        '    // Public OS notifications are unavailable; zero preserves bClientRM producers.\n'
        '    if (pAllocParams->notificationHandle != 0)\n'
        '        return NV_ERR_NOT_SUPPORTED;\n\n' + anchor)
    for name in ('semsurfCtrlCmdRegisterWaiter_IMPL', 'semsurfCtrlCmdUnregisterWaiter_IMPL'):
        start, end, body = function(proposed[sem], name)
        anchor = '    if (pParams->notificationHandle)\n'
        changed = replace_one(body, anchor,
            '    // No user OS-event registration exists in this immutable backend.\n'
            '    if (!bKernel && pParams->notificationHandle != 0)\n'
            '        return NV_ERR_NOT_SUPPORTED;\n\n' + anchor)
        proposed[sem] = proposed[sem][:start] + changed + proposed[sem][end:]
    for name in proposed:
        first = proposed[name].index('#include ')
        proposed[name] = proposed[name][:first] + SEAL + proposed[name][first:]
        target = output / 'source' / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposed[name])
    patch = ''.join(''.join(difflib.unified_diff(raw[name].splitlines(keepends=True),
        proposed[name].splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name)) for name in SOURCES)
    (output / 'os-event-additions-to-v3.patch').write_text(patch)
    fixture = []
    groups = {'eventapi': [], 'eventbuffer': [], 'semsurf': []}
    for label, sources in [('baseline', raw), ('proposed', proposed)]:
        for name, source in FUNCTIONS.items():
            body = function(sources[source], name)[2]
            renamed = re.sub(r'\b' + name + r'\b', label + '_' + name, body)
            fixture.append(renamed)
            group = 'eventapi' if name.startswith('eventapi') else 'eventbuffer' if name.startswith('eventbuffer') else 'semsurf'
            groups[group].append(renamed)
    (output / 'event_policy_bodies.h').write_text('\n\n'.join(fixture) + '\n')
    for name, bodies in groups.items():
        (output / (name + '_policy_bodies.h')).write_text('\n\n'.join(bodies) + '\n')
    final_files = dict(files)
    for name, text in proposed.items(): final_files[name] = {**files[name], 'sha256': sha(text.encode())}
    record = {'format': 1, 'status': 'isolated-os-event-guards-composed-not-admitted',
        'base_v3_tree_sha256': V3_TREE, 'base_file_count': 4005,
        'source_sha256': SOURCES, 'proposed_source_sha256': {n: sha(t.encode()) for n, t in proposed.items()},
        'composed_tree_sha256': sha(json.dumps(final_files, sort_keys=True, separators=(',', ':')).encode()),
        'additions_patch_sha256': sha(patch.encode()), 'complete_original_bodies_per_variant': 4,
        'guarded_translation_units': 3, 'required_configuration': 'S540_NVIDIA_NO_OS_EVENT_BACKEND=1',
        'original_callbacks_implemented': False, 'ctl_state_backend_supplied': False,
        'whole_bootstrap_exclusion_proven': False, 'production_candidate_allowed': False,
        'kernel_execution': 'not_tested', 'gpu_access': False}
    (output / 'composition.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record
