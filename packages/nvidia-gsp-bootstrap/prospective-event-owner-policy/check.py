#!/usr/bin/env python3
"""Actual RC body + immutable production rows + strong record + native timers.

GPU/sanity/1Hz/lock dependencies are explicit fixtures. This is not the
transitive RC callback policy and never grants hardware admission.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from prepare import HERE, REPO, PARENT, prepare, load, original_policy_overlay

def check(config):
    host_control=bool(config.get('host_control'))
    if not host_control and (sys.platform!='darwin' or platform.machine()!='x86_64'):
        raise ValueError('Native execution requires Intel macOS; use --host-control for separate Linux controls')
    output=Path(config['output']).resolve()
    own_sources={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in HERE.iterdir() if path.is_file() and path.suffix in {'.py','.c','.md'}}
    sdk=None
    if config.get('sdk'):
        sdk_path=Path(config['sdk']).resolve(strict=True)
        if output.is_relative_to(sdk_path) or sdk_path.is_relative_to(output):
            raise ValueError('Output overlaps SDK input')
        guard=load('rc_sdk_guard',PARENT/'original/common.py')
        sdk=guard.validate_sdk(sdk_path,config.get('sdk_archive'),host_control)
    prepare(output)
    cc=Path(config['cc']).absolute();cxx=Path(config['cxx']).absolute()
    upstream=Path(config['upstream']).resolve(strict=True)
    host=Path(config['host_overlay']).resolve(strict=True)
    if (host/'packages').is_dir():host=host/'packages'
    service=PARENT/'services';record=PARENT/'record';real=REPO/'packages/nvidia-darwin-services/src'
    extract=load('rc_extract',record/'prepare_actual_original.py')
    osapi=upstream/extract.OSAPI
    if hashlib.sha256(osapi.read_bytes()).hexdigest()!=extract.SOURCES[extract.OSAPI]:
        raise ValueError('Pinned original osapi.c changed')
    source=osapi.read_text()
    (output/'actual-rc-bodies.inc').write_text('\n'.join(extract.body(source,name)
        for name in ['rm_run_rc_callback','_tmrEventServiceTimerWorkItem']))
    metadata=(PARENT/'original/S540NvidiaGspFirstTransactionOriginal.c').read_text()
    (output/'actual-metadata.inc').write_text('\n'.join(extract.body(metadata,name)
        for name in ['s540FirstTxnInspectOriginalWork','s540FirstTxnInspectOriginalEvent','s540FirstTxnInspectOriginalOwner']))
    patch=(PARENT/'original/deferred-init-and-destruction-guards.patch').read_text()
    added='\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
    table=added[added.index('const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[] = {'):]
    table=table[:table.index('sizeof(s540FirstTxnOriginalDescriptors) / sizeof(s540FirstTxnOriginalDescriptors[0]);')+len('sizeof(s540FirstTxnOriginalDescriptors) / sizeof(s540FirstTxnOriginalDescriptors[0]);')]
    (output/'actual-policy.inc').write_text(original_policy_overlay(table)+'\n')
    prepare_work=load('rc_prepare_work',service/'prepare_services.py');prepare_work.prepare(output/'queue')
    sys.path.insert(0,str(REPO/'builders'))
    import compile_nvidia_global_rm as original
    bridge=original.original_bridge_flags(upstream,output/'profile',cc,Path(config['namespace']).resolve(strict=True))
    bridge=[flag for flag in bridge if flag not in {'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}]+['-fPIC']
    if host_control:bridge+=['-U__linux__','-U__linux']
    include=['-I',output,'-I',service,'-I',record,'-I',PARENT/'original','-I',real,'-I',output/'queue',
        '-I',REPO/'packages/nvidia-gsp-bootstrap/timers',
        '-I',host/'nvidia-global-rm/src','-I',host/'nvidia-global-rm-crypto/src',
        '-I',REPO/'packages/nvidia-global-rm-crypto/src','-I',REPO/'packages/nvidia-device-transport/src']
    sources=[(output/'S540NvidiaGspFirstTransaction.c',False),
        (record/'deps/S540NvidiaGspCancellation.c',False),
        (output/'S540NvidiaGspTimersOriginal.c',True),
        (output/'S540NvidiaFirstTxnRcOriginal.c',True),
        (host/'nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',False),
        (host/'nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c',True),
        (HERE/'check_rc.c',True)]
    cpp=[host/'nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp',
        service/'S540NvidiaFirstTxnServices.cpp',output/'queue/S540NvidiaDarwinWork.cpp',
        output/'S540NvidiaDarwinTimer.cpp',real/'S540NvidiaDarwinPlatform.cpp',real/'S540NvidiaDarwinSync.cpp']
    fault=output/'host-failure-control.cpp'
    fault.write_text('''/* Explicit native fault injector; uses the actual Host allocator control. */
#include "S540NvidiaGlobalRm.h"
extern "C" void s540RcControlFailNextAllocation(void) {
    S540NvidiaGlobalRmHostSnapshot snapshot = {};
    s540GlobalRmHostSnapshot(&snapshot);
    S540NvidiaGlobalRmNative::failAllocationAt(snapshot.allocations + 1);
}
''')
    cpp.append(fault)
    env=os.environ.copy()
    if host_control:env['ASAN_OPTIONS']='detect_leaks=0'
    def run(command,name):
        proc=subprocess.run([str(x) for x in command],text=True,capture_output=True,timeout=60,env=env)
        (output/(name+'.log')).write_text(proc.stdout+proc.stderr)
        if proc.returncode:raise RuntimeError(name+'\n'+proc.stdout+proc.stderr)
        return proc
    results={}
    for mode,san in [('plain',[]),('fatal-sanitized',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
        common=([] if host_control else ['-arch','x86_64','-mmacosx-version-min=15.0'])+['-O1','-g','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',*san]
        objects=[]
        for i,(path,typed) in enumerate(sources):
            obj=output/(str(i)+'-'+mode+'.o');objects.append(obj)
            run([cc,*common,*(bridge if typed else ['-std=c11']),'-mcmodel=small','-Wno-unused-parameter','-Wno-missing-field-initializers',*include,'-c',path,'-o',obj],str(i)+'-'+mode)
        binary=output/mode
        run([cxx,'-std=c++17',*common,'-pthread',*(['-no-pie','-Wl,--gc-sections'] if host_control else ['-Wl,-dead_strip']),*include,*cpp,*objects,'-o',binary],'link-'+mode)
        result=json.loads(run([binary],'run-'+mode).stdout)
        if result.get('failures'):raise RuntimeError('RC controls failed')
        results[mode]=result
    kernel_results=[]
    if sdk is not None:
        kernel=['-target','x86_64-apple-macos15','-mkernel','-DKERNEL','-D__KERNEL__',
            '-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin',
            '-fno-common','-fno-stack-protector','-fno-asynchronous-unwind-tables',
            '-fno-unwind-tables','-mno-red-zone','-nostdinc','-isystem',sdk_path/'Headers',
            '-I',REPO/'packages/nvidia-os-adapter/upstream/include',*include,
            '-Wframe-larger-than=4096','-Werror=frame-larger-than']
        typed_kernel=original.original_bridge_flags(upstream,output/'kernel-profile',cc,Path(config['namespace']).resolve(strict=True))
        typed_kernel+=['-target','x86_64-apple-macos15','-mkernel','-DKERNEL','-D__KERNEL__',
            '-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than',*include]
        for name,typed in [('S540NvidiaGspFirstTransaction.c',False),('S540NvidiaGspTimersOriginal.c',True),('S540NvidiaFirstTxnRcOriginal.c',True),('S540NvidiaDarwinTimer.cpp',False)]:
            path=output/name;obj=output/(name+'.kernel.o')
            cpp_mode=path.suffix=='.cpp'
            extra=['-std=c++17','-fapple-kext','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-fno-use-cxa-atexit','-mllvm','-disable-atexit-based-global-dtor-lowering','-nostdinc++','-Wno-deprecated-declarations'] if cpp_mode else ['-std=gnu11' if typed else '-std=c11']
            command=[cxx if cpp_mode else cc,*(typed_kernel if typed else kernel),*extra,'-c',path,'-o',obj]
            run(command,'kernel-'+name)
            definitions,imports,sections=original.macho_symbols(obj)
            kernel_results.append({'source':name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),'definitions':sorted(definitions),
                'imports':sorted(imports),'sections':sections,'command':[str(x) for x in command]})
    for name,expected in own_sources.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Candidate input changed during controls: '+name)
    tracked=[path for path,_ in sources]+cpp+[osapi,output/'actual-rc-bodies.inc',output/'actual-policy.inc',output/'S540NvidiaGspFirstTransaction.h']
    report={'status':'passed','results':results,'host_control':host_control,
        'native_apple_execution':not host_control,'production_modified':False,'hardware_admission':False,
        'candidate_source_sha256':own_sources,'sdk':sdk,'kernel_target_compilations':kernel_results,
        '1hz_target_closure':'not established; explicit fixture',
        'source_sha256':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}}
    (output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['upstream','namespace','output','cc','cxx','host-overlay']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--sdk',type=Path);parser.add_argument('--sdk-archive',type=Path)
    parser.add_argument('--host-control',action='store_true')
    result=check(vars(parser.parse_args()));print(json.dumps(result['results'],indent=2))
