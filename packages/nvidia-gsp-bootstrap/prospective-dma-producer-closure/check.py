#!/usr/bin/env python3
"""Actual retained record, cancellation and complete Session CPU controls."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import prepare

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v): p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def inventory(root):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
def execute(command,log,environment=None,expected=0):
    r=subprocess.run([str(v) for v in command],text=True,capture_output=True,timeout=180,env=environment)
    log.write_text(r.stdout+r.stderr)
    if r.returncode!=expected:raise ValueError('DMA body command failed: '+str(log)+'\n'+r.stderr[-5000:])
    return r
def materialize(base,output):
    project=output/'project';shutil.copytree(base/'project',project)
    pm=load('s540_dma_pm_prepare',HERE.parent/'prospective-pm-revocation-closure/prepare.py')
    for name,text in pm.transforms({n:(base/'project'/n).read_text() for n in pm.INPUTS}).items():
        (project/name).write_text(text)
    for module in (pm,prepare):
        for name,path in module.COMPANIONS.items():
            target=project/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    for name,text in prepare.transforms({n:(base/'project'/n).read_text() for n in prepare.INPUTS}).items():(project/name).write_text(text)
    for name,text in prepare.original_transforms({n:(base/'source'/n).read_text() for n in prepare.ORIGINAL_INPUTS}).items():
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    return project,pm
def run(args):
    base=args.base.resolve(strict=True);output=args.output.resolve()
    if output.exists() or output.is_relative_to(HERE):raise ValueError('Fresh isolated DMA output required')
    if sha(base/'composition.json')!='40f0fd1fc279421464c14f9b98f7fa84f6850e6fafb61d46aa60663ce471dd4c':raise ValueError('Exact operational2 source parent required')
    manifest=json.loads((base/'composition.json').read_text())
    base_project={name:row['sha256'] for name,row in manifest['project_files'].items()}
    if inventory(base/'project')!=base_project:raise ValueError('Authenticated parent project/header inventory changed')
    output.mkdir(parents=True)
    project,pm=materialize(base,output)
    inputs={str(p):sha(p) for p in [Path(__file__),HERE/'prepare.py',HERE/'cleanup-mask.c.inc',HERE/'S540NvidiaDmaProducer.h',
        HERE/'tests/check_record.c',HERE/'tests/check_session.cpp',pm.HERE/'prepare.py',pm.HERE/'commit-api.c.inc',*pm.COMPANIONS.values()]}
    project_before=inventory(project)
    compiler_bindings={str(path.resolve(strict=True)):sha(path.resolve(strict=True)) for path in (args.cc,args.cxx)}
    package=project/'packages'
    record=package/'nvidia-gsp-bootstrap/prospective-first-transaction/record'
    cancellation=project/pm.CANCEL
    includes=[record,record/'deps',package,package/'nvidia-darwin-services/src',package/'nvidia-device-transport/src',
        project/prepare.PREFIX,project/pm.DIRECTORY,package/'nvidia-gsp-bootstrap/prospective-irq-callback-closure']
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-ffunction-sections','-fdata-sections',
        *[flag for path in includes for flag in ('-I',str(path))]]
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    result={'format':1,'status':'running','base_composition_sha256':sha(base/'composition.json'),'source_sha256':inputs,
        'variants':{},'genuine_strong_record':True,'genuine_cancellation_commit':True,'complete_session_implementation':True,
        'compiler_file_sha256':compiler_bindings,'parent_project_headers_verified':True,
        'selected_project_inventory_sha256':hashlib.sha256(json.dumps(project_before,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'clock_thread_metadata_original_return_and_backend_endpoints':'explicit CPU fixtures',
        'original_entry_admission':False,'hardware_execution':False,'whole_dma_stop_proven':False,'pm_acknowledgement_authorized':False}
    write(output/'results.json',result)
    try:
        for variant in args.variants:
            work=output/variant;work.mkdir()
            selected=[*flags]
            if variant=='sanitized':selected+=['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            cancel=work/'cancellation.o'
            commands=[]
            command=[str(args.cc),'-std=c11',*selected,'-MD','-MF',str(cancel.with_suffix('.d')),'-c',str(cancellation),'-o',str(cancel)]
            execute(command,cancel.with_suffix('.log'));commands.append(command)
            record_binary=work/'record'
            command=[str(args.cc),'-std=c11',*selected,str(project/prepare.RECORD),str(HERE/'tests/check_record.c'),str(cancel),'-Wl,--gc-sections','-o',str(record_binary)]
            execute(command,work/'record-compile.log');commands.append(command)
            session_binary=work/'session'
            command=[str(args.cxx),'-std=c++17',*selected,str(project/prepare.SESSION),str(HERE/'tests/check_session.cpp'),str(cancel),'-Wl,--gc-sections','-o',str(session_binary)]
            execute(command,work/'session-compile.log');commands.append(command)
            observations={}
            for label,binary,count in [('record',record_binary,21),('session',session_binary,8)]:
                rows=[];binary_hash=sha(binary)
                for scenario in range(count):
                    raw=execute([binary,scenario],work/(label+'-%02d.log'%scenario),env)
                    row=json.loads(raw.stdout)
                    if row['failures']:raise ValueError('DMA source body assertion failed')
                    rows.append(row)
                if sha(binary)!=binary_hash:raise ValueError('Executed DMA CPU binary changed during cases')
                observations[label]={'scenarios':count,'checks':sum(row['checks'] for row in rows),'observations':rows,'binary_sha256':binary_hash}
            negative={}
            for label in ('foreign-cleanup-authorizer','session-bme-commit-bypass'):
                if label=='foreign-cleanup-authorizer':
                    source=work/'mutant-record.c'
                    original=(project/prepare.RECORD).read_text()
                    text=prepare.modify(original,'s540FirstTxnCleanupMaskReadMaster',lambda body: prepare.once(body,
                        'if (checkedMaster(nv) != NV_OK || !exactGlobalMaster())', 'if (NV_FALSE)'))
                    source.write_text(text)
                    binary=work/'mutant-record'
                    command=[str(args.cc),'-std=c11',*selected,str(source),str(HERE/'tests/check_record.c'),str(cancel),'-Wl,--gc-sections','-o',str(binary)]
                    scenario=1
                else:
                    source=work/'mutant-session.cpp'
                    original=(project/prepare.SESSION).read_text()
                    source.write_text(prepare.once(original,'if ((rmBound_ || hardwareDmaHeld_) &&', 'if (false &&'))
                    binary=work/'mutant-session'
                    command=[str(args.cxx),'-std=c++17',*selected,str(source),str(HERE/'tests/check_session.cpp'),str(cancel),'-Wl,--gc-sections','-o',str(binary)]
                    scenario=3
                # Quoted relative includes in the complete original record
                # remain relative to its genuine selected source directory.
                if label=='foreign-cleanup-authorizer':command[2:2]=['-I',str((project/prepare.RECORD).parent)]
                execute(command,work/(label+'-compile.log'));commands.append(command)
                raw=execute([binary,scenario],work/(label+'-run.log'),env,expected=1)
                row=json.loads(raw.stdout)
                if not row['failures']:raise ValueError('DMA negative source mutation was not detected')
                negative[label]={'scenario':scenario,'failures_detected':row['failures'],'binary_sha256':sha(binary),'source_sha256':sha(source)}
            result['variants'][variant]={'status':'passed','controls':observations,'negative_controls':negative,'commands':commands}
            write(output/'results.json',result)
        if inventory(project)!=project_before or inventory(base/'project')!=base_project:raise ValueError('Selected CPU project/header source changed during controls')
        for path,digest in compiler_bindings.items():
            if sha(Path(path))!=digest:raise ValueError('CPU compiler changed during controls')
        for p,d in inputs.items():
            if sha(Path(p))!=d:raise ValueError('DMA/PM source changed during controls: '+p)
        result['status']='passed-actual-retained-record-and-session-dma-guards'
        return result
    except Exception as error:
        result.update(status='failed',error=str(error));raise
    finally:write(output/'results.json',result)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('base','output','cc','cxx'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--variants',nargs='+',choices=('plain','sanitized'),default=['plain','sanitized'])
    result=run(parser.parse_args());print(json.dumps({'status':result['status'],'variants':{v:{k:r['checks'] for k,r in data['controls'].items()} for v,data in result['variants'].items()}}))
