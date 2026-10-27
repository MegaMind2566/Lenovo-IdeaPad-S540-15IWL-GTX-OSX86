#!/usr/bin/env python3
"""Add scalar unavailable-source observations without changing refusal policy."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-unavailable-service-witness'
HOST = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
INPUTS = (HOST, CONTEXT)
ORIGINAL_INPUTS = ()
COMPANIONS = {DIRECTORY + '/S540HostUnavailableDiagnostics.h':
              HERE / 'S540HostUnavailableDiagnostics.h'}
PROJECT_UNITS = ()
EXPORTS = {HOST: ('s540GlobalRmReadUnavailableDiagnostics',)}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json',
    'unavailable-storage.cpp.inc', 'unavailable-read.cpp.inc', 'context-unavailable.c.inc',
    'check.py', 'tests/check_host.cpp.inc', 'tests/check_context.c.inc')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    result = {}
    for row in (HERE / 'BASE-SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', row)
        if match is None or match[2] in result:
            raise ValueError('Exact unique B9 preceding-prefix input hashes required')
        result[match[2]] = match[1]
    if set(result) != set(INPUTS):
        raise ValueError('Exactly Host and Context input hashes required')
    return result


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Unavailable diagnostic anchor changed: ' + before[:120])
    return text.replace(before, after)


def edit(text, name, before, after):
    start, end = function_span(text, name)
    return text[:start] + once(text[start:end], before, after) + text[end:]


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exact Host and Context project inputs required')
    for name, value in values.items():
        if hashlib.sha256(value.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Frozen preceding-prefix input changed: ' + name)
    host = once(values[HOST], '#include "S540NvidiaGlobalRm.h"',
        '#include "S540NvidiaGlobalRm.h"\n#include "../../nvidia-gsp-bootstrap/'
        'prospective-unavailable-service-witness/S540HostUnavailableDiagnostics.h"')
    host = once(host, 'S540NvidiaGlobalRmHostSnapshot counters = {};',
        'S540NvidiaGlobalRmHostSnapshot counters = {};\n' +
        (HERE / 'unavailable-storage.cpp.inc').read_text().rstrip())
    # The original aggregate body is preserved verbatim in recordUnavailableAt;
    # no TLS marker, recursion, extra refusal or double increment is introduced.
    start, end = function_span(host, 's540GlobalRmRecordUnavailable')
    body_start = host.index('{', start)
    original_body = host[body_start + 1:end - 1].strip()
    storage = (HERE / 'unavailable-storage.cpp.inc').read_text()
    if storage.count(original_body) != 1:
        raise ValueError('Original central refusal / aggregate sequence changed')
    host = host[:body_start] + '{\n    recordUnavailableAt(service, S540_HOST_UNAVAILABLE_EXTERNAL);\n}' + host[end:]
    replacements = (
        ('s540GlobalRmHostShutdown', 's540GlobalRmRecordUnavailable(0)', 'SHUTDOWN_ORDINARY'),
        ('allocateTracked', 's540GlobalRmRecordUnavailable(0)', 'ALLOCATE_ORDINARY'),
        ('freeTracked', 'if (!s540Darwin_os_semaphore_may_sleep()) {\n        s540GlobalRmRecordUnavailable(0);', 'FREE_ORDINARY'),
        ('freeTracked', '        unlock();\n        s540GlobalRmRecordUnavailable(0);\n        return;', 'FREE_PERMIT'),
        ('freeTracked', 'if (completed != NV_OK) s540GlobalRmRecordUnavailable(0);', 'FREE_COMPLETION'),
        ('s540GlobalRmHostSnapshot', 's540GlobalRmRecordUnavailable(0)', 'SNAPSHOT_ORDINARY'),
        ('s540GlobalRmRecordService', 's540GlobalRmRecordUnavailable(service)', 'SERVICE_RANGE'),
        ('s540GlobalRmRecordServiceName', 'if (!name) { s540GlobalRmRecordUnavailable(0);', 'NULL_SERVICE_NAME'),
        ('s540GlobalRmRecordServiceName', '    s540GlobalRmRecordUnavailable(0);', 'SERVICE_TABLE_FULL'),
    )
    for function, anchor, site in replacements:
        updated = anchor.replace('s540GlobalRmRecordUnavailable(', 'recordUnavailableAt(')
        service = 'service' if site == 'SERVICE_RANGE' else '0'
        updated = updated.replace('recordUnavailableAt(' + service + ')',
            'recordUnavailableAt(' + service + ', S540_HOST_UNAVAILABLE_' + site + ')')
        host = edit(host, function, anchor, updated)
    anchor = 'extern "C" void s540GlobalRmRecordUnavailable(NvU32 service)'
    host = once(host, anchor, (HERE / 'unavailable-read.cpp.inc').read_text().rstrip() + '\n\n' + anchor)
    context = once(values[CONTEXT], '#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n'
        '#include "../prospective-unavailable-service-witness/S540HostUnavailableDiagnostics.h"')
    start, unused_end = function_span(context, 's540LogRetainedProfileFailure')
    start = context.rfind('\n', 0, start) + 1
    context = context[:start] + (HERE / 'context-unavailable.c.inc').read_text().rstrip() + '\n' + context[start:]
    context = edit(context, 's540LogRetainedProfileFailure',
        '    s540LogAttachFailureWitness(context);',
        '    s540LogAttachFailureWitness(context);\n    s540LogUnavailableServiceWitness(context);')
    return {HOST: host, CONTEXT: context}
