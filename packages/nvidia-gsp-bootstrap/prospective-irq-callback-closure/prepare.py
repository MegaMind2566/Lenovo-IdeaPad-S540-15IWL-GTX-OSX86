#!/usr/bin/env python3
"""Opt-in source successor: genuine IRQ scopes, public BH callout and retention.

No production gates, original policy rows, hardware-stop receipts or final
release issuers are added. transforms() consumes an already composed project.
"""
from pathlib import Path
import argparse
import hashlib
import json

HERE=Path(__file__).resolve().parent
BASE='packages/nvidia-device-transport/src/'
DEVICE=BASE+'S540NvidiaDarwinDevice.cpp'
TRANSPORT=BASE+'S540NvidiaDeviceTransport.hpp'
RECORD='packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
CANCEL='packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c'
CANCEL_ORIGIN='packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps/S540NvidiaGspCancellation.c'
PARTICIPANTS='packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps/Participants.h'
INPUTS=(DEVICE,TRANSPORT,RECORD,CANCEL,CANCEL_ORIGIN,PARTICIPANTS)
ORIGINAL='packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/rc/S540NvidiaIrqOriginal.c'
EXPORTS={
    DEVICE:('s540FirstTxnIrqReadContext',),
    RECORD:('s540FirstTxnIrqBind','s540FirstTxnIrqCheckArm','s540FirstTxnIrqEnter',
        's540FirstTxnIrqLeave','s540FirstTxnIrqOrigin','s540FirstTxnIrqReadEnteredScope',
        's540FirstTxnIrqValidateDrained','s540FirstTxnIrqValidateSoftwareDrained'),
    CANCEL:('s540GspCancellationEnterIrqScope','s540GspCancellationLeaveIrqScope',
        's540GspCancellationIrqOrigin'),
    ORIGINAL:('s540FirstTxnIrqMaskHardware','s540FirstTxnDrainQueued1Hz'),
}

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('IRQ source anchor missing or ambiguous: '+old[:100])
    return text.replace(old,new,1)

def function(text,signature,replacement):
    if text.count(signature)!=1:raise ValueError('IRQ function changed: '+signature)
    first=text.index(signature);last=text.index('\n}\n',first)+3
    return text[:first]+replacement.rstrip()+'\n'+text[last:]

def transforms(values):
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    for name,expected in contract['candidate_sha256'].items():
        path=HERE/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Pinned IRQ successor changed: '+name)
    out=dict(values)
    text=out[DEVICE]
    text=once(text,'#include <kern/thread_call.h>',
        '#include <kern/clock.h>\n'
        '#include "../../nvidia-darwin-services/src/S540NvidiaPublicCallout.hpp"\n'
        '#include "../../nvidia-gsp-bootstrap/prospective-irq-callback-closure/S540NvidiaIrqClosure.h"\n'
        '#include "../../nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"\n'
        '#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"\n'
        '#if !defined(S540_NVIDIA_IRQ_CALLBACK_CLOSURE) || S540_NVIDIA_IRQ_CALLBACK_CLOSURE != 1\n'
        '#error "Explicit IRQ callback closure profile required"\n#endif')
    text=once(text,'struct Platform {','''struct Platform {
    S540FirstTxnHostIdentity backendIdentity;
    Platform *retainedNext;
    NvU32 permanentRetention;
    NvU64 irqGeneration,topThread,bottomThread;
    NvU32 topStage,bottomStage,bottomOrigin;
    bool drained;
    IODMACommand *retainedBypassProbe;''')
    text=once(text,'    thread_call_t bottomHalf;','    S540PublicCallout bottomHalf;')
    text=once(text,'struct Allocation {',(HERE/'backend-lifetime.hpp.inc').read_text()+'\nstruct Allocation {')
    text=function(text,'void releaseBypassProbe(','''void releaseBypassProbe(void *opaque,void *probe) {
    auto *p=static_cast<Platform *>(opaque);
    if(probe==p->retainedBypassProbe)return;
    IrqBackendRelease release(p);
    if(release.status!=NV_OK){p->retainedBypassProbe=static_cast<IODMACommand *>(probe);return;}
    static_cast<IODMACommand *>(probe)->release();
}''')
    # A retained actual kBypassed probe remains the route's factory witness.
    # Each reuse still passes the original current platform/provider/mapper
    # observations before and after borrowing it. Never overwrite a held probe.
    text=once(text,'    // Pinned XNU PE start sets mapper-required before publishing getPlatform.',
        '    auto *p=static_cast<Platform *>(opaque);\n'
        '    if(p->retainedBypassProbe){*out=p->retainedBypassProbe;return NV_OK;}\n'
        '    // Pinned XNU PE start sets mapper-required before publishing getPlatform.')
    anchor='''        if (p->registers) { p->registers->release(); p->registers = nullptr; }'''
    text=once(text,anchor,'''        IrqBackendRelease release(p);
        if(release.status!=NV_OK)return release.status;
'''+anchor)
    anchor='''NV_STATUS stop(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);'''
    text=once(text,anchor,anchor+'''
    IrqBackendRelease release(p);
    if(release.status!=NV_OK)return release.status;''')
    bodies=(HERE/'irq-bodies.cpp.inc').read_text()
    for signature in ('void bottomHalf(','void interrupt(','NV_STATUS installInterrupt(','NV_STATUS stopInterrupt('):
        first=bodies.index(signature);last=bodies.index('\n}\n',first)+3
        text=function(text,signature,bodies[first:last])
    text=once(text,'    p->controllerEnableAttempted = true;',
        '    __atomic_store_n(&p->drained,false,__ATOMIC_RELEASE);\n    p->controllerEnableAttempted = true;')
    text=once(text,'    p->hardwareMaskRequired = true;',
        '    __atomic_store_n(&p->hardwareMaskRequired,true,__ATOMIC_RELEASE);')
    arm='''NV_STATUS armInterrupt(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);'''
    text=once(text,arm,arm+'''
    if(!p->controllerAttached||s540FirstTxnIrqCheckArm(p)!=NV_OK)return NV_ERR_INVALID_STATE;''')
    query='''extern "C" NV_STATUS s540FirstTxnIrqReadContext(const void *backend,NvU32 role,S540FirstTxnIrqContext *out) {
    Platform *p=__atomic_load_n(&registeredIrqBackend,__ATOMIC_ACQUIRE);
    if(!out||!backend||backend!=p||role>2)return NV_ERR_INVALID_ARGUMENT;
    S540FirstTxnIrqContext value{};
    value.nv=p->interrupt.originalState;value.generation=p->irqGeneration;
    value.topStage=__atomic_load_n(&p->topStage,__ATOMIC_ACQUIRE);
    value.bottomStage=__atomic_load_n(&p->bottomStage,__ATOMIC_ACQUIRE);
    value.pending=__atomic_load_n(&p->pending,__ATOMIC_ACQUIRE);
    value.callbacks=__atomic_load_n(&p->callbacks,__ATOMIC_ACQUIRE);
    value.accepting=__atomic_load_n(&p->accepting,__ATOMIC_ACQUIRE);
    value.controllerAttached=__atomic_load_n(&p->controllerAttached,__ATOMIC_ACQUIRE);
    value.drained=__atomic_load_n(&p->drained,__ATOMIC_ACQUIRE);
    value.maskRequired=__atomic_load_n(&p->hardwareMaskRequired,__ATOMIC_ACQUIRE);
    if(role==S540_FIRST_IRQ_TOP && ml_at_interrupt_context()) {
        value.stage=value.topStage;value.thread=__atomic_load_n(&p->topThread,__ATOMIC_ACQUIRE);
    } else if(role==S540_FIRST_IRQ_BOTTOM && ordinary(p)) {
        value.stage=value.bottomStage;value.thread=__atomic_load_n(&p->bottomThread,__ATOMIC_ACQUIRE);
        value.origin=__atomic_load_n(&p->bottomOrigin,__ATOMIC_ACQUIRE);
    }
    *out=value;return NV_OK;
}
'''
    text=once(text,'void S540NvidiaDeviceTransport::destroyDarwinBackend(void *opaque) {',
        query+'\nvoid S540NvidiaDeviceTransport::destroyDarwinBackend(void *opaque) {\n'
        '    IrqBackendRelease release(static_cast<Platform *>(opaque));\n'
        '    if(release.status!=NV_OK)return;')
    anchor='''    auto *platform = static_cast<Platform *>(IOMalloc(sizeof(Platform)));'''
    text=once(text,anchor,'''    IrqBackendScope construction;
    if(construction.status!=NV_OK)return construction.status;
'''+anchor)
    anchor='''    *platform = Platform{}; platform->provider = provider; platform->owner = owner;'''
    text=once(text,anchor,anchor+'\n    platform->backendIdentity=construction.identity;')
    text=once(text,'    else if (!active()) IOFree(platform, sizeof(*platform));',
        '    else if (!active()) destroyDarwinBackend(platform);')
    if 'thread_call_' in text:raise ValueError('Private IRQ thread-call API survived')
    out[DEVICE]=text
    out[TRANSPORT]=once(out[TRANSPORT],'    bool (*readyToArm)(void *context);',
        '    bool (*readyToArm)(void *context);\n'
        '    const void *originalState; // exact immutable nv_state_t, required by IRQ participant')
    text=out[RECORD]
    text=once(text,'#include "S540NvidiaGspFirstTransaction.h"',
        '#include "S540NvidiaGspFirstTransaction.h"\n#include "../../prospective-irq-callback-closure/S540NvidiaIrqClosure.h"')
    text=once(text,'SITE_HOST=9','SITE_HOST=9, SITE_IRQ=12')
    text=once(text,'static NvBool authorized(void) {',
        'static NvBool irqAuthorized(NvU64);\nstatic NvBool authorized(void) {')
    text=once(text,'active(work,tid)>=0 || active(direct,tid)>=0);',
        'active(work,tid)>=0 || active(direct,tid)>=0 || irqAuthorized(tid));')
    text=once(text,'NV_STATUS s540FirstTxnBeginOwner(',
        (HERE/'record-api.c.inc').read_text()+'\nNV_STATUS s540FirstTxnBeginOwner(')
    anchor='''    status=s540FirstTxnServicesSealAndDrain(nv,LD(&record.generation));if(status!=NV_OK)return refuse(status,SITE_SERVICE);'''
    text=once(text,anchor,anchor+'\n    status=s540FirstTxnIrqValidateDrained();if(status!=NV_OK)return refuse(status,SITE_IRQ);')
    out[RECORD]=text
    text=out[PARTICIPANTS]
    text=once(text,'typedef NvU64 S540GspCancellationLease;',
        'NV_STATUS s540GspCancellationEnterIrqScope(const void *, NvU32 role, NvU32 inheritedOrigin);\n'
        'NV_STATUS s540GspCancellationLeaveIrqScope(const void *, NvU32 role);\n'
        'NvU32 s540GspCancellationIrqOrigin(NvU32 role);\n'
        'NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *, NvU32 role, NvU32 *actualOrigin);\n'
        'typedef NvU64 S540GspCancellationLease;')
    out[PARTICIPANTS]=text
    text=out[CANCEL]
    if text!=out[CANCEL_ORIGIN]:raise ValueError('Composed cancellation participant and origin differ')
    text=once(text,'static NvBool leasesPending(void) {',
        'static NvBool irqScopePending(void);\nstatic NvBool leasesPending(void) {\n'
        '    if(irqScopePending())return NV_TRUE;')
    text=once(text,'static NvU64 currentOrigin(NvU64 value) {',
        'static NvU64 irqScopeOrigin(NvU64,NvU64);\nstatic NvU64 currentOrigin(NvU64 value) {')
    text=once(text,'    if (ownerThread()) return value & CLEANUP ? CLEANUP : value & OPERATION ? OPERATION : 0;',
        '    { NvU64 interrupted=irqScopeOrigin(value,tid);if(interrupted)return interrupted; }\n'
        '    if (ownerThread()) return value & CLEANUP ? CLEANUP : value & OPERATION ? OPERATION : 0;')
    text=once(text,'NV_STATUS s540GspCancellationCaptureCurrent(',
        (HERE/'cancellation-api.c.inc').read_text()+'\nNV_STATUS s540GspCancellationCaptureCurrent(')
    # Reserve the same publication word before checking pending scopes. This
    # also closes an existing capture/finish ABA window for ordinary leases.
    finish='''NV_STATUS s540GspCancellationFinish(S540GspCancellationToken token) {
    NvU64 value=word(),reserved;
    if(!owner()||!matches(value,token))return NV_ERR_INVALID_STATE;
    for(;;) {
        if(!matches(value,token))return NV_ERR_INVALID_STATE;
        if(value&(CAPTURE_BUSY|PUBLISHING))return NV_ERR_IN_USE;
        reserved=value|CAPTURE_BUSY;
        if(__atomic_compare_exchange_n(&slot.control,&value,reserved,NV_FALSE,
            __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))break;
    }
    if(leasesPending()) {
        __atomic_fetch_and(&slot.control,~(NvU64)CAPTURE_BUSY,__ATOMIC_RELEASE);return NV_ERR_IN_USE;
    }
    // Preserve a concurrent revocation publication; only phase/busy are ours.
    __atomic_fetch_and(&slot.control,~(NvU64)(OPERATION|CLEANUP|CAPTURE_BUSY),__ATOMIC_RELEASE);
    return NV_OK;
}'''
    text=function(text,'NV_STATUS s540GspCancellationFinish(',finish)
    # Unbind starts only after Finish removed both phases; new IRQ/capture
    # admission then refuses. Its existing CAS handles a racing revocation.
    out[CANCEL]=out[CANCEL_ORIGIN]=text
    return out

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(composition,output):
    composition=composition.resolve(strict=True);manifest=json.loads(composition.read_text())
    if manifest.get('status')!='materialized-source-only':raise ValueError('Complete source-only composition required')
    project=(composition.parent/manifest['project']).resolve(strict=True);output=output.resolve()
    if output.exists() or output.is_relative_to(project) or project.is_relative_to(output):
        raise ValueError('Fresh output outside input project required')
    values={};inputs={}
    for name in INPUTS:
        path=project/name;expected=manifest['project_files'][name]['sha256']
        if path.is_symlink() or sha(path)!=expected:raise ValueError('Composed IRQ input changed: '+name)
        values[name]=path.read_text();inputs[name]=expected
    changed=transforms(values);output.mkdir(parents=True);rows={}
    for name,value in changed.items():
        path=output/'project'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
        rows[name]={'source':path.relative_to(output).as_posix(),'input_sha256':inputs[name],'output_sha256':sha(path)}
    if any(sha(project/name)!=value for name,value in inputs.items()):raise ValueError('IRQ input changed during preparation')
    report={'format':1,'mode':'irq-callback-public-callout-retained-backends','sources':rows,
        'composition_sha256':sha(composition),'hardware_stop_receipt_issued':False,
        'production_candidate_allowed':False,'original_entry_admission':False,'production_default_changed':False,
        'additional_required_project_header':'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/S540NvidiaIrqClosure.h',
        'required_define':'S540_NVIDIA_IRQ_CALLBACK_CLOSURE=1'}
    (output/'project-successor.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(prepare(args.composition,args.output),indent=2))
