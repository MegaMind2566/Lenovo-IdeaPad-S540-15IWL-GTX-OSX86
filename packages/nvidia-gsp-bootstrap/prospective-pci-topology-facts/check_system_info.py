#!/usr/bin/env python3
"""Actual retained SystemInfo preparation with explicit CPU endpoint faults."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import shlex
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SHARED=ROOT/'packages/nvidia-gsp-bootstrap/cancellation/prepare_wait_candidates.py'
SHARED_SHA='f8e0099f904b5e1a756e628985ef991c9a09475214f52a38c921ccc5df6de471'
sys.path.insert(0,str(SHARED.parent))
from prepare_wait_candidates import function_span


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text,name):
    first,last=function_span(text,name)
    first=text.rfind('\n',0,first)+1
    previous=text.rfind('\n',0,first-1)+1
    if re.fullmatch(r'(?:static )?NV_STATUS\s*',text[previous:first]):first=previous
    return text[first:last]


def dependencies(path):
    return {str(Path(n).resolve(strict=True)):sha(Path(n).resolve(strict=True))
        for n in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1])}


def run(kernel_text,output,cc):
    output=Path(output).absolute();cc=Path(cc).expanduser().absolute()
    require(not output.exists(),'Fresh SystemInfo CPU output required')
    require(not output.is_relative_to(HERE),'CPU output overlaps source helpers')
    require(sha(SHARED)==SHARED_SHA,'Reviewed exact function parser changed')
    require(cc.resolve(strict=True).is_file() and os.access(cc,os.X_OK),'Executable C compiler required')
    prepare=function(kernel_text,'_kgspPrepareSystemInfo')
    guard=function(kernel_text,'_s540RequirePciTopology')
    init=function(kernel_text,'kgspInitRm_IMPL')
    statements=re.findall(r'NV_CHECK_OK_OR_GOTO\(status,\s*LEVEL_ERROR,\s*_kgspPrepareSystemInfo\(pGpu,\s*pKernelGsp\),\s*done\);',init)
    require(len(statements)==1,'One actual SystemInfo caller refusal boundary required')
    caller=statements[0]
    headers=[ROOT/'packages/nvidia-os-adapter/upstream/include'/n for n in ('nvtypes.h','nvstatus.h')]
    helpers=[Path(__file__),HERE/'tests/check_system_info.c.inc',SHARED,*headers,
        ROOT/'packages/nvidia-os-adapter/upstream/include/nvstatuscodes.h']
    bindings={str(p):sha(p) for p in helpers}
    output.mkdir(parents=True);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    variants={};commands=[]
    def execute(label,body,consumer=caller,sanitized=False,negative=False):
        text=(HERE/'tests/check_system_info.c.inc').read_text()
        for marker,value in {'HEADERS':'\n'.join('#include "'+str(p)+'"' for p in headers),
                'PREPARE_BODY':body,'CALLER_STATEMENT':consumer}.items():
            token='@'+marker+'@';require(text.count(token)==1,'Actual SystemInfo fixture token changed: '+marker)
            text=text.replace(token,value)
        path=output/(label+'.c');path.write_text(text);binary=output/label;dep=output/(label+'.d')
        argv=[str(cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function']
        if sanitized:argv+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        argv+=['-MD','-MF',str(dep),str(path),'-o',str(binary)]
        built=subprocess.run(argv,capture_output=True,text=True,timeout=120)
        (output/(label+'-compile.log')).write_text(built.stdout+built.stderr)
        require(built.returncode==0,'Actual SystemInfo preparation failed compile: '+label+'\n'+built.stderr[-6000:])
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
        result=subprocess.run([str(binary)],capture_output=True,text=True,env=env,timeout=30)
        (output/(label+'-run.log')).write_text(result.stdout+result.stderr)
        row=dict(source_sha256=sha(path),binary_sha256=sha(binary),returncode=result.returncode,
            dependency_sha256=dependencies(dep),sanitized=sanitized,negative_control=negative)
        if negative:
            require(result.returncode!=0,'Actual SystemInfo mutant survived: '+label);row['killed']=True
        else:
            require(result.returncode==0,'Actual SystemInfo CPU case failed: '+label+'\n'+result.stderr[-3500:])
            row.update(json.loads(result.stdout))
        variants[label]=row;commands.append(argv)
    execute('plain',prepare);execute('fatal-sanitizers',prepare,sanitized=True)
    require(variants['plain']['checks']==variants['fatal-sanitizers']['checks'],'Plain/fatal sanitizer checks differ')
    pre='''    status = _s540RequirePciTopology(pGpu);
    if (status != NV_OK)
        goto s540_topology_failure;'''
    post='''    if (status == NV_OK)
        status = _s540RequirePciTopology(pGpu);'''
    deferred='    (void)s540FirstTxnRequestDeferredCleanupGpu(pGpu, status);'
    # Match the source indentation without changing the retained error branch.
    deferred=re.search(r'^\s*\(void\)s540FirstTxnRequestDeferredCleanupGpu\(pGpu, status\);$',prepare,re.M)[0]
    mutations={
        'drop-pre-probe':(pre,pre.replace('status = _s540RequirePciTopology(pGpu);','status = NV_OK;')),
        'ignore-pre-status':(pre,pre.replace('if (status != NV_OK)','if ((void)status, NV_FALSE)')),
        'drop-post-probe':(post,post.replace('status = _s540RequirePciTopology(pGpu);','status = NV_OK;')),
        'ignore-post-status':(post,post.replace('status = _s540RequirePciTopology(pGpu);','(void)_s540RequirePciTopology(pGpu);')),
        'overwrite-encoder-error':(post,'    status = _s540RequirePciTopology(pGpu);'),
        'drop-RM-lock-gate':('    NV_ASSERT_OR_RETURN(rmapiLockIsOwner(), NV_ERR_INVALID_LOCK_STATE);','    (void)rmapiLockIsOwner();'),
        'physical-free-restored':(deferred,'        portMemFree(pKernelGsp->pEncodedSystemInfo);'),
        'clear-retained-pointer':(deferred,'        pKernelGsp->pEncodedSystemInfo = NULL;\n'+deferred),
        'clear-retained-count':(deferred,'        pKernelGsp->encodedSystemInfoCount = 0;\n'+deferred),
        'omit-deferred-observation':(deferred,'        (void)pGpu;'),
        'error-forged-success':('        return status;','        return NV_OK;'),
        'encoder-error-reclassified':('        return status;','        return NV_ERR_NOT_SUPPORTED;'),
    }
    for name,(before,after) in mutations.items():
        require(prepare.count(before)==1,'One actual SystemInfo mutation anchor required: '+name)
        execute('mutant-'+name,prepare.replace(before,after),negative=True)
    bypass='status = _kgspPrepareSystemInfo(pGpu, pKernelGsp);\n    if ((void)status, NV_FALSE) goto done;'
    execute('mutant-publish-after-error',prepare,consumer=bypass,negative=True)
    require({str(p):sha(p) for p in helpers}==bindings,'SystemInfo helper/header changed during controls')
    report=dict(format=1,status='passed-actual-retained-SystemInfo-preparation-controls',
        cases=variants['plain']['cases'],checks_per_mode=variants['plain']['checks'],
        mutants_killed=sum(r.get('killed') is True for r in variants.values()),
        selected_kernel_sha256=hashlib.sha256(kernel_text.encode()).hexdigest(),
        actual_prepare_sha256=hashlib.sha256(prepare.encode()).hexdigest(),
        actual_caller_statement_sha256=hashlib.sha256(caller.encode()).hexdigest(),
        actual_guard_source_sha256=hashlib.sha256(guard.encode()).hexdigest(),
        source_file_sha256=bindings,variants=variants,commands=commands,
        compiler_invocation_path=str(cc),compiler_resolved_path=str(cc.resolve(strict=True)),compiler_sha256=sha(cc.resolve(strict=True)),
        actual_full_prepare_executed=True,actual_caller_statement_executed=True,
        caller_NV_CHECK_macro_is_explicit_CPU_endpoint=True,
        actual_guard_executed_here=False,guard_endpoint_is_explicit=True,
        modeled_endpoints=['NVOC field layout','RM-lock ownership','pure topology/authority status boundary',
            'encoder and epoch/sticky/cancellation changes during encode','allocation/deferred observation','RPC submission counter'],
        full_RM_initialization_executed=False,full_encoder_executed=False,IOKit_executed=False,GSP_or_GPU_execution=False,
        physical_release_authorized=False,native_Darwin_compilation=False,
        sanitizer_policy=dict(address_and_undefined_fatal=True,leak_sanitizer_enabled=False,
            leak_sanitizer_reason='Disabled on traced host, not reported passed.'))
    (output/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-gsp',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cc',type=Path,required=True)
    parser.add_argument('--host-control',action='store_true')
    args=parser.parse_args();require(args.host_control,'Explicit --host-control is required')
    path=args.kernel_gsp.resolve(strict=True);before=sha(path)
    result=run(path.read_text(),args.output,args.cc)
    require(sha(path)==before,'Input kernel source changed during CPU controls')
    print(json.dumps({k:result[k] for k in ('status','cases','checks_per_mode','mutants_killed')},sort_keys=True))
