#!/usr/bin/env python3
"""Extract current production lifecycle bodies into explicit CPU fixtures."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def bodies(text):
    path=HERE.parent/'cancellation/prepare_wait_candidates.py'
    spec=importlib.util.spec_from_file_location('s540_backend_span',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names=('stopPending','closeCancellationPublication',
        'S540ExperimentalTargetControl::publishOwnerObservation','S540ExperimentalTargetControl::runOnce',
        'S540ExperimentalTargetControl::requestStop','S540ExperimentalTargetClient::clientClose')
    result=[]
    for name in names:
        start,end=module.function_span(text,name)
        start=text.rfind('\n',0,start)+1
        result.append(text[start:end])
    return '\n\n'.join(result)+'\n',names

def run(args):
    args.cc,args.cxx=args.cc.absolute(),args.cxx.absolute()
    output=args.output.absolute()
    if output.exists():raise ValueError('Fresh backend lifecycle control output required')
    output.mkdir(parents=True)
    source=HERE/'S540ExperimentalTargetKernel.cpp'
    template=HERE/'tests/check_backend.cpp.inc'
    raw=source.read_text();actual,names=bodies(raw)
    unit=template.read_text().replace('@ACTUAL_BODIES@',actual)
    generated=output/'actual-backend.cpp';generated.write_text(unit)
    def execute(command,label,*,allowed_failure=False):
        result=subprocess.run([str(v) for v in command],capture_output=True,text=True,timeout=15,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
        (output/(label+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode and not allowed_failure:raise ValueError(label+' failed: '+result.stderr[-5000:])
        return result
    results=[]
    for mode,flags in [('plain',[]),('fatal',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all'])]:
        obj=output/(mode+'-state.o');binary=output/mode
        base=['-O1','-g','-Wall','-Wextra','-Werror',*flags]
        execute([args.cc,*base,'-std=c11','-c',HERE/'S540ExperimentalTargetState.c','-o',obj],mode+'-state')
        execute([args.cxx,*base,'-std=c++17','-pthread','-I',HERE,'-I',HERE.parent/'prospective-runtime-coordinator',
            '-I',HERE.parent/'prospective-retained-stop',generated,obj,'-o',binary],mode+'-backend')
        result=json.loads(execute([binary],mode+'-run').stdout)
        if result.get('status')!='passed' or result.get('failures')!=0:raise ValueError('Actual backend body control failed')
        results.append(dict(mode=mode,result=result))
    mutations={
        'readonly-close-always-stops':('if (control && owns) (void)control->requestStop();','if (control) (void)control->requestStop();'),
        'pending-stop-hidden':('bool pending=state.snapshot.stopRequested!=0;','bool pending=false;'),
        'publisher-join-omitted':('        closeCancellationPublication();','        /* missing publication join */'),
        'owner-publication-outside-guard':('IOLockLock(guard); owner=created; state.snapshot.ownerAllocated=1; IOLockUnlock(guard);','owner=created; state.snapshot.ownerAllocated=1;')}
    killed=[]
    for name,(before,after) in mutations.items():
        if raw.count(before)!=1:raise ValueError('Current mutation anchor changed:'+name)
        changed,_=bodies(raw.replace(before,after));path=output/(name+'.cpp')
        path.write_text(template.read_text().replace('@ACTUAL_BODIES@',changed));binary=output/name
        execute([args.cxx,'-std=c++17','-O1','-pthread','-I',HERE,'-I',HERE.parent/'prospective-runtime-coordinator',
            '-I',HERE.parent/'prospective-retained-stop',path,output/'plain-state.o','-o',binary],name+'-compile')
        result=execute([binary],name+'-run',allowed_failure=True)
        if result.returncode==0:raise ValueError('Actual backend controls accepted mutant:'+name)
        killed.append(dict(name=name,rejected=True))
    inputs=[source,template,Path(__file__),HERE/'S540ExperimentalTargetState.c',HERE/'S540ExperimentalTargetState.h',
        HERE/'S540ExperimentalTargetProtocol.h',HERE.parent/'prospective-runtime-coordinator/S540ExperimentalRuntime.h',
        HERE.parent/'prospective-retained-stop/S540NvidiaRetainedStop.h']
    report=dict(format=1,status='actual-backend-lifecycle-controls-passed',controls=results,mutants=killed,
        extracted_function_names=names,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},
        generated_test_sha256=sha(generated),host_control=True,native_darwin_compilation=False,
        fixture_instruments_owner_field_publication=True,kernel_execution='not_tested',gpu_access=False)
    (output/'results.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('cc','cxx','output'):p.add_argument('--'+name,type=Path,required=True)
    print(json.dumps(run(p.parse_args()),sort_keys=True))

if __name__=='__main__':main()
