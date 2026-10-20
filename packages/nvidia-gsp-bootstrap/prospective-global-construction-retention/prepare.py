#!/usr/bin/env python3
"""Retain failed original global construction before destructive unwind.

Reconstructed source revision after the October 20 scratch loss. Historical
uncommitted binaries, freeze files and test results are not validation inputs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
RECORD='packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
HEADER=RECORD[:-1]+'h'
SYSTEM='src/nvidia/src/kernel/core/system.c'
GENERATED='src/nvidia/generated/g_system_nvoc.c'
PROJECT_INPUTS=(RECORD,HEADER)
ORIGINAL_INPUTS=(SYSTEM,GENERATED)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Exact construction-retention anchor missing or ambiguous: '+old[:100])
    return text.replace(old,new)
def project_transforms(values):
    if set(values)!=set(PROJECT_INPUTS):raise ValueError('Exact strong record/header inputs required')
    if 'static NvBool exactGlobalMaster(void)' not in values[RECORD]:
        raise ValueError('The actual one-shot global-epoch predecessor is required')
    out=dict(values)
    out[RECORD]=once(out[RECORD],'static NvU64 lastEpoch;',
        'static S540FirstTxnGlobalConstructionRetention failedGlobalSystem;\nstatic NvU64 lastEpoch;')
    out[RECORD]=once(out[RECORD],'NV_STATUS s540FirstTxnBeginOwner(',
        (HERE/'record-api.c.inc').read_text()+'\nNV_STATUS s540FirstTxnBeginOwner(')
    out[HEADER]=once(out[HEADER],'NV_STATUS s540FirstTxnHostCaptureAllocation(',
        (HERE/'record-api.h.inc').read_text()+'\nNV_STATUS s540FirstTxnHostCaptureAllocation(')
    return out
def original_transforms(values):
    if set(values)!=set(ORIGINAL_INPUTS):raise ValueError('Exactly the two original constructor TUs are required')
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    for name,text in values.items():
        if hashlib.sha256(text.encode()).hexdigest()!=contract['original_source_input_sha256'][name]:
            raise ValueError('Exact original construction input changed: '+name)
    out=dict(values)
    out[SYSTEM]=once(out[SYSTEM],'NV_STATUS\nsysConstruct_IMPL(OBJSYS *pSys)',
        '''/* This narrow boundary is published only by the actual failing
 * constructor and is cleared before returning to generated NVOC cleanup. */
static struct { const OBJSYS *system; NvU32 failure,active; } s540FailedSysBoundary;
NV_STATUS s540FirstTxnGlobalOriginalSystemFailure(const void *system,NV_STATUS failure)
{
    if (!system || failure == NV_OK ||
        !__atomic_load_n(&s540FailedSysBoundary.active,__ATOMIC_ACQUIRE) ||
        system != SYS_GET_INSTANCE() ||
        system != __atomic_load_n(&s540FailedSysBoundary.system,__ATOMIC_ACQUIRE) ||
        failure != __atomic_load_n(&s540FailedSysBoundary.failure,__ATOMIC_ACQUIRE))
        return NV_ERR_INVALID_STATE;
    return NV_OK;
}

NV_STATUS
sysConstruct_IMPL(OBJSYS *pSys)''')
    out[SYSTEM]=once(out[SYSTEM],'failed:\n\n    _sysDestroyMemExportCache(pSys);',
        '''failed:

    /* Retain the failed global system before cache/server/lock/child cleanup.
     * The caller still receives the actual original constructor failure. */
    if (pSys == SYS_GET_INSTANCE() && status != NV_OK) {
        NV_STATUS retentionStatus;
        __atomic_store_n(&s540FailedSysBoundary.system,pSys,__ATOMIC_RELEASE);
        __atomic_store_n(&s540FailedSysBoundary.failure,status,__ATOMIC_RELEASE);
        __atomic_store_n(&s540FailedSysBoundary.active,1U,__ATOMIC_RELEASE);
        retentionStatus=s540FirstTxnGlobalRetainFailedSystem(pSys,status);
        __atomic_store_n(&s540FailedSysBoundary.active,0U,__ATOMIC_RELEASE);
        if (retentionStatus == NV_OK)
            return status;
    }

    _sysDestroyMemExportCache(pSys);''')
    out[SYSTEM]='#include "S540NvidiaGspFirstTransaction.h"\n'+out[SYSTEM]
    out[GENERATED]=once(out[GENERATED],'__nvoc_ctor_OBJSYS_fail__init:\n',
        '__nvoc_ctor_OBJSYS_fail__init:\n'
        '    if (s540FirstTxnGlobalFailedSystemRetained(arg_this)) return status;\n')
    out[GENERATED]=once(out[GENERATED],'__nvoc_objCreate_OBJSYS_cleanup:\n',
        '''__nvoc_objCreate_OBJSYS_cleanup:
    if (s540FirstTxnGlobalFailedSystemRetained(__nvoc_pThis)) {
        /* Preserve heap-construction failure output without ancestor
         * destruction, unlink, in-place zeroing, or physical release. */
        if (!(__nvoc_createFlags & NVOC_OBJ_CREATE_FLAGS_IN_PLACE_CONSTRUCT))
            *__nvoc_ppThis = NULL;
        return __nvoc_status;
    }
''')
    out[GENERATED]='#include "S540NvidiaGspFirstTransaction.h"\n'+out[GENERATED]
    return out
def prepare(composition,output):
    sys.path.insert(0,str(ROOT/'builders'))
    import compose_nvidia_first_transaction as composer
    composition=composition.resolve(strict=True)
    if composition.is_dir():composition=composition/'composition.json'
    composer.verify_composition(composition.parent)
    project=composition.parent/'project';source=composition.parent/'source'
    output=composer.new_output(output,[composition.parent,HERE]);output.mkdir(parents=True)
    rows=[]
    for scope,base,names,transform in [('project',project,PROJECT_INPUTS,project_transforms),
            ('original',source,ORIGINAL_INPUTS,original_transforms)]:
        for name,text in transform({n:(base/n).read_text() for n in names}).items():
            target=output/('source' if scope=='original' else 'project')/name
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
            rows.append({'scope':scope,'source':name,'input_sha256':sha(base/name),'output_sha256':sha(target)})
    report={'format':2,'component':'reconstructed-failed-original-global-construction-retention',
        'composition_sha256':sha(composition),'sources':rows,
        'original_entry_admission':False,'physical_reclamation_authorized':False,
        'failed_global_initialized_published':False,'kernel_gate_preserved':True,
        'historical_uncommitted_evidence_reused':False}
    (output/'source-successor.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.composition,args.output)
