#!/usr/bin/env python3
"""Execute the unchanged selected Binding header with explicit Session API fixtures."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
PACKAGE=HERE.parent
PROJECT=HERE.parents[3]
PREFIX='packages/nvidia-gsp-bootstrap/prospective-irq-installation/'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check(args):
    selection=args.selection.resolve(strict=True)
    packages=selection/'project/packages'
    selected=packages/'nvidia-gsp-bootstrap/prospective-irq-installation'
    inputs={name:sha(PACKAGE/name) for name in ('S540NvidiaGspIrqInstallation.hpp','S540NvidiaGspIrqIdentity.h')}
    for name,expected in inputs.items():
        path=selected/name
        if path.is_symlink() or sha(path)!=expected:raise ValueError('Selected production header differs: '+name)
    dependencies={name:sha(selection/'project'/name) for name in (
        'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp',
        'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.hpp',
        'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h',
        'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.h',
        'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/S540NvidiaIrqClosure.h',
        'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/rc/S540NvidiaIrqOriginal.h')}
    environment=dict(os.environ);environment['ASAN_OPTIONS']=environment.get('ASAN_OPTIONS','')+':detect_leaks=0'
    commands=[];results={}
    with tempfile.TemporaryDirectory(prefix='s540-irq-installation-binding-') as temporary:
        work=Path(temporary)
        for mode,sanitizers in [('plain',[]),('fatal-sanitized',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
            command=[str(args.cc),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                '-DS540_NVIDIA_IRQ_INSTALLATION=1','-I'+str(selected),
                '-I'+str(packages/'nvidia-gsp-bootstrap/prospective-first-transaction/record/deps'),
                '-I'+str(packages/'nvidia-os-adapter/upstream/include'),*sanitizers,
                str(HERE/'installation_binding.cpp'),'-o',str(work/mode)]
            commands.append(command)
            built=subprocess.run(command,capture_output=True,text=True,timeout=60)
            if built.returncode:raise RuntimeError(mode+' compile:\n'+built.stdout+built.stderr)
            ran=subprocess.run([str(work/mode)],capture_output=True,text=True,timeout=20,env=environment)
            if ran.returncode or ran.stderr:raise RuntimeError(mode+' execution:\n'+ran.stdout+ran.stderr)
            results[mode]=json.loads(ran.stdout)
    if any(sha(PACKAGE/name)!=expected or sha(selected/name)!=expected for name,expected in inputs.items()):
        raise ValueError('Production or selected Binding headers changed during controls')
    report={'format':1,'status':'passed','profile':'unchanged-irq-installation-Binding-control',
        'production_header_sha256':inputs,'dependency_header_sha256':dependencies,
        'checker_sha256':sha(HERE/'installation_binding.py'),'fixture_sha256':sha(HERE/'installation_binding.cpp'),
        'results':results,'commands':commands,'actual_binding_body_executed_unchanged':True,
        'dependencies':'actual selected Session/Lease declarations; explicit Context, strong-master, cancellation, Session, Lease, mask/drain API endpoint fixtures',
        'revocation_controls':['before registration','after registration before arm','during enable'],
        'session_implementation_executed':False,'backend_implementation_executed':False,
        'original_isr_body_executed':False,'controller_registration_execution':False,
        'hardware_irq_execution':False,'whole_irq_admission':False,'gpu_initialization_proved':False,
        'drain_limit':'software/full-mask ordering is an explicit endpoint fixture; full-mask refusal retains Session booleans and never proves hardware stop'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--cc',type=Path,required=True);parser.add_argument('--output',type=Path)
    print(json.dumps(check(parser.parse_args()),indent=2,sort_keys=True))
