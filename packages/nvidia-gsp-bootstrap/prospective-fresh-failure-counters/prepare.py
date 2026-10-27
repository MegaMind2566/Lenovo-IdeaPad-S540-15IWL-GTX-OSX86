#!/usr/bin/env python3
"""Observe fresh post-return failures without altering initialization policy."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-fresh-failure-counters'
DEVICE = 'packages/nvidia-device-transport/src/S540NvidiaDeviceServices.cpp'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
INPUTS = (DEVICE, CONTEXT)
ORIGINAL_INPUTS = ()
COMPANIONS = {DIRECTORY + '/S540DeviceAllocationDiagnostics.h':
              HERE / 'S540DeviceAllocationDiagnostics.h'}
PROJECT_UNITS = ()
EXPORTS = {DEVICE: ('s540DeviceReadAllocationDiagnostics',)}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json',
    'allocation-counters.cpp.inc', 'allocation-first-failure.cpp.inc', 'allocation-read.cpp.inc',
    'context-failure.c.inc', 'check.py', 'check_context.py',
    'tests/check_allocation.cpp.inc', 'tests/check_context.c.inc',
    'tests/mock/machine/machine_routines.h', 'tests/mock/libkern/libkern.h',
    'tests/mock/IOKit/IOLib.h')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    result = {}
    for row in (HERE / 'BASE-SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', row)
        if match is None or match[2] in result:
            raise ValueError('Exact unique B7 project input hashes required')
        result[match[2]] = match[1]
    if set(result) != set(INPUTS):
        raise ValueError('Exactly two B7 project inputs required')
    return result


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Fresh-counter anchor changed: ' + before[:120])
    return text.replace(before, after)


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('The exact two B7 project inputs are required')
    for name, value in values.items():
        if hashlib.sha256(value.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Frozen B7 input changed: ' + name)
    text = once(values[DEVICE], '#include "nv_device_services.h"',
        '#include "nv_device_services.h"\n#include "../../nvidia-gsp-bootstrap/'
        'prospective-fresh-failure-counters/S540DeviceAllocationDiagnostics.h"\n'
        '#include "../../nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"\n'
        '#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"')
    anchor = 'struct UnprotectedCpuRegisters { NvU32 eax, ebx, ecx, edx; };'
    text = once(text, anchor, (HERE / 'allocation-counters.cpp.inc').read_text() + '\n' + anchor)
    text = once(text, '    increment(diagnostics.allocationAttempts);',
        '    increment(diagnostics.allocationAttempts);\n    observeAllocationAttempt(pages);')
    text = once(text, 'NV_STATUS allocationFailed(NvU32 pages, NvU64 pageBytes, NV_STATUS status) {',
        (HERE / 'allocation-first-failure.cpp.inc').read_text() + '\n' +
        'NV_STATUS allocationFailed(NvU32 pages, NvU64 pageBytes, NV_STATUS status) {')
    anchor = 'extern "C" NV_STATUS NV_API_CALL s540Global_nv_alloc_pages('
    text = once(text, anchor, (HERE / 'allocation-read.cpp.inc').read_text() + '\n' + anchor)
    first, last = function_span(text, 's540Global_nv_alloc_pages')
    body = once(text[first:last], '    if (!stateValid(state)) return NV_ERR_INVALID_STATE;',
        '    if (!stateValid(state)) {\n        recordAllocationEntryRejection();\n'
        '        return NV_ERR_INVALID_STATE;\n    }')
    body = once(body, '    auto fail = [&](NV_STATUS status, const char *stage) {',
        '    auto fail = [&](NV_STATUS status, const char *stage, NvU32 observedStage) {\n'
        '        observeAllocationFailureRequest(pages, pageSize, contiguous, cache, zeroed,\n'
        '            unencrypted, node, cpu, observedStage, status);')
    for label, stage in (('arguments', 'ARGUMENTS'), ('geometry', 'GEOMETRY'),
                         ('host-profile', 'HOST_PROFILE'), ('records', 'RECORDS'),
                         ('token', 'TOKEN'), ('session', 'SESSION')):
        body = once(body, ', "' + label + '");',
            ', "' + label + '", S540_ALLOC_FAILURE_' + stage + ');')
    text = text[:first] + body + text[last:]
    context = once(values[CONTEXT], '#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n'
        '#include "../prospective-fresh-failure-counters/S540DeviceAllocationDiagnostics.h"\n'
        '#include "../prospective-attach-failure-witness/S540AttachFailureWitness.h"')
    first, last = function_span(context, 's540LogRetainedProfileFailure')
    first = context.rfind('\n', 0, first) + 1
    context = context[:first] + (HERE / 'context-failure.c.inc').read_text().rstrip() + context[last:]
    return {DEVICE: text, CONTEXT: context}
