#!/usr/bin/env python3
"""Reconstructed retained Owner source successor; original-entry gates stay closed."""
from pathlib import Path
import argparse,hashlib,json,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BOOTSTRAP='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
HEADER='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.hpp'
CONTEXT='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
PRIVATE_HEADER='packages/nvidia-gsp-bootstrap/prospective-retained-owner-recovery/S540NvidiaRetainedOwner.h'
INPUTS=(BOOTSTRAP,HEADER,CONTEXT)
IRQ_HEADER='packages/nvidia-gsp-bootstrap/prospective-irq-participant/S540NvidiaIrqParticipant.h'
RECORD_HEADER='packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'
sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def once(source,old,new):
    if source.count(old)!=1:raise ValueError('Exact retained Owner anchor required: '+old[:100])
    return source.replace(old,new,1)
def replace_function(source,name,replacement):
    begin,end=function_span(source,name)
    return source[:begin]+replacement+source[end:]
def transforms(values):
    if set(values)!=set(INPUTS):raise ValueError('Exact Bootstrap/header/Context input set required')
    out=dict(values);source=out[BOOTSTRAP]
    source=once(source,'#include "S540NvidiaGspBootstrap.hpp"',
        '#include "S540NvidiaGspBootstrap.hpp"\n#include "S540NvidiaGspFirstTransaction.h"\n'
        '#include "S540NvidiaFirstTxnContext.h"\n'
        '#include "../prospective-control-state/S540NvidiaControlState.h"\n'
        '#include "S540NvidiaIrqParticipant.h"\n'
        '#include "../prospective-retained-owner-recovery/S540NvidiaRetainedOwner.h"\n'
        '#include "S540NvidiaGlobalRm.h"')
    source=once(source,'    NV_STATUS failed(NV_STATUS failure) {',
        (HERE/'owner-retention.cpp.inc').read_text()+'\n    NV_STATUS failed(NV_STATUS failure) {\n'
        '        if(state.retainedOwnerAttempted||transport.hardwareDmaLifetimeHeld())return retainedFailure(failure);')
    source=once(source,'        host = true;\n#if defined(KERNEL)',
        '        host = true;\n'
        '        state.retainedOwnerAttempted=true;state.retainedForever=true;\n'
        '        status=s540FirstTxnBeginOwner(this);if(status!=NV_OK)return retainedFailure(status);\n'
        '        state.retainedOwnerStarted=true;\n'
        '        S540FirstTxnHostIdentity ownerIdentity{};\n'
        '        status=s540FirstTxnMasterIdentity(&ownerIdentity);if(status!=NV_OK)return retainedFailure(status);\n'
        '        state.ownerGeneration=ownerIdentity.generation;\n'
        '        status=s540ControlStatePrepare();if(status!=NV_OK)return retainedFailure(status);\n'
        '#if defined(KERNEL)')
    source=once(source,'        deviceBound = true;\n        status = S540NvidiaDeviceTransport::queryRmDmaRemap',
        '        deviceBound = true;\n'
        '        status=S540NvidiaDeviceTransport::beginRmHardwareDma(&transport);\n'
        '        if(status!=NV_OK)return retainedFailure(status);\n'
        '        status = S540NvidiaDeviceTransport::queryRmDmaRemap')
    source=once(source,'        __atomic_store_n(&cancellationToken, token, __ATOMIC_RELEASE);',
        '        __atomic_store_n(&cancellationToken, token, __ATOMIC_RELEASE);\n'
        '        status=s540GspCancellationBegin(token);if(status!=NV_OK)return retainedFailure(status);')
    # function_span starts at the function name; the original return type stays.
    source=replace_function(source,'initialize',
        (HERE/'owner-initialize.cpp.inc').read_text().strip().removeprefix('NV_STATUS '))
    source=once(source,'    NV_STATUS stop() {\n        if (state.cleanupComplete)',
        '    NV_STATUS stop() {\n'
        '        if(state.retainedOwnerAttempted||transport.hardwareDmaLifetimeHeld())return retainedStop();\n'
        '        if (state.cleanupComplete)')
    source=once(source,'        auto *self = static_cast<Impl *>(owner);\n        if (!self || !self->owned() || !self->context ||',
        '        auto *self = static_cast<Impl *>(owner);\n'
        '        if(self&&self->state.retainedOwnerAttempted)return NV_ERR_IN_USE;\n'
        '        if (!self || !self->owned() || !self->context ||')
    source=once(source,'        result.ownsResources = !state.cleanupComplete;',
        '        result.ownsResources = !state.cleanupComplete;\n'
        '        result.hardwareDmaHeld=transport.hardwareDmaLifetimeHeld();\n'
        '        result.globalInitialized=s540GlobalRmIsInitialized()!=0;')
    out[BOOTSTRAP]=source
    out[HEADER]=once(out[HEADER],'// prepare() success proves only real resource/binding preparation. initialize()\n// unconditionally refuses BEFORE every original global/adapter entry: the ABI,',
        '// This retained successor starts its permanent owner before Context/firmware\n'
        '// allocation. Initialize calls the still-gated global lifecycle and binds\n'
        '// nv/services only after validated global return. Adapter entry retains\n'
        '// the immutable gates: the ABI,')
    out[HEADER]=once(out[HEADER],'    NvU64 workerThread;',
        '    NvU64 workerThread;\n'
        '    bool retainedOwnerAttempted,retainedOwnerStarted,retainedForever,hardwareDmaHeld;\n'
        '    bool globalAttempted,firstTransactionBound,privatePreparationAttempted,privatePrepared;\n'
        '    bool irqPreparationAttempted,adapterEntryAttempted,shutdownProtocolAttempted,shutdownProtocolCompleted;\n'
        '    NV_STATUS firstRetainedStatus,shutdownProtocolStatus;\n    NvU64 ownerGeneration;')
    source=out[CONTEXT]
    source=once(source,'#include "S540NvidiaGspContext.h"',
        '#include "S540NvidiaGspContext.h"\n'
        '#include "../prospective-retained-owner-recovery/S540NvidiaRetainedOwner.h"\n'
        '#include "../prospective-shutdown-protocol/S540NvidiaShutdownProtocol.h"\n'
        '#include "S540NvidiaIrqParticipant.h"')
    source=once(source,'    NvU64 firstTxnGeneration;',
        '    NvU64 firstTxnGeneration;\n    NvU64 retainedOwnerGeneration;\n'
        '    NvBool retainedShutdownAttempted;\n    S540ShutdownProtocolEvidence retainedShutdown;')
    source=once(source,'    allocationBase = s540GlobalRmHostAllocate(sizeof(*context) + 15);',
        '    S540FirstTxnHostIdentity ownerIdentity={0};\n'
        '    status=s540FirstTxnMasterIdentity(&ownerIdentity);if(status!=NV_OK)return status;\n'
        '    allocationBase = s540GlobalRmHostAllocate(sizeof(*context) + 15);')
    source=once(source,'    context->ownerThread = thread;',
        '    context->ownerThread = thread;\n    context->retainedOwnerGeneration=ownerIdentity.generation;')
    source=once(source,'fail:\n    if (s540GspContextDestroy(context, NV_TRUE, NULL) != NV_OK) {',
        'fail:\n    if(context->retainedOwnerGeneration){context->state.quarantined=NV_TRUE;*out=context;\n'
        '        s540FirstTxnObserveServiceRefusal(9,2,status);return status;}\n'
        '    if (s540GspContextDestroy(context, NV_TRUE, NULL) != NV_OK) {')
    source=once(source,'    if (!owner(context) || !context->nv.handle || !s540GlobalRmIsInitialized() || !cleanHost() ||',
        '    if (!owner(context) || !context->firstTxnGeneration || !context->nv.handle || !s540GlobalRmIsInitialized() || !cleanHost() ||')
    source=once(source,'    if (!owner(context) || !context->state.privateState || context->firstTxnGeneration ||\n        context->state.adapterAttempted || context->state.quarantined)',
        '    if (!owner(context) || context->state.privateState || context->state.eventLocks || context->firstTxnGeneration ||\n'
        '        context->state.adapterAttempted || context->state.quarantined)')
    source=once(source,'    status = s540FirstTxnBind(&context->nv, token);',
        '    S540FirstTxnGlobalSnapshot epoch={0};\n'
        '    status=s540FirstTxnGlobalReadMaster(&epoch);\n'
        '    if(status!=NV_OK||epoch.nv||epoch.generation!=context->retainedOwnerGeneration||\n'
        '        epoch.state!=S540_FIRST_GLOBAL_READY||!epoch.validated||!epoch.originalReturned||epoch.originalStatus!=NV_OK)\n'
        '        return status==NV_OK?NV_ERR_NOT_READY:status;\n'
        '    status = s540FirstTxnBind(&context->nv, token);')
    for name in ('s540GspContextReleaseOriginalState','s540GspContextDestroy'):
        begin,end=function_span(source,name);body=source[begin:end];brace=body.index('{')+1
        body=body[:brace]+'\n    if(context&&context->retainedOwnerGeneration)return NV_ERR_IN_USE;'+body[brace:]
        source=source[:begin]+body+source[end:]
    out[CONTEXT]=source+'\n'+(HERE/'context-retention.c.inc').read_text()
    return out

def validate_dependencies(manifest,project):
    profiles=manifest.get('fixed_source_profiles',{})
    required=('irq_participant','global_epoch','retained_backends','retained_diagnostic','shutdown_protocol')
    if any(profiles.get(name) is not True for name in required):
        raise ValueError('Retained Owner requires actual IRQ, epoch, backend, Host and shutdown source profiles')
    checks={RECORD_HEADER:('s540FirstTxnMasterIdentity','s540FirstTxnGlobalReadMaster'),
        IRQ_HEADER:('s540GspIrqInstall','s540IrqParticipantValidateDrained'),
        'packages/nvidia-gsp-bootstrap/prospective-control-state/S540NvidiaControlState.c':('portSyncSpinlockInitialize','s540FirstTxnMasterIdentity')}
    for name,symbols in checks.items():
        path=project/name
        if not path.is_file() or any(symbol not in path.read_text() for symbol in symbols):
            raise ValueError('Concrete retained Owner dependency missing: '+name)

def prepare(composition,output):
    sys.path.insert(0,str(ROOT/'builders'));import compose_nvidia_first_transaction as composer
    composition=Path(composition).resolve(strict=True)
    if composition.is_file():composition=composition.parent
    manifest=composer.verify_composition(composition);project=composition/'project'
    validate_dependencies(manifest,project)
    values={name:(project/name).read_text() for name in INPUTS}
    changed=transforms(values);output=composer.new_output(Path(output),[composition,HERE]);output.mkdir(parents=True)
    rows=[]
    for name,value in changed.items():
        path=output/'project'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
        rows.append({'source':name,'input_sha256':sha(project/name),'output_sha256':sha(path)})
    header=output/'project'/PRIVATE_HEADER;header.parent.mkdir(parents=True,exist_ok=True);header.write_bytes((HERE/'S540NvidiaRetainedOwner.h').read_bytes())
    report={'format':1,'component':'reconstructed-retained-owner-source','sources':rows,'private_header':PRIVATE_HEADER,
        'composition_sha256':sha(composition/'composition.json'),'kernel_global_gate_preserved':True,
        'original_entry_admission':False,'hardware_dma_stop_receipt':False,'physical_release_authorized':False}
    (output/'source-successor.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.composition,args.output),indent=2))
