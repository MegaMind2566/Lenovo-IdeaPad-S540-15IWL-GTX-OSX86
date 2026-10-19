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
 's540GspCancellationPauseCurrent','s540GspCancellationSkipOptionalCurrent'}

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

def merge_v2(raw,changes,name,ordered):
 groups={}
 for row in changes:
  if row['start']==row['end']:groups.setdefault(row['start'],[]).append(row)
 for position,rows in groups.items():
  if len(rows)<2:continue
  expected={'wait-cancellation':['#include "S540NvidiaGspCancellationOriginal.h"\n'],
            'v2:optional-log-cancellation-prospective.patch':['#include "S540NvidiaGspCancellation.h"\n']}
  if name!='src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c' or {r['layer']:r['replacement'] for r in rows}!=expected:
   raise ValueError('Unreviewed shared raw insertion point')
  for row in rows:row['ordered_include']=0 if row['layer']=='wait-cancellation' else 1
  ordered.append({'source':name,'raw_line':position+1,
   'order':['wait-cancellation','v2:optional-log-cancellation-prospective.patch'],
   'reason':'Retain both exact independently pinned includes; no fuzzy context application'})
 lines=raw.decode().splitlines(True);out=[];position=0;records=[]
 for row in sorted(changes,key=lambda r:(r['start'],r['end'],r.get('ordered_include',0),r['layer'])):
  start,end=row['start'],row['end']
  if start<position:raise ValueError('Overlapping source changes')
  if records and start==records[-1]['raw_start_line']-1 and start==end and 'ordered_include' not in row:
   raise ValueError('Unreviewed duplicate insertion')
  out+=lines[position:start];new_start=len(out);out+=row['replacement'];position=end
  records.append({'layer':row['layer'],'raw_start_line':start+1,'raw_end_line_exclusive':end+1,
   'composed_start_line':new_start+1,'composed_end_line_exclusive':len(out)+1,
   'explicit_line_offset':new_start-start,'old_sha256':row['old_sha256'],
   'replacement_sha256':sha(''.join(row['replacement']).encode())})
 return ''.join(out+lines[position:]).encode(),records

def diff_patch(before,after):
 return ''.join(''.join(difflib.unified_diff(before[name].decode().splitlines(True),
   after[name].decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
   for name in sorted(after) if after[name]!=before[name]).encode()

def main():
 parser=argparse.ArgumentParser()
 for name in ('repo','upstream','checked-source','namespace','cc','output'):
  parser.add_argument('--'+name,type=Path,required=True)
 parser.add_argument('--extras-root',type=Path,default=Path(__file__).parent/'inputs')
 parser.add_argument('--cross-probe',action='store_true')
 parser.add_argument('--source-contract',type=Path,default=Path(__file__).parent.parent/'prospective/PROSPECTIVE-SOURCE-PROFILE.json')
 args=parser.parse_args()
 compositor_sha256=digest(Path(__file__).resolve())
 for key in ('repo','upstream','checked_source','namespace','cc','output','source_contract','extras_root'):
  setattr(args,key,getattr(args,key).absolute())
 native=sys.platform=='darwin' and platform.machine()=='x86_64'
 if not native and not args.cross_probe:
  raise ValueError('Authoritative compile requires Intel macOS; use --cross-probe explicitly elsewhere')
 v2_contract_path=Path(__file__).with_name('PROSPECTIVE-SOURCE-PROFILE.json')
 v2_contract_sha256=digest(v2_contract_path)
 v2_contract=json.loads(v2_contract_path.read_text())
 if v2_contract['helper_sha256']!=compositor_sha256:raise ValueError('The v2 helper changed')
 for name,expected in v2_contract['project_input_sha256'].items():
  if digest(args.repo/name)!=expected:raise ValueError('Frozen v2 project input changed: '+name)
 contract_sha256=digest(args.source_contract)
 contract=json.loads(args.source_contract.read_text())
 if contract['helper_sha256']!=digest(args.repo/'packages/nvidia-gsp-bootstrap/prospective/check_combined_profile.py'):
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
 # Separate scratch-only v2 inputs. None replaces the repository v1 files.
 memory=args.repo/'packages/nvidia-device-transport/prospective'
 monitored(memory/'generate_memory_unwind.py','8cf4cdb4f297d49da2578204776ef7c5ec4d2ef24be8b8393e8cf229945100d5')
 memory_module=module(memory/'generate_memory_unwind.py')
 memory_audit=json.loads((memory/'MEMORY-UNWIND-AUDIT.json').read_text())
 monitored(memory/'MEMORY-UNWIND-AUDIT.json')
 extra_specs=[
  (memory/'physical-import-publication-prospective.patch','74de77f90efbe6a3043de87f1accce4e007e54ca49fd84ab663edaa9c61ebb1c'),
  (memory/'indirect-peer-map-unwind-prospective.patch','271ef6ec6389a66b29ab2926a379cc5e5525ad99dd9664a5fcfa52296b3865d8'),
  (memory/'peer-bar-borrowed-owner-prospective.patch','69bf46ab391e8bf631d8ba4583317963e493bf1fd415b97124d2415720342764'),
  (args.extras_root/'cancellation-epoch-prospective/gsp-bootstrap-stop-epoch-prospective.patch','7a4d5a2e04551152894f066d6b53101f7993474a3becb175a1428d2fb6c2ff22'),
  (args.extras_root/'cancellation-log-prospective/optional-log-cancellation-prospective.patch','e17937ca2142da72e4622b7797c7d400c0846bf892cce1d71d3bfcef210d33f2'),
  (args.extras_root/'cancellation-timer-status-prospective/timer-cancel-status-prospective.patch','2a11f85f46a0271edf5b9d313f2225a829f2dec99a98c3f9e400025775437441'),
 ]
 extra_hashes=dict(memory_audit['source_sha256'])
 for name,expected in memory_module.PINNED.items():
  if extra_hashes.get(name)!=expected:raise ValueError('Memory source audit/generator differ')
 extra_manifest={}
 for directory in ('cancellation-epoch-prospective','cancellation-log-prospective','cancellation-timer-status-prospective'):
  path=args.extras_root/directory/'source-manifest.json';monitored(path)
  data=json.loads(path.read_text());extra_manifest[directory]=data
  values=data['original_sha256']
  if isinstance(values,str):values={data['source']:values}
  extra_hashes.update(values)
 hashes={}
 for inventory in (adapter_module.PINNED_HASHES,wait.SOURCES,status.SOURCES,locks.SOURCES,edges.SOURCES,extra_hashes):
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
 v1_layers=dict(layers)
 for path,expected in extra_specs:
  monitored(path,expected);changed=original._strict_patch(raw,path.read_bytes())
  layers['v2:'+path.name]=changed
  patch_records['v2:'+path.name]={'sha256':expected,'raw_source_sha256':{name:sha(raw[name]) for name in changed}}
 # Validate every manifest's standalone target against the strict patch output.
 for directory,data in extra_manifest.items():
  candidate=data['prospective_sha256']
  if isinstance(candidate,str):candidate={data['source']:candidate}
  patchname={'cancellation-epoch-prospective':'gsp-bootstrap-stop-epoch-prospective.patch',
    'cancellation-log-prospective':'optional-log-cancellation-prospective.patch',
    'cancellation-timer-status-prospective':'timer-cancel-status-prospective.patch'}[directory]
  if {name:sha(value) for name,value in layers['v2:'+patchname].items()}!=candidate:
   raise ValueError('Standalone patch target/manifest differs: '+directory)
 # Verify the independent memory generator reproduces its exact standalone patches.
 for path,adapt in ((memory_module.PHYSICAL,memory_module.adapt_physical),
                    (memory_module.VIRTUAL,memory_module.adapt_virtual),
                    (memory_module.PEER_BAR,memory_module.adapt_peer_bar)):
  matches=[value[path] for key,value in layers.items() if key.startswith('v2:') and path in value]
  if matches!=[adapt(raw[path].decode()).encode()]:raise ValueError('Memory generator/patch mismatch')
 # Preserve v1 project bytes and build a separate strong project overlay.
 port_patch=args.extras_root/'cancellation-log-prospective/optional-log-port-prospective.patch'
 monitored(port_patch,'1f373cacd791ce5d8d3eca6b937744e686c66397998b428bd8c9d0680a0d9c62')
 port_prefix='packages/nvidia-gsp-bootstrap/cancellation/'
 port_raw={port_prefix+name:(cancel/name).read_bytes() for name in ('S540NvidiaGspCancellation.c','S540NvidiaGspCancellation.h')}
 port_changed=original._strict_patch(port_raw,port_patch.read_bytes())
 expected_port={port_prefix+'S540NvidiaGspCancellation.c':'f5cf0c934342c71ec193a55ad7d972786dd87bf0d0c3fcacf0303a0eb7880a9f',
                port_prefix+'S540NvidiaGspCancellation.h':'a63bb08341cefc34fab533a645d136ebbea92069f90ae50cbddadadeca6db048'}
 if {name:sha(data) for name,data in port_changed.items()}!=expected_port:raise ValueError('Prospective strong port differs')
 project_overlay=args.output/'project-overlay'
 for name,expected in contract['project_input_sha256'].items():
  target=project_overlay/name;target.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(args.repo/name,target)
 for name,data in port_changed.items():(project_overlay/name).write_bytes(data)
 cancel_compile=project_overlay/port_prefix
 body_reports={}
 for label,relative,checks in [('epoch','cancellation-epoch-prospective/results.json',90),
  ('optional_logs','cancellation-log-prospective/results.json',37),
  ('timers','cancellation-timer-status-prospective/results.json',49)]:
  path=args.extras_root/relative;monitored(path);data=json.loads(path.read_text())
  directory=str(Path(relative).parent)
  if data['source']!=extra_manifest[directory]:raise ValueError('Body control source differs from its manifest')
  for mode in ('native','sanitized'):
   result=data['controls'][mode]
   if result['checks']!=checks or result['failures']!=0 or result['status']!='passed':raise ValueError('Body control failed')
  body_reports[label]={'sha256':digest(path),'checks_each_variant':checks,
   'candidate':data['controls'],'baseline':data['unmodified_original_controls'],
   'scope':'actual source bodies; explicit modeled hardware dependencies; not combined runtime execution'}
 path=args.extras_root/'memory-unwind-control-peer/memory-unwind-body-checks.json';monitored(path);data=json.loads(path.read_text())
 if data['generator_sha256']!='8cf4cdb4f297d49da2578204776ef7c5ec4d2ef24be8b8393e8cf229945100d5':raise ValueError('Memory body generator differs')
 if data['original_source_sha256']!=memory_audit['source_sha256']:raise ValueError('Memory body original hashes differ')
 if data['patch_sha256']!=memory_audit['patch_sha256']:raise ValueError('Memory body patch hashes differ')
 fixture=memory/'check_memory_unwind_bodies.c';monitored(fixture)
 if data['fixture_sha256']!=digest(fixture):raise ValueError('Memory body fixture bytes differ')
 for result in data['results']['candidate']['variants'].values():
  if result['checks']!=127 or result['failures'] or result['status']!='passed':raise ValueError('Memory body control failed')
 body_reports['memory']={'sha256':digest(path),'checks_each_variant':127,'results':data['results'],
  'scope':'complete actual original bodies with modeled dependencies; not combined runtime execution'}
 for path in cancel.glob('S540NvidiaGspCancellation*'):
  if path.suffix in ('.h','.c'):monitored(path)
 v1_edits={}
 for layer,changed in v1_layers.items():
  for name,new in changed.items():v1_edits.setdefault(name,[]).extend(edits(raw[name],new,layer))
 v1_final={name:merge(raw[name],values)[0] for name,values in v1_edits.items()}
 if {name:sha(data) for name,data in v1_final.items()}!=contract['final_sources_sha256']:
  raise ValueError('Frozen v1 source bytes no longer reconstruct')
 ordered_insertions=[]
 all_edits={}
 for layer,changed in layers.items():
  for name,new in changed.items():all_edits.setdefault(name,[]).extend(edits(raw[name],new,layer))
 final={};offsets={}
 for name,changes in all_edits.items():final[name],offsets[name]=merge_v2(raw[name],changes,name,ordered_insertions)
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
 if combined_tree_sha256!=v2_contract['combined_tree_sha256'] or {name:sha(data) for name,data in final.items()}!=v2_contract['final_sources_sha256']:
  raise ValueError('The v2 source composition changed')
 if sha(raw_combined)!=v2_contract['all_combined_patch_sha256'] or sha(additional)!=v2_contract['additional_patch_sha256']:
  raise ValueError('The exact v2 combined patch bytes changed')
 private_names={name:original.PREFIX+name for name in NEW_ORIGINAL_NAMES}
 ns=args.output/'prospective-private-namespace.h'
 if any(re.search(r'^#define\s+'+name+r'\s',args.namespace.read_text(),re.M) for name in private_names):
  raise ValueError('A new original alias already exists in baseline namespace')
 ns.write_text('/* Isolated prospective additive aliases; original namespace bytes unchanged. */\n'+
   '#include "'+str(args.namespace)+'"\n'+''.join('#define '+name+' '+value+'\n' for name,value in private_names.items()))
 changed_original=[name for name in sorted(final) if name.endswith('.c')]
 prospective_changed=[name for name in sorted(final) if final[name]!=checked_inputs[name]]
 report={'format':1,'profile':'isolated-prospective-combined-v2-not-approved','status':'composed',
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
  'monitored_project_inputs':inputs,'v1_source_contract_sha256':contract_sha256,
  'ordered_shared_insertions':ordered_insertions,'standalone_body_test_reports':body_reports,
  'project_overlay_sha256':expected_port,'project_port_patch_sha256':digest(port_patch),
  'translation_units':[],'production_candidate_allowed':False,
  'approved_profile':False,'native_apple_compiler':native and not args.cross_probe,'cross_compile_probe':args.cross_probe,
  'compiler':{'path':str(args.cc),'sha256':digest(args.cc),'version':compiler_version},
  'source_contract_sha256':contract_sha256,
  'kernel_execution':'not_tested','gpu_access':False,
  'limitations':['Changed translation units only; shared header changes do not establish all1100 compilation. V1 sources/contracts remain unchanged.',
   'Per-function frame limit is not a full call-chain stack bound.',
   'No link/target KXLD closure, PM acknowledgement, DMA quiescence or adapter outcome is established.']}
 write_json(args.output/'combined-profile-audit.json',report)
 commands=original.original_commands(args.upstream,args.output,args.cc)
 by_source={row[row.index('-c')+1]:row for row in commands}
 source_root=source/'src/nvidia';objects=args.output/'objects';objects.mkdir()
 def compile_one(name):
  relative=__import__('os').path.relpath(name,'src/nvidia')
  row=by_source[relative]
  command=[str(args.cc),*row[1:row.index('-c')],'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__',
   '-DNV_VERSION_STRING="'+original.RELEASE+'"','-include',str(ns),'-I',str(cancel_compile),
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
  project_source=cancel_compile/filename;obj=objects/(filename+'.o');dep=obj.with_suffix('.d')
  command=[str(args.cc),*bridge_common,'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__',
   '-DNV_VERSION_STRING="'+original.RELEASE+'"','-include',str(ns),'-I',str(cancel_compile),
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
 if digest(v2_contract_path)!=v2_contract_sha256:raise ValueError('The v2 contract changed during compilation')
 for name,expected in v2_contract['project_input_sha256'].items():
  if digest(args.repo/name)!=expected:raise ValueError('A v2 project input changed during compilation: '+name)
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
