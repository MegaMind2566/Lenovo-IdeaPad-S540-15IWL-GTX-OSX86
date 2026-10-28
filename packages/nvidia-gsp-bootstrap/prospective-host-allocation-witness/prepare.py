#!/usr/bin/env python3
"""Observe specific refusal producers and actual Host allocation failures."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-host-allocation-witness'
HOST = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp'
OS = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmOs.c'
ACPI = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmAcpi.c'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
INPUTS = (HOST, OS, ACPI, CONTEXT)
ORIGINAL_INPUTS = ()
COMPANIONS = {DIRECTORY + '/S540HostAllocationDiagnostics.h':
              HERE / 'S540HostAllocationDiagnostics.h'}
PROJECT_UNITS = ()
EXPORTS = {HOST: ('s540GlobalRmRecordUnavailableProducer',
                 's540GlobalRmReadAllocationDiagnostics')}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json',
    'host-allocation-storage.cpp.inc', 'host-allocation-read.cpp.inc',
    'context-host-allocation.c.inc', 'check.py',
    'tests/check_host.cpp.inc', 'tests/check_context.c.inc', 'tests/nv.h')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    result = {}
    for row in (HERE / 'BASE-SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', row)
        if match is None or match[2] in result:
            raise ValueError('Exact unique preceding-prefix hashes required')
        result[match[2]] = match[1]
    if set(result) != set(INPUTS):
        raise ValueError('Exactly Host, Os, Acpi and Context hashes required')
    return result


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Host allocation diagnostic anchor changed: ' + before[:120])
    return text.replace(before, after)


def edit(text, name, before, after):
    start, end = function_span(text, name)
    return text[:start] + once(text[start:end], before, after) + text[end:]


def transforms(values):
    if set(values) != set(INPUTS):
        raise ValueError('Exact Host allocation diagnostic inputs required')
    for name, value in values.items():
        if hashlib.sha256(value.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Frozen preceding-prefix input changed: ' + name)
    outputs = dict(values)
    include = '#include "../../nvidia-gsp-bootstrap/prospective-host-allocation-witness/S540HostAllocationDiagnostics.h"'
    for name in (HOST, OS, ACPI):
        outputs[name] = once(outputs[name], '#include "S540NvidiaGlobalRm.h"',
            '#include "S540NvidiaGlobalRm.h"\n' + include)
    host = once(outputs[HOST], 'S540NvidiaGlobalRmHostSnapshot counters = {};',
        'S540NvidiaGlobalRmHostSnapshot counters = {};\n' +
        (HERE / 'host-allocation-storage.cpp.inc').read_text().rstrip())
    host = once(host, 'static void *allocationFailure(NV_STATUS status, NvU32 site)',
        'static void *allocationFailure(NV_STATUS status, NvU32 site, NvU64 bytes, bool original)')
    host = edit(host, 'allocationFailure',
        '    s540FirstTxnObserveServiceRefusal(4, site, status);',
        '    s540FirstTxnObserveServiceRefusal(4, site, status);\n'
        '    observeHostAllocation(status, site, bytes, original);')
    # Original status, return path, gates and aggregate counters stay intact.
    calls = (
        ('NV_ERR_INVALID_STATE', 1), ('NV_ERR_INVALID_STATE', 2),
        ('NV_ERR_NO_MEMORY', 3), ('NV_ERR_INVALID_STATE', 4), ('captured', 5),
        ('NV_ERR_INVALID_STATE', 6), ('NV_ERR_NO_MEMORY', 7), ('failure', 8),
        ('checked != NV_OK && checked != NV_ERR_OBJECT_NOT_FOUND ? checked : NV_ERR_INVALID_STATE', 9),
        ('NV_ERR_NO_MEMORY', 10),
    )
    for status, stage in calls:
        before = f'allocationFailure({status}, {stage})'
        host = edit(host, 'allocateTracked', before,
            f'allocationFailure({status}, {stage}, bytes, original)')
    anchor = 'extern "C" void s540GlobalRmRecordUnavailable(NvU32 service)'
    host = once(host, anchor,
        (HERE / 'host-allocation-read.cpp.inc').read_text().rstrip() + '\n\n' + anchor)
    outputs[HOST] = host
    outputs[OS] = edit(outputs[OS], 'os_alloc_mem',
        's540GlobalRmRecordUnavailable(CALL_ALLOC);',
        's540GlobalRmRecordUnavailableProducer(CALL_ALLOC, S540_HOST_ALLOCATION_PRODUCER_OS_ALLOC_CONTEXT);')
    acpi = once(outputs[ACPI], 'static NV_STATUS unavailable(const char *name)',
        'static NV_STATUS unavailable(const char *name, NvU32 producer)')
    acpi = edit(acpi, 'unavailable', 's540GlobalRmRecordUnavailable(0);',
        's540GlobalRmRecordUnavailableProducer(0, producer);')
    for name, producer in (
        ('nv_acpi_d3cold_dsm_for_upstream_port', 'ACPI_D3COLD'),
        ('nv_acpi_ddc_method', 'ACPI_DDC'), ('nv_acpi_dod_method', 'ACPI_DOD'),
        ('nv_acpi_dsm_method', 'ACPI_DSM'), ('nv_acpi_get_powersource', 'ACPI_POWERSOURCE'),
        ('nv_acpi_mux_method', 'ACPI_MUX')):
        acpi = edit(acpi, name, 'unavailable(__func__)',
            'unavailable(__func__, S540_HOST_ALLOCATION_PRODUCER_' + producer + ')')
    acpi = edit(acpi, 'nv_acpi_methods_init', 's540GlobalRmRecordUnavailable(0);',
        's540GlobalRmRecordUnavailableProducer(0, S540_HOST_ALLOCATION_PRODUCER_ACPI_INIT_NULL);')
    outputs[ACPI] = acpi
    context = once(values[CONTEXT], '#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n'
        '#include "../prospective-host-allocation-witness/S540HostAllocationDiagnostics.h"')
    start, unused_end = function_span(context, 's540LogRetainedProfileFailure')
    start = context.rfind('\n', 0, start) + 1
    context = context[:start] + (HERE / 'context-host-allocation.c.inc').read_text().rstrip() + '\n' + context[start:]
    outputs[CONTEXT] = edit(context, 's540LogRetainedProfileFailure',
        '    s540LogUnavailableServiceWitness(context);',
        '    s540LogUnavailableServiceWitness(context);\n    s540LogHostAllocationWitness(context);')
    return outputs
