#!/usr/bin/env python3
"""Extract complete source bodies into the caller's output directory only."""
from __future__ import annotations
from pathlib import Path
from common import function_span, sha, write_json
from prepare import prepare

OSINIT = 'src/nvidia/arch/nvalloc/unix/src/osinit.c'
OSAPI = 'src/nvidia/arch/nvalloc/unix/src/osapi.c'
RUNTIME = 'src/nvidia/src/libraries/nvoc/src/runtime.c'
TIMER_CREATE = 'src/nvidia/generated/g_objtmr_nvoc.c'

def body(text: str, name: str, prefix: str) -> str:
    start, end = function_span(text, name)
    return prefix + '\n' + text[start:end] + '\n'

def prepare_controls(upstream: Path, v3_root: Path | None, output: Path) -> dict:
    result = prepare(upstream, v3_root, output)
    proposed, source = result['proposed'], result['base_source']
    output = output.resolve()
    rmapi = (source / 'src/nvidia/src/kernel/rmapi/rmapi.c').read_text()
    start = rmapi.index('typedef struct\n{')
    end = rmapi.index('} RMAPI_LOCK;', start) + len('} RMAPI_LOCK;')
    bodies = {
        'actual-rmapi-lock-bodies.inc': rmapi[start:end] + '\nstatic RMAPI_LOCK g_RmApiLock;\n'
            'static void _rmapiLockRelease(NvBool);\n' + '\n'.join(body(rmapi, name, prefix) for name, prefix in (
                ('rmapiLockAcquire', 'NV_STATUS'), ('_rmapiLockRelease', 'static void'),
                ('rmapiLockRelease', 'void'), ('rmapiLockIsOwner', 'NvBool'))),
        'actual-wrapper-bodies.inc': body(proposed[OSINIT], '_s540RmRetainInitFailure', 'static void') +
            body(proposed[OSAPI], 'rm_init_adapter', 'NvBool NV_API_CALL'),
        'actual-nvoc-bodies.inc': '\n'.join(body(proposed[RUNTIME], name, prefix) for name, prefix in (
            ('objRemoveChild_IMPL', 'void'), ('objGetChild_IMPL', 'Object *'),
            ('s540FirstTxnObjDeleteChecked', 'NV_STATUS'), ('__nvoc_objDelete', 'void'))),
        'actual-timer-ctor-body.inc': body(proposed[TIMER_CREATE], '__nvoc_ctor_OBJTMR', 'NV_STATUS'),
    }
    for name, text in bodies.items():
        (output / name).write_text(text)
    write_json(output / 'body-source-manifest.json', {'format': 1,
        'complete_extracted_bodies': 11, 'original_functions_and_wrappers': 9,
        'new_source_resident_helpers': 2,
        'body_sha256': {p: sha(t.encode()) for p, t in bodies.items()},
        'gpu_init_endpoint_fixture': True, 'record_endpoint_fixture': True,
        'original_entry_admission': False})
    return result
