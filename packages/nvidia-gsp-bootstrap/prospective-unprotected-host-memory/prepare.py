#!/usr/bin/env python3
"""Admit unprotected owned pages only on the observed selected Intel profile."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-unprotected-host-memory'
DEVICE = 'packages/nvidia-device-transport/src/S540NvidiaDeviceServices.cpp'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
INPUTS = (DEVICE, CONTEXT)
ORIGINAL_INPUTS = ()
COMPANIONS = {}
PROJECT_UNITS = ()
EXPORTS = {}
INCLUDE_DIRECTORIES = ()
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'host-policy.cpp.inc',
                'allocate-pages.cpp.inc', 'check.py', 'tests/check_memory.cpp.inc',
                'context-failure.c.inc', 'check_context.py', 'tests/check_context.c.inc')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    lines = (HERE / 'BASE-SHA256SUMS').read_text().splitlines()
    result = {}
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if match is None or match[2] in result:
            raise ValueError('Exact unique B6 project input hashes required')
        result[match[2]] = match[1]
    if set(result) != set(INPUTS):
        raise ValueError('Exactly two B6 project input hashes required')
    return result


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Unprotected allocation anchor changed: ' + before[:100])
    return text.replace(before, after)


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('The exact two B6 project inputs are required')
    for name, value in values.items():
        if hashlib.sha256(value.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('The frozen B6 input changed: ' + name)
    text = values[DEVICE]
    text = once(text, '#include <libkern/libkern.h>',
                '#include <libkern/libkern.h>\n#include <IOKit/IOLib.h>')
    anchor = 'NV_STATUS allocationFailed(NvU32 pages, NvU64 pageBytes, NV_STATUS status) {'
    text = once(text, anchor, (HERE / 'host-policy.cpp.inc').read_text() + '\n' + anchor)
    start, end = function_span(text, 's540Global_nv_alloc_pages')
    start = text.rfind('\n', 0, start) + 1
    text = text[:start] + (HERE / 'allocate-pages.cpp.inc').read_text().rstrip() + text[end:]
    context = values[CONTEXT]
    anchor = 'NV_STATUS s540GspContextInitializeAdapter(S540GspContext *context)'
    context = once(context, anchor, (HERE / 'context-failure.c.inc').read_text() + '\n' + anchor)
    before = '''    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);
    if (profile != NV_OK) { context->state.quarantined = NV_TRUE; return profile; }'''
    after = '''    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);
    if (profile != NV_OK) {
        context->state.quarantined = NV_TRUE;
        s540LogRetainedProfileFailure(context, profile);
        return profile;
    }'''
    context = once(context, before, after)
    return {DEVICE: text, CONTEXT: context}
