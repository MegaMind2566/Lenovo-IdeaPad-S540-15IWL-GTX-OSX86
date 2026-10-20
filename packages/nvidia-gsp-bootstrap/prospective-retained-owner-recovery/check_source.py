#!/usr/bin/env python3
"""Fresh structural source controls only; no native, kernel, or hardware execution."""
from pathlib import Path
import argparse,importlib.util,json,sys
import prepare as candidate
HERE=candidate.HERE;ROOT=candidate.ROOT

def run(output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Fresh source-control output required')
    if not output.is_relative_to(ROOT/'build'):raise ValueError('Controls must write under the repository build directory')
    sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/services'))
    import prepare_context
    observed={p:candidate.sha(ROOT/p) for p in candidate.INPUTS}
    prepare_context.prepare(output/'first-transaction-context')
    values={candidate.BOOTSTRAP:(ROOT/candidate.BOOTSTRAP).read_text(),
        candidate.HEADER:(ROOT/candidate.HEADER).read_text(),
        candidate.CONTEXT:(output/'first-transaction-context/S540NvidiaGspContext.c').read_text()}
    changed=candidate.transforms(values);checks=[]
    def expect(condition,name):
        if not condition:raise ValueError(name)
        checks.append(name)
    def ordered(source,*markers):
        positions=[source.index(marker) for marker in markers]
        return positions==sorted(positions) and len(positions)==len(set(positions))
    boot=changed[candidate.BOOTSTRAP];context=changed[candidate.CONTEXT]
    expect(ordered(boot,'status = s540GlobalRmHostInitialize','status=s540FirstTxnBeginOwner(this)',
        'status=s540ControlStatePrepare()','status = s540GspContextCreate'),
        'Host, permanent owner, unbound control state precede Context allocation')
    expect(ordered(boot,'status = s540GspCancellationBind','status=s540GspCancellationBegin(token)',
        'status = S540NvidiaDeviceTransport::bindRmDevice','status=S540NvidiaDeviceTransport::beginRmHardwareDma',
        'status = S540NvidiaDeviceTransport::queryRmDmaRemap','gsp = s540GlobalRmHostAllocate'),
        'Cancellation operation and immediate actual DMA hold precede firmware allocation')
    begin,end=candidate.function_span(boot,'initialize');initialize=boot[begin:end]
    expect(ordered(initialize,'s540GlobalRmInitialize','s540FirstTxnGlobalReadMaster',
        's540GspContextBindFirstTransaction','s540ControlStateBindAdapter','s540GspContextPrepare',
        's540GspIrqInstall','if(kBlockedGates)','s540GspContextInitializeAdapter'),
        'Global validation, single Context binding, private, IRQ and immutable adapter gate are ordered')
    expect(boot.count('s540GspContextBindFirstTransaction(')==1 and 's540FirstTxnBind(' not in boot,
        'Owner never separately duplicates the strong bind owned by Context')
    expect('NV_STATUS NV_STATUS' not in boot,'Replacement preserves one return type')
    gate='constexpr NvU32 kBlockedGates = OriginalAbiClosure | PowerLifetime |\n    AllocationRetirementUnderActiveIrq | OriginalStackBoundary;'
    expect(gate in boot,'Existing immutable blocked gate declaration is unchanged')
    for name in ('failed','stop'):
        begin,end=candidate.function_span(boot,name)
        expect('state.retainedOwnerAttempted||transport.hardwareDmaLifetimeHeld()' in boot[begin:end],
            name+' dispatches retained attempts before legacy cleanup')
    begin,end=candidate.function_span(boot,'retainedStop');stop=boot[begin:end]
    expect(ordered(stop,'transport.stopInterrupt()','s540GspContextStopRetainedServices',
        's540GspContextRunRetainedShutdownProtocol'),'Actual interrupt stop and source seal precede retained shutdown protocol')
    forbidden=('s540GlobalRmHostFree(','s540GspContextDestroy(','s540GspContextReleaseOriginalState(',
        's540GspCancellationFinish(','s540GspCancellationUnbind(','drainRmRetirements(',
        'firmware.shutdown(','acknowledgeRevocation(','dispatcher.stop(','~Impl(')
    expect(not any(word in stop for word in forbidden),'Retained stop contains no legacy physical cleanup')
    begin,end=candidate.function_span(context,'s540GspContextBindFirstTransaction');bind=context[begin:end]
    expect(ordered(bind,'s540FirstTxnGlobalReadMaster','s540FirstTxnBind','s540FirstTxnServicesBind'),
        'Actual Context waits for unbound validated epoch then owns both bindings')
    expect('context->state.privateState || context->state.eventLocks' in bind and
        'epoch.generation!=context->retainedOwnerGeneration' in bind and 'epoch.originalStatus!=NV_OK' in bind,
        'Context binding requires exact retained generation and pristine private state')
    expect(ordered(context,'status=s540FirstTxnMasterIdentity(&ownerIdentity)',
        'allocationBase = s540GlobalRmHostAllocate','context->retainedOwnerGeneration=ownerIdentity.generation'),
        'Context allocation captures genuine retained owner generation')
    for name in ('s540GspContextReleaseOriginalState','s540GspContextDestroy'):
        begin,end=candidate.function_span(context,name)
        expect('if(context&&context->retainedOwnerGeneration)return NV_ERR_IN_USE;' in context[begin:end],
            name+' refuses retained original state')
    expect('if(context->retainedOwnerGeneration){context->state.quarantined=NV_TRUE;*out=context;' in context,
        'Partial Context construction publishes its retained pointer instead of destroying backing')
    begin,end=candidate.function_span(context,'s540GspContextRunRetainedShutdownProtocol');shutdown=context[begin:end]
    expect(ordered(shutdown,'s540IrqParticipantValidateDrained','s540ShutdownProtocolRun'),
        'Shutdown takes actual drained IRQ evidence, no caller readiness value')
    try:candidate.transforms(changed)
    except ValueError:checks.append('Duplicate successor application fails closed')
    else:raise ValueError('Duplicate transform unexpectedly accepted')
    try:candidate.validate_dependencies({},ROOT)
    except ValueError:checks.append('Missing concrete predecessor profiles fail closed')
    else:raise ValueError('Absent dependency profiles unexpectedly accepted')
    forged={'fixed_source_profiles':{k:True for k in ('irq_participant','global_epoch','retained_backends','retained_diagnostic','shutdown_protocol')}}
    try:candidate.validate_dependencies(forged,ROOT)
    except ValueError:checks.append('Profile Booleans cannot substitute for absent actual dependency APIs')
    else:raise ValueError('Forged dependency profile unexpectedly accepted')
    rows=[]
    for name,value in changed.items():
        path=output/'project'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
        rows.append({'source':name,'input_sha256':__import__('hashlib').sha256(values[name].encode()).hexdigest(),
            'output_sha256':candidate.sha(path)})
    header=output/'project'/candidate.PRIVATE_HEADER;header.parent.mkdir(parents=True,exist_ok=True)
    header.write_bytes((HERE/'S540NvidiaRetainedOwner.h').read_bytes())
    expect(all(candidate.sha(ROOT/name)==digest for name,digest in observed.items()),'Restored source inputs remain unchanged')
    report={'format':1,'status':'passed','kind':'fresh-structural-source-controls-only','checks':checks,
        'source_rows':rows,'restored_source_sha256':observed,'native_execution':'not_run','kernel_compilation':'not_run',
        'original_entry_admission':False,'hardware_admission':False,'stop_receipt_issued':False,'physical_release_authorized':False}
    (output/'source-controls.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    r=run(p.parse_args().output);print(json.dumps({'status':r['status'],'source_checks':len(r['checks']),'native_execution':r['native_execution'],'kernel_compilation':r['kernel_compilation']}))
