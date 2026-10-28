#!/usr/bin/env python3
"""Execute original optional ACPI cache consumers and actual pure authority."""
from pathlib import Path
import argparse, hashlib, json, os, re, resource, shlex, shutil, subprocess
import prepare
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SHARED=ROOT/'packages/nvidia-gsp-bootstrap/cancellation/prepare_wait_candidates.py'
SHARED_SHA='f8e0099f904b5e1a756e628985ef991c9a09475214f52a38c921ccc5df6de471'
CANCELLATION='packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c'
HELPERS=('currentThread','bound','exact','master','first','checkedMaster','globalMaster','exactGlobalMaster')
PROBES=('s540FirstTxnOptionalNvlinkActive','s540FirstTxnOptionalNvlinkReturned')
INVALID=('foreign_nv','null_nv','foreign_master','irq','thread_error','thread_zero','unbound','owner_missing','owner_mismatch','generation_mismatch','master_mismatch','sticky','phase','not_inflight','exit_ready','already_returned','global_state','global_unvalidated','global_not_returned','global_status','global_validation','cancel_scope','cancel_idle','cancel_token','cancel_unbound','cancel_owner','cancel_cleanup','cancel_revoked','cancel_publication','cancel_generation','cancel_format','cancel_bound','cancel_output_generation','cancel_race')
CASES=('active','all_absence','dod_only','each_dsm','repeat_dsm','repeat_dod','bad_query','bad_dsm_function','bad_dod_function','prefailed','override','success','tegra','gps_skip','raw_facades','direct_probe','fallback_nonzero','arg3_retry','reserve_failure','reserve_generation','pending_existing','stale_commit','log_absent','log_sticky','log_unavailable','log_foreign','get_null','get_unpublished','get_sticky','get_inflight','get_no_exit','get_not_returned','get_stale','get_foreign_nv','get_foreign_master','get_irq',*INVALID)

def require(ok,message):
    if not ok: raise ValueError(message)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def changed(text,before,after,count=1):
    require(text.count(before)==count,'Actual C mutation anchor changed: '+before[:160])
    return text.replace(before,after)
def function(text,name):
    first,last=prepare.function_span(text,name)
    begin=text.rfind('\n',0,first)+1
    if not text[begin:first].strip(): begin=text.rfind('\n',0,begin-1)+1
    return text[begin:last]+'\n'
def dependencies(path):
    return {str(Path(p).resolve(strict=True)):sha(Path(p).resolve(strict=True)) for p in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1])}

def run(args):
    require(args.host_control,'Explicit --host-control required')
    require(sha(SHARED)==SHARED_SHA,'Actual function extractor changed')
    source=args.input_source.resolve(strict=True);project=args.input_project.resolve(strict=True);out=args.output.absolute()
    require(not out.exists() and not any(out.is_relative_to(p) or p.is_relative_to(out) for p in(source,project)),'Fresh nonoverlapping output required')
    originals={p:(source/p).read_text() for p in prepare.ORIGINAL_INPUTS}
    inputs={p:(project/p).read_text() for p in prepare.INPUTS}
    original_output=prepare.original_transforms(originals);project_output=prepare.transforms(inputs)
    if args.composed_source:
        final=args.composed_source.resolve(strict=True)
        require(all((final/p).read_text()==v for p,v in original_output.items()),'Actual composed original ACPI source differs')
    if args.composed_project:
        final=args.composed_project.resolve(strict=True)
        require(all((final/p).read_text()==v for p,v in project_output.items()),'Actual composed project differs')
        require(all(sha(final/p)==sha(v) for p,v in prepare.COMPANIONS.items()),'Actual companion differs')
    refusals=0
    for transform,values in((prepare.original_transforms,originals),(prepare.transforms,inputs)):
        for altered in({},dict(values,unexpected='extra'),{**values,next(iter(values)):values[next(iter(values))]+'\n'}):
            try:transform(altered)
            except ValueError:refusals+=1
            else:raise ValueError('Changed exact optional ACPI input accepted')
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    for group in('CPU_header_sha256','project_binding_sha256'):
        for name,digest in contract[group].items():require(sha(project/name)==digest,'Actual bound project dependency changed: '+name)
    for name,digest in contract['original_binding_sha256'].items():require(sha(source/name)==digest,'Actual bound original dependency changed: '+name)
    record=(project/prepare.RECORD).read_text();cancellation=(project/CANCELLATION).read_text();acpi=original_output[prepare.ACPI]
    storage=re.search(r'static struct \{\n    NvU64 control,.*?\n\} record;',record,re.S)
    global_storage=re.search(r'static struct \{ NvU32 state,originalStatus,.*?\} globalEpoch;',record,re.S)
    cancellation_bits=re.search(r'enum \{ BOUND = 1,.*?SHIFT = 8 \};',cancellation,re.S)
    cancellation_slot=re.search(r'static struct \{\n    NvU64 control, generation, ownerThread,.*?\} slot;',cancellation,re.S)
    require(storage and global_storage and cancellation_bits and cancellation_slot,'Actual authority storage changed')
    nv_header=(source/'src/nvidia/arch/nvalloc/unix/include/nv.h').read_text()
    nv_macro=re.search(r'#define NV_GET_NV_STATE\(pGpu\) \\\n[^\n]+',nv_header)
    require(nv_macro is not None,'Actual GPU identity macro changed')
    facade=(project/prepare.PROVIDER).read_text()
    facade_functions=('unavailable','nv_acpi_methods_init','nv_acpi_methods_uninit','nv_acpi_d3cold_dsm_for_upstream_port','nv_acpi_ddc_method','nv_acpi_dod_method','nv_acpi_dsm_method','nv_acpi_get_powersource','nv_acpi_mux_method')
    callback_macros='\n'.join(line for line in(source/'src/nvidia/inc/kernel/platform/acpi_common.h').read_text().splitlines() if line.startswith('#define NV_ACPI_CALLBACKS_RET_'))
    parts=dict(RECORD_STORAGE=storage.group()+'\n'+global_storage.group(),
        CANCELLATION_STORAGE=cancellation_bits.group()+'\n'+cancellation_slot.group(),
        CANCELLATION_WORD=changed(function(cancellation,'word'),'word(void)','actualCancellationWord(void)'),
        CANCELLATION_HELPERS='\n'.join(function(cancellation,n) for n in('generation','matches')),
        CANCELLATION_SNAPSHOT=changed(function(cancellation,'s540GspCancellationGetSnapshot'),'s540GspCancellationGetSnapshot(','actualCancellationSnapshot('),
        RECORD_HELPERS='\n'.join(function(record,n) for n in HELPERS),RECORD_PROBES='\n'.join(function(record,n) for n in PROBES),
        REGISTRY_NV_MACRO=nv_macro.group(),CALLBACK_MACROS=callback_macros,
        ACPI_FACADE='\n'.join(function(facade,n) for n in facade_functions),
        DSM_SUBFUNCTION_CHECK=function(acpi,'testIfDsmSubFunctionEnabled'),DSM_CALL_CHECK=function(acpi,'checkDsmCall'),DSM_ERROR=function(acpi,'_isDsmError'),
        CACHE_SUPPORT=function(acpi,'_acpiDsmSupportedFuncCacheInit'),CACHE_GENERIC=function(acpi,'_acpiGenFuncCacheInit'),CACHE_CALLBACK=function(acpi,'_acpiDsmCallbackInit'),
        CACHE_CAPS=function(acpi,'_acpiDsmCapsInit'),CACHE_FEATURE=function(acpi,'_acpiDsmFeatureInit'),CACHE_METHODS=function(acpi,'_acpiCacheMethodData'),ACPI_INIT=function(acpi,'acpiDsmInit'),
        CONTEXT_LOGGER=function(project_output[prepare.CONTEXT],'s540LogOptionalAcpiAbsence'))
    require('s540FirstTxnGetSnapshot' not in parts['RECORD_PROBES'] and 'checkExecution(' not in parts['RECORD_PROBES'],'Cached/mutating authority used')
    initialize=function(project_output[prepare.CONTEXT],'s540GspContextInitializeAdapter')
    require(initialize.count('    s540LogOptionalAcpiAbsence(context);')==1 and initialize.index('    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);')<initialize.index('    s540LogOptionalAcpiAbsence(context);'),'Post-wrapper order changed')
    require(project_output[prepare.PROVIDER]==inputs[prepare.PROVIDER] and project_output[prepare.PROFILE]==inputs[prepare.PROFILE],'Actual provider/profile mutated')
    compiler=args.cc.expanduser().absolute();executable=compiler.resolve(strict=True)
    require(executable.is_file() and os.access(compiler,os.X_OK),'Executable C compiler required')
    helper_paths=(SHARED,HERE/'prepare.py',*(HERE/p for p in prepare.SOURCE_FILES),*prepare.COMPANIONS.values())
    helper_hashes={str(p.relative_to(ROOT)):sha(p) for p in helper_paths}
    out.mkdir(parents=True);copy=out/'project';shutil.copytree(project,copy)
    for name,body in project_output.items():(copy/name).write_text(body)
    for name,path in prepare.COMPANIONS.items():
        target=copy/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    template=(HERE/'tests/check_optional.c.inc').read_text();production=(HERE/'S540OptionalAcpiAbsence.c').read_text()
    report=dict(format=1,status='running',scope='actual-original-optional-ACPI-cache-consumers-actual-strong-record-and-cancellation-authority-private-C-TU',
        input_original_sha256={p:sha(source/p) for p in originals},input_project_sha256={p:sha(project/p) for p in inputs},
        output_original_sha256={p:hashlib.sha256(v.encode()).hexdigest() for p,v in original_output.items()},output_project_sha256={p:hashlib.sha256(v.encode()).hexdigest() for p,v in project_output.items()},
        helper_sha256=helper_hashes,exact_input_refusals=refusals,compiler_invocation_path=str(compiler),compiler_path=str(executable),compiler_sha256=sha(executable),
        actual_record_storage_and_probe_bodies_executed=True,actual_cancellation_storage_and_stable_snapshot_bodies_executed=True,cancellation_counter_purity_checked=True,
        actual_original_ACPI_cache_consumers_executed=True,actual_original_checkDsmCall_body_executed=True,actual_six_ACPI_facade_bodies_executed=True,
        actual_original_DSM_OS_GUID_dispatch_executed=False,explicit_remap_and_OS_and_device_CPU_endpoints=True,cached_FirstTxn_snapshot_authority=False,
        full_original_driver_execution=False,actual_AML_execution=False,hardware_ACPI_absence_claimed=False,actual_GSP_execution=False,native_Darwin_compilation=False,physical_release_authorized=False,
        wrapper_return_logging_boundary_checked=True,leak_sanitizer_enabled=False,leak_sanitizer_reason='Managed host task inventory unavailable; scalar/endpoint ownership checked explicitly.',
        variants={},negative_controls={},commands=[],dependency_sha256={})
    path=out/'results.json';env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    def write():path.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    def execute(command,log):
        result=subprocess.run([str(x) for x in command],capture_output=True,text=True,env=env,timeout=120);log.write_text(result.stdout+result.stderr);report['commands'].append([str(x) for x in command]);return result
    def variant(label,selected_parts,selected_production,cases,*,sanitized=False,negative=False,profile=None):
        work=out/label;work.mkdir();text=template
        for marker,body in selected_parts.items():
            require(text.count('@'+marker+'@')==1,'Actual body marker not unique: '+marker);text=text.replace('@'+marker+'@',body)
        fixture=work/'check-optional.c';fixture.write_text(text);unit=copy/prepare.UNIT;original=unit.read_bytes();profile_path=copy/prepare.PROFILE;original_profile=profile_path.read_bytes()
        try:
            unit.write_text(selected_production)
            if profile=='enabled':profile_path.write_text(changed(original_profile.decode(),'#define S540_GLOBAL_RM_ACPI_EVENTS_ENABLED 0','#define S540_GLOBAL_RM_ACPI_EVENTS_ENABLED 1'))
            elif profile=='version':profile_path.write_text(changed(original_profile.decode(),'#define S540_GLOBAL_RM_PROFILE_VERSION 2U','#define S540_GLOBAL_RM_PROFILE_VERSION 3U'))
            instrumentation=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'] if sanitized else []
            include=(copy/'packages',copy/Path(prepare.RECORD_HEADER).parent,copy/prepare.DIRECTORY,copy/'packages/nvidia-os-adapter/upstream/include',source/'src/nvidia/interface',source/'src/common/inc',source/'src/common/sdk/nvidia/inc')
            flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function',*instrumentation,*[item for p in include for item in('-I',str(p))]]
            objects=[]
            for name,source_file in(('fixture',fixture),('production',unit)):
                obj=work/(name+'.o');dep=work/(name+'.d');built=execute([compiler,*flags,'-MD','-MF',dep,'-c',source_file,'-o',obj],work/(name+'-compile.log'))
                require(built.returncode==0,'Optional ACPI fixture compilation failed: '+label+'\n'+built.stderr[-7000:]);report['dependency_sha256'][label+'-'+name]=dependencies(dep);objects.append(obj)
            binary=work/'check-optional';linked=execute([compiler,*instrumentation,*objects,'-o',binary],work/'link.log');require(linked.returncode==0,'Optional ACPI link failed: '+linked.stderr[-3000:])
            checks=0
            for case in cases:
                result=execute([binary,case],work/(case+'.log'))
                if negative:
                    require(result.returncode!=0,'Actual optional ACPI mutant survived: '+label);return dict(killed=True,case=case,returncode=result.returncode,binary_sha256=sha(binary))
                require(result.returncode==0,'Optional ACPI case failed: '+case+'\n'+result.stderr[-3000:]);observed=json.loads(result.stdout);require(observed['status']=='passed' and observed['checks']>0,'No CPU observations');checks+=observed['checks']
            return dict(status='passed',cases=len(cases),checks=checks,binary_sha256=sha(binary),fatal_sanitizers=sanitized,altered_profile_control=profile)
        finally:unit.write_bytes(original);profile_path.write_bytes(original_profile)
    write()
    try:
        report['variants']['plain']=variant('plain',parts,production,CASES)
        report['variants']['fatal-sanitizers']=variant('fatal-sanitizers',parts,production,CASES,sanitized=True)
        require(report['variants']['plain']['checks']==report['variants']['fatal-sanitizers']['checks'],'Plain/sanitized observations differ')
        report['variants']['enabled-backend-control']=variant('enabled-backend-control',parts,production,('profile_enabled',),profile='enabled')
        report['variants']['changed-backend-version-control']=variant('changed-backend-version-control',parts,production,('profile_version',),profile='version')
        mutants=[]
        def mutation(label,part,before,after,case,count=1):
            altered=dict(parts);altered[part]=changed(altered[part],before,after,count);mutants.append((label,altered,production,case))
        mutation('existing-success-overwritten','CACHE_SUPPORT','pGpu->acpi.dsm[func].suppFuncStatus == DSM_FUNC_STATUS_UNKNOWN &&','NV_TRUE &&','success')
        mutation('integer-retry-lost','CACHE_SUPPORT','pGpu->acpi.dsm[func].bArg3isInteger = NV_TRUE;','pGpu->acpi.dsm[func].bArg3isInteger = NV_FALSE;','arg3_retry')
        mutation('direct-facade-refusal-hidden','ACPI_FACADE','    s540GlobalRmRecordUnavailable(0);\n    return NV_ERR_NOT_SUPPORTED;','    return NV_ERR_NOT_SUPPORTED;','raw_facades')
        mutation('DSM-absence-returns-success','CACHE_SUPPORT','status = NV_ERR_NOT_SUPPORTED;','status = NV_OK;','all_absence')
        mutation('DOD-absence-returns-success','CACHE_METHODS','status = NV_ERR_NOT_SUPPORTED;','status = NV_OK;','all_absence')
        mutation('DOD-bypasses-original-fallback','CACHE_METHODS','S540_OPTIONAL_ACPI_DOD, 0U) == NV_OK','S540_OPTIONAL_ACPI_DOD, 0U) != NV_OK','all_absence')
        mutation('DSM-absence-guard-inverted','CACHE_SUPPORT','S540_OPTIONAL_ACPI_DSM_SUPPORT, (NvU32)func) == NV_OK','S540_OPTIONAL_ACPI_DSM_SUPPORT, (NvU32)func) != NV_OK','all_absence')
        mutation('foreign-nv-admitted','RECORD_HELPERS','return bound() && nv && nv==LD(&record.nv);','return bound() && nv;','foreign_nv')
        mutation('foreign-master-admitted','RECORD_HELPERS','return tid && tid==LD(&record.masterThread);','return tid != 0;','foreign_master')
        mutation('ordinary-context-ignored','RECORD_HELPERS','s540Darwin_os_semaphore_may_sleep()','NV_TRUE','irq',2)
        mutation('epoch-generation-ignored','RECORD_HELPERS','globalEpoch.generation==LD(&record.generation) &&','NV_TRUE &&','generation_mismatch')
        for label,before,after,case,count in(
            ('phase-ignored','LD(&record.phase) != S540_FIRST_OP ||','NV_FALSE ||','phase',1),
            ('inflight-ignored','!LD(&record.originalInFlight) || LD(&record.originalExitReady) ||','LD(&record.originalExitReady) ||','not_inflight',1),
            ('global-validation-ignored','!LD(&globalEpoch.validated) || !LD(&globalEpoch.originalReturned) ||','!LD(&globalEpoch.originalReturned) ||','global_unvalidated',2),
            ('cancel-phase-ignored','cancellation.phase != S540_GSP_CANCEL_OPERATION','NV_FALSE','cancel_idle',1),
            ('cancel-publication-ignored','if (cancellation.publicationInFlight) return NV_ERR_NOT_READY;','if (0) return NV_ERR_NOT_READY;','cancel_publication',1),
            ('cancel-revoke-ignored','if (cancellation.revoked) return NV_ERR_OPERATION_ABORTED;','if (0) return NV_ERR_OPERATION_ABORTED;','cancel_revoked',1),
            ('read-before-wrapper-return','LD(&record.originalInFlight) || !LD(&record.originalExitReady) ||\n        !LD(&record.originalReturned) ||','NV_FALSE ||','all_absence',1)):
            mutation(label,'RECORD_PROBES',before,after,case,count)
        mutation('cancellation-getter-mutates-counter','CANCELLATION_SNAPSHOT','result.checks = __atomic_load_n(&slot.checks, __ATOMIC_RELAXED);','result.checks = __atomic_fetch_add(&slot.checks, 1U, __ATOMIC_RELAXED);','all_absence')
        mutation('unstable-cancellation-word-admitted','CANCELLATION_SNAPSHOT','if (word() != value) return NV_ERR_BUSY_RETRY;','if (0) return NV_ERR_BUSY_RETRY;','cancel_race')
        mutation('absence-log-invents-AML','CONTEXT_LOGGER','amlExecuted=0 hardwareAbsenceClaimed=0','amlExecuted=1 hardwareAbsenceClaimed=0','log_absent')
        mutants.append(('second-authority-probe-omitted',parts,changed(production,'status = s540FirstTxnOptionalNvlinkActive(nv, &confirmed);','confirmed = generation; status = NV_OK;'),'reserve_failure'))
        mutants.append(('second-generation-ignored',parts,changed(production,'if (!generation || generation != confirmed) return NV_ERR_INVALID_STATE;','if (!generation) return NV_ERR_INVALID_STATE;'),'reserve_generation'))
        mutants.append(('pending-diagnostic-published',parts,changed(production,'if (__atomic_load_n(&absenceState, __ATOMIC_ACQUIRE) != 2U)','if (0)'),'pending_existing'))
        mutants.append(('idempotence-lost',parts,changed(production,'if (!(absence.dsmAbsentMask & bit)) {','if (1) {'),'repeat_dsm'))
        mutants.append(('stored-generation-ignored',parts,changed(production,'} else if (absence.generation != generation) {','} else if (0) {'),'stale_commit'))
        for label,selected,unit,case in mutants:report['negative_controls'][label]=variant(label,selected,unit,(case,),negative=True)
        guard='if (S540_GLOBAL_RM_PROFILE_VERSION != 2U || S540_GLOBAL_RM_ACPI_EVENTS_ENABLED != 0)'
        for profile,case in(('enabled','profile_enabled'),('version','profile_version')):
            label='backend-'+profile+'-guard-ignored'
            report['negative_controls'][label]=variant(label,parts,changed(production,guard,'if (0)'),(case,),negative=True,profile=profile)
        for name,digest in helper_hashes.items():require(sha(ROOT/name)==digest,'Bound helper changed during controls: '+name)
        for label,bindings in report['dependency_sha256'].items():
            for name,digest in bindings.items():
                if name not in(str((copy/prepare.UNIT).resolve()),str((copy/prepare.PROFILE).resolve())):require(sha(name)==digest,'Bound header or fixture changed: '+name)
        report['status']='passed-actual-optional-ACPI-capability-and-record-CPU-controls';return report
    except Exception as error:report.update(status='failed',error=str(error));raise
    finally:write()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in('input-source','input-project','output','cc'):parser.add_argument('--'+name,type=Path,required=True)
    for name in('composed-source','composed-project'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--host-control',action='store_true');result=run(parser.parse_args())
    print(json.dumps(dict(status=result['status'],variants=result['variants'],mutants_killed=len(result['negative_controls']))))
