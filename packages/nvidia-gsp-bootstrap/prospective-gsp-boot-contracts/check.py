#!/usr/bin/env python3
"""Execute actual Radix3, page propagation, retry and timeout bodies with explicit CPU endpoints."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import resource
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHARED = ROOT / 'packages/nvidia-gsp-bootstrap/cancellation/prepare_wait_candidates.py'
SHARED_SHA256 = 'f8e0099f904b5e1a756e628985ef991c9a09475214f52a38c921ccc5df6de471'
sys.path.insert(0, str(SHARED.parent))
from prepare_wait_candidates import function_span


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text, name):
    first, last = function_span(text, name)
    start = text.rfind('\n', 0, first) + 1
    if not text[start:first].strip():
        previous = text.rfind('\n', 0, start - 1) + 1
        require(re.fullmatch(r'(?:static )?(?:void|NV_STATUS|NvBool|NvU64)\s*',
                            text[previous:start]), 'Unknown exact original return declaration: ' + name)
        start = previous
    return text[start:last]


def module():
    spec = importlib.util.spec_from_file_location('s540_gsp_boot_contracts', HERE / 'prepare.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def macro(text, name):
    found = re.findall(r'^#define\s+' + re.escape(name) + r'\b(?:\([^\n]*?\))?[^\n]*$', text, re.M)
    require(len(found) == 1, 'One exact pinned macro required: ' + name)
    return found[0]



def retry_body(text):
    full=function(text,'kgspInitRm_IMPL')
    begin=full.index('    NvBool bRetry = NV_FALSE;')
    end=full.index('(pKernelGsp->bootAttempts < maxGspBootAttempts));',begin)
    return full[begin:end+len('(pKernelGsp->bootAttempts < maxGspBootAttempts));')]


def fixture(source, project, kernel, replacements=None):
    sdk=source/'src/common/sdk/nvidia/inc'
    files={
        'memdesc':source/'src/nvidia/src/kernel/gpu/mem_mgr/mem_desc.c',
        'os':source/'src/nvidia/arch/nvalloc/unix/src/os.c',
        'desc_header':source/'src/nvidia/generated/g_mem_desc_nvoc.h',
        'prelude':source/'src/nvidia/inc/kernel/core/prelude.h',
        'nv_header':source/'src/nvidia/arch/nvalloc/unix/include/nv.h',
        'registry':source/'src/nvidia/interface/nvrm_registry.h',
        'libos':source/'src/common/uproc/os/common/include/libos_init_args.h',
        'timer':source/'src/nvidia/src/kernel/core/thread_state.c',
        'timer_header':source/'src/nvidia/inc/kernel/core/thread_state.h',
        'cancel':project/'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellationOriginal.c',
        'services':project/'packages/nvidia-device-transport/src/S540NvidiaDeviceServices.cpp',
        'device_header':project/'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp',
    }
    raw={name:path.read_text() for name,path in files.items()}
    require('if (pageSize != kPageBytes || pages > kMaximumPages || cache > 2 || node != -1)' in raw['services'],
        'Actual Darwin backend no longer has the exact reviewed geometry refusal')
    require(re.search(r'constexpr\s+NvU32\s+kPageBytes\s*=\s*4096;',raw['device_header']),
        'Actual Darwin base-page constant changed')
    headers=[sdk/name for name in ('nvtypes.h','nvstatus.h','nvmisc.h','nv-kernel-interface-api.h')]
    headers += [source/'src/nvidia/inc/kernel/gpu/mem_mgr/rm_page_size.h',source/'src/nvidia/inc/kernel/os/nv_memory_type.h']
    constants=[]
    for names,key in (
        (('MEMDESC_FLAGS_NONE','MEMDESC_FLAGS_KERNEL_MODE','MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY',
          'MEMDESC_FLAGS_PHYSICALLY_CONTIGUOUS','MEMDESC_FLAGS_GUEST_ALLOCATED',
          'MEMDESC_FLAGS_MEMORY_TYPE_DISPLAY_NISO','MEMDESC_FLAGS_ALLOC_32BIT_ADDRESSABLE',
          'memdescTagAlloc','ADDR_SYSMEM','AT_CPU','AT_GPU','AT_VARIANT'),'desc_header'),
        (('RM_ALIGN_UP','RM_PAGE_ALIGN_UP'),'prelude'),
        (('NV_RM_PAGE_SHIFT','NV_RM_PAGE_SIZE'),'nv_header'),
        (('NV_REG_STR_RM_GSP_BOOT_RETRY_ATTEMPTS_DEFAULT',),'registry'),
        (('LIBOS_MEMORY_REGION_RADIX_PAGE_LOG2','LIBOS_MEMORY_REGION_RADIX_PAGE_SIZE'),'libos'),
        (('THREAD_STATE_SETUP_FLAGS_TIMEOUT_ENABLED','THREAD_STATE_FLAGS_TIMEOUT_INITED'),'timer_header')):
        constants += [macro(raw[key],name) for name in names]
    tag=re.findall(r'^\s*(NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_17\s*=\s*\d+U),',raw['desc_header'],re.M)
    require(len(tag)==1,'Exact actual Radix3 allocation tag required');constants.append('enum { '+tag[0]+' };')
    abi=[]
    for name in ('nv_alloc_pages','nv_alias_pages'):
        decl=re.findall(r'^NV_STATUS\s+NV_API_CALL\s+'+name+r'\s*(\([^\n]+\));$',raw['nv_header'],re.M)
        require(len(decl)==1,'Exact actual OS allocation ABI required: '+name)
        abi+=['typedef NV_STATUS (NV_API_CALL *fixture_'+name+'_abi)'+decl[0]+';',
            '_Static_assert(__builtin_types_compatible_p(__typeof__(&'+name+'),fixture_'+name+'_abi),"Actual OS allocation endpoint ABI");']
    parts={
        'MEMDESC_BODIES':'\n\n'.join(function(raw['memdesc'],n) for n in ('memdescGetContiguity','memdescGetPageSize','memdescSetPageSize','memdescGetAdjustedPageSize')),
        'OS_BODIES':'\n\n'.join(function(raw['os'],n) for n in ('osGetPagesInfo','osAllocPagesInternal')),
        'RADIX_BODY':function(kernel,'kgspCreateRadix3_IMPL'),
        'RETRY_BODY':retry_body(kernel),
        'TIMEOUT_BODY':function(raw['timer'],'threadStateResetTimeout'),
        'CANCEL_BODY':function(raw['cancel'],'s540GspCancellationCheckGpu'),
    }
    if replacements:
        for key,before,after in replacements:
            require(parts[key].count(before)==1,'One actual mutation anchor required: '+key+' '+before)
            parts[key]=parts[key].replace(before,after)
    tokens=dict(HEADERS='\n'.join('#include "'+str(p)+'"' for p in headers),
        PROJECT_HEADERS='#include "'+str(project/'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellationOriginal.h')+'"',
        CONSTANTS='\n'.join(constants),ABI_ASSERTIONS='\n'.join(abi),**parts)
    text=(HERE/'tests/check_boot.c.inc').read_text()
    for name,value in tokens.items():
        marker='@'+name+'@';require(text.count(marker)==1,'Exact boot fixture marker required: '+name);text=text.replace(marker,value)
    require(not re.search(r'@[A-Z_0-9]+@',text),'Unexpanded boot fixture marker')
    inputs={str(p):sha(p) for p in (*files.values(),*headers,SHARED)}
    return text,inputs,{name:hashlib.sha256(value.encode()).hexdigest() for name,value in parts.items()},sdk


def dependencies(path):
    return {str(Path(n).resolve(strict=True)):sha(Path(n).resolve(strict=True))
        for n in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1])}


def run(args):
    require(args.host_control,'Explicit --host-control is required for CPU endpoint controls')
    require(sha(SHARED)==SHARED_SHA256,'Reviewed exact shared function parser changed')
    source=args.input_source.resolve(strict=True);project=args.input_project.resolve(strict=True)
    output=args.output.absolute();require(not output.exists(),'Fresh boot CPU output required')
    require(not output.is_relative_to(source) and not output.is_relative_to(project) and not output.is_relative_to(HERE),
        'CPU output must not overwrite inputs or source helpers')
    prepare=module();original={n:(source/n).read_text() for n in prepare.ORIGINAL_INPUTS}
    selected=prepare.original_transforms(original)
    if args.composed_source:
        composed=args.composed_source.resolve(strict=True)
        require(all((composed/n).read_text()==body for n,body in selected.items()),'Actual composed boot differs from exact transform')
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    bound={}
    for field,base in (('original_binding_sha256',source),('project_binding_sha256',project),('CPU_header_sha256',project)):
        for name,digest in contract[field].items():
            require(sha(base/name)==digest,'Exact boot dependency binding changed: '+name)
            bound[str(base/name)]=digest
    require(contract['original_input_sha256']==prepare.BASE_SHA256,'Boot contract and exact preceding prefix differ')
    if args.composed_project:
        composed_project=args.composed_project.resolve(strict=True)
        for field in ('project_binding_sha256','CPU_header_sha256'):
            require(all(sha(composed_project/n)==h for n,h in contract[field].items()),'Unexpected project changes at boot boundary')
    refused=[]
    for values in ({},dict(original,unknown='unreviewed'),dict(original,**{prepare.KERNEL_GSP:original[prepare.KERNEL_GSP]+'\n'})):
        try:prepare.original_transforms(values)
        except ValueError:refused.append('missing-extra-or-changed-source-refused')
        else:raise ValueError('Changed boot source admitted')
    paths=[HERE/'prepare.py',*(HERE/p for p in prepare.SOURCE_FILES)]
    helpers={str(p.relative_to(ROOT)):sha(p) for p in paths}
    output.mkdir(parents=True);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    cc=args.cc.expanduser().absolute();target=cc.resolve(strict=True)
    require(target.is_file() and os.access(cc,os.X_OK),'Executable actual C compiler required')
    variants={};commands=[];endpoint_inputs=dict(bound);extracted={}
    def execute(label,kernel,baseline=False,sanitized=False,negative=False,replacements=None):
        text,inputs,bodies,sdk=fixture(source,project,kernel,replacements)
        endpoint_inputs.update(inputs);extracted[label]=bodies
        path=output/(label+'.c');path.write_text(text);binary=output/label;dep=output/(label+'.d')
        argv=[str(cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter',
            '-Wno-gnu-variable-sized-type-not-at-end','-I'+str(sdk),'-DBASELINE='+str(int(baseline))]
        if sanitized:argv+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        argv+=['-MD','-MF',str(dep),str(path),'-o',str(binary)]
        built=subprocess.run(argv,capture_output=True,text=True,timeout=120)
        (output/(label+'-compile.log')).write_text(built.stdout+built.stderr)
        require(built.returncode==0,'Actual boot bodies failed compile: '+label+'\n'+built.stderr[-7000:])
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
        result=subprocess.run([str(binary)],capture_output=True,text=True,env=env,timeout=30)
        (output/(label+'-run.log')).write_text(result.stdout+result.stderr)
        row=dict(source_sha256=sha(path),binary_sha256=sha(binary),returncode=result.returncode,
            dependency_sha256=dependencies(dep),sanitized=sanitized,negative_control=negative)
        if negative:
            require(result.returncode!=0,'Actual boot mutant survived: '+label);row['killed']=True
        else:
            require(result.returncode==0,'Actual boot CPU case failed: '+label+'\n'+result.stderr[-3500:]);row.update(json.loads(result.stdout))
        variants[label]=row;commands.append(argv)
    for baseline,kernel in ((True,original[prepare.KERNEL_GSP]),(False,selected[prepare.KERNEL_GSP])):
        name='baseline' if baseline else 'selected'
        execute(name,kernel,baseline=baseline);execute(name+'_sanitized',kernel,baseline=baseline,sanitized=True)
        require(variants[name]['checks']==variants[name+'_sanitized']['checks'],'Plain and fatal sanitizer counts differ')
    kernel=selected[prepare.KERNEL_GSP]
    radix_line='    memdescSetPageSize(*ppMemdescRadix3, AT_GPU, RM_PAGE_SIZE);'
    # The fallback retains the same line; modify only its first occurrence.
    radix=function(kernel,'kgspCreateRadix3_IMPL')
    index=radix.index(radix_line)
    body_mutations={
        'initial-huge-pages':('RADIX_BODY',radix[:index]+radix_line,radix[:index]+radix_line.replace('RM_PAGE_SIZE);','RM_PAGE_SIZE_HUGE);')),
        'reinterpret-86-as-81':('RADIX_BODY','    if (status == NV_ERR_NO_MEMORY)','    if (status == NV_ERR_NOT_SUPPORTED) status = NV_ERR_NO_MEMORY;\n    if (status == NV_ERR_NO_MEMORY)'),
        'fallback-on-unsupported':('RADIX_BODY','    if (status == NV_ERR_NO_MEMORY)','    if (status == NV_ERR_NOT_SUPPORTED)'),
        'hide-allocation-error':('RADIX_BODY','    NV_ASSERT_OK_OR_GOTO(status, status, error_ret);','    NV_ASSERT_OK_OR_GOTO(status, NV_OK, error_ret);'),
        'drop-unprotected-request':('RADIX_BODY','        flags |= MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY;','        (void)flags;'),
        'wrong-physical-stride':('RADIX_BODY','\n            RM_PAGE_SIZE,               // stride','\n            RM_PAGE_SIZE_HUGE,          // stride'),
        'omit-data-copy':('RADIX_BODY','        portMemCopy(pRadix3Buf + dataOffset, size, pData, size);','        (void)pData;'),
        'omit-page-table-zero':('RADIX_BODY','    portMemSet(pRadix3Buf, 0, ptSize);','    (void)ptSize;'),
        'omit-data-padding-zero':('RADIX_BODY','            portMemSet(pRadix3Buf + dataOffset + size, 0, clearSize);','            (void)clearSize;'),
        'omit-success-unmap':('RADIX_BODY','    memdescUnmap(*ppMemdescRadix3, NV_TRUE,\n                  pVaKernel, pPrivKernel);','    (void)pVaKernel; (void)pPrivKernel;'),
        'erase-retained-error':('RADIX_BODY','    (void)s540FirstTxnRequestDeferredCleanupGpu(pGpu, status);','    status = NV_OK;'),
        'retry-status-clobber':('RETRY_BODY','        const NV_STATUS cancelStatus = s540GspCancellationCheckGpu(pGpu);','        const NV_STATUS cancelStatus = (status = s540GspCancellationCheckGpu(pGpu));'),
        'ignore-cancellation':('RETRY_BODY','        if (cancelStatus != NV_OK)','        if ((void)cancelStatus, NV_FALSE)'),
        'hide-cancellation-status':('RETRY_BODY','            status = cancelStatus;','            status = NV_OK;'),
        'omit-timeout-reset':('RETRY_BODY','            threadStateResetTimeout(pGpu);','            (void)pGpu;'),
        'invert-timeout-reset':('RETRY_BODY','        if (status != NV_OK)\n            threadStateResetTimeout(pGpu);','        if (status == NV_OK)\n            threadStateResetTimeout(pGpu);'),
        'ignore-aborted-boot':('RETRY_BODY','status != NV_ERR_OPERATION_ABORTED && bRetry &&','bRetry &&'),
        'drop-gpu-lock-check':('RETRY_BODY','rmapiLockIsOwner() && (gpusLockedMask != 0)','rmapiLockIsOwner()'),
        'drop-api-lock-check':('RETRY_BODY','rmapiLockIsOwner() && (gpusLockedMask != 0)','(gpusLockedMask != 0)'),
        'drop-attempt-limit':('RETRY_BODY','(pKernelGsp->bootAttempts < maxGspBootAttempts)','(pKernelGsp->bootAttempts <= maxGspBootAttempts)'),
        'drop-retry-eligibility':('RETRY_BODY','status != NV_ERR_OPERATION_ABORTED && bRetry &&','status != NV_ERR_OPERATION_ABORTED && (bRetry | NV_TRUE) &&'),
        'relabel-2M-in-page-helper':('MEMDESC_BODIES','        pageSize = memdescGetPageSize(pMemDesc, AT_GPU);','        pageSize = osGetPageSize();'),
        'wrong-OS-page-count':('OS_BODIES','    *osPageCount = alignedSize >> BIT_IDX_32(osPageSize);','    *osPageCount = (alignedSize >> BIT_IDX_32(osPageSize)) + 1;'),
        'skip-OS-array-limit':('OS_BODIES','        NV_ASSERT_OR_RETURN(*rmPageCount <= pMemDesc->pageArraySize, NV_ERR_INVALID_ARGUMENT);','        (void)pMemDesc;'),
        'timeout-failure-forged-success':('TIMEOUT_BODY','            pThreadNode->flags |= THREAD_STATE_FLAGS_TIMEOUT_INITED;','            pThreadNode->flags |= 0;'),
        'drop-NV-identity-forwarding':('CANCEL_BODY','s540GspCancellationCheckState(NV_GET_NV_STATE(gpu))','s540GspCancellationCheckState(NULL)'),
    }
    # The abort-condition control needs an eligible aborted endpoint, which the
    # actual callee forbids as well; test the original loop independently by
    # retaining the exact guard and binding rather than an unkillable mutant.
    body_mutations.pop('ignore-aborted-boot')
    for label,(part,before,after) in body_mutations.items():
        execute('mutant-'+label,kernel,negative=True,replacements=[(part,before,after)])
    require(all(sha(Path(p))==h for p,h in endpoint_inputs.items()),'An actual source/header dependency changed during boot controls')
    require(all((source/n).read_text()==text for n,text in original.items()),'Actual pre-boot source mutated')
    require({str(p.relative_to(ROOT)):sha(p) for p in paths}==helpers,'Boot helper or contract changed during controls')
    report=dict(format=1,status='passed-actual-GSP-Radix3-and-retry-contract-controls',
        exact_input_sha256={n:hashlib.sha256(v.encode()).hexdigest() for n,v in original.items()},
        exact_output_sha256={n:hashlib.sha256(v.encode()).hexdigest() for n,v in selected.items()},
        source_file_sha256=helpers,original_input_sha256=endpoint_inputs,extracted_body_sha256=extracted,
        variants=variants,commands=commands,exact_source_refusals=refused,
        compiler_invocation_path=str(cc),compiler_resolved_path=str(target),compiler_sha256=sha(target),
        actual_functions=['kgspCreateRadix3_IMPL','memdescGetContiguity','memdescGetPageSize','memdescSetPageSize','memdescGetAdjustedPageSize','osGetPagesInfo','osAllocPagesInternal','kgspInitRm_IMPL retry region','s540GspCancellationCheckGpu','threadStateResetTimeout'],
        modeled_endpoints=['NVOC resource descriptor fields/properties','strict4K typed OS allocation/mapping and unprotected admission','deferred-cleanup observation (no release)','CheckState cancellation admission','hardware GSP boot/eligible retry result','current-thread timeout lookup/time initializer'],
        limits=dict(full_kgspInitRm_executed=False,full_cancellation_record_executed=False,descriptor_fields_are_explicit_CPU_endpoints=True,physical_NVOC_layout_claimed=False,
            nonsticky_no_memory_endpoint_is_control_flow_only=True,retained_failure_modeled_separately=True,external_descriptor_success_variant_executed=False,IOKit_executed=False,native_Darwin_compilation=False,GSP_or_GPU_execution=False,physical_release_authorized=False),
        sanitizer_policy=dict(address_and_undefined_fatal=True,leak_sanitizer_enabled=False,leak_sanitizer_reason='Disabled on traced host; not reported passed.'),github_workflows_started=0)
    (output/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input-source','input-project','output','cc'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('composed-source','composed-project'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--host-control',action='store_true')
    result=run(parser.parse_args())
    print(json.dumps(dict(status=result['status'],cases=result['variants']['selected']['cases'],checks=result['variants']['selected']['checks'],mutants_killed=sum(bool(r.get('killed')) for r in result['variants'].values()))))
