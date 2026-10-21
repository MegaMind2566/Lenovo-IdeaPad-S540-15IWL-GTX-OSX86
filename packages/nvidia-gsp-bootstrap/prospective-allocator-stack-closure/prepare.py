#!/usr/bin/env python3
"""Opt-in global allocator dispatch and retained portable initialization guards."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CORE = 'src/nvidia/src/libraries/nvport/core/core.c'
MEMORY = 'src/nvidia/src/libraries/nvport/memory/memory_tracking.c'
INPUTS = ()
ORIGINAL_INPUTS = (CORE, MEMORY)
BASE_SHA256 = {
    CORE: 'ab654590c63b55dad276da4edf9d1ab5f621b2d2f956a71e0e28aca36811bd1c',
    MEMORY: '2f0f0f56272725a6348bae85d04a1330bd7352d3421bf94a90fff2d9debf7618'}
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-allocator-stack-closure'
UNIT = DIRECTORY + '/S540NvidiaAllocatorEpoch.c'
COMPANIONS = {DIRECTORY + '/' + name: HERE / name
              for name in ('S540NvidiaAllocatorEpoch.c', 'S540NvidiaAllocatorEpoch.h')}
PROJECT_UNITS = ({'source': UNIT, 'kind': 'original-c'},)
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
EXPORTS = {UNIT: ('s540AllocatorPortableBegin', 's540AllocatorPortableEnd',
    's540AllocatorMemoryBegin', 's540AllocatorMemoryEnd', 's540AllocatorPortableRelease',
    's540AllocatorMemoryShutdown', 's540AllocatorGlobalUse',
    's540AllocatorPortableVisible', 's540AllocatorEpochSnapshot',
    's540AllocatorTrackingRefused')}
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Allocator successor anchor absent/ambiguous: ' + before[:100])
    return text.replace(before, after)


def transforms(values):
    if values:
        raise ValueError('Allocator successor changes no existing project TU.')
    return {}


def modify_function(text, name, change):
    start, end = function_span(text, name)
    return text[:start] + change(text[start:end]) + text[end:]


def original_transforms(values):
    if set(values) != set(ORIGINAL_INPUTS):
        raise ValueError('Exact allocator/core source pair required.')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Allocator source/writer inventory changed: ' + name)
    out = dict(values)
    for name in out:
        # An appended include avoids depending on the order of original
        # includes while retaining the pinned source body and original types.
        index = out[name].find('\n#include ')
        if index < 0:
            raise ValueError('Original include boundary missing.')
        out[name] = out[name][:index] + '\n#include "S540NvidiaAllocatorEpoch.h"' + out[name][index:]

    def portable_init(body):
        body = once(body, 'portInitialize(void)\n{',
            'portInitialize(void)\n{\n'
            '    NV_STATUS epochStatus = s540AllocatorPortableBegin();\n'
            '    if (epochStatus != NV_OK) return epochStatus;')
        body = once(body, '                return status;',
            '                return s540AllocatorPortableEnd(status);')
        return once(body, '    return NV_OK;', '    return s540AllocatorPortableEnd(NV_OK);')
    out[CORE] = modify_function(out[CORE], 'portInitialize', portable_init)
    out[CORE] = modify_function(out[CORE], 'portShutdown', lambda body: once(body,
        'portShutdown(void)\n{', 'portShutdown(void)\n{\n'
        '    if (s540AllocatorPortableRelease(portState.initCount) != NV_OK) return;'))
    out[CORE] = once(out[CORE], '    return portState.initCount > 0;',
        '    return portState.initCount > 0 &&\n'
        '        s540AllocatorPortableVisible();')

    def memory_init(body):
        body = once(body, '    NV_STATUS status;',
            '    NV_STATUS status;\n'
            '    status = s540AllocatorMemoryBegin();\n'
            '    if (status != NV_OK) return status;')
        if body.count('return NV_OK;') != 2:
            raise ValueError('Original memory initialization success paths changed.')
        body = body.replace('return NV_OK;', 'return s540AllocatorMemoryEnd(NV_OK);')
        return once(body, '        return status;', '        return s540AllocatorMemoryEnd(status);')
    out[MEMORY] = modify_function(out[MEMORY], 'portMemInitialize', memory_init)
    out[MEMORY] = modify_function(out[MEMORY], 'portMemShutdown', lambda body: once(body,
        'portMemShutdown(NvBool bForceSilent)\n{',
        'portMemShutdown(NvBool bForceSilent)\n{\n'
        '    if (s540AllocatorMemoryShutdown() != NV_OK) return;'))
    # The public constructor is not an authority to mutate retained global
    # tracking. Only this source-local original implementation is called by
    # the genuine memory initializer, in its original order after lock setup.
    private_tracking = 's540AllocatorInitializeTracking'
    start, end = function_span(out[MEMORY], 'portMemInitializeAllocatorTracking')
    original_tracking = out[MEMORY][start:end]
    signature = original_tracking[:original_tracking.index('{')]
    reserved = ('pTracking == &portMemGlobals.mainTracking ||\n'
        '        pTracking == &portMemGlobals.alloc.pagedImpl.tracking ||\n'
        '        pTracking == &portMemGlobals.alloc.nonPagedImpl.tracking')
    wrapper = signature + '{\n'
    wrapper += ('    if (pAlloc == &portMemGlobals.alloc.paged ||\n'
        '        pAlloc == &portMemGlobals.alloc.nonPaged ||\n'
        '        ' + reserved + ') {\n'
        '        s540AllocatorTrackingRefused();\n'
        '        return;\n'
        '    }\n'
        '    if (s540AllocatorGlobalUse() != NV_OK) return;\n'
        '    ' + private_tracking + '(pAlloc, pTracking PORT_MEM_CALLERINFO_COMMA_PARAM);\n}\n'
        '\nstatic void\n' + original_tracking.replace('portMemInitializeAllocatorTracking', private_tracking, 1))
    out[MEMORY] = out[MEMORY][:start] + wrapper + out[MEMORY][end:]
    declaration = ('static void ' + private_tracking + '(PORT_MEM_ALLOCATOR *pAlloc,\n'
        '    PORT_MEM_ALLOCATOR_TRACKING *pTracking PORT_MEM_CALLERINFO_COMMA_TYPE_PARAM);\n\n')
    out[MEMORY] = once(out[MEMORY], 'NV_STATUS\nportMemInitialize(void)',
        declaration + 'NV_STATUS\nportMemInitialize(void)')
    def private_initializers(body):
        if body.count('portMemInitializeAllocatorTracking(') != 3:
            raise ValueError('Original global tracking construction sites changed.')
        return body.replace('portMemInitializeAllocatorTracking(', private_tracking + '(')
    out[MEMORY] = modify_function(out[MEMORY], 'portMemInitialize', private_initializers)
    # Public getters expose mutable fields. Exact global identities select
    # original static tracking; dynamic allocators keep their own tracking.
    out[MEMORY] = modify_function(out[MEMORY], '_portMemGetTracking', lambda body: once(body,
        '    else\n        return pAlloc->pTracking;',
        '    else if (pAlloc == &portMemGlobals.alloc.paged)\n'
        '        return &portMemGlobals.alloc.pagedImpl.tracking;\n'
        '    else if (pAlloc == &portMemGlobals.alloc.nonPaged)\n'
        '        return PORT_MEM_TRACK_USE_FENCEPOSTS ?\n'
        '            &portMemGlobals.alloc.nonPagedImpl.tracking : &portMemGlobals.alloc.pagedImpl.tracking;\n'
        '    else\n        return pAlloc->pTracking;'))
    for name, result in (('_portMemAllocatorAlloc', 'NULL'), ('_portMemAllocatorFree', '')):
        def guard_global(body, result=result):
            anchor = '    if (pAlloc == NULL)\n    {\n        PORT_BREAKPOINT_CHECKED();\n        return ' + result + ';\n    }'
            return once(body, anchor, anchor + '\n'
                '    if ((pAlloc == &portMemGlobals.alloc.nonPaged ||\n'
                '         pAlloc == &portMemGlobals.alloc.paged) &&\n'
                '        s540AllocatorGlobalUse() != NV_OK) return ' + result + ';')
        # Void original bodies spell an unadorned return statement.
        if name == '_portMemAllocatorFree':
            def guard_global(body):
                anchor = '    if (pAlloc == NULL)\n    {\n        PORT_BREAKPOINT_CHECKED();\n        return;\n    }'
                return once(body, anchor, anchor + '\n'
                    '    if ((pAlloc == &portMemGlobals.alloc.nonPaged ||\n'
                    '         pAlloc == &portMemGlobals.alloc.paged) &&\n'
                    '        s540AllocatorGlobalUse() != NV_OK) return;')
        out[MEMORY] = modify_function(out[MEMORY], name, guard_global)
        def guard_tracking_alias(body, result=result):
            anchor = '    if ((pAlloc == &portMemGlobals.alloc.nonPaged ||'
            guard = ('    if (pAlloc != &portMemGlobals.alloc.paged &&\n'
                '        pAlloc != &portMemGlobals.alloc.nonPaged &&\n'
                '        (pAlloc->pTracking == &portMemGlobals.mainTracking ||\n'
                '         pAlloc->pTracking == &portMemGlobals.alloc.pagedImpl.tracking ||\n'
                '         pAlloc->pTracking == &portMemGlobals.alloc.nonPagedImpl.tracking)) {\n'
                '        s540AllocatorTrackingRefused();\n'
                '        return' + (' ' + result if result else '') + ';\n    }\n')
            return once(body, anchor, guard + anchor)
        out[MEMORY] = modify_function(out[MEMORY], name, guard_tracking_alias)
    out[MEMORY] = once(out[MEMORY], '        pMem = pAlloc->_portAlloc(pAlloc, paddedLength);',
        '        /* Global identities use their immutable original implementations.\n'
        '         * Keep padding, tracking, limits, fences and OOM around this call.\n'
        '         * Generic dynamic/existing-block allocators retain their callback. */\n'
        '        if (pAlloc == &portMemGlobals.alloc.nonPaged)\n'
        '            pMem = _portMemAllocatorAllocNonPagedWrapper(pAlloc, paddedLength);\n'
        '        else if (pAlloc == &portMemGlobals.alloc.paged)\n'
        '            pMem = _portMemAllocatorAllocPagedWrapper(pAlloc, paddedLength);\n'
        '        else\n'
        '            pMem = pAlloc->_portAlloc(pAlloc, paddedLength);')
    out[MEMORY] = once(out[MEMORY], '            pAlloc->_portFree(pAlloc, pMem);',
        '            if (pAlloc == &portMemGlobals.alloc.nonPaged ||\n'
        '                pAlloc == &portMemGlobals.alloc.paged)\n'
        '                _portMemAllocatorFreeWrapper(pAlloc, pMem);\n'
        '            else\n'
        '                pAlloc->_portFree(pAlloc, pMem);')
    out[MEMORY] = modify_function(out[MEMORY], 'portMemAllocatorRelease', lambda body: once(body,
        '    if (pAllocator == NULL)',
        '    /* The selected outer epoch retains both global allocators.\n'
        '     * A mutable callback field cannot turn a global getter into a\n'
        '     * destructor or erase its tracking behind that epoch. */\n'
        '    if (pAllocator == &portMemGlobals.alloc.nonPaged ||\n'
        '        pAllocator == &portMemGlobals.alloc.paged) {\n'
        '        (void)s540AllocatorMemoryShutdown();\n'
        '        return;\n'
        '    }\n'
        '    if (pAllocator == NULL)'))
    out[MEMORY] = modify_function(out[MEMORY], 'portMemAllocatorRelease', lambda body: once(body,
        '    _portMemTrackingRelease(pAllocator->pTracking, NV_TRUE);',
        '    if (pAllocator->pTracking == &portMemGlobals.mainTracking ||\n'
        '        pAllocator->pTracking == &portMemGlobals.alloc.pagedImpl.tracking ||\n'
        '        pAllocator->pTracking == &portMemGlobals.alloc.nonPagedImpl.tracking) {\n'
        '        (void)s540AllocatorMemoryShutdown();\n'
        '        return;\n    }\n'
        '    _portMemTrackingRelease(pAllocator->pTracking, NV_TRUE);'))
    out[MEMORY] = modify_function(out[MEMORY], '_portMemTrackingRelease', lambda body: once(body,
        '    if (pTracking == NULL) return;',
        '    if (' + reserved + ') {\n'
        '        (void)s540AllocatorMemoryShutdown();\n'
        '        return;\n    }\n'
        '    if (pTracking == NULL) return;'))
    out[MEMORY] = modify_function(out[MEMORY], '_portMemAllocatorCreateOnExistingBlock', lambda body: once(body,
        '    PORT_MEM_ALLOCATOR *pAllocator = (PORT_MEM_ALLOCATOR *)pPreallocatedBlock;',
        '    /* Caller-owned storage cannot overlap retained global metadata. */\n'
        '    NvUPtr blockStart = (NvUPtr)pPreallocatedBlock;\n'
        '    NvUPtr globalStart = (NvUPtr)&portMemGlobals;\n'
        '    NvUPtr globalEnd = globalStart + sizeof(portMemGlobals);\n'
        '    if (blockSizeBytes > (~(NvUPtr)0 - blockStart) ||\n'
        '        (blockStart >= globalStart && blockStart < globalEnd) ||\n'
        '        (blockStart < globalStart && blockSizeBytes > globalStart - blockStart)) {\n'
        '        s540AllocatorTrackingRefused();\n'
        '        return NULL;\n    }\n'
        '    PORT_MEM_ALLOCATOR *pAllocator = (PORT_MEM_ALLOCATOR *)pPreallocatedBlock;'))
    return out


def prepare(source, output):
    if output.exists():
        raise ValueError('Fresh allocator successor output required.')
    source = source.resolve(strict=True)
    values = {name: (source / name).read_text() for name in ORIGINAL_INPUTS}
    changed = original_transforms(values)
    output.mkdir(parents=True)
    rows = {}
    for name, text in changed.items():
        destination = output / 'source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text)
        rows[name] = {'input_sha256': BASE_SHA256[name],
                      'output_sha256': hashlib.sha256(text.encode()).hexdigest()}
    for name, path in COMPANIONS.items():
        destination = output / 'project' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
    report = {'format': 1, 'status': 'materialized-opt-in-allocator-stack-successor',
        'sources': rows, 'project_units': PROJECT_UNITS,
        'original_entry_admission': False, 'hardware_execution': False,
        'production_candidate_allowed': False}
    (output / 'allocator-successor.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output)))
