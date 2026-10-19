#!/usr/bin/env python3
"""Isolated exact-source composition and changed-TU Mach-O cross probe.

No approved source profile, compiler default, or repository file is modified.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import difflib
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

EXPECTED_PATCHES = {
 'gsp-teardown-status-prospective.patch':'c0934a4d822cf62d58e27ae72e124e7bf9c0e541a7c1a6dfdff9be7aefb13818',
 'rm-lock-cancellation-prospective.patch':'393230985616ff2b93d9bd28895566f66c1055074dc66863e525ffae2e1d96ed',
 'falcon-reset-status-prospective.patch':'e85e9aa9f0002c586ce47753f98babc245f06d6bf747df8718916a6df2fe98a0',
 'caps-minor-guard-prospective.patch':'2c56c9400ed2d12fc99154a78b9bcb6545cf3710c8834c54aa426b2726cd6628',
}
WAIT_GENERATOR_SHA='f8e0099f904b5e1a756e628985ef991c9a09475214f52a38c921ccc5df6de471'
WAIT_PATCH_SHA='70805a4c1b8a15415fcbedf33e296a50a0e04577fe41f9c2cf17dd5e1be6e7c2'
ADAPTER_SHA='8431461295f67b24f8a11c2c1602ac5d515181b7d993a4e201b8554f9b6dab61'
ADAPTER_PATCH_SHA='fa2e6c19194467026e9edb025af40c9e15ab393690b228829d01de104a84fc2d'
NEW_ORIGINAL_NAMES=(
 'RmShutdownAdapterChecked','RmDisableAdapterChecked','s540RmAdapterHasResources',
 's540RmDisableAdapterChecked','s540RmShutdownAdapterChecked')
PROJECT_BRIDGES={
 's540GspCancellationCheckGpu','s540GspCancellationBeginCleanupState',
 's540GspCancellationCurrentScopeActive','s540GspCancellationCheckCurrent',
 's540GspCancellationPauseCurrent'}

def sha(data):return hashlib.sha256(data).hexdigest()
def digest(path):return sha(path.read_bytes())
def write_json(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
def module(path):
 spec=importlib.util.spec_from_file_location(path.stem,path);assert spec and spec.loader
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def edits(raw,new,layer):
 before=raw.decode().splitlines(True);after=new.decode().splitlines(True)
 return [{'layer':layer,'start':a,'end':b,'replacement':after[c:d],
          'old_sha256':sha(''.join(before[a:b]).encode())}
         for tag,a,b,c,d in difflib.SequenceMatcher(None,before,after,autojunk=False).get_opcodes()
         if tag!='equal']

def merge(raw,changes):
 lines=raw.decode().splitlines(True);out=[];position=0;records=[]
 for change in sorted(changes,key=lambda row:(row['start'],row['end'],row['layer'])):
  start,end=change['start'],change['end']
  if start<position:raise ValueError('Overlapping raw-source edits: '+str(change))
  if records and start==records[-1]['raw_start_line']-1 and start==end:
   raise ValueError('Ambiguous shared raw insertion point')
  out+=lines[position:start]
  new_start=len(out)
  out+=change['replacement'];position=end
  records.append({'layer':change['layer'],'raw_start_line':start+1,'raw_end_line_exclusive':end+1,
                  'composed_start_line':new_start+1,'composed_end_line_exclusive':len(out)+1,
                  'explicit_line_offset':new_start-start,'old_sha256':change['old_sha256'],
                  'replacement_sha256':sha(''.join(change['replacement']).encode())})
 return ''.join(out+lines[position:]).encode(),records

def diff_patch(before,after):
 return ''.join(''.join(difflib.unified_diff(before[name].decode().splitlines(True),
   after[name].decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
   for name in sorted(after) if after[name]!=before[name]).encode()

def main():
 parser=argparse.ArgumentParser()
 for name in ('repo','upstream','checked-source','namespace','cc','output'):
  parser.add_argument('--'+name,type=Path,required=True)
 parser.add_argument('--cross-probe',action='store_true')
 parser.add_argument('--source-contract',type=Path,default=Path(__file__).with_name('PROSPECTIVE-SOURCE-PROFILE.json'))
 args=parser.parse_args()
 compositor_sha256=digest(Path(__file__).resolve())
 for key in ('repo','upstream','checked_source','namespace','cc','output','source_contract'):
  setattr(args,key,getattr(args,key).absolute())
 native=sys.platform=='darwin' and platform.machine()=='x86_64'
 if not native and not args.cross_probe:
  raise ValueError('Authoritative compile requires Intel macOS; use --cross-probe explicitly elsewhere')
 contract_sha256=digest(args.source_contract)
 contract=json.loads(args.source_contract.read_text())
 if contract['helper_sha256']!=compositor_sha256:
  raise ValueError('The prospective helper differs from the source contract')
 for name,expected in contract['project_input_sha256'].items():
  path=Path(name)
  if path.is_absolute() or '..' in path.parts or digest(args.repo/path)!=expected:
   raise ValueError('Frozen project input changed: '+name)
 compiler_version=subprocess.run([str(args.cc),'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
 target_flags=(['-target','x86_64-macos-none','-fPIC'] if args.cross_probe else
               ['-mkernel','-arch','x86_64','-mmacosx-version-min=15.0'])
 if args.output.exists():raise ValueError('A fresh isolated output is required')
 args.output.mkdir(parents=True)
 sys.path.insert(0,str(args.repo/'builders'))
 import compile_nvidia_global_rm as original
 baseline=original.validate_checked_source(args.upstream,args.checked_source)
 if len(baseline['patches'])!=10 or baseline['tree_sha256']!=contract['verified_ten_tree_sha256']:
  raise ValueError('The frozen verified ten-patch baseline changed')
 namespace_contract=json.loads((args.repo/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
 if digest(args.namespace)!=namespace_contract['namespace_sha256']:
  raise ValueError('The baseline private namespace bytes changed')
 cancel=args.repo/'packages/nvidia-gsp-bootstrap/cancellation'
 adapter=args.repo/'packages/nvidia-gsp-bootstrap/adapter'
 sys.path.insert(0,str(cancel))
 inputs={}
 def monitored(path,expected=None):
  value=digest(path)
  if expected and value!=expected:raise ValueError('Frozen input digest mismatch: '+str(path))
  inputs[str(path)]=value
  return value
 monitored(adapter/'generate_checked_unwind.py',ADAPTER_SHA)
 adapter_module=module(adapter/'generate_checked_unwind.py')
 monitored(adapter/'adapter-status-unwind-prospective.patch',ADAPTER_PATCH_SHA)
 monitored(adapter/'ADAPTER-STATUS-AUDIT.json')
 monitored(cancel/'prepare_wait_candidates.py',WAIT_GENERATOR_SHA)
 wait=module(cancel/'prepare_wait_candidates.py')
 status=module(cancel/'check_gsp_teardown_status.py');monitored(cancel/'check_gsp_teardown_status.py')
 locks=module(cancel/'check_rm_lock_cancellation.py');monitored(cancel/'check_rm_lock_cancellation.py')
 edges=module(cancel/'check_original_status_edges.py');monitored(cancel/'check_original_status_edges.py')
 hashes={}
 for inventory in (adapter_module.PINNED_HASHES,wait.SOURCES,status.SOURCES,locks.SOURCES,edges.SOURCES):
  for name,expected in inventory.items():
   if name in hashes and hashes[name]!=expected:raise ValueError('Conflicting original source digest')
   hashes[name]=expected
 raw={name:(args.upstream/name).read_bytes() for name in set(hashes)|set(baseline['changed_files'])}
 for name,expected in hashes.items():
  if sha(raw[name])!=expected:raise ValueError('Raw original digest mismatch: '+name)
 layers={}
 layers['verified-ten-profile']={name:(args.checked_source/name).read_bytes()
                                 for name in baseline['changed_files']}
 adapter_inputs={name:raw[name].decode() for name in adapter_module.PINNED_HASHES}
 adapter_changed={name:text.encode() for name,text in adapter_module.adapt(adapter_inputs).items()}
 adapter_patch=(adapter/'adapter-status-unwind-prospective.patch').read_bytes()
 if original._strict_patch(raw,adapter_patch)!=adapter_changed:
  raise ValueError('Adapter generator and frozen standalone patch differ')
 layers['adapter-status-ownership']=adapter_changed
 wait_dir=args.output/'standalone-waits'
 wait_record=wait.prepare(args.upstream,wait_dir)
 wait_patch=(wait_dir/'wait-cancellation-prospective.patch').read_bytes()
 if sha(wait_patch)!=WAIT_PATCH_SHA:raise ValueError('Frozen generated wait patch digest mismatch')
 wait_changed=original._strict_patch(raw,wait_patch)
 if {name:sha(data) for name,data in wait_changed.items()}!=wait_record['prospective_sha256']:
  raise ValueError('Wait standalone reconstruction differs')
 layers['wait-cancellation']=wait_changed
 patch_records={
  'adapter-status-ownership':{'sha256':sha(adapter_patch),'raw_source_sha256':adapter_module.PINNED_HASHES},
  'wait-cancellation':{'sha256':sha(wait_patch),'raw_source_sha256':wait.SOURCES},
 }
 for filename,expected in EXPECTED_PATCHES.items():
  path=cancel/filename;monitored(path,expected)
  changed=original._strict_patch(raw,path.read_bytes())
  layers[filename]=changed
  patch_records[filename]={'sha256':expected,'raw_source_sha256':{name:sha(raw[name]) for name in changed}}
 for path in cancel.glob('S540NvidiaGspCancellation*'):
  if path.suffix in ('.h','.c'):monitored(path)
 all_edits={}
 for layer,changed in layers.items():
  for name,new in changed.items():all_edits.setdefault(name,[]).extend(edits(raw[name],new,layer))
 final={};offsets={}
 for name,changes in all_edits.items():final[name],offsets[name]=merge(raw[name],changes)
 raw_combined=diff_patch(raw,final)
 if original._strict_patch(raw,raw_combined)!=final:
  raise ValueError('The reconstructed raw combined patch does not reproduce every final byte')
 checked_inputs={name:(args.checked_source/name).read_bytes() for name in final}
 additional=diff_patch(checked_inputs,final)
 additional_changed=original._strict_patch(checked_inputs,additional)
 if {**checked_inputs,**additional_changed}!=final:
  raise ValueError('The reconstructed additional patch does not reproduce the final profile')
 (args.output/'all-prospective-overlays-from-raw.patch').write_bytes(raw_combined)
 (args.output/'prospective-additions-to-verified-ten.patch').write_bytes(additional)
 source=args.output/'source';shutil.copytree(args.checked_source,source)
 for name,data in final.items():(source/name).write_bytes(data)
 files=dict(baseline['files'])
 for name,data in final.items():files[name]={**files[name],'sha256':sha(data)}
 observed={p.relative_to(source).as_posix():{'sha256':digest(p),'mode':'100755' if p.stat().st_mode&0o111 else '100644'}
           for p in source.rglob('*') if p.is_file()}
 if observed!=files:raise ValueError('Isolated source tree differs from exact4005-file composition')
 combined_tree_sha256=sha(json.dumps(files,sort_keys=True,separators=(',',':')).encode())
 if combined_tree_sha256!=contract['combined_tree_sha256'] or {name:sha(data) for name,data in final.items()}!=contract['final_sources_sha256']:
  raise ValueError('The final prospective profile differs from its frozen source contract')
 if sha(raw_combined)!=contract['all_combined_patch_sha256'] or sha(additional)!=contract['additional_patch_sha256']:
  raise ValueError('The exact reconstructed combined patch bytes changed')
 private_names={name:original.PREFIX+name for name in NEW_ORIGINAL_NAMES}
 ns=args.output/'prospective-private-namespace.h'
 if any(re.search(r'^#define\s+'+name+r'\s',args.namespace.read_text(),re.M) for name in private_names):
  raise ValueError('A new original alias already exists in baseline namespace')
 ns.write_text('/* Isolated prospective additive aliases; original namespace bytes unchanged. */\n'+
   '#include "'+str(args.namespace)+'"\n'+''.join('#define '+name+' '+value+'\n' for name,value in private_names.items()))
 changed_original=[name for name in sorted(final) if name.endswith('.c')]
 prospective_changed=[name for name in sorted(final) if final[name]!=checked_inputs[name]]
 report={'format':1,'profile':'isolated-prospective-combined-not-approved','status':'composed',
  'upstream_commit':original.COMMIT,'composition_script_sha256':compositor_sha256,'verified_ten_tree_sha256':baseline['tree_sha256'],
  'baseline_patch_count':len(baseline['patches']),'baseline_patch_hashes':baseline['patches'],
  'standalone_patches':patch_records,'raw_original_sha256':{name:sha(data) for name,data in sorted(raw.items())},
  'final_sources_sha256':{name:sha(data) for name,data in sorted(final.items())},
  'verified_ten_additional_source_paths':prospective_changed,'raw_to_composed_edit_offsets':offsets,
  'all_combined_patch_sha256':sha(raw_combined),'additional_patch_sha256':sha(additional),
  'combined_tree_file_count':len(files),'combined_tree_sha256':combined_tree_sha256,
  'baseline_namespace_sha256':digest(args.namespace),'additive_namespace_sha256':digest(ns),
  'new_original_private_names':private_names,'unique_project_bridge_dependencies':sorted(PROJECT_BRIDGES),
  'all_changed_original_c_units':changed_original,'changed_headers':[n for n in sorted(final) if n.endswith('.h')],
  'monitored_project_inputs':inputs,'translation_units':[],'production_candidate_allowed':False,
  'approved_profile':False,'native_apple_compiler':native and not args.cross_probe,'cross_compile_probe':args.cross_probe,
  'compiler':{'path':str(args.cc),'sha256':digest(args.cc),'version':compiler_version},
  'source_contract_sha256':contract_sha256,
  'kernel_execution':'not_tested','gpu_access':False,
  'limitations':['Changed translation units only; shared header changes do not establish all1100 compilation.',
   'Per-function frame limit is not a full call-chain stack bound.',
   'No link/target KXLD closure, PM acknowledgement, DMA quiescence or adapter outcome is established.']}
 write_json(args.output/'combined-profile-audit.json',report)
 commands=original.original_commands(args.upstream,args.output,args.cc)
 by_source={row[row.index('-c')+1]:row for row in commands}
 source_root=source/'src/nvidia';objects=args.output/'objects';objects.mkdir()
 def compile_one(name):
  relative=Path(name).relative_to('src/nvidia').as_posix()
  row=by_source[relative]
  command=[str(args.cc),*row[1:row.index('-c')],'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__',
   '-DNV_VERSION_STRING="'+original.RELEASE+'"','-include',str(ns),'-I',str(cancel),
   *target_flags,'-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than']
  obj=objects/(relative.replace('/','__')+'.o');dep=obj.with_suffix('.d')
  command+=['-MMD','-MF',str(dep),'-c',str(source/name),'-o',str(obj)]
  result=subprocess.run(command,cwd=source_root,text=True,capture_output=True,timeout=300)
  obj.with_suffix('.log').write_text(result.stdout+result.stderr)
  if result.returncode:raise ValueError(name+' failed:\n'+result.stderr[-6500:])
  defined,undefined,sections=original.macho_symbols(obj)
  unnamespaced=defined-{n for n in defined if n.startswith(original.PREFIX)}
  if unnamespaced:raise ValueError('Unnamespaced original definitions: '+repr(sorted(unnamespaced)))
  project_imports={n for n in undefined if n.startswith('s540') and not n.startswith(original.PREFIX)}
  if project_imports-PROJECT_BRIDGES:raise ValueError('Unreviewed unique project imports: '+repr(project_imports-PROJECT_BRIDGES))
  dependencies=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
  header_hashes={}
  for dependency in dependencies:
   path=Path(dependency);path=path if path.is_absolute() else source_root/path
   path=path.resolve(strict=True)
   if path.is_relative_to(args.upstream):raise ValueError('Compiler used a raw header outside the composed profile')
   header_hashes[str(path)]=digest(path)
  return {'source':name,'source_sha256':sha(final[name]),'object':obj.name,'object_sha256':digest(obj),
   'definitions':sorted(defined),'imports':sorted(undefined),'sections':sections,
   'new_original_definitions':sorted(set(private_names.values())&defined),
   'unique_project_bridge_imports':sorted(project_imports),'dependency_sha256':header_hashes,'command':command}
 failures=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  jobs={pool.submit(compile_one,name):name for name in changed_original}
  for job in concurrent.futures.as_completed(jobs):
   name=jobs[job]
   try:report['translation_units'].append(job.result());print('PASS '+name,flush=True)
   except Exception as exc:failures.append({'source':name,'error':str(exc)});print('FAIL '+name,flush=True)
   write_json(args.output/'combined-profile-audit.json',report)
 report['translation_units'].sort(key=lambda row:row['source'])
 report['project_bridge_translation_units']=[]
 bridge_common=commands[0][1:commands[0].index('-c')]
 for filename in ('S540NvidiaGspCancellation.c','S540NvidiaGspCancellationOriginal.c'):
  project_source=cancel/filename;obj=objects/(filename+'.o');dep=obj.with_suffix('.d')
  command=[str(args.cc),*bridge_common,'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__',
   '-DNV_VERSION_STRING="'+original.RELEASE+'"','-include',str(ns),'-I',str(cancel),
   *target_flags,'-Werror','-Wframe-larger-than=4096',
   '-Werror=frame-larger-than','-MMD','-MF',str(dep),'-c',str(project_source),'-o',str(obj)]
  result=subprocess.run(command,cwd=source_root,text=True,capture_output=True,timeout=300)
  obj.with_suffix('.log').write_text(result.stdout+result.stderr)
  if result.returncode:
   failures.append({'source':str(project_source),'error':result.stderr[-6500:]});continue
  defined,undefined,sections=original.macho_symbols(obj)
  if any(not name.startswith('s540GspCancellation') for name in defined):
   raise ValueError('Unexpected project bridge definition')
  dependencies=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
  dependency_hashes={}
  for dependency in dependencies:
   path=Path(dependency);path=path if path.is_absolute() else source_root/path
   path=path.resolve(strict=True);dependency_hashes[str(path)]=digest(path)
  report['project_bridge_translation_units'].append({
   'source':str(project_source),'source_sha256':digest(project_source),'object':obj.name,
   'object_sha256':digest(obj),'definitions':sorted(defined),'imports':sorted(undefined),
   'sections':sections,'dependency_sha256':dependency_hashes,'command':command,
   'role':'unique strong project bridge, not an original-source private alias'})
 if not failures:
  project_defined=set().union(*(set(row['definitions']) for row in report['project_bridge_translation_units']))
  if not PROJECT_BRIDGES<=project_defined:raise ValueError('Required strong project bridges missing')
  report['required_unique_project_bridges_defined']=sorted(PROJECT_BRIDGES)
 if not failures:
  original_defined=set().union(*(set(row['definitions']) for row in report['translation_units']))
  if not set(private_names.values())<=original_defined:raise ValueError('New private original definitions missing')
 original._verify_workspace(source,{'files':files})
 report['compile_failures']=failures
 report['status']='failed' if failures else 'changed-original-units-compiled'
 for path,expected in inputs.items():
  if digest(Path(path))!=expected:raise ValueError('A frozen project input changed during compilation: '+path)
 if digest(args.namespace)!=report['baseline_namespace_sha256']:
  raise ValueError('The baseline private namespace changed during compilation')
 for row in report['translation_units']+report['project_bridge_translation_units']:
  for path,expected in row['dependency_sha256'].items():
   if digest(Path(path))!=expected:raise ValueError('An actual compiler dependency changed: '+path)
 if digest(args.source_contract)!=contract_sha256:
  raise ValueError('The prospective source contract changed during compilation')
 for name,expected in contract['project_input_sha256'].items():
  if digest(args.repo/name)!=expected:raise ValueError('A frozen project input changed during compilation: '+name)
 if digest(Path(__file__).resolve())!=compositor_sha256:
  raise ValueError('The composition helper changed during validation')
 write_json(args.output/'combined-profile-audit.json',report)
 print(json.dumps({'status':report['status'],'changed_original_c_units':len(changed_original),
   'compiled':len(report['translation_units']),'failures':failures,'audit':str(args.output/'combined-profile-audit.json')},indent=2))
 if failures:raise SystemExit(1)

if __name__=='__main__':main()
