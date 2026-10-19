#!/usr/bin/env python3
"""Validate an isolated original lock observer. Never enable/load/enter RM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
sys.path.insert(0,str(REPO/'builders'))
import compile_nvidia_global_rm as original
import check_nvidia_execution as execution
import nvidia_metaclass_initializers as metaclass
from prepare import prepare,sha
sys.path.insert(0,str(REPO/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original'))
from common import validate_sdk

def require(value,message):
    if not value:raise ValueError(message)

def check(args):
    output=args.output.resolve();upstream=args.upstream.resolve(strict=True)
    v3=args.v3_root.resolve(strict=True);namespace=args.namespace.resolve(strict=True)
    v3_project=(v3.parent/'project-overlay').resolve(strict=True)
    require(not output.exists(),'Fresh output directory required')
    sdk_value=args.sdk or os.environ.get('MAC_KERNEL_SDK') or os.environ.get('KERNEL_SDK')
    sdk_path=Path(sdk_value).resolve(strict=True) if sdk_value else None
    for tree in [HERE,upstream,v3,v3_project,*([sdk_path] if sdk_path else [])]:
        require(not output.is_relative_to(tree) and not tree.is_relative_to(output),'Output overlaps source input')
    require(not (output.is_relative_to(REPO) and not output.is_relative_to(REPO/'build')),'Repo output allowed only under build/')
    require(execution.commands.run('git','-C',str(upstream),'rev-parse','HEAD').stdout.strip()==original.COMMIT,'Wrong original commit')
    require(not execution.commands.run('git','-C',str(upstream),'status','--porcelain').stdout,'Dirty original source')
    namespace_contract=json.loads((REPO/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    require(sha(namespace.read_bytes())==namespace_contract['namespace_sha256'],'Wrong private original namespace')
    sdk=validate_sdk(sdk_path,args.sdk_archive,args.host_control)
    output.mkdir(parents=True)
    prepared=prepare(upstream,v3,output/'source')
    execution.commands.run(sys.executable,str(HERE/'tests/test_source_contracts.py'),
        '--upstream',str(upstream),'--v3-root',str(v3),diagnostic_log=output/'provenance.log')
    native=execution.original_header_case(output,'lock-ownership',upstream,namespace,
        [HERE/'S540ProspectiveRmLockOwnership.c',HERE/'tests/check_lock_ownership.c'],
        [HERE/'tests/context_control.cpp',*[execution.SERVICES/('src/S540NvidiaDarwin'+name+'.cpp') for name in execution.SERVICE_NAMES]],
        {'component':'prospective-rm-lock-ownership','checks':CHECKS,'actual_original_bodies':10,
         'state_and_lifecycle_fixtures':True,'original_entry_admission':False},
        host_control=args.host_control,
        extra_c_flags=['-std=gnu11','-Werror','-Wno-unused-parameter',
            '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1','-I',str(HERE),'-I',str(output/'source')])
    cc,_=execution.crypto.compiler_pair(args.host_control)
    cc=Path(cc[0])
    commands=original.original_commands(upstream,output/'full-objects',cc)
    units=[]
    for relative in ['src/nvidia/src/kernel/core/locks.c','src/nvidia/src/kernel/rmapi/rmapi.c',
            'src/nvidia/arch/nvalloc/unix/src/os.c','S540ProspectiveRmLockOwnership.c']:
        if relative.startswith('src/'):
            matches=[c for c in commands if (upstream/'src/nvidia'/c[c.index('-c')+1]).resolve()==upstream/relative]
            require(len(matches)==1,'Original TU command not unique: '+relative)
            command=matches[0][:matches[0].index('-c')]
            source=output/'source'/relative if relative in prepared['composed_original_sources'] else v3/relative
        else:
            command=commands[0][:commands[0].index('-c')];source=HERE/relative
        obj=output/(source.stem+'-kernel.o')
        command += ['-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__','-DNV_VERSION_STRING="615.78.08"',
            '-include',str(namespace),'-I',str(HERE),
            *(['-iquote',str((v3/relative).parent)] if relative.startswith('src/') else []),
            '-I',str(v3_project/'packages/nvidia-gsp-bootstrap/cancellation'),
            '-I',str(v3_project/'packages/nvidia-gsp-bootstrap/timers'),
            '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1',
            *(['-target','x86_64-macos-none'] if args.host_control else ['-arch','x86_64']),
            '-fPIC','-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than',
            '-c',str(source),'-o',str(obj)]
        original.execute(command,cwd=v3/'src/nvidia',diagnostic_log=output/(source.stem+'-kernel.log'))
        defined,imports,sections=original.macho_symbols(obj);metaclass.verify_no_initializers(obj)
        units.append({'source':relative,'source_sha256':sha(source.read_bytes()),'object':obj.name,
            'object_sha256':sha(obj.read_bytes()),'definitions':sorted(defined),'imports':sorted(imports),'sections':sections,'command':command})
    require('s540ProspectiveOriginalGpuOwnership' in units[0]['definitions'],'Actual original GPU getter missing')
    require('s540ProspectiveOriginalApiOwnership' in units[1]['definitions'],'Actual original API getter missing')
    expected_legacy={original.PREFIX+name for name in ['osAcquireRmSema','osCondAcquireRmSema','osReleaseRmSema']}
    require(expected_legacy <= set(units[2]['definitions']),'Actual original legacy definitions missing')
    flags=original.original_bridge_flags(upstream,output,cc,namespace)
    flags += [*(['-target','x86_64-macos-none'] if args.host_control else ['-arch','x86_64']),
        '-Werror','-I',str(HERE)]
    negatives=[]
    for index,profile in enumerate([[],['-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=0'],['-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=2']]):
        result=subprocess.run([str(cc),*flags,*profile,'-c',str(HERE/'S540ProspectiveRmLockOwnership.c'),'-o',str(output/f'refused-{index}.o')],text=True,capture_output=True)
        diagnostic=result.stdout+result.stderr;(output/f'negative-{index}.log').write_text(diagnostic)
        require(result.returncode!=0 and 'Explicit sealed original no-legacy-RM-semaphore profile required' in diagnostic,'Profile refusal missing')
        negatives.append({'flags':profile,'rejected':True})
    result={'format':1,'status':'passed-isolated-source-candidate','native':native,'prepared_source':prepared,
        'kernel_target_compile_actions':units,'sdk_identity':sdk,'configuration_negative_controls':negatives,
        'native_apple_execution':not args.host_control,'actual_kernel_execution':'not_tested',
        'serialized_global_lifetime_and_irq_dpc_exclusion':'required-caller-precondition-not-issued-by-this-query',
        'final_image_original_definition_binding':'not_proved','foreign_quiescence_proved':False,
        'frozen_first_transaction_modified':False,'production_default_changed':False,
        'production_candidate_allowed':False,'original_entry_admission':False,'gpu_access':False}
    (output/'rm-lock-ownership-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result

CHECKS=78
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['upstream','v3-root','namespace','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--sdk',type=Path);parser.add_argument('--sdk-archive',type=Path)
    parser.add_argument('--host-control',action='store_true')
    result=check(parser.parse_args())
    print(json.dumps({'status':result['status'],'checks_per_variant':CHECKS,'kernel_target_compile_actions':4,'original_entry_admission':False}))
