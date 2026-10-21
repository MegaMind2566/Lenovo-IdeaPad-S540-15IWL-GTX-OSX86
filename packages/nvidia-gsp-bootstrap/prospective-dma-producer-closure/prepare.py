#!/usr/bin/env python3
"""Narrow source-bound BME commit and retained cleanup-mask identity guards."""
from pathlib import Path
import hashlib
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = 'packages/nvidia-gsp-bootstrap/prospective-dma-producer-closure'
SESSION = 'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.cpp'
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
IRQ = 'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/rc/S540NvidiaIrqOriginal.c'
GPU = 'src/nvidia/src/kernel/gpu/arch/maxwell/kern_gpu_gm107.c'
INPUTS = (SESSION, RECORD, IRQ)
ORIGINAL_INPUTS = (GPU,)
BASE_SHA256 = {
 SESSION: 'edcdb89fb766848c118af188c0426bf1edb9d520e6ec5995373d65e5c349e34d',
 RECORD: '56c7f4f082308255d1474475d7d64a9d7f088bd664508caaabeb7d0f687af496',
 IRQ: '5995e259aef081013bdcdb441f5aca7ee560d9fd693acf1d0e92e9726085e7fe',
 GPU: '5551162ba1a6c895eb4332074d49824b37b40d437755060c483371801c8670c9'}
COMPANIONS = {PREFIX + '/S540NvidiaDmaProducer.h': HERE / 'S540NvidiaDmaProducer.h'}
PROJECT_UNITS = ()
EXPORTS = {RECORD: ('s540FirstTxnCleanupMaskReadMaster',)}
COMPILE_DEFINITIONS = {}
INCLUDE_DIRECTORIES = (PREFIX, 'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure')
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

def once(text, before, after):
    if text.count(before) != 1: raise ValueError('DMA source anchor changed: ' + before[:90])
    return text.replace(before, after)

def modify(text, name, change):
    begin, end = function_span(text, name)
    return text[:begin] + change(text[begin:end]) + text[end:]

def exact(values, names):
    if set(values) != set(names): raise ValueError('Exact DMA source input set required')
    for name, text in values.items():
        if hashlib.sha256(text.encode()).hexdigest() != BASE_SHA256[name]:
            raise ValueError('DMA reviewed source identity changed: ' + name)

def transforms(values):
    exact(values, INPUTS)
    out = dict(values)
    for name in out:
        marker = '\n#include '
        index = out[name].find(marker)
        if index < 0: raise ValueError('DMA source include boundary missing')
        out[name] = out[name][:index] + '\n#include "S540NvidiaDmaProducer.h"' + out[name][index:]
    def write_config(body):
        old = '    return backend_.configWrite ? backend_.configWrite(backend_.context, offset, width, value) : NV_STATUS(NV_ERR_NOT_SUPPORTED);'
        new = '''    if (!backend_.configWrite) return NV_ERR_NOT_SUPPORTED;
    S540GspCancellationCommitLease commit = 0;
    if ((rmBound_ || hardwareDmaHeld_) &&
        s540DmaConfigWriteEnablesBusMaster(offset, width, value)) {
        if (!hardwareDmaState_) return NV_ERR_INVALID_STATE;
        const NV_STATUS accepted = s540GspCancellationCommitEnterState(hardwareDmaState_, &commit);
        if (accepted != NV_OK) return accepted;
    }
    const NV_STATUS written = backend_.configWrite(backend_.context, offset, width, value);
    const NV_STATUS completed = commit ?
        s540GspCancellationCommitLeaveState(hardwareDmaState_, commit) : NV_STATUS(NV_OK);
    return written != NV_OK ? written : completed;'''
        return once(body, old, new)
    out[SESSION] = modify(out[SESSION], 'Session::writeConfig', write_config)
    marker = '\nNV_STATUS s540FirstTxnIrqValidateDrained(void) {'
    out[RECORD] = once(out[RECORD], marker, '\n' + (HERE / 'cleanup-mask.c.inc').read_text() + marker)
    # Only full hardware masking gets the retained CLEANUP observer. The 1Hz
    # callback dispatcher retains the old OP/first-error authorizer unchanged.
    marker = '\nstatic NV_STATUS readLocks('
    wrapper = '''
static NV_STATUS maskMasterIdentity(nv_state_t *nv, S540FirstTxnGlobalSnapshot *out)
{
    NV_STATUS status = masterIdentity(nv, out);
    return status == NV_OK ? status : s540FirstTxnCleanupMaskReadMaster(nv, out);
}
'''
    out[IRQ] = once(out[IRQ], marker, wrapper + marker)
    out[IRQ] = once(out[IRQ], '    status = masterIdentity(nv, &epoch);',
        '    status = mask ? maskMasterIdentity(nv, &epoch) : masterIdentity(nv, &epoch);')
    out[IRQ] = once(out[IRQ], '    status = masterIdentity(nv, &recheck);',
        '    status = mask ? maskMasterIdentity(nv, &recheck) : masterIdentity(nv, &recheck);')
    return out

def original_transforms(values):
    exact(values, ORIGINAL_INPUTS)
    text = values[GPU]
    marker = '\n#include '
    index = text.find(marker)
    text = text[:index] + '\n#include "nv.h"\n#include "S540NvidiaDmaProducer.h"' + text[index:]
    def bus(body):
        old = '    GPU_REG_WR32(pGpu, DEVICE_BASE(NV_PCFG) + index, value);\n\n    return NV_OK;'
        new = '''    if (index & 3U) return NV_ERR_INVALID_ARGUMENT;
    S540GspCancellationCommitLease commit = 0;
    if (s540DmaConfigWriteEnablesBusMaster(index, 4, value)) {
        NV_STATUS accepted = s540GspCancellationCommitEnterState(NV_GET_NV_STATE(pGpu), &commit);
        if (accepted != NV_OK) return accepted;
    }
    GPU_REG_WR32(pGpu, DEVICE_BASE(NV_PCFG) + index, value);
    return commit ? s540GspCancellationCommitLeaveState(NV_GET_NV_STATE(pGpu), commit) : NV_OK;'''
        return once(body, old, new)
    text = modify(text, 'gpuWriteBusConfigReg_GM107', bus)
    def function(body):
        body = once(body, '    switch (function)',
            '    if (index & 3U) return NV_ERR_INVALID_ARGUMENT;\n\n    switch (function)')
        for name in ('NV_PCFG', 'NV_PCFG1'):
            old = '            GPU_REG_WR32_EX(pGpu, DEVICE_BASE(' + name + ') + index, data, pThreadState);'
            if name == 'NV_PCFG1': old = '    ' + old
            indent = ' ' * (12 if name == 'NV_PCFG' else 16)
            new = (indent + 'S540GspCancellationCommitLease commit = 0;\n' +
                indent + 'if (s540DmaConfigWriteEnablesBusMaster(index, 4, data)) {\n' +
                indent + '    NV_STATUS accepted = s540GspCancellationCommitEnterState(NV_GET_NV_STATE(pGpu), &commit);\n' +
                indent + '    if (accepted != NV_OK) return accepted;\n' + indent + '}\n' + old + '\n' +
                indent + 'if (commit) {\n' + indent + '    NV_STATUS completed = s540GspCancellationCommitLeaveState(NV_GET_NV_STATE(pGpu), commit);\n' +
                indent + '    if (completed != NV_OK) return completed;\n' + indent + '}')
            body = once(body, old, new)
        return body
    text = modify(text, 'gpuWriteFunctionConfigRegEx_GM107', function)
    return {GPU: text}
