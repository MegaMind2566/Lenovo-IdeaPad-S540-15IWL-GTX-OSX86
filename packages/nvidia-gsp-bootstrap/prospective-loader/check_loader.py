#!/usr/bin/env python3
"""Isolated source-only loader controls; never loads a kext or invokes RM."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import struct
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[3]
PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'builders'))
import check_nvidia_global_crypto as crypto
import compile_nvidia_global_rm as original
import nvidia_execution_commands as commands
import nvidia_metaclass_initializers as metaclass
ROOT_NAMES = tuple('RmDestroyRegistry RmPackageRegistry RmReadRegistryDword RmShutdownRm RmWriteRegistryDword coreInitializeRm rm_acquire_api_lock rm_acquire_gpu_lock rm_destroy_event_locks rm_disable_adapter rm_execute_work_item rm_free_private_state rm_gpu_handle_mmu_faults rm_init_adapter rm_init_event_locks rm_init_private_state rm_is_supported_device rm_isr rm_isr_bh rm_isr_bh_unlocked rm_release_api_lock rm_release_gpu_lock rm_run_nano_timer_callback rm_run_rc_callback rm_shutdown_adapter'.split())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,message):
    if not ok: raise ValueError(message)
def native_state(output,host_control):
    cc,cxx=crypto.compiler_pair(host_control)
    target=[] if host_control else ['-arch','x86_64','-mmacosx-version-min=15.0']
    results={}
    for label,extra in [('plain',[]),('fatal',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
        work=output/label;work.mkdir(parents=True,exist_ok=True)
        obj=work/'state.o';binary=work/'check'
        flags=[*target,'-O1','-g','-Wall','-Wextra','-Werror',*extra]
        commands.run(*cc,*flags,'-std=c11','-c',str(PACKAGE/'S540ProspectiveLoaderState.c'),'-o',str(obj),diagnostic_log=work/'compile-c.log')
        commands.run(*cxx,*flags,'-std=c++17','-pthread',str(PACKAGE/'tests/check_loader_state_native.cpp'),str(obj),'-o',str(binary),diagnostic_log=work/'compile-cpp.log')
        crypto.verify_binary(obj,1,host_control);crypto.verify_binary(binary,2,host_control)
        result=json.loads(commands.run(str(binary),diagnostic_log=work/'run.log').stdout)
        for key,value in {'status':'passed','checks':46,'failures':0,'kernel_execution':'not_tested','gpu_access':False,'entry_policy_closed':True,'target_loader_admission_proven':False,'original_rm_called':False}.items():
            require(type(result.get(key)) is type(value) and result[key]==value,'Native loader control mismatch:'+key)
        results[label]=result
    return results

def root_inventory(path):
    obj=metaclass.Object(path)
    defined,undefined,_=original.macho_symbols(path)
    expected={original.PREFIX+name for name in ROOT_NAMES}
    require(undefined==expected,'The prospective original root set changed.')
    metaclass.verify_no_initializers(path)
    table=next(symbol for symbol in obj.symbols if symbol.name=='_s540ProspectiveOriginalRoots')
    section=obj.sections[table.section-1];start=table.value-section.address
    pointers=[r for r in obj.relocations(section) if start<=r.offset<start+8*len(expected)]
    require(len(pointers)==25 and {r.offset for r in pointers}=={start+8*i for i in range(25)},'Original root pointer table lost a slot.')
    require(all(r.external and not r.pc_relative and r.width==8 and r.kind==0 for r in pointers),'Original root table requires unsigned exact function-address relocations.')
    require({obj.symbols[r.symbol].name for r in pointers}=={'_'+name for name in expected},'Original root pointer relocations do not match the reviewed names.')
    for text in (s for s in obj.sections if s.name=='__text'):
        require(not any(r.external and obj.symbols[r.symbol].name in {'_'+name for name in expected} for r in obj.relocations(text)), 'A metadata helper gained a direct original call/reference outside its data table.')
    # N_NO_DEAD_STRIP is an n_desc bit; the generic reader intentionally does
    # not interpret it. Check the exact table's actual nlist record here.
    data=path.read_bytes();position=32;table_command=None
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,position)
        if command==2: table_command=struct.unpack_from('<4I',data,position+8)
        position+=size
    symbol_offset,symbol_count,string_offset,string_bytes=table_command
    no_strip=False
    for i in range(symbol_count):
        string,kind,ordinal,descriptor,value=struct.unpack_from('<IBBHQ',data,symbol_offset+16*i)
        end=data.find(b'\0',string_offset+string,string_offset+string_bytes)
        name=data[string_offset+string:end].decode()
        if name==table.name: no_strip=bool(descriptor&0x20)
    require(no_strip,'The root address object lacks Mach-O N_NO_DEAD_STRIP.')
    return {'root_count':25,'roots':sorted(expected),'typed_actual_original_header_references':True,
        'exact_pointer_relocations':25,'n_no_dead_strip':True,'original_calls':False,
        'final_link_retention_verified':False,'object_sha256':digest(path)}

def loader_graph(actual,reference):
    a=metaclass.Object(actual).loader_graph();r=metaclass.Object(reference).loader_graph()
    require(a==r,'Actual prospective loader structors differ from the independent SDK reference.')
    require([entry['section'] for entry in r['entries']]==['__mod_init_func','__mod_term_func'],'Only the exact initializer/finalizer pair is admitted.')
    external=set();data=set();strings=set()
    names=('S540ProspectiveLoaderControl','S540ProspectiveLoaderClient')
    prefixes={'__ZN'+str(len(name))+name for name in names}
    allowed_data={p+'10gMetaClassE':0 for p in prefixes}
    allowed_data.update({'__ZTVN'+str(len(n))+n+'9MetaClassE':16 for n in names})
    allowed_external={'__ZN11OSMetaClassC2EPKcPKS_j','__ZN11OSMetaClassD2Ev','__ZN9IOService10gMetaClassE','__ZN12IOUserClient10gMetaClassE'}
    for name,function in r['functions'].items():
        require(name=='<translation-unit-initializer>' or name.startswith('__GLOBAL__D_') or any(name.startswith(p+'9MetaClass') for p in prefixes),'Reference gained non-metaclass loader code:'+name)
        for relocation in function['relocations']:
            target=relocation['target']
            if 'external' in target:
                require(target['external'] in allowed_external and target['addend']==0,'Unreviewed loader external/addend.');external.add(target['external'])
            elif 'data' in target:
                require(target['data'] in allowed_data and target['addend']==allowed_data[target['data']],'Unreviewed loader data.');data.add(target['data'])
            elif 'cstring' in target:
                require(target['cstring'] in names,'Unreviewed class name.');strings.add(target['cstring'])
    require(external==allowed_external and data==set(allowed_data) and strings==set(names),'Incomplete SDK registration reference.')
    return {'status':'exact-two-metaclass-reference-match','classes':list(names),'loader_entries':2,
        'loader_function_count':len(r['functions']),'loader_external_symbols':sorted(external),
        'graph_sha256':hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'actual_object_sha256':digest(actual),'reference_object_sha256':digest(reference),
        'target_kernel_execution':'not_tested'}

def sdk_controls(output,upstream,namespace,sdk,host_control):
    work=output/'sdk';work.mkdir(parents=True,exist_ok=True)
    sdk_commit='3f750085caa17ec3a7880f11c11bf4f48cd6a164'
    contract=json.loads((PACKAGE/'LOADER-PROTOTYPE-CONTRACTS.json').read_text())
    for source,expected in contract['reference_sdk_inputs_sha256'].items():
        require(digest(sdk/source)==expected,'A reviewed SDK input changed:'+source)
    sdk_git_verified=False
    for tree,commit,label in ((sdk,sdk_commit,'SDK'),(upstream,original.COMMIT,'original RM')):
        if label=='SDK' and host_control and not (sdk/'.git').exists():
            # An extracted SDK archive is an explicit local cross-control,
            # not evidence of a verified Git checkout or native Apple run.
            continue
        require(commands.run('git','-C',str(tree),'rev-parse','HEAD').stdout.strip()==commit,
                label+' source identity changed.')
        require(not commands.run('git','-C',str(tree),'status','--porcelain').stdout,
                label+' source must be unchanged.')
        if label=='SDK': sdk_git_verified=True
    namespace_contract=json.loads((ROOT/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    require(digest(namespace)==namespace_contract['namespace_sha256'],'Original private namespace bytes changed.')
    cc,cxx=crypto.compiler_pair(host_control)
    common=['--target=x86_64-apple-macos15.0','-mkernel','-fno-builtin','-ffreestanding','-fno-common',
        '-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables','-mno-red-zone',
        '-DKERNEL','-D__KERNEL__','-O2','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations',
        '-nostdinc','-isystem',str(sdk/'Headers'),'-I',str(ROOT/'packages/nvidia-os-adapter/upstream/include'),'-Wframe-larger-than=4096']
    cpp=['-std=c++17','-fapple-kext','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-nostdinc++',
        '-fno-use-cxa-atexit','-mllvm','-disable-atexit-based-global-dtor-lowering']
    objects={}
    for source in [PACKAGE/'S540ProspectiveLoaderState.c',PACKAGE/'S540ProspectiveLoaderKernel.cpp',PACKAGE/'S540ProspectiveLoaderKmod.cpp',PACKAGE/'tests/sdk_loader_metaclass_reference.cpp']:
        obj=work/(source.stem+'.o')
        commands.run(*(cc if source.suffix=='.c' else cxx),*common,*(['-std=c11'] if source.suffix=='.c' else cpp),'-c',str(source),'-o',str(obj),diagnostic_log=work/(source.stem+'.log'))
        objects[source.stem]=obj
    actual=objects['S540ProspectiveLoaderKernel'];reference=objects['sdk_loader_metaclass_reference']
    graph=loader_graph(actual,reference)
    for name in ('S540ProspectiveLoaderState','S540ProspectiveLoaderKmod'):
        metaclass.verify_no_initializers(objects[name])
    _,imports,_=original.macho_symbols(actual,reviewed_project_initializers=True)
    require(not any('OSRuntime' in name or 'cxa_atexit' in name or 'dso_handle' in name for name in imports),'Obsolete or unsupported C++ runtime import.')
    require(not any(name.startswith(original.PREFIX) for name in imports),'IOKit loader backend gained an original RM call.')
    source=PACKAGE/'roots/S540NvidiaGspOriginalRoots.c';obj=work/'original-roots.o'
    flags=original.original_bridge_flags(upstream,work,Path(cc[0]) if host_control else Path('/usr/bin/clang'),namespace)
    commands.run(*cc,*flags,'--target=x86_64-apple-macos15.0','-mkernel','-DKERNEL','-D__KERNEL__','-std=gnu11','-Werror','-Wno-unused-parameter','-Wframe-larger-than=4096','-c',str(source),'-o',str(obj),diagnostic_log=work/'original-roots.log')
    roots=root_inventory(obj)
    archive=sdk/'Library/x86_64/libkmod.a';members=[]
    for member,allowed in [('c_start.o',{'_realmain','kmod_info'}),('c_stop.o',{'_antimain'})]:
        result=subprocess.run(['ar','p',str(archive),member],check=True,capture_output=True)
        path=work/member;path.write_bytes(result.stdout)
        definitions,references,_=original.macho_symbols(path);metaclass.verify_no_initializers(path)
        require(references==allowed,'Pinned libkmod C wrapper acquired a runtime dependency.')
        members.append({'member':member,'defined':sorted(definitions),'undefined':sorted(references),'sha256':digest(path)})
    result={'status':'passed-development-sdk-controls','native_apple_compiler':not host_control,
        'kernel_execution':'not_tested','gpu_access':False,'production_candidate_allowed':False,
        'metaclass':graph,'original_roots':roots,'module_runtime':{'archive':'Library/x86_64/libkmod.a',
            'archive_sha256':digest(archive),'members':members,'legacy_cplus_runtime_used':False},
        'object_sha256':{name:digest(path) for name,path in objects.items()},'actual_backend_import_count':len(imports),
        'reviewed_kernel_sdk_commit':sdk_commit,'sdk_git_identity_verified':sdk_git_verified,
        'original_commit':original.COMMIT,'private_namespace_sha256':digest(namespace),
        'compiler':commands.run(*cc,'--version').stdout.splitlines()[0]}
    if not host_control:
        # Compile only. The tool does not load a module and is never executed by this check.
        commands.run(*cc,'-arch','x86_64','-mmacosx-version-min=15.0','-std=c11','-Wall','-Wextra','-Werror',str(PACKAGE/'tests/s540_prospective_ctl.c'),'-framework','IOKit','-framework','CoreFoundation','-o',str(work/'s540_prospective_ctl'),diagnostic_log=work/'userspace-control.log')
        result['userspace_control_tool']='compiled-only; not-executed'
    else: result['userspace_control_tool']='not-compiled; real-userspace-macOS-SDK-required'
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--upstream',type=Path,required=True);parser.add_argument('--namespace',type=Path,required=True)
    parser.add_argument('--sdk',type=Path,required=True);parser.add_argument('--host-control',action='store_true')
    args=parser.parse_args();output=args.output_dir.absolute();output.mkdir(parents=True,exist_ok=True)
    report={'format':1,'component':'nvidia-prospective-loader','status':'running','source_only':True,
        'production_candidate_allowed':False,'kernel_execution':'not_tested','target_loader_admission_proven':False,
        'original_rm_called':False,'gpu_access':False,'host_system':platform.system(),'host_architecture':platform.machine()}
    path=output/'prospective-loader-checks.json'
    try:
        commands.run(sys.executable,str(PACKAGE/'tests/test_loader_contracts.py'),
                     '--upstream',str(args.upstream),diagnostic_log=output/'source-contracts.log')
        report['state_controls']=native_state(output,args.host_control)
        report['sdk_controls']=sdk_controls(output,args.upstream.resolve(strict=True),args.namespace.resolve(strict=True),args.sdk.resolve(strict=True),args.host_control)
        report['source_sha256']={p.relative_to(PACKAGE).as_posix():digest(p) for p in sorted(PACKAGE.rglob('*')) if p.suffix in ('.c','.cpp','.h','.hpp','.py','.plist')}
        report['status']='passed-development-controls'
    except Exception as error:
        report.update(status='failed',failure_type=type(error).__name__,failure=str(error));raise
    finally: path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__': main()
