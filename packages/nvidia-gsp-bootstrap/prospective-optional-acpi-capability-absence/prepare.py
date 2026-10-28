#!/usr/bin/env python3
"""Preserve the original optional-ACPI absence fallback before facade calls."""
from pathlib import Path
import hashlib
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORY = 'packages/nvidia-gsp-bootstrap/prospective-optional-acpi-capability-absence'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
ACPI = 'src/nvidia/src/kernel/platform/acpi_common.c'
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
RECORD_HEADER = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'
PROVIDER = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmAcpi.c'
PROFILE = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmProfile.h'
# These exact pass-through inputs bind both the compile-selected backend and
# its actual disabled method provider. An events flag alone is insufficient.
INPUTS = (CONTEXT, PROVIDER, PROFILE)
ORIGINAL_INPUTS = (ACPI,)
HEADER = DIRECTORY + '/S540OptionalAcpiAbsence.h'
UNIT = DIRECTORY + '/S540OptionalAcpiAbsence.c'
COMPANIONS = {HEADER: HERE / 'S540OptionalAcpiAbsence.h', UNIT: HERE / 'S540OptionalAcpiAbsence.c'}
PROJECT_UNITS = ({'source': UNIT, 'kind': 'plain-c'},)
EXPORTS = {UNIT: ('s540OptionalAcpiCommitAbsent', 's540OptionalAcpiRead')}
INCLUDE_DIRECTORIES = (DIRECTORY,)
COMPILE_DEFINITIONS = {}
SOURCE_FILES = ('BASE-SHA256SUMS', 'SOURCE-CONTRACT.json', 'README.md',
                'context-absence.c.inc', 'check.py', 'tests/check_optional.c.inc')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def input_hashes():
    result = {}
    for row in (HERE / 'BASE-SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', row)
        if match is None or match[2] in result:
            raise ValueError('Exact unique B9 source hashes are required')
        result[match[2]] = match[1]
    if set(result) != set(INPUTS + ORIGINAL_INPUTS):
        raise ValueError('Exactly the B9 Context/provider/profile and original ACPI inputs are required')
    return result


BASE_SHA256 = input_hashes()


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('The exact optional-ACPI source anchor changed: ' + before[:110])
    return text.replace(before, after)


def exact(values, names):
    if set(values) != set(names):
        raise ValueError('The exact optional-ACPI source inventory is required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('The exact B9 source identity changed: ' + name)


def transforms(values):
    exact(values, INPUTS)
    context = once(values[CONTEXT], '#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n'
        '#include "../prospective-optional-acpi-capability-absence/S540OptionalAcpiAbsence.h"')
    marker = 'static void s540LogRetainedProfileFailure('
    if context.count(marker) != 1:
        raise ValueError('Actual retained post-wrapper logger declaration changed')
    index = context.index(marker)
    context = context[:index] + (HERE / 'context-absence.c.inc').read_text() + '\n' + context[index:]
    context = once(context,
        '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);',
        '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);\n'
        '    s540LogOptionalAcpiAbsence(context);')
    return {CONTEXT: context, PROVIDER: values[PROVIDER], PROFILE: values[PROFILE]}


def original_transforms(values):
    exact(values, ORIGINAL_INPUTS)
    text = once(values[ACPI], '#include "gpu/disp/kern_disp.h"',
        '#include "gpu/disp/kern_disp.h"\n#include "S540OptionalAcpiAbsence.h"\n'
        '_Static_assert(ACPI_DSM_FUNCTION_COUNT == S540_OPTIONAL_ACPI_DSM_FUNCTIONS,\n'
        '               "Reviewed optional ACPI function inventory changed");')
    # Intercept exactly these two optional initialization probes, retaining
    # their actual downstream failure/cache handling and every other caller.
    first, last = function_span(text, '_acpiDsmSupportedFuncCacheInit')
    body = text[first:last]
    before = '''        status = osCallACPI_DSM(pGpu,
                                func,
                                NV_ACPI_ALL_FUNC_SUPPORT,
                                (NvU32 *) &supportFuncs,
                                &rtnSize);'''
    after = '''        if (pGpu->acpi.dsm[func].suppFuncStatus == DSM_FUNC_STATUS_UNKNOWN &&
            s540OptionalAcpiCommitAbsent(pGpu->pOsGpuInfo,
                S540_OPTIONAL_ACPI_DSM_SUPPORT, (NvU32)func) == NV_OK)
        {
            // Selected backend capability absence; no AML method ran.
            status = NV_ERR_NOT_SUPPORTED;
        }
        else
        {
''' + '\n'.join('    ' + line for line in before.splitlines()) + '''
        }'''
    body = once(body, before, after)
    text = text[:first] + body + text[last:]
    first, last = function_span(text, '_acpiCacheMethodData')
    body = text[first:last]
    before = '    status = osCallACPI_DOD(pGpu, pGpu->acpiMethodData.dodMethodData.acpiIdList, &pGpu->acpiMethodData.dodMethodData.acpiIdListLen);'
    after = '''    if (s540OptionalAcpiCommitAbsent(pGpu->pOsGpuInfo,
            S540_OPTIONAL_ACPI_DOD, 0U) == NV_OK)
    {
        // No display list was supplied by this selected backend.
        status = NV_ERR_NOT_SUPPORTED;
    }
    else
    {
    ''' + before + '''
    }'''
    body = once(body, before, after)
    return {ACPI: text[:first] + body + text[last:]}
