#!/usr/bin/env python3
"""Execute exact selected IRQ lifecycle bodies with explicit CPU-only endpoints."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import resource
import shlex
import shutil
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span
def require(value,message):
    if not value:raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def function(text,name):
    first,last=function_span(text,name);first=text.rfind('\n',0,first)+1
    return text[first:last]
def module():
    spec=importlib.util.spec_from_file_location('s540_irq_source_selection',HERE/'prepare.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def fixture(project,device,baseline=False,old=None):
    first=device.index('struct Platform {');last=device.index('\n};',first)+3
    platform='struct RegisterView {void *address;NvU64 bytes;};\n'+device[first:last]
    first=device.index('static Platform *retainedIrqBackends;');last=device.index('\nstruct Allocation {',first)
    lifetime=device[first:last]
    names=('readOriginalMode','bottomHalf','interrupt','interruptStatistics','installInterrupt','armInterrupt','stopInterrupt')
    bodies='\n\n'.join(function(old if baseline and name=='readOriginalMode' else device,name) for name in names)
    text=(HERE/'tests/check_irq.cpp.inc').read_text()
    tokens={'TRANSPORT_HEADER':str(project/'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp'),
        'IRQ_HEADER':str(project/'packages/nvidia-gsp-bootstrap/prospective-irq-installation/S540NvidiaGspIrqIdentity.h'),
        'RECORD_HEADER':str(project/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'),
        'COMMIT_HEADER':str(project/'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure/S540NvidiaGspCommit.h'),
        'CLOSURE_HEADER':str(project/'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/S540NvidiaIrqClosure.h'),
        'PLATFORM':platform,'LIFETIME':lifetime,'BODIES':bodies}
    for key,value in tokens.items():
        marker='@'+key+'@';require(text.count(marker)==1,'Exact IRQ fixture token required: '+key);text=text.replace(marker,value)
    return text
def dependencies(path):
    return {str(Path(name).resolve(strict=True)):sha(Path(name).resolve(strict=True))
        for name in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1])}
def run(args):
    require(args.host_control,'Explicit --host-control is required; these are CPU fixtures')
    project=args.input_project.resolve(strict=True);output=args.output.resolve()
    require(not output.exists(),'Fresh IRQ source controls output required')
    prepare=module();original={name:(project/name).read_text() for name in prepare.INPUTS}
    selected=prepare.transforms(original)
    if args.composed_project:
        composed=args.composed_project.resolve(strict=True)
        require(all((composed/name).read_text()==text for name,text in selected.items()),
            'Composed IRQ/runtime sources differ from exact source-selection profile')
    refusals=[]
    for invalid in ({},dict(original,unknown='not allowed'),dict(original,**{prepare.DEVICE:original[prepare.DEVICE]+'\n'})):
        try:prepare.transforms(invalid)
        except ValueError:refusals.append('missing/extra/changed-source-refused')
        else:raise ValueError('Changed exact source accepted')
    source_files=[HERE/'prepare.py',*(HERE/f for f in prepare.SOURCE_FILES)]
    hashes={str(p.relative_to(ROOT)):sha(p) for p in source_files}
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));output.mkdir(parents=True)
    copy=output/'project';shutil.copytree(project,copy)
    for name,text in selected.items():(copy/name).write_text(text)
    compiler=args.cxx.expanduser().absolute();compiler_target=compiler.resolve(strict=True)
    require(compiler_target.is_file() and os.access(compiler,os.X_OK),'Executable C++ compiler required')
    flags=['-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function',
        '-I'+str(copy/'packages')]
    variants={};commands=[]
    def execute(label,device,baseline=False,sanitize=False,negative=False):
        source=output/(label+'.cpp');source.write_text(fixture(copy,device,baseline,original[prepare.DEVICE]))
        executable=output/label;dep=output/(label+'.d')
        command=[str(compiler),*flags,'-DBASELINE='+str(int(baseline))]
        if sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        command+=['-MD','-MF',str(dep),str(source),'-o',str(executable)]
        built=subprocess.run(command,capture_output=True,text=True,timeout=120)
        (output/(label+'-compile.log')).write_text(built.stdout+built.stderr)
        require(built.returncode==0,'Actual IRQ bodies did not compile '+label+': '+built.stderr[-5000:])
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
        result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=30,env=env)
        (output/(label+'-run.log')).write_text(result.stdout+result.stderr);commands.append(command)
        row=dict(source_sha256=sha(source),binary_sha256=sha(executable),dependency_sha256=dependencies(dep),
            returncode=result.returncode,sanitized=sanitize,negative_control=negative)
        if negative:
            require(result.returncode!=0,'Actual IRQ mutant survived: '+label);row['killed']=True
        else:
            require(result.returncode==0,'Actual IRQ fixture failed '+label+': '+result.stderr[-3000:])
            row.update(json.loads(result.stdout));(output/(label+'-results.json')).write_text(result.stdout)
        variants[label]=row
    device=selected[prepare.DEVICE]
    for baseline in (True,False):
        label='baseline' if baseline else 'selected'
        for sanitize in (False,True):execute(label+('_sanitized' if sanitize else ''),device,baseline,sanitize)
        require(variants[label]['checks']==variants[label+'_sanitized']['checks'],'Plain/sanitized result differs')
    mutations={
        'assume_source_zero':('p->irqSource=selected;','p->irqSource=0;'),
        'disable_source_zero':('p->provider->disableInterrupt(static_cast<int>(p->irqSource))','p->provider->disableInterrupt(0)'),
        'unregister_source_zero':('p->provider->unregisterInterrupt(static_cast<int>(p->irqSource))','p->provider->unregisterInterrupt(0)'),
        'register_source_zero':('p->provider->registerInterrupt(static_cast<int>(p->irqSource),p->owner,interrupt,p)','p->provider->registerInterrupt(0,p->owner,interrupt,p)'),
        'enable_source_zero':('p->provider->enableInterrupt(static_cast<int>(p->irqSource))','p->provider->enableInterrupt(0)'),
        'ignore_callback_identity':('if(!p->irqSourceValid||provider!=p->provider||source<0||static_cast<NvU32>(source)!=p->irqSource)',
            'if((static_cast<void>(provider),static_cast<void>(source),false))'),
        'accept_ambiguous_sources':('value.messageSignaled=messages==1;','value.messageSignaled=messages>0;'),
        'accept_unknown_type':('known=false;break;','known=true;break;'),
        'remove_source_bound':('count<=32U','count<=64U'),
        'omit_arm_revalidation':('NV_STATUS routeStatus=readOriginalMode(p,currentMode);','NV_STATUS routeStatus=(static_cast<void>(currentMode),NV_OK);')}
    for name,(before,after) in mutations.items():
        require(device.count(before)==1,'Exact production mutation anchor changed: '+name)
        execute('mutant_'+name,device.replace(before,after),negative=True)
    report=dict(format=1,status='passed-actual-IRQ-source-selection-and-lifecycle-controls',
        exact_input_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in original.items()},
        exact_output_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in selected.items()},
        source_file_sha256=hashes,exact_source_refusal_controls=refusals,variants=variants,commands=commands,
        compiler_invocation_path=str(compiler),compiler_resolved_path=str(compiler_target),compiler_sha256=sha(compiler_target),
        source_inventory_fixture='explicit CPU fixture: legacy0+MSI1, not an actual raw Lenovo source capture',
        sanitizer_policy=dict(address_and_undefined_fatal=True,leak_sanitizer_enabled=False,
            leak_sanitizer_reason='Traced host cannot enumerate /proc tasks; disabled explicitly, not reported passed.'),
        original_RM_executed=False,IOKit_executed=False,native_Darwin_compilation=False,
        hardware_executed=False,GPU_initialization_proven=False,whole_DMA_stop_proven=False,
        system_security_changed=False,github_workflows_started=0)
    require({str(p.relative_to(ROOT)):sha(p) for p in source_files}==hashes,'Checked production/helper source changed during controls')
    (output/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-project',type=Path,required=True)
    parser.add_argument('--composed-project',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cxx',type=Path,required=True)
    parser.add_argument('--host-control',action='store_true')
    result=run(parser.parse_args())
    print(json.dumps(dict(status=result['status'],cases=result['variants']['selected']['cases'],
        checks=result['variants']['selected']['checks'],sanitized_checks=result['variants']['selected_sanitized']['checks'],
        mutants_killed=sum(bool(v.get('killed')) for v in result['variants'].values()))))
