#!/usr/bin/env python3
"""Run actual transformed IRQ/cancellation bodies with explicit OS/record fixtures."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module

def extract(text,signature):
    if text.count(signature)!=1:raise ValueError('Actual source body changed: '+signature)
    first=text.index(signature);return text[first:text.index('\n}\n',first)+3]

def run(composition,sanitize=False,output=None):
    composition=Path(composition).resolve(strict=True);manifest=json.loads(composition.read_text())
    project=(composition.parent/manifest['project']).resolve(strict=True)
    prepare=load('irq_closure_prepare',HERE/'prepare.py')
    values={name:(project/name).read_text() for name in prepare.INPUTS}
    for name in prepare.INPUTS:
        path=project/name
        if path.is_symlink() or prepare.sha(path)!=manifest['project_files'][name]['sha256']:
            raise ValueError('Changed canonical composed source: '+name)
    transformed=prepare.transforms(values)
    # The once anchors refuse deleted and duplicated source boundaries.
    negative=0
    for name,anchor in [(prepare.DEVICE,'    thread_call_t bottomHalf;'),
                        (prepare.RECORD,'static NvBool authorized(void) {'),
                        (prepare.CANCEL,'static NvU64 currentOrigin(NvU64 value) {')]:
        for replacement in ['',anchor+'\n'+anchor]:
            altered=dict(values);altered[name]=altered[name].replace(anchor,replacement)
            try:prepare.transforms(altered)
            except ValueError:negative+=1
            else:raise AssertionError('Changed source anchor admitted')
    cc=shutil.which('clang') or shutil.which('gcc');cxx=shutil.which('clang++') or shutil.which('g++')
    if not cc or not cxx:raise RuntimeError('C11/C++17 compilers required')
    with tempfile.TemporaryDirectory(prefix='s540-irq-closure-') as temporary:
        work=Path(temporary);copy=work/'project';shutil.copytree(project,copy)
        target=copy/'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure'
        shutil.copytree(HERE,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        for name,value in transformed.items():(copy/name).write_text(value)
        mock=project/'packages/nvidia-gsp-bootstrap/prospective-public-callback-closure/tests/mock'
        # The materialized profile retains only live project files; the source
        # package supplies the immutable framework fixtures for these controls.
        if not mock.is_dir():mock=HERE.parent/'prospective-public-callback-closure/tests/mock'
        device=transformed[prepare.DEVICE]
        start=device.index('struct Platform {');end=device.index('\n};',start)+3
        (work/'actual-platform.inc').write_text('struct RegisterView { void *address; NvU64 bytes; };\n'+device[start:end])
        (work/'actual-backend-lifetime.inc').write_text((HERE/'backend-lifetime.hpp.inc').read_text())
        (work/'actual-irq-bodies.inc').write_text('\n'.join(extract(device,s) for s in
            ['void bottomHalf(','void interrupt(','NV_STATUS installInterrupt(','NV_STATUS stopInterrupt(']))
        (work/'actual-arm.inc').write_text(extract(device,'NV_STATUS armInterrupt('))
        (work/'actual-irq-query.inc').write_text(extract(device,'extern "C" NV_STATUS s540FirstTxnIrqReadContext('))
        flags=['-O1','-g','-Wall','-Wextra','-Werror','-pthread']
        if sanitize:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        deps=copy/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps'
        include=['-I'+str(work),'-I'+str(copy/'packages'),'-I'+str(deps),'-I'+str(HERE),
            '-I'+str(copy/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record'),
            '-I'+str(copy/'packages/nvidia-device-transport/src'),
            '-I'+str(copy/'packages/nvidia-darwin-services/src'),'-I'+str(mock)]
        commands=[];results={}
        env=dict(os.environ)
        if sanitize:env['ASAN_OPTIONS']=env.get('ASAN_OPTIONS','')+':detect_leaks=0'
        for name,command in [
            ('cancellation',[cc,'-std=c11',*flags,*include,str(copy/prepare.CANCEL),
                str(HERE/'tests/check_cancellation.c'),'-o',str(work/'cancellation')]),
            ('backend',[cxx,'-std=c++17',*flags,*include,str(HERE/'tests/check_backend.cpp'),'-o',str(work/'backend')])]:
            compiled=subprocess.run(command,text=True,capture_output=True,timeout=60)
            if compiled.returncode:raise RuntimeError(name+' compile:\n'+compiled.stdout+compiled.stderr)
            executed=subprocess.run([str(work/name)],text=True,capture_output=True,timeout=30,env=env)
            if executed.returncode or executed.stderr:raise RuntimeError(name+' execution:\n'+executed.stdout+executed.stderr)
            results[name]=json.loads(executed.stdout);commands.append(command)
        report={'format':1,'status':'passed','sanitizers':sanitize,'results':results,
            'composition_sha256':prepare.sha(composition),'negative_source_controls':negative,
            'input_sha256':{name:prepare.sha(project/name) for name in prepare.INPUTS},
            'transformed_sha256':{name:hashlib.sha256(value.encode()).hexdigest() for name,value in transformed.items()},
            'commands':commands,'required_defines':['S540_NVIDIA_IRQ_CALLBACK_CLOSURE=1','S540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1'],
            'real_iokit_execution':False,'hardware_interrupt_delivery':False,'original_gpu_init':False,
            'hardware_stop_receipt_issued':False,'production_default_changed':False,
            'strong_record_in_backend_test':'explicit fixed policy fixture; cancellation authority fixture is explicit',
            'kernel_cross_compilation':'separate rc/check_irq_original.py and selected compiler report',
            'original_entry_admission':False,'production_candidate_allowed':False}
    if output:
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--sanitize',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args();print(json.dumps(run(args.composition,args.sanitize,args.output),indent=2))
