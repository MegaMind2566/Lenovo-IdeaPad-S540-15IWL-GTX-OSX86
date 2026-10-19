#!/usr/bin/env python3
"""Validate the isolated first-transaction candidate; never enable runtime.

All generated sources, binaries and logs live under --output. The path is
resolved before any subprocess changes directory. clang++ symlinks deliberately
keep their driver basename. Default native execution requires Intel macOS.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=next(p for p in HERE.parents if (p/'builders/check_nvidia_execution.py').is_file())

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(root, omitted=()):
    files={}
    for path in root.rglob('*'):
        if '__pycache__' in path.parts:
            continue
        if path.is_symlink():
            raise ValueError('Candidate input must not contain symlinks: '+str(path))
        if path.is_file() and path.name not in omitted:
            files[path.relative_to(root).as_posix()]=sha(path)
    return files

def verify_freeze(root, name, required=True):
    manifest=root/name
    if not manifest.exists():
        if required:raise ValueError('Missing frozen input manifest: '+str(manifest))
        return None
    expected=json.loads(manifest.read_text())
    if inventory(root,(name,))!=expected['files']:
        raise ValueError('Frozen candidate inventory changed: '+str(root))
    return expected

def project_dependencies():
    # All project C/C++ headers, implementations and checked-source inputs used
    # by these component commands, plus their imported builder modules. The raw
    # NVIDIA and SDK trees have their own full-inventory verification below.
    roots=['packages/nvidia-darwin-services/src','packages/nvidia-device-transport/src',
        'packages/nvidia-global-rm/src','packages/nvidia-global-rm-crypto/src',
        'packages/nvidia-global-rm/upstream','packages/nvidia-os-adapter/upstream/include',
        'packages/nvidia-gsp-bootstrap/src','packages/nvidia-gsp-bootstrap/timers',
        'packages/nvidia-gsp-bootstrap/cancellation','packages/nvidia-gsp-bootstrap/prospective-v3',
        'packages/nvidia-gsp-bootstrap/prospective-timer-checked']
    result={}
    for relative in roots:
        for name,digest in inventory(REPO/relative).items():result[relative+'/'+name]=digest
    harness='packages/nvidia-global-rm/tests/check_host_domains_native.cpp'
    result[harness]=sha(REPO/harness)
    # Enumerate before importing the helper graph, so a changed executable
    # dependency is refused before it can run during module initialization.
    for name in ['nvidia_metaclass_initializers.py','nvidia_stack_usage.py',
        'compile_nvidia_global_rm.py','build_nvidia_transport.py',
        'nvidia_execution_commands.py','check_nvidia_global_crypto.py','check_nvidia_execution.py']:
        result['builders/'+name]=sha(REPO/'builders'/name)
    return result

def aggregate_reports(output, sdk):
    def read(relative):return json.loads((output/relative).read_text())
    host=read('host/heap-retention-controls.json')
    services=read('services/controls/results.json')
    joint=read('joint/results.json')
    record=read('record/results.json')
    original=read('original/wrapper-results.json')
    counts={}
    for label,hmode,mode,rmode,omode in [
        ('plain','plain','plain','plain','native'),
        ('fatal-sanitized','fatal-sanitizers','fatal-sanitized','fatal-sanitizers','sanitized')]:
        cases=[*host['results'][hmode].values(),*services['native'][mode].values(),
            joint['variants'][mode],record['results'][rmode],original['controls'][omode]]
        if any(case.get('failures',0)!=0 for case in cases):
            raise ValueError('Component failure in '+label)
        counts[label]={
            'host':sum(case['checks'] for case in host['results'][hmode].values()),
            'queue':services['native'][mode]['queue']['checks'],
            'timer':services['native'][mode]['timer']['checks'],
            'joint':joint['variants'][mode]['checks'],
            'actual_original_bodies':record['results'][rmode]['checks'],
            'original_boundaries':original['controls'][omode]['checks']}
        counts[label]['total']=sum(counts[label].values())
    if counts['plain']!=counts['fatal-sanitized']:
        raise ValueError('Plain and sanitizer component inventories differ')
    compiles={}
    if sdk:
        host_sdk=read('host-sdk/sdk-compile.json')
        original_sdk=read('original/full-tu-compilation.json')
        compiles={'host_and_producers':1+len(host_sdk['producer_and_record_units']),
            'services_and_context':len(services['sdk']),'strong_record_and_participants':len(record['sdk']),
            'original_and_typed_probe':len(original_sdk['results'])}
        compiles['total']=sum(compiles.values())
    # These are compile actions, not distinct original TUs or runtime evidence.
    # The pure original C units validate the configured SDK identity but do not
    # consume IOKit declarations; the actual backend C++ units do.
    return {'controls_per_variant':counts,'kernel_target_compile_actions':compiles}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['upstream','namespace','output','cc','cxx']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--sdk',type=Path)
    parser.add_argument('--sdk-archive',type=Path)
    parser.add_argument('--v3-root',type=Path)
    parser.add_argument('--host-control',action='store_true')
    args=parser.parse_args()
    if not args.host_control and (sys.platform!='darwin' or platform.machine()!='x86_64'):
        raise ValueError('Native authority requires Intel macOS; --host-control is explicitly limited')
    args.upstream=args.upstream.resolve(strict=True)
    args.namespace=args.namespace.resolve(strict=True)
    output=args.output.resolve()
    if output.exists():raise ValueError('Fresh output directory required')
    # Use the same canonical source/output separation as the original-source
    # helpers. Only the repository's build subtree may contain generated output.
    for source in [args.v3_root,args.sdk]:
        if source is not None:
            source=source.resolve(strict=True)
            if output.is_relative_to(source) or source.is_relative_to(output):
                raise ValueError('Output overlaps an input tree: '+str(source))
    # Source directories stay unchanged. Existing historical reports are
    # included in the package audit but never reused as this run's evidence.
    before=inventory(HERE)
    frozen=HERE/'FROZEN-SHA256.json'
    expected=verify_freeze(HERE,frozen.name)
    host=REPO/'packages/nvidia-gsp-bootstrap/prospective-host-retention'
    verify_freeze(host,'FROZEN-SHA256.json')
    host_before=inventory(host)
    dependency='../prospective-host-retention/FROZEN-SHA256.json'
    if expected.get('dependencies',{}).get(dependency)!=sha(host/'FROZEN-SHA256.json'):
        raise ValueError('Frozen Host companion dependency changed')
    dependencies_before=project_dependencies()
    if expected.get('project_dependencies')!=dependencies_before:
        raise ValueError('Frozen project dependencies changed')
    spec=importlib.util.spec_from_file_location('first_transaction_common',HERE/'original/common.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    output=guard.output_path(output,args.upstream)
    cc=args.cc.absolute();cxx=args.cxx.absolute()
    common=['--upstream',args.upstream.resolve(),'--namespace',args.namespace.resolve(),
        '--cc',cc,'--cxx',cxx]
    mode=['--host-control'] if args.host_control else []
    commands=[]
    def run(label,script,arguments):
        command=[sys.executable,str(script),*[str(x) for x in arguments]]
        result=subprocess.run(command,text=True,capture_output=True,
            env={**os.environ,**({'ASAN_OPTIONS':'detect_leaks=0'} if args.host_control else {})})
        (output/(label+'.log')).write_text(result.stdout+result.stderr)
        commands.append({'label':label,'command':command,'status':result.returncode})
        if result.returncode:raise RuntimeError(label+' failed; see '+str(output/(label+'.log')))
    run('host',host/'check_heap_retention.py',[
        '--repo',REPO,'--record',HERE/'record','--participants',HERE/'record/deps',
        *common,'--output',output/'host',*mode])
    sdk=['--sdk',args.sdk.resolve()] if args.sdk else []
    archive=['--sdk-archive',args.sdk_archive.resolve()] if args.sdk_archive else []
    if args.sdk:
        run('host-sdk',host/'check_sdk.py',[
            '--repo',REPO,'--record',HERE/'record','--overlay',output/'host/overlay',
            *common,'--output',output/'host-sdk',*sdk,*archive,*mode])
    run('services',HERE/'services/check_services.py',[*common,'--output',output/'services',*sdk,*archive,*mode])
    joint=[*common,'--host-overlay',output/'host/overlay','--services-overlay',output/'services/overlay',*mode]
    run('joint',HERE/'services/check_joint.py',[*joint,'--output',output/'joint'])
    run('actual-original-bodies',HERE/'record/check_actual_original.py',[
        *joint,'--output',output/'record',*sdk])
    original_args=[*common,'--output',output/'original',*mode]
    if args.v3_root:original_args += ['--v3-root',args.v3_root.resolve()]
    run('original-boundaries',HERE/'original/check.py',original_args)
    if args.sdk:
        run('original-compile',HERE/'original/compile_full.py',[
            *original_args,'--sdk',args.sdk.resolve(),*archive])
    if inventory(HERE)!=before:raise ValueError('Candidate input changed during validation')
    if inventory(host)!=host_before:raise ValueError('Host input changed during validation')
    if project_dependencies()!=dependencies_before:raise ValueError('Project dependency changed during validation')
    report={'format':1,'status':'passed','execution':'host-control' if args.host_control else 'native-intel-macos',
        'native_apple_execution':not args.host_control,'production_modified':False,
        'original_entry_admission':False,'hardware_admission':False,'kernel_execution':'not_tested',
        'commands':commands,'package_sha256':before,'host_companion_sha256':host_before,
        'project_dependencies_sha256':dependencies_before,
        'summary':aggregate_reports(output,args.sdk),
        'reports':{'host':'host/heap-retention-controls.json','services':'services/controls/results.json',
            'host_sdk':'host-sdk/sdk-compile.json' if args.sdk else None,
            'joint':'joint/results.json','actual_original_bodies':'record/results.json',
            'original_boundaries':'original/wrapper-results.json',
            'original_compilation':'original/full-tu-compilation.json' if args.sdk else None}}
    (output/'first-transaction-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':'passed','output':str(output),'hardware_admission':False}))

if __name__=='__main__':main()
