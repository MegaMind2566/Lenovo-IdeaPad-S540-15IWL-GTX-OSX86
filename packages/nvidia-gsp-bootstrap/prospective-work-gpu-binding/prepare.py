#!/usr/bin/env python3
"""Additional source-only GPU identity overlay after frozen first-transaction.

Never modify the frozen parent, V3, upstream, production sources or admission.
All complete generated translation units belong below the explicit output.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import importlib.util
import json
import re
import stat
import sys

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'builders/check_nvidia_execution.py').is_file())
PARENT=HERE.parent/'prospective-first-transaction'
PARENT_FREEZE='7084ff0cf9c795a3f1dc5f4cc24fb53652b46462c336978e33d072bc4fcb2366'
OSINIT='src/nvidia/arch/nvalloc/unix/src/osinit.c'
OSAPI='src/nvidia/arch/nvalloc/unix/src/osapi.c'
GPUMGR='src/nvidia/src/kernel/gpu_mgr/gpu_mgr.c'
V2_NAMESPACE_CONTRACT_SHA='ce3fe72438c0548098d94fc0147b7ad036307378578e0b9c418a74aae96b938e'
BASELINE_NAMESPACE_CONTRACT_SHA='7cee49f7c2032ce844fdd6b15b62311ac62a73ac8448a0c8c0604db983ad2100'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(data):return hashlib.sha256(data).hexdigest()
def once(source,old,new):
    if source.count(old)!=1:raise ValueError('Source boundary changed: '+old[:100])
    return source.replace(old,new,1)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def _ordinary_canonical(path):
    path=Path(path).absolute()
    if path != path.resolve(strict=True) or any(p.is_symlink() for p in (path,*path.parents)) or \
            not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('The V3 namespace requires ordinary canonical files without symlinks')
    return path
def namespace_guard(path):
    # V3 deliberately writes an absolute baseline include. Pin the independent
    # baseline and alias contract, then reconstruct every wrapper byte; a raw
    # wrapper hash from another native checkout cannot identify this input.
    path=_ordinary_canonical(path)
    baseline_contract=_ordinary_canonical(REPO/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json')
    v2_contract=_ordinary_canonical(REPO/'packages/nvidia-gsp-bootstrap/prospective-v2/PROSPECTIVE-SOURCE-PROFILE.json')
    if sha(baseline_contract)!=BASELINE_NAMESPACE_CONTRACT_SHA or sha(v2_contract)!=V2_NAMESPACE_CONTRACT_SHA:
        raise ValueError('The independent namespace source contracts changed')
    raw=path.read_bytes()
    match=re.fullmatch(rb'/\* V3 original private aliases; project bridges remain strong\. \*/\n'
                       rb'#include "([^"\r\n]+)"\n(.*)',raw,re.DOTALL)
    if match is None:
        raise ValueError('The verified V3 private namespace wrapper changed')
    include=Path(match.group(1).decode('utf-8'))
    if not include.is_absolute():
        raise ValueError('The V3 baseline namespace include is not absolute')
    baseline=_ordinary_canonical(include)
    expected_baseline=json.loads(baseline_contract.read_text())['namespace_sha256']
    if sha(baseline)!=expected_baseline:
        raise ValueError('The independently pinned baseline private namespace changed')
    aliases=json.loads(v2_contract.read_text())['new_original_private_names']
    # The frozen V2 report is JSON written with sort_keys=True; V3 consumes its
    # alias dictionary in that exact order.
    expected=('/* V3 original private aliases; project bridges remain strong. */\n#include "'+
              str(baseline)+'"\n'+''.join('#define '+key+' '+value+'\n'
              for key,value in sorted(aliases.items()))).encode('utf-8')
    if raw!=expected:
        raise ValueError('The verified V3 private namespace aliases or directives changed')
    return path
def parent_guard():
    if sha(PARENT/'FROZEN-SHA256.json')!=PARENT_FREEZE:
        raise ValueError('The frozen parent candidate changed')
    contract=json.loads((PARENT/'FROZEN-SHA256.json').read_text())
    observed={p.relative_to(PARENT).as_posix() for p in PARENT.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.name!='FROZEN-SHA256.json'}
    if observed!=set(contract['files']):raise ValueError('Parent input inventory changed')
    for relative,digest in contract['files'].items():
        path=PARENT/relative
        if path.is_symlink() or sha(path)!=digest:
            raise ValueError('Parent input changed before helper import: '+relative)
    for relative,digest in contract['project_dependencies'].items():
        if sha(REPO/relative)!=digest:
            raise ValueError('Parent project dependency changed: '+relative)
    top=load('work_gpu_parent_top',PARENT/'check_first_transaction.py')
    top.verify_freeze(PARENT,'FROZEN-SHA256.json')
    host=PARENT.parent/'prospective-host-retention'
    top.verify_freeze(host,'FROZEN-SHA256.json')
    if contract['project_dependencies']!=top.project_dependencies():
        raise ValueError('The parent project dependencies changed')
    return top

def prepare(upstream,v3_root,output):
    top=parent_guard()
    sys.path.insert(0,str(PARENT/'original'))
    import common
    parent_prepare=load('work_gpu_parent_original_prepare',PARENT/'original/prepare.py')
    from prepare_wait_candidates import edit_function,function_span
    upstream=Path(upstream).resolve(strict=True)
    output=Path(output).resolve()
    if v3_root is not None:
        v3_root=Path(v3_root).resolve(strict=True)
        if output.is_relative_to(v3_root) or v3_root.is_relative_to(output):
            raise ValueError('Output overlaps the supplied V3 input')
    output=common.output_path(output,upstream)
    base=parent_prepare.prepare(upstream,v3_root,output/'parent-original')
    before={OSINIT:base['proposed'][OSINIT],OSAPI:base['proposed'][OSAPI],
        GPUMGR:(base['base_source']/GPUMGR).read_text()}
    changed=dict(before)
    changed[OSINIT]=edit_function(changed[OSINIT],'osAttachGpu',[
        ('    nvp = NV_GET_NV_PRIV(nv);',
         '    NV_STATUS status = s540FirstTxnOriginalGpuAttachBegin(pGpu, pOsGpuInfo);\n'
         '    if (status != NV_OK) return status;\n\n    nvp = NV_GET_NV_PRIV(nv);'),
        ('    NV_SET_NV_STATE(pGpu, (void *)nv);',
         '    NV_SET_NV_STATE(pGpu, (void *)nv);\n\n'
         '    status = s540FirstTxnOriginalGpuAttachCommit(pGpu, pOsGpuInfo);\n'
         '    if (status != NV_OK) return status;')])
    changed[OSINIT]=edit_function(changed[OSINIT],'osInitNvMapping',[
        ('    portMemFree(gpuAttachArg);\n    if (status->rmStatus != NV_OK)\n    {\n'
         '        NV_STATUS cleanupStatus = s540RmCleanupPendingDevice(nv);\n'
         '        if (cleanupStatus != NV_OK) status->rmStatus = cleanupStatus;',
         '    if (status->rmStatus != NV_OK)\n    {\n'
         '        // Preserve this first-attempt attach owner, arguments, device and\n'
         '        // GPU lock before any caller rollback. No ordinary detach receipt.\n'
         '        (void)s540FirstTxnOriginalGpuAttachFailed(nv, status->rmStatus);'),
        ('    nvp->flags |= NV_INIT_FLAG_GPUMGR_ATTACH;',
         '    portMemFree(gpuAttachArg);\n    nvp->flags |= NV_INIT_FLAG_GPUMGR_ATTACH;')])
    changed[OSINIT]=edit_function(changed[OSINIT],'RmInitPrivateState',[
        ('    NV_SET_NV_PRIV(pNv, NULL);',
         '    if (s540FirstTxnGpuPrivateStateMayChange(pNv) != NV_OK) return NV_FALSE;\n\n'
         '    NV_SET_NV_PRIV(pNv, NULL);')])
    changed[OSINIT]=edit_function(changed[OSINIT],'RmClearPrivateState',[
        ('    if (pNv->flags & NV_FLAG_IN_RECOVERY)',
         '    if (s540FirstTxnGpuPrivateStateMayChange(pNv) != NV_OK) return;\n\n'
         '    if (pNv->flags & NV_FLAG_IN_RECOVERY)')])
    changed[OSINIT]=edit_function(changed[OSINIT],'RmFreePrivateState',[
        ('    gpumgrUnregisterGpuId(pNv->gpu_id);',
         '    if (s540FirstTxnGpuPrivateStateMayChange(pNv) != NV_OK) return;\n\n'
         '    gpumgrUnregisterGpuId(pNv->gpu_id);')])
    changed[GPUMGR]='#include "S540NvidiaGspFirstTransactionOriginal.h"\n'+changed[GPUMGR]
    changed[GPUMGR]=edit_function(changed[GPUMGR],'gpumgrAttachGpu',[
        ('    NvU32 prevGpuInst = NV_U32_MAX;',
         '    NvU32 prevGpuInst = NV_U32_MAX;\n    NvBool firstTxnVisibilityCaptured = NV_FALSE;'),
        ('    prevGpuInst = gpumgrSetCurrentGpuInstance(pGpu->gpuInstance);',
         '    prevGpuInst = gpumgrSetCurrentGpuInstance(pGpu->gpuInstance);\n'
         '    firstTxnVisibilityCaptured = NV_TRUE;'),
        ('    NV_ASSERT_OK_OR_RETURN(_gpumgrDetermineConfComputeCapabilities(pGpuMgr, pGpu));',
         '    status = _gpumgrDetermineConfComputeCapabilities(pGpuMgr, pGpu);\n'
         '    if (status != NV_OK) goto gpumgrAttach_error_and_exit;')])
    start,end=function_span(changed[GPUMGR],'gpumgrAttachGpu')
    function=changed[GPUMGR][start:end]
    begin=function.index('gpumgrAttach_error_and_exit:\n')
    function=function[:begin]+'''gpumgrAttach_error_and_exit:
    // This opt-in first-attempt profile preserves every partial owner.
    // Restore only the actual thread visibility token; no mask/count,
    // capability, DPC, object, registry or device mutation may precede it.
    (void)s540FirstTxnOriginalGpuAttachFailed(pAttachArg->pOsAttachArg, status);
    if (firstTxnVisibilityCaptured)
        gpumgrSetCurrentGpuInstance(prevGpuInst);
    return status;
}'''
    changed[GPUMGR]=changed[GPUMGR][:start]+function+changed[GPUMGR][end:]
    # The removed rollback was this wrapper's only caller. Its under-lock
    # implementation remains used by ordinary probe removal; do not suppress
    # compiler diagnostics or expose a new unused cleanup entry point.
    start,end=function_span(changed[GPUMGR],'_gpumgrUnregisterRmCapsForGpu')
    prefix='static void\n'
    if changed[GPUMGR][start-len(prefix):start]!=prefix:
        raise ValueError('Unused rollback wrapper declaration changed')
    changed[GPUMGR]=changed[GPUMGR][:start-len(prefix)]+changed[GPUMGR][end:]
    changed[GPUMGR]=edit_function(changed[GPUMGR],'gpumgrDetachGpu',[
        ('    NvBool bDelClientResourcesFromGpuMask = !pGpu->getProperty(pGpu, PDB_PROP_GPU_IN_TIMEOUT_RECOVERY);',
         '    NvBool bDelClientResourcesFromGpuMask;\n    NV_STATUS status;'),
        ('    NV_ASSERT_OR_RETURN(rmapiLockIsOwner(), NV_ERR_INVALID_LOCK_STATE);',
         '    NV_ASSERT_OR_RETURN(rmapiLockIsOwner(), NV_ERR_INVALID_LOCK_STATE);\n\n'
         '    status = s540FirstTxnOriginalGpuDetach(pGpu);\n'
         '    if (status != NV_OK) return status;\n'
         '    bDelClientResourcesFromGpuMask = !pGpu->getProperty(pGpu, PDB_PROP_GPU_IN_TIMEOUT_RECOVERY);')])
    changed[OSAPI]=edit_function(changed[OSAPI],'RmExecuteWorkItem',[
        ('    OsQueueWorkItemFlags releaseLocks = {0};',
         '    OsQueueWorkItemFlags releaseLocks = {0};\n    NV_STATUS gpuBindingStatus;'),
        ('    if (NV_OK != workItemLocksAcquire(pWi->gpuInstance, pWi->flags,\n'
         '                                      &releaseLocks, &gpuMask))\n    {\n        goto done;',
         '    gpuBindingStatus = workItemLocksAcquire(pWi->gpuInstance, pWi->flags,\n'
         '                                           &releaseLocks, &gpuMask);\n'
         '    if (gpuBindingStatus != NV_OK)\n    {\n'
         '        (void)s540FirstTxnOriginalRejectWorkGpu(pWi, gpuBindingStatus);\n        goto done;'),
        ('            NV_ASSERT_OR_GOTO(nv != NULL, done);',
         '            gpuBindingStatus = s540FirstTxnOriginalCheckWorkGpu(pWi, pGpu);\n'
         '            if (gpuBindingStatus != NV_OK) goto done;\n'
         '            NV_ASSERT_OR_GOTO(nv != NULL, done);'),
        ('            NV_PRINTF(LEVEL_ERROR, "Invalid GPU instance for workitem\\n");',
         '            (void)s540FirstTxnOriginalRejectWorkGpu(pWi, NV_ERR_INVALID_DEVICE);\n'
         '            NV_PRINTF(LEVEL_ERROR, "Invalid GPU instance for workitem\\n");')])
    project={}
    record=(PARENT/'record/S540NvidiaGspFirstTransaction.c').read_text()
    record=once(record,'#define CAPACITY 64',
        'static NV_STATUS gpuBindingCheckMetadata(const S540FirstTxnOriginalWork *);\n#define CAPACITY 64')
    record=once(record,'        if(d<0)return refuse(NV_ERR_NOT_SUPPORTED,SITE_WORK);',
        '        if(d<0)return refuse(NV_ERR_NOT_SUPPORTED,SITE_WORK);\n'
        '        status=gpuBindingCheckMetadata(&metadata);if(status!=NV_OK)return refuse(status,SITE_WORK);')
    record=once(record,'        if(status==NV_OK && entries[i].eventId){',
        '        if(status==NV_OK)status=gpuBindingCheckMetadata(&metadata);\n'
        '        if(status==NV_OK && entries[i].eventId){')
    project['S540NvidiaGspFirstTransaction.c']=record+'\n'+(HERE/'record-gpu.c.inc').read_text()
    header=(PARENT/'record/S540NvidiaGspFirstTransaction.h').read_text()
    header=once(header,'    NvUPtr callback; NvU32 flags;',
        '    NvUPtr callback; NvU32 flags; NvU32 gpuInstance;')
    header=once(header,'#ifdef __cplusplus\n}\n#endif\n#endif',
        (HERE/'record-gpu.h.inc').read_text()+'\n#ifdef __cplusplus\n}\n#endif\n#endif')
    project['S540NvidiaGspFirstTransaction.h']=header
    probe=(PARENT/'original/S540NvidiaGspFirstTransactionOriginal.c').read_text()
    for path in ['../../../nvidia-global-rm/src/','../../../nvidia-device-transport/src/',
        '../../../nvidia-global-rm-crypto/src/','../../../nvidia-darwin-services/src/']:
        probe=probe.replace('#include "'+path,'#include "')
    probe=once(probe,'    out->flags = flags;',
        '    out->flags = flags;\n'
        '    out->gpuInstance = work->flags.bRequiresGpu ? work->gpuInstance : NV_U32_MAX;')
    project['S540NvidiaGspFirstTransactionOriginal.c']=probe+'\n'+(HERE/'original-gpu.c.inc').read_text()
    header=(PARENT/'original/S540NvidiaGspFirstTransactionOriginal.h').read_text()
    header=once(header,'#include "../record/S540NvidiaGspFirstTransaction.h"',
        '#include "S540NvidiaGspFirstTransaction.h"')
    project['S540NvidiaGspFirstTransactionOriginal.h']=header.rsplit('#endif',1)[0]+(HERE/'original-gpu.h.inc').read_text()+'\n#endif\n'
    sys.path.insert(0,str(PARENT/'services'))
    import prepare_services,prepare_timers,prepare_context
    services=output/'services-overlay'
    prepare_services.prepare(services);prepare_timers.prepare(services);prepare_context.prepare(services)
    context=(services/'S540NvidiaGspContext.c').read_text()
    context=edit_function(context,'s540GspContextReleaseOriginalState',[
        ('    if (context->state.originalReleased) return NV_OK;',
         '    if (context->state.originalReleased) return NV_OK;\n'
         '    if (context->firstTxnGeneration) {\n'
         '        status = s540FirstTxnGpuPrivateStateMayChange(&context->nv);\n'
         '        if (status != NV_OK) return status;\n    }')])
    project['S540NvidiaGspContext.c']=context
    project_root=output/'project-overlay';project_root.mkdir(exist_ok=True)
    for name,text in project.items():(project_root/name).write_text(text)
    source=output/'source'
    for name,text in changed.items():
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    patch=''.join(''.join(difflib.unified_diff(before[name].splitlines(True),text.splitlines(True),
        fromfile='a/'+name,tofile='b/'+name)) for name,text in changed.items())
    (output/'work-gpu-binding-original.patch').write_text(patch)
    manifest={'format':1,'profile':'isolated-first-transaction-nano-work-gpu-binding',
        'parent_freeze_sha256':PARENT_FREEZE,'original_base':'exact frozen first-transaction on verified V3',
        'base_source':str(base['base_source']),'original_input_sha256':{p:digest(v.encode()) for p,v in before.items()},
        'original_output_sha256':{p:digest(v.encode()) for p,v in changed.items()},
        'project_overlay_sha256':{p:digest(v.encode()) for p,v in project.items()},
        'patch_sha256':digest(patch.encode()),'v3_full_inventory_verified':True,
        'descriptor_rows_unchanged':True,'generic_original_locks_released':'NV_ERR_NOT_SUPPORTED',
        'production_modified':False,'original_entry_admission':False,'hardware_admission':False,
        'final_release_issuer':False,'new_gpu_owner_policy':False,'rc_or_rearm_admission':False}
    (output/'source-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    parent_guard()
    return {'manifest':manifest,'source':source,'project':project_root,'services':services,
        'base_source':base['base_source'],'parent_source':base['source']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--v3-root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=prepare(args.upstream,args.v3_root,args.output)
    print(json.dumps(result['manifest'],indent=2))

if __name__=='__main__':main()
