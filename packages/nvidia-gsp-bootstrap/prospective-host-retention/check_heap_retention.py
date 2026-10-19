#!/usr/bin/env python3
"""Compile and run real Host, strong record and Darwin backend CPU controls."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import platform
import subprocess
import shlex

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def capture_dependencies(path,frozen):
    for name in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1]):
        dependency=Path(name).resolve(strict=True);value=sha(dependency)
        previous=frozen.setdefault(str(dependency),value)
        if previous!=value:raise ValueError('Actual CPU dependency changed during compilation')
def main():
    p=argparse.ArgumentParser()
    for name in ('repo','record','participants','upstream','namespace','cc','cxx','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--host-control',action='store_true')
    a=p.parse_args()
    for name in ('repo','record','participants','upstream','namespace'):setattr(a,name,getattr(a,name).resolve(strict=True))
    a.output=a.output.resolve();a.cc=a.cc.absolute();a.cxx=a.cxx.absolute()
    native=sys.platform=='darwin' and platform.machine()=='x86_64'
    if not native and not a.host_control:raise ValueError('Intel macOS required; use --host-control explicitly elsewhere')
    if a.output.exists():raise ValueError('Fresh output required')
    a.output.mkdir(parents=True)
    spec=importlib.util.spec_from_file_location('heap_prepare',HERE/'prepare_heap_retention.py')
    prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
    overlay=a.output/'overlay';overlay.mkdir();manifest=prepare.prepare(a.repo,overlay)
    host=overlay/'packages/nvidia-global-rm/src'
    common=['-O1','-g','-Wall','-Wextra','-Werror','-pthread','-ffunction-sections','-fdata-sections',
            '-I',str(host),'-I',str(a.record),'-I',str(a.repo/'packages/nvidia-device-transport/src'),
            '-I',str(a.repo/'packages/nvidia-global-rm-crypto/src')]
    if not a.host_control:common += ['-arch','x86_64','-mmacosx-version-min=15.0']
    sources=[(a.record/'S540NvidiaGspFirstTransaction.c','c'),(a.participants/'S540NvidiaGspCancellation.c','c'),
        (host/'S540NvidiaGlobalRmHost.cpp','cpp'),
        (overlay/'packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c','c'),
        (overlay/'packages/nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c','original-c')]
    sys.path.insert(0,str(a.repo/'builders'));import compile_nvidia_global_rm as original
    import check_nvidia_global_crypto as binary_control
    original_flags=original.original_bridge_flags(a.upstream,a.output,a.cc,a.namespace)
    kernel_only={'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}
    original_flags=[v for v in original_flags if v not in kernel_only]+['-fPIC']
    if a.host_control:original_flags += ['-U__linux__','-U__linux']
    services=a.repo/'packages/nvidia-darwin-services/src'
    sources += [(services/('S540NvidiaDarwin'+n+'.cpp'),'cpp') for n in
        ['Runtime','Sync','Process','Work','Timer','UserCopy','Platform','Check']]
    input_files=[path for path,kind in sources]+[a.record/'S540NvidiaGspFirstTransaction.h',
        a.participants/'Participants.h',HERE/'check_host_retention.cpp',HERE/'check_refusal_producers.cpp',
        HERE/'check_heap_retention.py',HERE/'prepare_heap_retention.py',HERE/'S540NvidiaGlobalRmHostRetention.h',HERE/'tracked-allocation-body.inc',
        HERE/'retention-observers.inc',HERE/'host-lifetime.inc',HERE/'initialize-shutdown.inc',HERE/'check_startup_refusals.cpp',HERE/'check_allocation_failure.cpp',
        a.repo/'packages/nvidia-global-rm/tests/check_host_domains_native.cpp']
    input_files += sorted(path for path in (a.record/'deps').rglob('*') if path.is_file() and path.suffix in ('.c','.h'))
    frozen={str(path):sha(path) for path in input_files}
    results={}
    for mode,flags in [('plain',[]),('fatal-sanitizers',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
        work=a.output/mode;work.mkdir();objects=[]
        for index,(source,kind) in enumerate(sources):
            obj=work/(str(index)+'-'+source.stem+'.o')
            command=[str(a.cxx if kind=='cpp' else a.cc),*(original_flags if kind=='original-c' else []),*common,*flags,
                *(['-Wno-unused-parameter'] if kind=='original-c' else []),
                '-std=c++17' if kind=='cpp' else '-std=gnu11','-MD','-MF',str(obj.with_suffix('.d')),'-c',str(source),'-o',str(obj)]
            completed=subprocess.run(command,capture_output=True,text=True)
            obj.with_suffix('.log').write_text(completed.stdout+completed.stderr)
            completed.check_returncode();binary_control.verify_binary(obj,1,a.host_control);objects.append(obj)
            capture_dependencies(obj.with_suffix('.d'),frozen)
        records={}
        cases=[('retention',HERE/'check_host_retention.cpp'),('completion_fault',HERE/'check_host_retention.cpp'),
               ('allocation_race',HERE/'check_host_retention.cpp'),('healthy_domains',a.repo/'packages/nvidia-global-rm/tests/check_host_domains_native.cpp')]
        cases += [('producer_'+domain,HERE/'check_refusal_producers.cpp') for domain in ('host','crypto','memory','invalid')]
        cases += [('prebind_'+domain,HERE/'check_refusal_producers.cpp') for domain in ('host','crypto','memory','invalid')]
        cases += [('startup_'+domain,HERE/'check_startup_refusals.cpp') for domain in ('reserving','host','crypto','memory','invalid','initialize','lifetime')]
        cases += [('allocation_'+domain,HERE/'check_allocation_failure.cpp') for domain in ('fault','cap','zero','retry')]
        for label,test in cases:
            binary=work/label
            command=[str(a.cxx),*common,*flags,'-std=c++17','-MD','-MF',str(work/(label+'.d')),str(test),*(str(o) for o in objects),
                     '-Wl,--gc-sections' if a.host_control else '-Wl,-dead_strip','-o',str(binary)]
            completed=subprocess.run(command,capture_output=True,text=True)
            (work/(label+'-link.log')).write_text(completed.stdout+completed.stderr);completed.check_returncode()
            capture_dependencies(work/(label+'.d'),frozen)
            binary_control.verify_binary(binary,2,a.host_control)
            arguments=['completion-fault'] if label=='completion_fault' else (['allocation-race'] if label=='allocation_race' else [])
            if label.startswith('producer_'):arguments=[label.removeprefix('producer_')]
            if label.startswith('prebind_'):arguments=[label.removeprefix('prebind_'),'prebind']
            if label.startswith('startup_'):arguments=[label.removeprefix('startup_')]
            if label.startswith('allocation_') and label!='allocation_race':arguments=[label.removeprefix('allocation_')]
            environment={**os.environ}
            if a.host_control:environment['ASAN_OPTIONS']='detect_leaks=0'
            completed=subprocess.run([str(binary),*arguments],capture_output=True,text=True,env=environment)
            (work/(label+'-run.log')).write_text(completed.stdout+completed.stderr);completed.check_returncode()
            record=json.loads(completed.stdout)
            if record['status']!='passed' or record['failures']:raise ValueError('CPU controls failed')
            records[label]=record
        results[mode]=records
    for path,expected in frozen.items():
        if sha(Path(path))!=expected:raise ValueError('CPU control input changed during execution')
    report={'format':1,'status':'passed','profile':'isolated-host-heap-retention','native_apple_execution':native and not a.host_control,
            'host_control':a.host_control,
            'production_modified':False,'original_entry_admission':False,'kernel_execution':'not_tested',
            'source_manifest':manifest,'input_sha256':frozen,'results':results}
    (a.output/'heap-retention-controls.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'passed','checks_per_variant':{mode:sum(case['checks'] for case in cases.values()) for mode,cases in results.items()},
                      'actual_input_files':len(frozen),'native_apple_execution':report['native_apple_execution']}))
if __name__=='__main__':main()
