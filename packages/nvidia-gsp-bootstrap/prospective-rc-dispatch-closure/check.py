#!/usr/bin/env python3
"""CPU controls execute the exact transformed original timer TU and real cancellation."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE));import prepare
sys.path.insert(0,str(ROOT/'builders'));import compose_nvidia_first_transaction as composer
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(command,cwd,log,environment=None):
    result=subprocess.run([str(x) for x in command],cwd=cwd,capture_output=True,text=True,env=environment,timeout=120)
    log.write_text(result.stdout+'\n'+result.stderr)
    if result.returncode:raise RuntimeError('Failed: '+str(log)+'\n'+result.stderr)
    return result.stdout
def original_flags(args,base,manifest,output):
    # Replay the original make-declared ABI flags directly. The older generic
    # bridge helper also validates its frozen loader hash, whereas this parent
    # already has the reviewed permanent-lifetime loader successor. This oracle
    # consumes the verified source inventory, not a modified loader assertion.
    row=composer.original.original_commands(args.upstream,output/'bridge-profile',args.cc)[0]
    raw=row[1:row.index('-c')];flags=[];i=0
    while i<len(raw):
        flag=raw[i];flags.append(flag)
        if flag in {'-I','-include'}:
            i+=1;path=Path(raw[i])
            if path.is_absolute():raise ValueError('Unexpected absolute original include')
            flags.append(str((base/'source/src/nvidia'/path).resolve(strict=flag=='-include')))
        i+=1
    return [*flags,'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__','-DNV_VERSION_STRING="615.78.08"',
        '-include',str(base/manifest['namespace']),*composer.include_flags(base)]
def check(args):
    if not args.host_control:raise ValueError('Explicit --host-control required')
    args.cc=args.cc.resolve(strict=True);args.upstream=args.upstream.resolve(strict=True)
    base=args.composition.resolve(strict=True)
    manifest=composer.verify_composition(base)
    output=composer.new_output(args.output,[base,HERE,args.upstream]);output.mkdir(parents=True)
    values={name:(base/'source'/name).read_text() for name in prepare.ORIGINAL_INPUTS}
    changed=prepare.original_transforms(values)
    for name,text in changed.items():(output/Path(name).name).write_text(text)
    text=changed[prepare.TIMER]
    begin=text.index('/* One permanent diagnostic epoch.')
    fixture=(HERE/'tests/actual-rc-control.c.inc').read_text()
    if fixture.count('/* EXACT_TRANSFORMED_ORIGINAL_BODY */')!=1:raise ValueError('Exact actual body marker required')
    generated=output/'actual-rc-control.c'
    generated.write_text(text[:begin]+fixture.replace('/* EXACT_TRANSFORMED_ORIGINAL_BODY */',text[begin:]))
    flags=original_flags(args,base,manifest,output)
    kernel_only={'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}
    flags=[x for x in flags if x not in kernel_only]
    flags+=['-fPIC','-U__linux__','-U__linux','-O1','-g','-std=gnu11','-Werror','-Wno-unused-parameter',
        '-ffunction-sections','-fdata-sections','-I',str(HERE/'include')]
    sources=[generated,
        base/'project/packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellationOriginal.c',
        base/'project/packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c']
    environment=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    results={};dependencies={}
    for label,instrumentation in [('native',[]),('sanitized',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
        folder=output/label;folder.mkdir();objects=[]
        for i,source in enumerate(sources):
            obj=folder/f'part-{i}.o';dep=obj.with_suffix('.d')
            run([args.cc,*flags,*instrumentation,'-MD','-MF',dep,'-c',source,'-o',obj],output,obj.with_suffix('.log'))
            objects.append(obj)
            for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
                path=Path(name);path=path.resolve(strict=True) if path.is_absolute() else (output/path).resolve(strict=True)
                digest=sha(path)
                if dependencies.setdefault(str(path),digest)!=digest:raise ValueError('Dependency changed while compiling')
        binary=folder/'check'
        run([args.cc,*instrumentation,*objects,'-Wl,--gc-sections','-o',binary],output,folder/'link.log')
        scenarios=[]
        for i in range(20):
            row=json.loads(run([binary,str(i)],output,folder/f'scenario-{i}.log',environment))
            if row.get('status')!='passed' or row.get('failures') or row.get('pm_30_second_shutdown_bound_proven') is not False:raise ValueError('Bad actual-body control result')
            scenarios.append(row)
        results[label]={'status':'passed','scenarios':scenarios,'checks':sum(row['checks'] for row in scenarios)}
    for name,digest in dependencies.items():
        if sha(Path(name))!=digest:raise ValueError('Compiler-observed dependency changed')
    if composer.verify_composition(base)!=manifest:raise ValueError('Composition changed during controls')
    report={'format':1,'component':'actual-original-1hz-cooperative-dispatch-controls','status':'passed',
        'composition_sha256':sha(base/'composition.json'),'input_source_sha256':{name:sha(base/'source'/name) for name in prepare.ORIGINAL_INPUTS},
        'changed_source_sha256':{name:sha(output/Path(name).name) for name in prepare.ORIGINAL_INPUTS},
        'helper_sha256':{str(path.relative_to(HERE)):sha(path) for path in sorted(HERE.rglob('*')) if path.is_file() and path.suffix in {'.py','.inc','.h'} and '__pycache__' not in path.parts},
        'generated_actual_body_control_sha256':sha(generated),'dependency_sha256':dependencies,'results':results,
        'exact_transformed_complete_os_timer_body':True,'actual_cancellation_record':True,
        'first_record_observation_and_release_boundary_are_fixtures':True,
        'gpu_power_lock_clock_timer_endpoints_are_fixtures':True,
        'no_callback_duration_bound_inferred':True,'concurrent_revocation_and_timer_arm_share_commit_guard':False,
        'pm_30_second_shutdown_bound_proven':False,'hardware_stop_proven':False,'hardware_admission':False,'original_entry_admission':False}
    (output/'rc-controls.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'passed','checks':{k:v['checks'] for k,v in results.items()},'scenarios':20,'pm_30_second_shutdown_bound_proven':False}))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('composition','upstream','output','cc'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--host-control',action='store_true')
    check(parser.parse_args())
