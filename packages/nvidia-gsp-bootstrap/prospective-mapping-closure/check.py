#!/usr/bin/env python3
"""Exercise genuine mapping state with the actual strong record and real locks."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
GPU=HERE.parent/'prospective-work-gpu-binding'
sys.path.insert(0,str(GPU))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
gpu=load('mapping_gpu_checks',GPU/'check.py')
candidate=gpu.candidate
SOURCE='src/nvidia/arch/nvalloc/unix/src/dynamic-power.c'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(args):
 from profile_guard import validate_profile
 selected_profile=validate_profile()
 frozen={str(p):sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ('.c','.cpp','.py','.json')}
 output=Path(args.output).resolve()
 if output.exists():raise ValueError('Fresh output required')
 if output.is_relative_to(HERE) or HERE.is_relative_to(output):raise ValueError('Output overlaps candidate source')
 upstream=Path(args.upstream).resolve(strict=True)
 baseline=gpu.run(SimpleNamespace(**{**vars(args),'output':output/'parent'}))
 parent=output/'parent'
 support=(parent/'parent-support.inc').read_text()
 support=candidate.once(support,'static NvU32 checks,failures,callbackCalls,lockAcquires,lockReleases,workFrees;',
  'static void mapping_Run(void);\nstatic NvU32 checks,failures,callbackCalls,lockAcquires,lockReleases,workFrees;')
 old='__atomic_add_fetch(&callbackCalls,1U,__ATOMIC_RELAXED);}'
 support=candidate.once(support,old,'__atomic_add_fetch(&callbackCalls,1U,__ATOMIC_RELAXED);mapping_Run();}')
 (output/'parent-support.inc').write_text(support)
 extract=candidate.load('mapping_body_extract',candidate.PARENT/'record/prepare_actual_original.py')
 bodies=[]
 for name in ['RmIndicateIdle','RmForceGpuNotIdle']:
  body=extract.body((upstream/SOURCE).read_text(),name)
  bodies.append(re.sub(r'\b'+name+r'\b','control_'+name,body))
 (output/'actual-mapping-callers.inc').write_text('\n'.join(bodies))
 env=os.environ.copy()
 if args.host_control:env['ASAN_OPTIONS']='detect_leaks=0'
 commands=[];deps={};results={}
 def execute(command,name):
  command=[str(x) for x in command]
  p=subprocess.run(command,text=True,capture_output=True,env=env,timeout=60)
  (output/(name+'.log')).write_text(p.stdout+p.stderr);commands.append({'name':name,'command':command,'status':p.returncode})
  if p.returncode:raise RuntimeError(name+'\n'+p.stdout+p.stderr)
  return p.stdout
 profile='-DS540_NVIDIA_NO_USER_MAPPINGS=1'
 for mode in ['plain','fatal-sanitizers']:
  folder=output/mode;folder.mkdir()
  rows=[r for r in baseline['commands'] if r['name'].startswith(mode+'-')]
  objects=[];template=None
  for row in rows:
   command=row['command']
   if '-c' not in command:continue
   source=Path(command[command.index('-c')+1]);obj=Path(command[command.index('-o')+1])
   if source.name=='check_controls.c':template=command
   else:objects.append(obj)
  if template is None:raise ValueError('No actual parent original-header compile command')
  for index,source in enumerate([HERE/'check_controls.c',HERE/'S540NvidiaMappingClosure.c',HERE/'failure_fixture.cpp']):
   command=template.copy();command[command.index('-c')+1]=str(source)
   if source.suffix=='.cpp':
    command[0]=str(args.cxx.absolute());command=[x for x in command if x not in ('-std=gnu11','--std=gnu11')];command.insert(1,'-std=c++17')
   obj=folder/(str(index)+'-'+source.stem+'.o');command[command.index('-o')+1]=str(obj)
   dep=obj.with_suffix('.d');command[command.index('-MF')+1]=str(dep)
   command[1:1]=['-I',str(output),'-I',str(HERE),profile]
   execute(command,mode+'-'+source.stem);objects.append(obj)
   for filename in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
    p=Path(filename).resolve(strict=True);digest=sha(p)
    if deps.setdefault(str(p),digest)!=digest:raise ValueError('Dependency changed')
  link=next(r['command'] for r in rows if r['name']==mode+'-link').copy()
  first=next(i for i,x in enumerate(link) if x.endswith('.o'))
  end=first
  while end<len(link) and link[end].endswith('.o'):end+=1
  link[first:end]=[str(p) for p in objects];link[link.index('-o')+1]=str(folder/'check')
  execute(link,mode+'-link');record=json.loads(execute([folder/'check'],mode+'-run'))
  if record.get('status')!='passed' or record.get('cases')!=11 or record.get('failures'):raise ValueError('Mapping controls failed')
  results[mode]=record
 # Full original headers and full actual caller TU, no function reconstruction.
 sys.path.insert(0,str(candidate.PARENT/'original'));import common
 cc=common.compiler(str(args.cc));original=common.original
 namespace=candidate.namespace_guard(args.namespace)
 bridge=original.original_bridge_flags(upstream,output/'kernel-profile',cc,namespace)
 bridge+=['-target','x86_64-apple-macos15','-mkernel','-DKERNEL','-D__KERNEL__','-Werror',
  '-Wframe-larger-than=4096','-Werror=frame-larger-than']
 obj=output/'mapping-backend-kernel.o'
 execute([cc,*bridge,profile,'-c',HERE/'S540NvidiaMappingClosure.c','-o',obj],'kernel-mapping')
 defined,undefined,_=original.macho_symbols(obj)
 expected={'nv_acquire_mmap_lock','nv_release_mmap_lock','nv_get_all_mappings_revoked_locked','nv_set_safe_to_mmap_locked','nv_revoke_gpu_mappings'}
 if defined!={original.PREFIX+n for n in expected}:raise ValueError('Unexpected mapping exports')
 approved={'s540Darwin_os_acquire_mutex','s540Darwin_os_alloc_mutex','s540Darwin_os_get_current_thread',
  's540Darwin_os_release_mutex','s540Darwin_os_semaphore_may_sleep','s540FirstTxnGetSnapshot',
  's540FirstTxnHostCaptureAllocation','s540FirstTxnObserveServiceRefusal'}
 # Apple Clang emits a public zeroing helper for the 192-byte stack snapshot.
 # Required callbacks remain exact, including when the helper is present.
 compiler_memory_imports=undefined&{'__bzero'}
 if undefined-compiler_memory_imports!=approved:raise ValueError('Unexpected mapping imports: '+str(undefined))
 import nvidia_metaclass_initializers as metaclass
 metaclass.verify_no_initializers(obj)
 compile_commands=original.original_commands(upstream,output/'original-commands',cc)
 matches=[c for c in compile_commands if (upstream/'src/nvidia'/c[c.index('-c')+1]).resolve()==upstream/SOURCE]
 if len(matches)!=1:raise ValueError('Expected unique complete original dynamic-power TU')
 command=matches[0][:matches[0].index('-c')]+['-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__','-DNV_VERSION_STRING="615.78.08"','-include',namespace,
  *(['-target','x86_64-macos-none'] if args.host_control else ['-arch','x86_64']),'-fPIC','-Werror',
  '-Wframe-larger-than=4096','-Werror=frame-larger-than','-c',upstream/SOURCE,'-o',output/'original-dynamic-power.o']
 # Original command's relative include directories are bound to its original cwd.
 process=subprocess.run([str(x) for x in command],cwd=upstream/'src/nvidia',text=True,capture_output=True,timeout=60)
 (output/'kernel-original-dynamic-power.log').write_text(process.stdout+process.stderr)
 if process.returncode:raise RuntimeError(process.stdout+process.stderr)
 commands.append({'name':'kernel-original-dynamic-power','command':[str(x) for x in command],'cwd':str(upstream/'src/nvidia'),'status':process.returncode})
 negatives=[]
 for index,flags in enumerate([[],['-DS540_NVIDIA_NO_USER_MAPPINGS=0'],['-DS540_NVIDIA_NO_USER_MAPPINGS=2'],[profile,'-DNV_UVM_ENABLE=0'],[profile,'-DNV_UVM_ENABLE=1'],[profile,'-DNV_PM_RUNTIME_AVAILABLE=0'],[profile,'-DNV_PM_RUNTIME_AVAILABLE=1']]):
  p=subprocess.run([str(x) for x in [cc,*bridge,*flags,'-c',HERE/'S540NvidiaMappingClosure.c','-o',output/f'refused-{index}.o']],text=True,capture_output=True)
  text=p.stdout+p.stderr;(output/f'negative-{index}.log').write_text(text)
  if p.returncode==0 or '#error' not in text:raise ValueError('Invalid source profile not explicitly refused')
  negatives.append({'flags':flags,'refused':True})
 for p,digest in deps.items():
  if sha(Path(p))!=digest:raise ValueError('Mapping dependency changed after compile')
 for p,digest in frozen.items():
  if sha(Path(p))!=digest:raise ValueError('Mapping control source changed during validation')
 if validate_profile()!=selected_profile:raise ValueError('Selected loader changed during controls')
 report={'format':1,'status':'passed-isolated-mapping-controls',**{k:baseline[k] for k in ['authoritative_darwin_execution','host_control','host_system','compilers']},
  'results':results,'selected_source_profile':selected_profile,'input_sha256':frozen,'actual_strong_record':True,'actual_original_callers':2,'real_darwin_mutex':True,
  'parent_gpu_controls':baseline['results'],'original_source':SOURCE,'original_source_sha256':sha(upstream/SOURCE),
  'candidate_source_sha256':sha(HERE/'S540NvidiaMappingClosure.c'),'actual_dependency_sha256':deps,
  'kernel_target_compile_actions':2,'kernel_definitions':sorted(defined),'kernel_imports':sorted(undefined),
  'kernel_compiler_memory_imports':sorted(compiler_memory_imports),
  'configuration_negatives':negatives,'commands':commands,'implicit_initializers':False,'production_modified':False,
  'original_entry_admission':False,'gpu_access':False,'kernel_execution':'not_tested','dma_stop_receipt':False,
  'user_mapping_ingress':False,'mapping_mutex_permanently_retained':True}
 (output/'mapping-controls.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['upstream','namespace','output','cc','cxx']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--v3-root',type=Path);p.add_argument('--host-overlay',type=Path);p.add_argument('--host-control',action='store_true')
 r=run(p.parse_args());print(json.dumps({'status':r['status'],'results':r['results'],'kernel_target_compile_actions':2,'gpu_access':False}))
