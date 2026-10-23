#!/usr/bin/env python3
"""Read back BME and bound the selected real TP poll with cancellation."""
from pathlib import Path
import hashlib
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = 'packages/nvidia-gsp-bootstrap/prospective-dma-stop-closure'
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
GM107 = 'src/nvidia/src/kernel/gpu/bif/arch/maxwell/kernel_bif_gm107.c'
TU102 = 'src/nvidia/src/kernel/gpu/bif/arch/turing/kernel_bif_tu102.c'
INPUTS = (RECORD,)
ORIGINAL_INPUTS = (GM107, TU102)
BASE_SHA256 = {
    RECORD: '6d728dddb7ccd5ecb684ccfb11ed0b96f69d77dcb37e39dfdb4140e3234b3d0c',
    GM107: '8adf51c33580a9cabff61756d29a5ad1b93c4379fa9f70cf7e1c02c747f0e67b',
    TU102: 'deb0b0aa06023fd73e233e6c727e2fb2a2574ed764b990239605ee18a910a289'}
COMPANIONS = {}
PROJECT_UNITS = ()
EXPORTS = {}
COMPILE_DEFINITIONS = {}
INCLUDE_DIRECTORIES = ('packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure',)
SOURCE_FILES = ('check.py', 'check_sdk.py', 'control_common.py', 'tests/check_dma.c', 'tests/check_record.c', 'SOURCE-CONTRACT.json')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Exact DMA stop source anchor changed: ' + before[:100])
    return text.replace(before, after)


def exact(values, names):
    if set(values) != set(names):
        raise ValueError('Exact DMA stop source set required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('Reviewed DMA stop source changed: ' + name)


def modify(text, name, change):
    start, end = function_span(text, name)
    return text[:start] + change(text[start:end]) + text[end:]


def transforms(values):
    exact(values, INPUTS)
    def cleanup(body):
        body = once(body, '    if (first() == NV_OK || !LD(&record.originalReturned) ||',
            '    if (!LD(&record.originalReturned) ||')
        body = once(body, '    if (phase != S540_FIRST_RETAINED) return NV_ERR_INVALID_STATE;',
            '    if (!((phase == S540_FIRST_CLOSING && first() == NV_OK) ||\n'
            '          (phase == S540_FIRST_RETAINED && first() != NV_OK)))\n'
            '        return NV_ERR_INVALID_STATE;')
        body = once(body, 'view.firstStatus != (NvU32)first() || view.firstStatus == NV_OK ||',
            'view.firstStatus != (NvU32)first() || LD(&record.phase) != phase ||')
        body = once(body, '    /* This path exists only for a genuine sticky failure. The ordinary clean\n'
            '     * operation authorizer keeps its original rules and separate call sites. */',
            '    /* Only the real clean CLOSING or sticky RETAINED phase may use\n'
            '     * this observer. It grants masking identity, never OP admission. */')
        return body
    return {RECORD: modify(values[RECORD], 's540FirstTxnCleanupMaskReadMaster', cleanup)}


def original_transforms(values):
    exact(values, ORIGINAL_INPUTS)
    gm = once(values[GM107], '#include "gpu/bif/kernel_bif.h"',
        '#include "gpu/bif/kernel_bif.h"\n#include "nv.h"\n#include "S540NvidiaGspCommit.h"')
    gm = modify(gm, 'kbifStopSysMemRequests_GM107',
        lambda _: (HERE / 'stop-sysmem.c.inc').read_text().rstrip())
    tu = once(values[TU102], '#include "gpu/bif/kernel_bif.h"',
        '#include "gpu/bif/kernel_bif.h"\n#include "nv.h"\n#include "S540NvidiaGspCommit.h"')
    tu = modify(tu, 'kbifWaitForTransactionsComplete_TU102',
        lambda _: (HERE / 'transactions-complete.c.inc').read_text().rstrip())
    return {GM107: gm, TU102: tu}
