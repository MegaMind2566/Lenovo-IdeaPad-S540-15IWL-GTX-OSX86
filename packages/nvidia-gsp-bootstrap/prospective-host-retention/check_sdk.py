#!/usr/bin/env python3
"""Full SDK compile of the actual isolated Host retention source."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess,sys,importlib.util
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser()
    for name in ('repo','record','sdk','overlay','upstream','namespace','cc','cxx','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--sdk-archive',type=Path);p.add_argument('--host-control',action='store_true')
    a=p.parse_args()
    for name in ('repo','record','sdk','overlay','upstream','namespace'):setattr(a,name,getattr(a,name).resolve(strict=True))
    a.output=a.output.resolve();a.cc=a.cc.absolute();a.cxx=a.cxx.absolute()
    spec=importlib.util.spec_from_file_location('host_retention_sdk_guard',a.repo/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original/common.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    for source_root in (a.record,a.sdk,a.overlay,a.upstream):
        if a.output.is_relative_to(source_root) or source_root.is_relative_to(a.output):
            raise ValueError('SDK output must be separate from all source inputs')
    if a.output.exists():raise ValueError('Fresh SDK output required')
    a.output=guard.output_path(a.output,a.upstream)
    identity=guard.execution_identity(a.cc,a.cxx,a.host_control)
    identity['compiler_sha256']={'cc':sha(a.cc),'cxx':sha(a.cxx)}
    if a.sdk_archive is not None and not a.host_control:raise ValueError('Native SDK validation requires the clean pinned Git checkout')
    sdk_identity=guard.validate_sdk(a.sdk,a.sdk_archive,a.host_control)
    sdk_identity.pop('used_by_original_c_tus',None)
    sdk_identity['used_by_host_kernel_cpp']=True
    python_inputs={str(path):sha(path) for path in (Path(__file__).resolve(),
        a.repo/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/original/common.py',
        a.repo/'builders/compile_nvidia_global_rm.py',a.repo/'builders/check_nvidia_execution.py')}
    source=a.overlay/'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp';obj=a.output/'Host.o';dep=a.output/'Host.d'
    source_hash=sha(source)
    command=[str(a.cxx),'-target','x86_64-apple-macos15','-mkernel','-fno-builtin','-ffreestanding','-fno-common',
        '-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables','-mno-red-zone','-DKERNEL','-D__KERNEL__',
        '-O2','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations','-nostdinc','-isystem',str(a.sdk/'Headers'),
        '-I',str(a.repo/'packages/nvidia-os-adapter/upstream/include'),'-I',str(a.record),
        '-I',str(a.repo/'packages/nvidia-global-rm-crypto/src'),'-I',str(a.repo/'packages/nvidia-device-transport/src'),
        '-fapple-kext','-fno-exceptions','-fno-rtti',
        '-fno-threadsafe-statics','-fno-use-cxa-atexit','-mllvm','-disable-atexit-based-global-dtor-lowering','-nostdinc++',
        '-std=c++17','-Wframe-larger-than=4096','-Werror=frame-larger-than','-MD','-MF',str(dep),'-c',str(source),'-o',str(obj)]
    completed=subprocess.run(command,capture_output=True,text=True)
    (a.output/'Host.log').write_text(completed.stdout+completed.stderr);completed.check_returncode()
    sys.path.insert(0,str(a.repo/'builders'));import compile_nvidia_global_rm as original
    definitions,imports,sections=original.macho_symbols(obj)
    required={'s540GlobalRmHostRetentionPreflight','s540GlobalRmHostRetentionSnapshot','s540GlobalRmHostRetentionInspect'}
    if not required<=definitions:raise ValueError('Real Host retention exports missing')
    required_imports={'s540FirstTxnHostCaptureAllocation','s540FirstTxnHostAcquireFree','s540FirstTxnHostCompleteFree','s540FirstTxnObserveServiceRefusal'}
    if not required_imports<=imports:raise ValueError('Strong exact record dependencies missing')
    if any('HostRetentionNative' in n for n in definitions|imports):raise ValueError('Native scheduling observer leaked into kernel object')
    dependencies={}
    for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
        path=Path(name).resolve(strict=True);dependencies[str(path)]=sha(path)
    if sha(source)!=source_hash:raise ValueError('Host source changed during SDK compile')
    report={'format':1,'status':'passed','profile':'isolated-host-heap-retention','native_apple_compiler':not a.host_control,
        'cross_compile_probe':a.host_control,'execution_identity':identity,'sdk_identity':sdk_identity,
        'python_input_sha256':python_inputs,
        'kernel_execution':'not_tested','production_modified':False,'original_entry_admission':False,
        'source_sha256':source_hash,'object_sha256':sha(obj),'command':command,'definitions':sorted(definitions),
        'imports':sorted(imports),'sections':sections,'actual_dependency_sha256':dependencies,
        'sdk_reference_commit':'3f750085caa17ec3a7880f11c11bf4f48cd6a164',
        'compiler':{'sha256':sha(a.cxx),'version':subprocess.run([str(a.cxx),'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]}}
    report['producer_and_record_units']=[]
    cflags=['-target','x86_64-macos-none','-mkernel','-DKERNEL','-D__KERNEL__','-O2','-Werror',
            '-Wframe-larger-than=4096','-Werror=frame-larger-than','-nostdinc','-isystem',str(a.sdk/'Headers'),
            '-I',str(a.record),'-I',str(a.repo/'packages/nvidia-os-adapter/upstream/include'),
            '-I',str(a.repo/'packages/nvidia-global-rm-crypto/src'),'-I',str(a.repo/'packages/nvidia-device-transport/src')]
    bridge=original.original_bridge_flags(a.upstream,a.output,a.cc,a.namespace)
    for label,path,flags in [('crypto',a.overlay/'packages/nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',[]),
        ('memory',a.overlay/'packages/nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c',bridge),
        ('record',a.record/'S540NvidiaGspFirstTransaction.c',[])]:
        out=a.output/(label+'.o');dependency=out.with_suffix('.d');source_sha=sha(path)
        command_c=[str(a.cc),*flags,*cflags,'-std=gnu11','-MD','-MF',str(dependency),'-c',str(path),'-o',str(out)]
        done=subprocess.run(command_c,capture_output=True,text=True)
        (a.output/(label+'.log')).write_text(done.stdout+done.stderr);done.check_returncode()
        defined,external,segments=original.macho_symbols(out)
        expected=required_imports if label=='record' else {'s540FirstTxnObserveServiceRefusal'}
        if not expected <= (defined if label=='record' else external):raise ValueError('Real refusal source dependency missing')
        files={}
        for name in shlex.split(dependency.read_text().replace('\\\n',' ').split(':',1)[1]):
            dependency_path=Path(name).resolve(strict=True);files[str(dependency_path)]=sha(dependency_path)
        if sha(path)!=source_sha:raise ValueError('Producer source changed during SDK compile')
        report['producer_and_record_units'].append({'label':label,'source_sha256':source_sha,'object_sha256':sha(out),
            'definitions':sorted(defined),'imports':sorted(external),'sections':segments,'command':command_c,'actual_dependency_sha256':files})
    all_dependencies=dict(dependencies)
    for unit in report['producer_and_record_units']:
        for path,expected in unit['actual_dependency_sha256'].items():
            if all_dependencies.setdefault(path,expected)!=expected:raise ValueError('SDK dependency changed between units')
    for path,expected in all_dependencies.items():
        if sha(Path(path))!=expected:raise ValueError('SDK dependency changed during compilation')
    for path,expected in python_inputs.items():
        if sha(Path(path))!=expected:raise ValueError('SDK compiler helper changed during execution')
    (a.output/'sdk-compile.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':'passed','dependencies':len(dependencies),'source_sha256':source_hash}))
if __name__=='__main__':main()
