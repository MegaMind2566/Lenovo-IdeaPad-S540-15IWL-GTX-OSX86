#!/usr/bin/env python3
"""Actual original TX/msgq body controls with genuine composed cancellation.

Only GPU register, timeout, clock, copy-notification and CC endpoints are fixtures.
The full changed original translation unit is independently cross-compiled by
the integrated original-source compiler; these controls execute its exact body.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import prepare
sys.path.insert(0,str(ROOT/'builders'))
import compose_nvidia_first_transaction as composer
sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

MSGQ='src/nvidia/src/libraries/msgq/msgq.c'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def body(text,name,return_type):
    first,last=function_span(text,name)
    return return_type+' '+text[first:last]+'\n'
def run(command,cwd,log,environment=None):
    result=subprocess.run([str(x) for x in command],cwd=cwd,text=True,capture_output=True,
        timeout=120,env=environment)
    log.write_text('stdout:\n'+result.stdout+'\nstderr:\n'+result.stderr)
    if result.returncode:raise RuntimeError('Command failed; see '+str(log)+'\n'+result.stderr)
    return result.stdout

def check(args):
    if not args.host_control:raise ValueError('CPU execution requires explicit --host-control')
    composition=args.composition.resolve(strict=True)
    if composition.is_file():composition=composition.parent
    manifest=composer.verify_composition(composition)
    output=composer.new_output(args.output,[composition,HERE,args.upstream])
    output.mkdir(parents=True)
    source=composition/'source'
    original=(source/prepare.TX).read_text()
    changed=prepare.original_transforms({prepare.TX:original})[prepare.TX]
    msgq=(source/MSGQ).read_text()
    # Reuse the exact complete original include preamble and original types.
    preamble=original[:original.index('static void _gspMsgQueueCleanup')]
    exact=body(msgq,'msgqTxGetFreeSpace','unsigned')
    exact+=body(msgq,'msgqTxGetWriteBuffer','void *')
    exact+=body(msgq,'msgqTxSubmitBuffers','int')
    baseline=body(original,'GspMsgQueueSendCommand','NV_STATUS')
    baseline=baseline.replace('GspMsgQueueSendCommand(', 's540TxUnmodifiedOriginal(',1)
    exact+=baseline+body(changed,'GspMsgQueueSendCommand','NV_STATUS')
    fixture=(HERE/'tests/tx-control.c.inc').read_text()
    if fixture.count('/* EXACT_ACTUAL_BODIES */')!=1:raise ValueError('Exact TX fixture marker required')
    fixture=preamble+'\n'+fixture.replace('/* EXACT_ACTUAL_BODIES */',exact)
    generated=output/'actual-tx-control.c';generated.write_text(fixture)
    changed_path=output/'changed-message-queue-cpu.c';changed_path.write_text(changed)
    raw_flags=composer.composed_bridge_flags(args.upstream,composition,args.cc)
    kernel_only={'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx',
        '-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}
    flags=[x for x in raw_flags if x not in kernel_only]
    flags+=['-fPIC','-U__linux__','-U__linux','-O1','-g','-std=gnu11',
        '-Werror','-Wno-unused-parameter','-ffunction-sections','-fdata-sections']
    sources=[generated,
        composition/'project/packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellationOriginal.c',
        composition/'project/packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c']
    environment=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    results={};dependencies={}
    for label,instrumentation in [('native',[]),('sanitized',[
        '-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
        folder=output/label;folder.mkdir();objects=[]
        for index,path in enumerate(sources):
            obj=folder/f'part-{index}.o';dep=obj.with_suffix('.d')
            run([args.cc,*flags,*instrumentation,'-MD','-MF',dep,'-c',path,'-o',obj],
                output,obj.with_suffix('.log'))
            objects.append(obj)
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                p=Path(name);p=(output/p).resolve(strict=True) if not p.is_absolute() else p.resolve(strict=True)
                current=digest(p)
                if dependencies.setdefault(str(p),current)!=current:raise ValueError('Dependency changed during controls')
        binary=folder/'check'
        run([args.cc,*instrumentation,*objects,'-Wl,--gc-sections','-o',binary],output,folder/'link.log')
        result=json.loads(run([binary],output,folder/'run.log',environment))
        if result.get('status')!='passed' or result.get('failures') or result.get('pm_30_second_shutdown_bound_proven') is not False:
            raise ValueError('TX controls changed their scope or failed')
        results[label]=result
    for name,expected in dependencies.items():
        if digest(Path(name))!=expected:raise ValueError('Compiler-observed TX input changed: '+name)
    if composer.verify_composition(composition)!=manifest:raise ValueError('Composition changed during TX controls')
    report={'format':1,'component':'exact-original-gsp-tx-cancellation-controls','status':'passed',
        'composition_sha256':digest(composition/'composition.json'),
        'input_source_sha256':{prepare.TX:digest(source/prepare.TX),MSGQ:digest(source/MSGQ)},
        'changed_tx_source_sha256':digest(changed_path),'generated_actual_body_control_sha256':digest(generated),
        'dependency_sha256':dependencies,'results':results,
        'actual_original_send_and_msgq_bodies':True,'actual_composed_cancellation_record':True,
        'hardware_register_and_clock_endpoints_are_fixtures':True,
        'partial_fragments_remain_unpublished_on_observed_cancel':True,
        'concurrent_pm_revoke_and_submit_share_commit_word':False,
        'accepted_commit_is_not_relabelled_aborted':True,
        'pm_30_second_shutdown_bound_proven':False,'original_entry_admission':False,'hardware_stop_proven':False}
    (output/'tx-cancellation-controls.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'passed','checks':{k:v['checks'] for k,v in results.items()},'pm_deadline_closed':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cc',type=Path,required=True)
    parser.add_argument('--host-control',action='store_true')
    check(parser.parse_args())
