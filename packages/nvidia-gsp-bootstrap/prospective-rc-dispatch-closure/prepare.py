#!/usr/bin/env python3
"""Opt-in cooperative 1Hz dispatch; source selection grants no runtime entry."""
from pathlib import Path
import hashlib
import re

HERE = Path(__file__).resolve().parent
PREFIX = 'packages/nvidia-gsp-bootstrap/prospective-rc-dispatch-closure'
IRQ = 'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/rc/S540NvidiaIrqOriginal.c'
TIMER = 'src/nvidia/src/kernel/os/os_timer.c'
OSAPI = 'src/nvidia/arch/nvalloc/unix/src/osapi.c'
INPUTS = (IRQ,)
ORIGINAL_INPUTS = (TIMER, OSAPI)
COMPANIONS = {PREFIX+'/include/S540NvidiaRcDispatchOriginal.h': HERE/'include/S540NvidiaRcDispatchOriginal.h'}
PROJECT_UNITS = ()
INCLUDE_DIRECTORIES = (PREFIX+'/include',)
COMPILE_DEFINITIONS = {}
EXPORTS = {TIMER: ('s540Global_s540OsRun1HzCallbacksNowStatus',
                  's540Global_s540OsRunQueued1HzCallbacksUnderLockStatus')}
PINNED_INPUTS = {
    TIMER: '78da8c6f23d9732dc4ff393b83553ecf06d800699362b70bc67a5f867dd41b4c',
    OSAPI: '275e46868aa90b9c0a5d60c45c23aa0aa6773e11d0c268e56fc3d2e7f940cfaa'}

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Exact RC anchor absent or ambiguous: '+old[:100])
    return text.replace(old, new)

def transforms(values):
    if set(values) != set(INPUTS): raise ValueError('Exact RC project source set required')
    text = once(values[IRQ], '#include "S540NvidiaIrqOriginal.h"',
        '#include "S540NvidiaIrqOriginal.h"\n#include "S540NvidiaRcDispatchOriginal.h"')
    text = once(text,
        '        osRunQueued1HzCallbacksUnderLock(gpu);\n'
        '        status = gpu->bCallbackQueued ? NV_ERR_BUSY_RETRY : NV_OK;',
        '        status = s540Global_s540OsRunQueued1HzCallbacksUnderLockStatus(gpu);\n'
        '        if (status == NV_OK && gpu->bCallbackQueued) status = NV_ERR_BUSY_RETRY;')
    return {IRQ:text}

def original_transforms(values):
    if set(values) != set(ORIGINAL_INPUTS): raise ValueError('Exact RC original source set required')
    for name in ORIGINAL_INPUTS:
        if hashlib.sha256(values[name].encode()).hexdigest() != PINNED_INPUTS[name]:
            raise ValueError('Pinned original RC input changed: '+name)
    text = once(values[TIMER], '#include "core/system.h"',
        '#include "core/system.h"\n#include "nv.h"\n'
        '#include "S540NvidiaGspCancellationOriginal.h"\n'
        '#include "S540NvidiaGspFirstTransaction.h"\n'
        '#include "S540NvidiaRcDispatchOriginal.h"\n\n'+(HERE/'rc-state.c.inc').read_text())
    text = once(text, '    NvU32   i;\n\n    // Initialize',
        '    NvU32   i;\n    NV_STATUS status = s540RcMutating();\n'
        '    if (status != NV_OK) return status;\n\n    // Initialize')
    text = once(text, '    if (pTmr->pOs1HzEvent != NULL)\n    {\n        tmrEventDestroy',
        '    S540FirstTxnHostIdentity birth = {0};\n    NvU64 permit = 0;\n'
        '    NV_STATUS status = s540FirstTxnBackendBeginRelease(&birth, &permit);\n'
        '    if (status != NV_OK) return s540RcRefuse(status);\n'
        '    status = s540RcMutating();\n'
        '    if (status != NV_OK) { (void)s540FirstTxnBackendEnd(permit); return status; }\n'
        '    if (pTmr->pOs1HzEvent != NULL)\n    {\n        tmrEventDestroy')
    text = once(text, '    pTmr->pOs1HzCallbackFreeList = NULL;\n    return NV_OK;',
        '    pTmr->pOs1HzCallbackFreeList = NULL;\n'
        '    return s540FirstTxnBackendEnd(permit);')
    text = once(text, '    // Grab the next free timer entry.',
        '    nvStatus = s540RcCheck(pGpu);\n'
        '    if (nvStatus != NV_OK) return nvStatus;\n'
        '    // Grab the next free timer entry.')
    text = once(text, '        if ((pTmr->pOs1HzCallbackList == NULL) && (pTmr->pOs1HzEvent != NULL))',
        '        nvStatus = s540RcMutating();\n'
        '        if (nvStatus != NV_OK) return nvStatus;\n'
        '        if ((pTmr->pOs1HzCallbackList == NULL) && (pTmr->pOs1HzEvent != NULL))')
    text = once(text, '            NV_ASSERT_OK(tmrEventScheduleRelSec(pTmr, pTmr->pOs1HzEvent, 1));',
        '            nvStatus = tmrEventScheduleRelSec(pTmr, pTmr->pOs1HzEvent, 1);\n'
        '            if (nvStatus != NV_OK) return s540RcRefuse(nvStatus);\n'
        '            /* Once armed, complete the genuine registration. A racing\n'
        '             * revocation is not atomic with this original timer arm. */')
    # Actual list insertion/removal are the sole original mutation sites; bound
    # their scans and change the lifecycle serial BEFORE any pointer is changed.
    text = once(text, '    OS1HZTIMERENTRY   **ppEntryPtr;\n\n    ppEntryPtr',
        '    OS1HZTIMERENTRY   **ppEntryPtr;\n    NvU32 visited = 0;\n\n    ppEntryPtr')
    text = once(text, '        pEntry = *ppEntryPtr;\n        if ((pEntry->callback',
        '        pEntry = *ppEntryPtr;\n'
        '        if (visited++ == TMR_NUM_CALLBACKS_OS || !s540RcEntry(pTmr, pEntry))\n'
        '        { (void)s540RcRefuse(NV_ERR_INVALID_STATE); return; }\n'
        '        if ((pEntry->callback')
    text = once(text, '            *ppEntryPtr                  = pEntry->next;',
        '            if (s540RcMutating() != NV_OK) return;\n'
        '            *ppEntryPtr                  = pEntry->next;')
    begin = text.index('static void _osRunAll1HzCallbacks(')
    end = text.index('//\n// Return Value(TRUE)', begin)
    text = text[:begin]+(HERE/'rc-dispatch.c.inc').read_text()+'\n\n'+text[end:]
    text = once(text, 'NvBool\nosRun1HzCallbacksNow\n',
        'NV_STATUS\ns540Global_s540OsRun1HzCallbacksNowStatus\n')
    text = once(text, '    NvBool              bAcquired = NV_TRUE;',
        '    NvBool              bAcquired = NV_TRUE;\n'
        '    NV_STATUS           status = NV_ERR_BUSY_RETRY;')
    text = once(text, '\n    _osRunAll1HzCallbacks(pGpu);',
        '\n    status = _osRunAll1HzCallbacks(pGpu);\n'
        '    portAtomicSetU32(&pGpu->bCallbackQueued, status != NV_OK);')
    # The original lock and TLS cleanup remains byte-for-byte, including the
    # original acquire-failure branches. The acquired bool is not completion.
    text = once(text, '    return bAcquired;\n}', '    return status;\n}\n\n'
        'NvBool osRun1HzCallbacksNow(OBJGPU *pGpu)\n{\n'
        '    return s540Global_s540OsRun1HzCallbacksNowStatus(pGpu) == NV_OK;\n}')
    begin = text.index('void osRunQueued1HzCallbacksUnderLock(')
    end = text.index('/*!', begin)
    text = (text[:begin]+'void osRunQueued1HzCallbacksUnderLock(OBJGPU *pGpu)\n{\n'
        '    (void)s540Global_s540OsRunQueued1HzCallbacksUnderLockStatus(pGpu);\n}\n\n'+text[end:])
    text = once(text, '    POS1HZTIMERENTRY    pScan;\n',
        '    POS1HZTIMERENTRY    pScan;\n    NvU32 visited = 0;\n')
    text = once(text, '        if ((pScan->callback == callback)',
        '        if (visited++ == TMR_NUM_CALLBACKS_OS || !s540RcEntry(pTmr, pScan))\n'
        '        { (void)s540RcRefuse(NV_ERR_INVALID_STATE); return NV_TRUE; }\n'
        '        if ((pScan->callback == callback)')
    text = once(text, '    osRun1HzCallbacksNow(pGpu);\n\n    // TMR_FLAG_RECUR',
        '    NV_STATUS status = s540Global_s540OsRun1HzCallbacksNowStatus(pGpu);\n'
        '    if (status != NV_OK) return status;\n'
        '    status = s540RcCheck(pGpu);\n'
        '    if (status != NV_OK) return status;\n\n    // TMR_FLAG_RECUR')
    text = once(text, '    return tmrEventScheduleRelSec(pTmr, pTmrEvent, 1);',
        '    status = tmrEventScheduleRelSec(pTmr, pTmrEvent, 1);\n'
        '    if (status != NV_OK) {\n'
        '        portAtomicSetU32(&pGpu->bCallbackQueued, NV_TRUE);\n'
        '        return s540RcRefuse(status);\n    }\n    return status;')
    api = once(values[OSAPI], '#include <osapi.h>',
        '#include <osapi.h>\n#include "S540NvidiaRcDispatchOriginal.h"')
    # Scope exactly to this original wrapper; do not alter unrelated NV_OK returns.
    begin = api.index('NV_STATUS NV_API_CALL rm_run_rc_callback(')
    end = api.index('static void _tmrEventServiceTimerWorkItem', begin)
    old = api[begin:end]
    new = once(old, '    void   *fp;', '    void   *fp;\n    NV_STATUS status;')
    new = once(new, '    osRun1HzCallbacksNow(pGpu);',
        '    status = s540Global_s540OsRun1HzCallbacksNowStatus(pGpu);')
    new = once(new, '    return NV_OK;', '    return status;')
    api = api[:begin]+new+api[end:]
    return {TIMER:text, OSAPI:api}
