#!/usr/bin/env python3
"""Real control lock/strong-record checks; no descriptor/event admission."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
PARENT=HERE.parent/'prospective-first-transaction'
sys.path.insert(0,str(REPO/'builders'))
import compile_nvidia_global_rm as original
import nvidia_metaclass_initializers as metaclass

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def body(text,name):
    matches=list(re.finditer(r'(?m)^\s*(?:static\s+)?(?:NV_STATUS|void)(?:\s+NV_API_CALL)?\s+'+re.escape(name)+r'\s*\(',text))
    if len(matches)!=1:raise ValueError('Original function identity changed: '+name)
    start=matches[0].start();opening=text.index('{',matches[0].end());depth=1
    tokens=re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]',re.S)
    for token in tokens.finditer(text,opening+1):
        depth+=(token[0]=='{')-(token[0]=='}')
        if not depth:return text[start:token.end()]
    raise ValueError('Original function not closed: '+name)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def check(args):
    up=args.upstream.resolve(strict=True);composition=args.composition.resolve(strict=True)
    output=args.output.resolve()
    if output.exists() or output.is_relative_to(HERE) or output.is_relative_to(up):
        raise ValueError('Fresh independent control output required.')
    manifest=json.loads(composition.read_text());project=composition.parent/manifest['project']
    if manifest.get('status')!='materialized-source-only':raise ValueError('Exact source-only composition required.')
    for name,metadata in manifest['project_files'].items():
        if (project/name).is_symlink() or sha(project/name)!=metadata['sha256']:
            raise ValueError('Composed project changed: '+name)
    pin=load('s540_control_pin_prepare',HERE.parent/'prospective-retained-diagnostic/prepare.py')
    backends=load('s540_control_backends_prepare',HERE.parent/'prospective-retained-backends/prepare.py')
    epoch=load('s540_control_global_prepare',HERE.parent/'prospective-global-epoch/prepare.py')
    source_inputs=[HERE/'S540NvidiaControlState.c',HERE/'S540NvidiaControlState.h',HERE/'check_control.c',
        HERE/'check.py',PARENT/'services/check_joint.py',PARENT/'services/check_strong_joint.c',
        HERE.parent/'prospective-retained-diagnostic/prepare.py',
        *sorted((HERE.parent/'prospective-retained-backends').glob('*.inc')),
        HERE.parent/'prospective-retained-backends/prepare.py']
    source_inputs += [HERE.parent/'prospective-global-epoch/prepare.py',
                      *sorted((HERE.parent/'prospective-global-epoch').glob('*.inc')),
                      HERE/'SOURCE-CONTRACT.json']
    input_hashes={str(path):sha(path) for path in source_inputs}
    guard=load('s540_control_parent_guard',HERE.parent/'prospective-work-gpu-binding/prepare.py')
    guard.parent_guard()
    sys.path.insert(0,str(PARENT/'original'));import common
    identity=common.execution_identity(common.compiler(str(args.cc)),common.compiler(str(args.cxx)),args.host_control)
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    for root,key in ((up,'original_sha256'),(REPO,'project_sha256'),(HERE,'source_sha256')):
        for name,digest in contract[key].items():
            path=root/name
            if path.is_symlink() or sha(path)!=digest:raise ValueError('Control source contract changed: '+name)
    if original.execute(['git','-C',str(up),'status','--porcelain']).stdout:
        raise ValueError('Original source checkout must be clean.')
    if original.execute(['git','-C',str(up),'rev-parse','HEAD']).stdout.strip()!=original.COMMIT:
        raise ValueError('Wrong upstream commit.')
    namespace_contract=json.loads((REPO/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    if sha(args.namespace.resolve(strict=True))!=namespace_contract['namespace_sha256']:
        raise ValueError('Wrong original namespace.')
    output.mkdir(parents=True)
    host=output/'host';record=output/'record';services=output/'services'
    shutil.copytree(project,host);shutil.copytree(PARENT/'record',record,ignore=shutil.ignore_patterns('__pycache__'))
    services.mkdir()
    for name in ('S540NvidiaFirstTxnServices.cpp','S540NvidiaFirstTxnServices.h'):
        shutil.copy2(PARENT/'services'/name,services/name)
    parent_fixture=(PARENT/'services/check_strong_joint.c').read_text()
    parent_fixture=pin.once(parent_fixture,'static unsigned checks, failures;',
        '#include "S540NvidiaControlState.h"\nstatic NvU32 callbackControlStatus;\nstatic unsigned checks, failures;')
    parent_fixture=pin.once(parent_fixture,'    require(parameter == event && event->owner == object);',
        '    if(mode==8)callbackControlStatus=s540ControlStatePrepare();\n'
        '    require(parameter == event && event->owner == object);')
    (services/'parent-controls.inc').write_text(parent_fixture)
    shutil.copy2(HERE/'check_control.c',services/'check_strong_joint.c')
    values={name:(project/name).read_text() for name in (pin.HOST,pin.RETENTION,pin.RETENTION_ORIGIN)}
    if 'diagnosticRetiredAllocations' in values[pin.RETENTION]:
        raise ValueError('Use the baseline composition before the retained-diagnostic transform.')
    values[pin.RECORD]=(PARENT/'record/S540NvidiaGspFirstTransaction.c').read_text()
    values[pin.HEADER]=(PARENT/'record/S540NvidiaGspFirstTransaction.h').read_text()
    transformed=pin.transforms(values)
    backend_values={name:transformed[name] if name in transformed else (project/name).read_text()
                    for name in backends.INPUTS}
    transformed.update(backends.transforms(backend_values))
    epoch_values={name:transformed[name] if name in transformed else (project/name).read_text()
                  for name in epoch.INPUTS}
    transformed.update(epoch.transforms(epoch_values))
    for name,text in transformed.items():
        (host/name).write_text(text)
        if name==pin.RECORD:(record/'S540NvidiaGspFirstTransaction.c').write_text(text)
        if name==pin.HEADER:(record/'S540NvidiaGspFirstTransaction.h').write_text(text)
    sync=up/'src/nvidia/src/libraries/nvport/sync/sync_unix_kernel_os.c'
    os_source=up/'src/nvidia/arch/nvalloc/unix/src/os.c'
    bridge=REPO/'packages/nvidia-global-rm/src/S540NvidiaGlobalRmOs.c'
    actual_bridge=bridge.read_text();begin=actual_bridge.index('enum {');end=actual_bridge.index('NV_STATUS os_alloc_mem')
    pieces=['#include "nvport/nvport.h"\n#include "nvport/sync/inc/sync_unix_kernel_os_def.h"\n#include "nv-chardev-numbers.h"',
            actual_bridge[begin:end]]
    for line in actual_bridge.splitlines():
        if any(line.startswith(prefix+'('+name+',') for prefix in ('STATUS_BRIDGE','VOID_BRIDGE')
               for name in ('os_alloc_spinlock','os_acquire_spinlock','os_release_spinlock')):pieces.append(line)
    pieces+=['#undef MARK',body(sync.read_text(),'portSyncSpinlockInitialize'),
             body(sync.read_text(),'portSyncSpinlockAcquire'),body(sync.read_text(),'portSyncSpinlockRelease'),
             body(os_source.read_text(),'osUserHandleToKernelPtr').replace('osUserHandleToKernelPtr','control_osUserHandleToKernelPtr'),
             '#include "'+str(HERE/'S540NvidiaControlState.c')+'"']
    extracted=services/'control-original-bodies.inc';extracted.write_text('\n\n'.join(pieces)+'\n')
    sys.path.insert(0,str(PARENT/'services'))
    joint=load('s540_control_joint',PARENT/'services/check_joint.py');joint.HERE=services
    joint.SERVICE=host/'packages/nvidia-darwin-services/src'
    saved=joint.original.original_bridge_flags
    def flags(*values,**kwargs):
        return [*saved(*values,**kwargs),'-I'+str(up/'src/nvidia/src/libraries'),
                '-I'+str(HERE),'-DS540_NVIDIA_NO_CHARACTER_DEVICE=1','-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1']
    joint.original.original_bridge_flags=flags
    try:
        result=joint.check({'upstream':up,'namespace':args.namespace,'output':output/'checks',
            'cc':args.cc,'cxx':args.cxx,'host_overlay':host,
            'services_overlay':composition.parent/'inputs/work-gpu/services-overlay','host_control':args.host_control})
    finally:joint.original.original_bridge_flags=saved
    cc=common.compiler(str(args.cc))
    kernel_flags=[*saved(up,output/'kernel-profile',cc,args.namespace.resolve(strict=True)),
        '--target=x86_64-apple-macos15.0','-mkernel','-DKERNEL','-D__KERNEL__',
        '-I'+str(up/'src/nvidia/src/libraries'),'-I'+str(record),'-DS540_NVIDIA_NO_CHARACTER_DEVICE=1',
        '-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1','-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than','-fstack-usage']
    obj=output/'control-state-kernel.o'
    command=[str(cc),*kernel_flags,'-c',str(HERE/'S540NvidiaControlState.c'),'-o',str(obj)]
    original.execute(command,diagnostic_log=output/'kernel-compile.log')
    definitions,imports,_=original.macho_symbols(obj)
    metaclass.verify_no_initializers(obj)
    expected={'s540ControlStatePrepare','s540ControlStateBindAdapter',*[original.PREFIX+x for x in
        ('nv_get_ctl_state','nv_get_dev_minor','nv_get_file_private','nv_put_file_private','nv_post_event')]}
    if definitions!=expected:raise ValueError('Unreviewed control exports.')
    expected_imports={'s540Darwin_os_semaphore_may_sleep','s540Darwin_os_get_current_thread',
        's540FirstTxnMasterIdentity','s540FirstTxnObserveServiceRefusal','s540FirstTxnGetSnapshot',
        's540GlobalRmRecordServiceName','s540GlobalRmRecordUnavailable',
        original.PREFIX+'portSyncSpinlockInitialize',original.PREFIX+'os_bug_check'}
    if not expected_imports<=imports or imports-expected_imports-original.COMPILER_MEMORY_IMPORTS:
        raise ValueError('Unreviewed control imports: '+str(imports^expected_imports))
    profile_flags={'-DS540_NVIDIA_NO_CHARACTER_DEVICE=1','-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1'}
    bare_flags=[f for f in kernel_flags if f not in profile_flags]
    negative_profiles=[[],['-DS540_NVIDIA_NO_CHARACTER_DEVICE=1'],['-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1'],
        ['-DS540_NVIDIA_NO_CHARACTER_DEVICE=0','-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1'],
        ['-DS540_NVIDIA_NO_CHARACTER_DEVICE=2','-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1'],
        ['-DS540_NVIDIA_NO_CHARACTER_DEVICE=1','-DS540_NVIDIA_NO_OS_EVENT_BACKEND=0']]
    negatives=[]
    for index,profile in enumerate(negative_profiles):
        candidate=subprocess.run([str(cc),*bare_flags,*profile,'-c',str(HERE/'S540NvidiaControlState.c'),
            '-o',str(output/f'negative-{index}.o')],text=True,capture_output=True)
        diagnostic=candidate.stdout+candidate.stderr
        (output/f'negative-{index}.log').write_text(diagnostic)
        if not candidate.returncode or not ('Explicit no-character-device' in diagnostic or
                'Actual OS-event constructor refusal' in diagnostic):raise ValueError('Contradictory profile accepted.')
        negatives.append({'profile':profile,'refused':True})
    if any(sha(Path(path))!=digest for path,digest in input_hashes.items()):
        raise ValueError('Control input changed during validation.')
    for name,metadata in manifest['project_files'].items():
        if sha(project/name)!=metadata['sha256']:raise ValueError('Composition changed during validation.')
    result.update(component='permanent-control-empty-file-table',execution_identity=identity,
        original_body_controls={'complete_functions':4,'unchanged_original_spinlock_bodies':3,
            'original_handle_lookup':True,'source_sha256':{str(p):sha(p) for p in (sync,os_source,bridge)},
            'fixture_sha256':sha(extracted)},
        source_sha256={**result['source_sha256'],str(HERE/'S540NvidiaControlState.c'):sha(HERE/'S540NvidiaControlState.c'),
            str(HERE/'S540NvidiaControlState.h'):sha(HERE/'S540NvidiaControlState.h')},
        kernel_compile={'command':command,'object_sha256':sha(obj),'definitions':sorted(definitions),'imports':sorted(imports)},
        negative_profiles=negatives,
        control_inputs_sha256=input_hashes,
        file_descriptors_registered=0,os_events_admitted=False,final_release_implemented=False,
        fatal_handler_fixture=True,original_metadata_and_token_readers='explicit-parent-CPU-fixtures',
        production_candidate_allowed=False,original_entry_admission=False,module_loaded=False,gpu_access=False)
    (output/'control-state-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('upstream','namespace','composition','output','cc','cxx'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--host-control',action='store_true')
    check(parser.parse_args())
