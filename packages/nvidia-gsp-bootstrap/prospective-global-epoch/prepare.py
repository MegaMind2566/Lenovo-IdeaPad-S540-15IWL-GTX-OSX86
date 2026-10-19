#!/usr/bin/env python3
"""Isolated permanent global-owner epoch; emits exactly three changed files."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RECORD='packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
HEADER=RECORD[:-1]+'h'
LIFECYCLE='packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'
INPUTS=(RECORD,HEADER,LIFECYCLE)
sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Exact global epoch anchor missing or ambiguous: '+old[:100])
    return text.replace(old,new)
def transforms(values):
    if set(values)!=set(INPUTS):raise ValueError('Exact global epoch source set required')
    out=dict(values)
    out[RECORD]=once(out[RECORD],'SITE_HOST=9','SITE_HOST=9, SITE_GLOBAL=11')
    out[RECORD]=once(out[RECORD],'static NvU64 lastEpoch;',
        'static struct { NvU32 state,originalStatus,validationStatus,originalReturned,validated;\n'
        '    const void *owner; NvU64 generation,thread; } globalEpoch;\nstatic NvU64 lastEpoch;')
    out[RECORD]=once(out[RECORD],'NV_STATUS s540FirstTxnBeginOwner(',
        (HERE/'global-api.c.inc').read_text()+'\nNV_STATUS s540FirstTxnBeginOwner(')
    out[HEADER]=once(out[HEADER],'NV_STATUS s540FirstTxnHostCaptureAllocation(',
        (HERE/'global-api.h.inc').read_text()+'\nNV_STATUS s540FirstTxnHostCaptureAllocation(')
    lifecycle=out[LIFECYCLE]
    lifecycle=once(lifecycle,'#include "core/system.h"',
        '#include "core/system.h"\n#include "os/os.h"\n'
        '#include "S540NvidiaGspFirstTransaction.h"\n'
        '#include "S540ProspectiveRmLockOwnership.h"')
    lifecycle=once(lifecycle,'extern void RmShutdownRm(void);\n','')
    start,end=function_span(lifecycle,'cleanShutdown')
    start=lifecycle.rfind('static NvBool',0,start)
    lifecycle=lifecycle[:start]+lifecycle[end:]
    start,end=function_span(lifecycle,'s540GlobalRmInitialize')
    start=lifecycle.rfind('NV_STATUS',0,start)
    # The selected immutable lifecycle tail consists of exactly these APIs.
    for name in ('s540GlobalRmShutdown','s540GlobalRmIsInitialized'):
        function_span(lifecycle,name)
    lifecycle=lifecycle[:start]+(HERE/'lifecycle-api.c.inc').read_text()
    if 'RmShutdownRm' in lifecycle:raise ValueError('Retained global successor contains shutdown import')
    out[LIFECYCLE]=lifecycle
    return out

def prepare(composition,output):
    sys.path.insert(0,str(ROOT/'builders'))
    import compose_nvidia_first_transaction as composer
    composition=composition.resolve(strict=True)
    if composition.is_dir():composition=composition/'composition.json'
    manifest=composer.verify_composition(composition.parent)
    if not manifest.get('fixed_source_profiles',{}).get('retained_diagnostic'):
        raise ValueError('Permanent global epoch requires the exact retained diagnostic Host')
    output=composer.new_output(output,[composition.parent,HERE])
    project=composition.parent/'project'
    before={name:(project/name).read_text() for name in INPUTS}
    changed=transforms(before)
    output.mkdir(parents=True)
    rows=[]
    for name,text in changed.items():
        path=output/'project'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        rows.append({'source':name,'input_sha256':sha(project/name),'output_sha256':sha(path)})
    report={'format':1,'component':'permanent-serialized-original-global-epoch',
        'composition_sha256':sha(composition),'sources':rows,
        'transform_source_sha256':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
        'original_entry_admission':False,'kernel_gate_preserved':True,
        'global_destruction_implemented':False,'physical_reclamation_authorized':False}
    (output/'project-successor.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();prepare(a.composition,a.output)
