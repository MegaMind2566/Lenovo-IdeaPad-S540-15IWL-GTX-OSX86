#!/usr/bin/env python3
"""Execute selected backend/mode/IRQ bodies; all OS and record endpoints are fixtures."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,tempfile
HERE=Path(__file__).resolve().parent;PACKAGE=HERE.parent;PROJECT=PACKAGE.parents[2]
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def extract(text,signature):
    if text.count(signature)!=1:raise ValueError('Changed unique actual function: '+signature)
    start=text.index(signature);return text[start:text.index('\n}\n',start)+3]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    prepare=load('irq_install_prepare',PACKAGE/'prepare.py');parent=a.parent.resolve(strict=True)
    old={key:(parent/'project'/key).read_text() for key in prepare.INPUTS};selected=prepare.transforms(old)
    compiler=shutil.which('clang++') or shutil.which('g++')
    device=selected[prepare.BACKEND];reports=[]
    with tempfile.TemporaryDirectory(prefix='s540-irq-install-backend-') as temp:
        work=Path(temp);copy=work/'project';shutil.copytree(parent/'project',copy)
        for key,value in selected.items():(copy/key).write_text(value)
        for key,source in prepare.COMPANIONS.items():
            target=copy/key;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        start=device.index('struct Platform {');end=device.index('\n};',start)+3
        (work/'actual-platform.inc').write_text('struct RegisterView { void *address; NvU64 bytes; };\n'+device[start:end])
        start=device.index('static Platform *retainedIrqBackends;');end=device.index('\nstruct Allocation {',start)
        (work/'actual-backend-lifetime.inc').write_text(device[start:end])
        (work/'actual-irq-bodies.inc').write_text('\n'.join(extract(device,s) for s in (
            'NV_STATUS readOriginalMode(','void bottomHalf(','void interrupt(','NV_STATUS installInterrupt(','NV_STATUS stopInterrupt(')))
        (work/'actual-arm.inc').write_text(extract(device,'NV_STATUS armInterrupt('))
        (work/'actual-irq-query.inc').write_text(extract(device,'extern "C" NV_STATUS s540FirstTxnIrqReadContext('))
        (work/'actual-mode-query.inc').write_text(extract(device,'extern "C" NV_STATUS s540GspIrqReadBackendMode('))
        mock=PROJECT/'packages/nvidia-gsp-bootstrap/prospective-public-callback-closure/tests/mock'
        includes=[work,copy/'packages',copy/'packages/nvidia-device-transport/src',
            copy/'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
            copy/'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure',
            copy/'packages/nvidia-gsp-bootstrap/prospective-irq-installation',
            copy/'packages/nvidia-darwin-services/src',mock]
        for sanitize in (False,True):
            binary=work/('sanitized' if sanitize else 'plain')
            command=[compiler,'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-pthread',
                *['-I'+str(path) for path in includes],str(HERE/'check_backend.cpp'),'-o',str(binary)]
            if sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
            env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1';env['UBSAN_OPTIONS']='halt_on_error=1'
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30,env=env)
            if result.returncode or result.stderr:raise RuntimeError('Backend failed '+str(result.returncode)+'\n'+result.stdout+result.stderr)
            reports.append({'sanitized':sanitize,'result':json.loads(result.stdout),'command':command})
    report={'format':1,'status':'pass','reports':reports,'selected_backend_sha256':hashlib.sha256(device.encode()).hexdigest(),
        'test_sha256':sha(HERE/'check_backend.cpp'),'real_iokit_execution':False,'real_record_authority':False,
        'hardware_interrupt_delivery':False,'original_gpu_init':False,'full_hardware_cleanup_proven':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'pass','reports':[r['result'] for r in reports],'output':str(a.output)}))
if __name__=='__main__':main()
