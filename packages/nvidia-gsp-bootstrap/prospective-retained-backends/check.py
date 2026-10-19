#!/usr/bin/env python3
"""Compile/execute actual transformed backends and cross-compile kernel paths."""
from pathlib import Path
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import prepare as candidate


def run(args):
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'builders'))
    import compose_nvidia_first_transaction as composer
    import link_nvidia_first_transaction as linker
    common=composer.load('retained_backend_sdk_common',
        Path(__file__).resolve().parent.parent/'prospective-first-transaction/original/common.py')
    args.cc,args.cxx=common.compiler(str(args.cc)),common.compiler(str(args.cxx))
    identity=common.execution_identity(args.cc,args.cxx,args.host_control)
    root=args.composition.resolve(strict=True).parent
    manifest=json.loads(args.composition.read_text())
    original=(root/manifest['project']).resolve(strict=True)
    output=args.output.resolve()
    if output.exists():
        raise ValueError('Fresh output required')
    helper_inputs={str(p):candidate.sha(p) for p in candidate.HERE.iterdir()
        if p.is_file() and p.suffix in ('.py','.cpp','.inc')}
    candidate.prepare(args.composition,output)
    project=output/'execution-project'
    shutil.copytree(original,project,symlinks=False)
    for name in candidate.INPUTS:
        shutil.copyfile(output/'project'/name,project/name)
    # Pause only the actual platform allocation/free endpoints to expose their
    # race with the actual strong-record BeginOwner reservation. No policy or
    # lifetime check is replaced. Kernel compilation uses uninstrumented bytes.
    platform=project/candidate.PLATFORM
    data=platform.read_text()
    data=candidate.once(data,'namespace S540DarwinInternal {',
        'extern "C" void s540RetainedBackendControlPause(unsigned);\nnamespace S540DarwinInternal {')
    data=candidate.once(data,'    return std::calloc(1, size);',
        '    s540RetainedBackendControlPause(1);\n    return std::calloc(1, size);')
    data=candidate.once(data,'    std::free(object);',
        '    s540RetainedBackendControlPause(2);\n    std::free(object);')
    platform.write_text(data)
    record=project/candidate.RECORD
    data=candidate.once(record.read_text(),'    if(__atomic_load_n(&backendScopes,__ATOMIC_SEQ_CST)) {',
        '    extern void s540RetainedBackendControlPause(unsigned);\n'
        '    s540RetainedBackendControlPause(3);\n'
        '    if(__atomic_load_n(&backendScopes,__ATOMIC_SEQ_CST)) {')
    record.write_text(data)
    host=project/candidate.HOST
    data=candidate.once(host.read_text(),'    delete guard;',
        '    s540RetainedBackendControlPause(4);\n    delete guard;')
    data=candidate.once(data,'namespace {','extern "C" void s540RetainedBackendControlPause(unsigned);\nnamespace {')
    host.write_text(data)
    sdk=args.kernel_sdk.resolve(strict=True)
    sdk_identity=common.validate_sdk(sdk,args.sdk_archive,args.host_control)
    includes=[str(v).replace(str(original),str(project)) for v in composer.include_flags(root)]
    units=[project/name for name in (candidate.RECORD,candidate.PLATFORM,candidate.SYNC,
        candidate.TIMER,candidate.WORK,candidate.PROCESS,candidate.HOST)]
    units += [project/Path(candidate.RECORD).parent/'deps/S540NvidiaGspCancellation.c',
        project/'packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',
        project/'packages/nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c',candidate.HERE/'check.cpp']
    bridge=composer.composed_bridge_flags(args.upstream.resolve(strict=True),root,args.cc.resolve(strict=True))
    kernel_only={'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse',
        '-mno-sse2','-mno-3dnow','-fno-pic'}
    bridge=[str(v).replace(str(original),str(project)) for v in bridge if v not in kernel_only]
    if args.host_control:bridge+=['-U__linux__','-U__linux']
    bridge+=['-fPIC','-mcmodel=small','-Wno-unused-parameter']
    commands=[];dependencies={};results={}
    def execute(command,name,env=None):
        command=[str(v) for v in command]
        result=subprocess.run(command,text=True,capture_output=True,env=env,timeout=60)
        (output/(name+'.log')).write_text(result.stdout+result.stderr)
        commands.append({'name':name,'command':command,'status':result.returncode})
        if result.returncode:raise RuntimeError(name+'\n'+result.stdout+result.stderr)
        return result.stdout
    def dependency_map(path):
        for name in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1]):
            p=Path(name).resolve(strict=True)
            digest=candidate.sha(p)
            if dependencies.setdefault(str(p),digest)!=digest:
                raise ValueError('Compile dependency changed: '+str(p))
    for mode,sanitizers in [('plain',[]),('fatal-sanitizers',[
            '-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
        folder=output/mode;folder.mkdir()
        flags=[] if args.host_control else ['-arch','x86_64','-mmacosx-version-min=15.0']
        flags+=['-O1','-g','-Wall','-Wextra','-Werror','-pthread',
            '-ffunction-sections','-fdata-sections',*sanitizers,*includes]
        objects=[]
        for number,source in enumerate(units):
            obj=folder/(str(number)+'-'+source.stem+'.o');objects.append(obj)
            compiler=args.cc if source.suffix=='.c' else args.cxx
            dep=obj.with_suffix('.d')
            special=bridge if source.name=='S540NvidiaUnsupportedMemory.c' else []
            execute([compiler,*flags,'-std=c11' if source.suffix=='.c' else '-std=c++17',*special,
                '-MD','-MF',dep,'-c',source,'-o',obj],mode+'-'+source.stem)
            dependency_map(dep)
        binary=folder/'check'
        execute([args.cxx,*flags,*objects,
            '-Wl,--gc-sections' if args.host_control else '-Wl,-dead_strip','-o',binary],mode+'-link')
        env=None
        if args.host_control:
            env=os.environ.copy();env['ASAN_OPTIONS']='detect_leaks=0'
        else:
            execute(['/usr/bin/codesign','--force','--sign','-','--timestamp=none',binary],mode+'-codesign')
            execute(['/usr/bin/codesign','--verify','--strict',binary],mode+'-codesign-verify')
        result=json.loads(execute([binary],mode+'-run',env))
        if result.get('status')!='passed' or result.get('cases')!=14 or result.get('failures'):
            raise ValueError('Control inventory failed')
        results[mode]=result
    # Fresh canonical kernel-object commands over the entire verified SDK.
    # These never constitute a complete driver image link or kernel execution.
    folder=output/'kernel-cross';folder.mkdir()
    kernel=[]
    kernel_flags,cpp_flags=linker.kernel_flags(sdk)
    for name in candidate.INPUTS:
        if Path(name).suffix not in ('.c','.cpp'):
            continue
        source=output/'project'/name
        compiler=args.cc if source.suffix=='.c' else args.cxx
        command=[compiler,'-target','x86_64-apple-macos15',*kernel_flags]
        if source.suffix=='.cpp':command+=cpp_flags
        command+=['-std=c11' if source.suffix=='.c' else '-std=c++17',*includes,
            '-Wframe-larger-than=4096','-Werror=frame-larger-than','-fstack-usage']
        obj=folder/(source.stem+'.o');dep=obj.with_suffix('.d')
        command+=['-MD','-MF',dep,'-c',source,'-o',obj]
        execute(command,'kernel-'+source.stem)
        dependency_map(dep)
        kernel.append({'source':name,'object_sha256':candidate.sha(obj)})
    if len(kernel)!=7:raise ValueError('Missing changed kernel translation unit')
    # Full input inventories and generated code are checked again at the end.
    for name,row in manifest['project_files'].items():
        if candidate.sha(original/name)!=row['sha256']:
            raise ValueError('Composed project changed: '+name)
    for name,digest in dependencies.items():
        if candidate.sha(Path(name))!=digest:raise ValueError('Dependency changed: '+name)
    for name,digest in helper_inputs.items():
        if candidate.sha(Path(name))!=digest:raise ValueError('Successor helper changed: '+name)
    if common.validate_sdk(sdk,args.sdk_archive,args.host_control)!=sdk_identity:
        raise ValueError('Pinned SDK changed during controls')
    report={'format':1,'status':'passed',**identity,'results':results,'kernel_cross_compilation':kernel,
        'commands':commands,'actual_dependency_sha256':dependencies,
        'composition_sha256':candidate.sha(args.composition),
        'source_manifest_sha256':candidate.sha(output/'project-successor.json'),
        'input_profile':manifest.get('fixed_source_profiles',{}),
        'sdk_identity':sdk_identity,
        'compiler_binary_sha256':{str(p):candidate.sha(p.resolve())
            for p in (args.cc,args.cxx)},
        'native_darwin_compilation':not args.host_control,
        'kernel_object_compilation_native':not args.host_control,
        'control_source_sha256':helper_inputs,
        'actual_strong_record':True,'actual_transformed_backend_methods':True,
        'fixtures':['unused aborting original metadata adapters','raw timer wrapper absent no-binding return hook',
            'pauses in actual native allocate/deallocate, Host guard release, and owner reservation endpoints'],
        'kernel_execution':'not_tested','gpu_access':False,'native_macos_link':not args.host_control,
        'complete_driver_link':False,
        'hardware_admission':False,'original_entry_admission':False,'production_candidate_allowed':False}
    (output/'control-results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('composition','output','cc','cxx','upstream','kernel-sdk'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--sdk-archive',type=Path)
    parser.add_argument('--host-control',action='store_true',
        help='Explicit Linux x86_64 controls; default requires native Intel macOS and Apple clang.')
    result=run(parser.parse_args())
    print(json.dumps({'status':result['status'],'results':result['results'],
        'kernel_cross_units':len(result['kernel_cross_compilation']),'hardware_admission':False}))
