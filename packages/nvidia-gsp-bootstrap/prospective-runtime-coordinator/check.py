#!/usr/bin/env python3
"""Actual coordinator and immutable-profile bodies with explicit CPU fixtures."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def execute(command,log,*,expected=0):
    result=subprocess.run(list(map(str,command)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1'),timeout=120)
    log.write_bytes(result.stdout)
    if expected==0 and result.returncode!=0:raise ValueError('CPU control failed: '+str(log))
    if expected!=0 and result.returncode==0:raise ValueError('Mutant was not killed: '+str(log))
    return result
def fixture_text(entry=None,methods=None):
    text=(HERE/'tests/check_runtime.cpp').read_text()
    for relative in ('../S540ExperimentalRuntime.h','../../../nvidia-global-rm/src/S540NvidiaGlobalRm.h','../../src/S540NvidiaGspContext.h'):
        text=text.replace('"'+relative+'"','"'+str((HERE/'tests'/relative).resolve())+'"')
    for name,value in [('runtime-entry.cpp.inc',entry),('owner-methods.cpp.inc',methods),('facade-methods.cpp.inc',None)]:
        text=text.replace('#include "../'+name+'"',value if value is not None else (HERE/name).read_text())
    return text

def check(args):
    if not args.host_control:raise ValueError('Explicit CPU --host-control required')
    base=args.base.resolve(strict=True);output=args.output.resolve()
    if output.exists():raise ValueError('Fresh CPU evidence output required')
    output.mkdir(parents=True)
    compiler=args.cxx.resolve(strict=True)
    includes=[base/'project/packages',base/'project/packages/nvidia-gsp-bootstrap/src',
        base/'project/packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        base/'project/packages/nvidia-gsp-bootstrap/prospective-first-transaction/services']
    flags=['-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',*[x for p in includes for x in ('-I',str(p))]]
    commands=[];runs=[]
    for label,sanitize in [('plain',[]),('sanitized',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all'])]:
        source=output/(label+'.cpp');source.write_text(fixture_text())
        exe=output/(label+'.out');command=[compiler,*flags,*sanitize,source,'-o',exe]
        execute(command,output/(label+'-compile.log'));commands.append(list(map(str,command)))
        result=execute([exe],output/(label+'-run.log'));runs.append(dict(mode=label,**json.loads(result.stdout)))
    entry=(HERE/'runtime-entry.cpp.inc').read_text();methods=(HERE/'owner-methods.cpp.inc').read_text()
    mutants={
        'missing_operation_begin':(entry,methods.replace('status=s540GspCancellationBegin(token);if(status!=NV_OK)return runtimeFailure(status);','status=NV_OK;',1)),
        'mismatched_native_contract':(entry,methods.replace('!runtimeEqual(runtimeRequest.codeContractSha256,profile.codeContractSha256,32)','false',1)),
        'overwrite_first_attempt':(entry,methods.replace('if(runtimeState.stage!=S540_RUNTIME_UNUSED)return NV_ERR_STATE_IN_USE;','',1)),
        'foreign_global_master':(entry.replace('if(tid!=entry->thread)return NV_ERR_INVALID_STATE;','',1)
            .replace('global.masterThread!=tid||','',1).replace('cancellation.ownerThread!=tid||','',1),methods)}
    killed=[]
    for name,(badentry,badmethods) in mutants.items():
        if badentry==entry and badmethods==methods:raise ValueError('Stale mutation anchor '+name)
        source=output/(name+'.cpp');source.write_text(fixture_text(badentry,badmethods));exe=output/(name+'.out')
        command=[compiler,*flags,source,'-o',exe];execute(command,output/(name+'-compile.log'))
        execute([exe],output/(name+'-run.log'),expected=1);killed.append(name);commands.append(list(map(str,command)))
    profile=load('runtime_profile_control',HERE/'profile.py')
    good=profile.encode_profile('ab'*32,16384,16384)
    if len(good)!=104 or profile.decode_profile(good)['worker_stack_bytes']!=16384:raise ValueError('Profile ABI/equality differs')
    invalid=[]
    for label,offset,byte in [('format',0,2),('bytes',4,103),('target',40,ord('X')),('trailingtarget',47,1),
                             ('worker',63,1),('irq',71,1),('framework',73,0)]:
        changed=bytearray(good);changed[offset]=byte;invalid.append((label,bytes(changed),False))
    empty=bytearray(good);empty[8:40]=b'\0'*32;invalid.append(('emptycontract',bytes(empty),False))
    for _,data,_ in invalid:
        try:profile.decode_profile(data)
        except ValueError:pass
        else:raise ValueError('Invalid profile accepted')
    assets_source=(HERE/'tests/check_assets.cpp').read_text().replace('"../S540ExperimentalRuntime.h"','"'+str(HERE/'S540ExperimentalRuntime.h')+'"')
    assets_fixture=output/'check_assets.cpp';assets_fixture.write_text(assets_source)
    asset_runs=[]
    for label,data,valid in [('valid',good,True),*invalid,('firmware-boundary',good,True)]:
        payload=output/(label+'.bin');payload.write_bytes(data)
        asm=output/(label+'.S');gspSize=22901631 if label=='firmware-boundary' else 22901632
        asm.write_text('.section .rodata\n.globl s540ExperimentalNativeProfileBegin\n.globl s540ExperimentalNativeProfileEnd\n'
            's540ExperimentalNativeProfileBegin:\n.incbin "'+str(payload)+'"\ns540ExperimentalNativeProfileEnd:\n'
            '.globl s540_gsp_begin\n.globl s540_gsp_end\ns540_gsp_begin:\n.byte 0\n'
            '.set s540_gsp_end,s540_gsp_begin+'+str(gspSize)+'\n'
            '.globl s540_ucodes_begin\n.globl s540_ucodes_end\ns540_ucodes_begin:\n.byte 0\n'
            '.set s540_ucodes_end,s540_ucodes_begin+8837632\n.section .note.GNU-stack,"",@progbits\n')
        exe=output/(label+'-assets.out');command=[compiler,*flags,HERE/'S540ExperimentalAssets.cpp',assets_fixture,asm,'-o',exe]
        execute(command,output/(label+'-assets-compile.log'));commands.append(list(map(str,command)))
        execute([exe,'1' if valid else '0','0' if label=='firmware-boundary' else '1'],output/(label+'-assets-run.log'))
        asset_runs.append(label)
    prep=load('runtime_preparation_control',HERE/'prepare.py')
    pm=load('runtime_pm_control',ROOT/'packages/nvidia-gsp-bootstrap/prospective-pm-event-closure/prepare.py')
    project=base/'project';pmvalues=pm.transforms({name:(project/name).read_text() for name in pm.INPUTS})
    values={name:pmvalues.get(name,(project/name).read_text()) for name in prep.INPUTS}
    changed=prep.transforms(values)
    for name in prep.INPUTS:
        corrupt=dict(values);corrupt[name]+='\n'
        try:prep.transforms(corrupt)
        except ValueError:pass
        else:raise ValueError('Changed prerequisite admitted: '+name)
    report=dict(format=1,status='passed-actual-runtime-bodies-and-explicit-cpu-fixtures',
        hardware_executed=False,original_rm_executed=False,native_darwin_compilation=False,
        runs=runs,mutants_killed=killed,actual_assets_controls=asset_runs,profile_bytes=104,
        exact_source_refusal_controls=len(prep.INPUTS),commands=commands,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [*map(lambda n:HERE/n,prep.SOURCE_FILES),HERE/'tests/check_runtime.cpp',HERE/'tests/check_assets.cpp']},
        output_sha256={name:hashlib.sha256(text.encode()).hexdigest() for name,text in changed.items()},
        formal_stack_proof=False,whole_dma_stop_proven=False,physical_reclamation_authorized=False)
    (output/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cxx',type=Path,required=True);parser.add_argument('--host-control',action='store_true')
    result=check(parser.parse_args());print(json.dumps({key:result[key] for key in ('status','runs','mutants_killed','actual_assets_controls')}))
