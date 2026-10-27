#!/usr/bin/env python3
"""Omit only the actually disabled optional NVLink child before creation."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-optional-nvlink-absence'
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
RECORD_HEADER = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
GPU = 'src/nvidia/src/kernel/gpu/gpu.c'
GPU_HELPER = 's540GpuOptionalNvlinkAbsent'
INPUTS = (RECORD, RECORD_HEADER, CONTEXT)
ORIGINAL_INPUTS = (GPU,)
HEADER = DIRECTORY + '/S540OptionalNvlinkAbsence.h'
UNIT = DIRECTORY + '/S540OptionalNvlinkAbsence.c'
COMPANIONS = {HEADER: HERE / 'S540OptionalNvlinkAbsence.h',
              UNIT: HERE / 'S540OptionalNvlinkAbsence.c'}
PROJECT_UNITS = ({'source': UNIT, 'kind': 'plain-c'},)
EXPORTS = {RECORD: ('s540FirstTxnOptionalNvlinkActive', 's540FirstTxnOptionalNvlinkReturned'),
           UNIT: ('s540OptionalNvlinkCommitAbsent', 's540OptionalNvlinkRead')}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'README.md',
                'record-active.c.inc', 'record-api.h.inc', 'gpu-optional.c.inc',
                'context-absence.c.inc', 'check.py', 'tests/check_optional.c.inc')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    result = {}
    for row in (HERE / 'BASE-SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', row)
        if match is None or match[2] in result:
            raise ValueError('Exact unique B8 source hashes are required')
        result[match[2]] = match[1]
    if set(result) != set(INPUTS + ORIGINAL_INPUTS):
        raise ValueError('Exactly the B8 record/header/Context and GPU inputs are required')
    return result


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('The exact optional-engine source anchor changed: ' + before[:110])
    return text.replace(before, after)


def exact(values, names):
    if set(values) != set(names):
        raise ValueError('The exact optional-engine source inventory is required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('The exact B8 source identity changed: ' + name)


def transforms(values):
    exact(values, INPUTS)
    out = dict(values)
    out[RECORD] += '\n' + (HERE / 'record-active.c.inc').read_text()
    out[RECORD_HEADER] += '\n' + (HERE / 'record-api.h.inc').read_text()
    context = once(out[CONTEXT], '#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n'
        '#include "../prospective-optional-nvlink-absence/S540OptionalNvlinkAbsence.h"')
    marker = 'static void s540LogRetainedProfileFailure('
    index = context.index(marker)
    context = context[:index] + (HERE / 'context-absence.c.inc').read_text() + '\n' + context[index:]
    context = once(context,
        '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);',
        '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);\n'
        '    s540LogOptionalNvlinkAbsence(context);')
    out[CONTEXT] = context
    return out


def original_transforms(values):
    exact(values, ORIGINAL_INPUTS)
    text = once(values[GPU], '#include "S540AttachFailureWitness.h"',
        '#include "S540AttachFailureWitness.h"\n#include "S540OptionalNvlinkAbsence.h"')
    first, last = function_span(text, 'gpuCreateObject')
    body = text[first:last]
    anchor = '''    if (!gpuShouldCreateObject(pGpu, classId, instanceID))
        return NV_OK;
'''
    replacement = anchor + '''
    if (classId == classId(KernelNvlink) && instanceID == 0)
    {
        NvBool optionalAbsent = NV_FALSE;
        status = s540GpuOptionalNvlinkAbsent(pGpu, ppChildPtr, &optionalAbsent);
        if (status != NV_OK) return status;
        if (optionalAbsent) return NV_OK;
    }
'''
    body = once(body, anchor, replacement)
    helper = (HERE / 'gpu-optional.c.inc').read_text()
    # Insert immediately before the actual definition, after every original
    # typed header. Its declarations therefore use original NVOC/NVLink types.
    declaration = text.rfind('static NV_STATUS\n', 0, first)
    if declaration < 0 or text[declaration:first] != 'static NV_STATUS\n':
        raise ValueError('The actual GPU constructor declaration changed')
    text = text[:declaration] + helper + '\n' + text[declaration:first] + body + text[last:]
    return {GPU: text}
