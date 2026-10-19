#!/usr/bin/env python3
"""Run actual pinned bodies with real prospective services and the strong record.

Linux userspace is an explicit --host-control. Default execution requires macOS;
SDK object compilation alone never establishes kernel/hardware admission.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,subprocess,sys
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
prepare_module=load('s540_first_record_extract',HERE/'prepare_actual_original.py')
def run(config):
 def option(key,default=None):return config.get(key,default) if isinstance(config,dict) else getattr(config,key,default)
 upstream=Path(option('upstream')).resolve(strict=True);namespace=Path(option('namespace')).resolve(strict=True)
 output=Path(option('output')).resolve();cc=Path(option('cc')).absolute();cxx=Path(option('cxx')).absolute()
 if not cc.is_file() or not cxx.is_file():raise FileNotFoundError('Explicit compiler drivers are required')
 host_control=bool(option('host_control',False))
 if not host_control and sys.platform!='darwin':raise RuntimeError('Default authoritative native execution requires macOS; use --host-control for explicit Linux CPU controls')
 if output==HERE or HERE in output.parents:raise ValueError('Generated outputs must be outside the packaged record directory')
 if output==upstream or upstream in output.parents:raise ValueError('Generated outputs must not modify pinned upstream')
 output.mkdir(parents=True,exist_ok=True)
 service_overlay=Path(option('services_overlay')).resolve(strict=True);service_static=HERE.parent/'services'
 host_overlay=Path(option('host_overlay')).resolve(strict=True);host_packages=host_overlay/'packages' if (host_overlay/'packages').is_dir() else host_overlay
 host=host_packages/'nvidia-global-rm/src';real=REPO/'packages/nvidia-darwin-services/src'
 source=prepare_module.prepare(upstream,output)
 sys.path.insert(0,str(REPO/'builders'))
 import compile_nvidia_global_rm as original
 bridge=original.original_bridge_flags(upstream,output/'profile',cc,namespace)
 kernel_only={'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}
 bridge=[flag for flag in bridge if flag not in kernel_only]
 target=[] if host_control else ['-arch','x86_64','-mmacosx-version-min=15.0']
 if host_control:bridge += ['-U__linux__','-U__linux']
 includes=['-I',output,'-I',service_overlay,'-I',HERE,'-I',service_static,'-I',real,'-I',host,
  '-I',REPO/'packages/nvidia-gsp-bootstrap/timers','-I',REPO/'packages/nvidia-device-transport/src',
  '-I',REPO/'packages/nvidia-global-rm-crypto/src']
 cpp=[host/'S540NvidiaGlobalRmHost.cpp',service_overlay/'S540NvidiaDarwinWork.cpp',
  service_overlay/'S540NvidiaDarwinTimer.cpp',service_static/'S540NvidiaFirstTxnServices.cpp']
 cpp += [real/('S540NvidiaDarwin'+name+'.cpp') for name in ['Runtime','Sync','Process','UserCopy','Platform','Check']]
 units=[host_packages/'nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',host_packages/'nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c',HERE/'S540NvidiaGspFirstTransaction.c',HERE/'deps/S540NvidiaGspCancellation.c',HERE/'check_actual_original.c',service_overlay/'S540NvidiaGspTimersOriginal.c',*cpp]
 tracked=[*units,HERE/'S540NvidiaGspFirstTransaction.h',namespace,
  *[p for p in (HERE/'deps').rglob('*') if p.is_file() and p.suffix in ['.c','.h']],
  output/'actual-original-bodies.inc',output/'actual-original-metadata.inc',service_overlay/'S540NvidiaGspTimers.h']
 frozen={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
 environment=os.environ.copy()
 if host_control:environment['ASAN_OPTIONS']='detect_leaks=0'
 def execute(args,name):
  p=subprocess.run([str(arg) for arg in args],capture_output=True,text=True,
   env=environment,timeout=60)
  (output/(name+'.log')).write_text(p.stdout+p.stderr)
  if p.returncode:raise RuntimeError(name+'\n'+p.stdout+p.stderr)
  return p
 results={}
 for mode,san in [('plain',[]),('fatal-sanitizers',['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
  folder=output/mode;folder.mkdir(exist_ok=True);common=[*target,'-O1','-g','-Wall','-Wextra','-Werror','-pthread','-ffunction-sections','-fdata-sections',*san,*includes];objects=[]
  for index,p in enumerate(units):
   obj=folder/(str(index)+'-'+p.stem+'.o');objects.append(obj)
   actual=p.name in ['check_actual_original.c','S540NvidiaGspTimersOriginal.c','S540NvidiaUnsupportedMemory.c']
   command=[cc if p.suffix=='.c' else cxx,*common,*(['-std=gnu11'] if p.suffix=='.c' else ['-std=c++17'])]
   if actual:command += [*bridge,'-fPIC','-mcmodel=small','-Wno-unused-parameter','-Wno-missing-field-initializers']
   execute([*command,'-c',p,'-o',obj],mode+'-'+p.stem)
  binary=folder/'check';execute([cxx,*common,*objects,'-Wl,--gc-sections' if host_control else '-Wl,-dead_strip','-o',binary],mode+'-link')
  record=json.loads(execute([binary],mode+'-run').stdout)
  if record.get('status')!='passed' or record.get('checks')!=20 or record.get('failures')!=0:raise RuntimeError('Actual body control result mismatch')
  results[mode]=record
 sdk_results=[]
 if option('sdk'):
  sdk=Path(option('sdk')).resolve(strict=True);sdk=sdk/'Headers' if (sdk/'Headers').is_dir() else sdk
  for p in [HERE/'S540NvidiaGspFirstTransaction.c',HERE/'deps/S540NvidiaGspCancellation.c']:
   command=[cc,'-target','x86_64-apple-macos15','-mkernel','-DKERNEL','-D__KERNEL__','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector','-mno-red-zone','-nostdinc','-isystem',sdk,'-Wframe-larger-than=4096','-Werror=frame-larger-than','-c',p,'-o',output/(p.stem+'-sdk.o')]
   execute(command,p.stem+'-sdk');sdk_results.append({'source':str(p),'status':0,'command':[str(x) for x in command]})
 for p,digest in frozen.items():
  if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('Control input changed during execution: '+p)
 report={'format':1,'status':'passed','source':source,'results':results,'sdk':sdk_results,
  'input_sha256':frozen,'host_control':host_control,'native_apple_execution':not host_control,
  'production_modified':False,'kernel_execution':'not_tested','hardware_admission':False}
 (output/'results.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['upstream','namespace','output','cc','cxx','host-overlay','services-overlay']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--host-control',action='store_true');p.add_argument('--sdk',type=Path)
 a=p.parse_args();report=run(vars(a));print(json.dumps({'status':report['status'],'results':report['results'],'sdk_compile_units':len(report['sdk']),'hardware_admission':False}))
