#!/usr/bin/env python3
"""Real service source overlays, native fault controls and pinned SDK compile.

Record hooks are explicit dependency controls here. Strong-record integration
has its own report and must not be inferred from these boundary controls.
"""
from pathlib import Path
import hashlib, json, os, subprocess, sys, argparse, platform, importlib.util
from prepare_services import HERE, REPO, SERVICE, prepare as prepare_work
import prepare_timers
import prepare_context
sys.path.insert(0, str(REPO/'builders'))
import compile_nvidia_global_rm as original

def arguments():
    parser=argparse.ArgumentParser()
    for name in ['upstream','namespace','output','cc','cxx']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--sdk',type=Path)
    parser.add_argument('--sdk-archive',type=Path)
    parser.add_argument('--host-control',action='store_true')
    return vars(parser.parse_args())

def run(command, name):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True)
    (OUT/(name+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode: raise RuntimeError(str(command)+'\n'+result.stdout+result.stderr)
    return result

def check(config):
    global OUT
    if not config.get('host_control') and (sys.platform!='darwin' or platform.machine()!='x86_64'):
        raise ValueError('Authoritative native checks require Intel macOS; --host-control is explicitly limited')
    WORK=Path(config['output']).resolve();WORK.mkdir(parents=True,exist_ok=True)
    OUT=WORK/'controls';OUT.mkdir(exist_ok=True)
    CC=Path(config['cc']).absolute();CXX=Path(config['cxx']).absolute();UP=Path(config['upstream']).resolve()
    SDK=Path(config['sdk']).resolve() if config.get('sdk') else None
    sdk_guard = None
    if SDK is not None:
        spec=importlib.util.spec_from_file_location('first_transaction_sdk_guard',HERE.parent/'original/common.py')
        guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        sdk_guard=guard.validate_sdk(SDK,config.get('sdk_archive'),config.get('host_control',False))
    prepare_work(WORK/'overlay');prepare_timers.prepare(WORK/'overlay');prepare_context.prepare(WORK/'overlay')
    include = ['-I', WORK, '-I', WORK/'overlay', '-I', HERE, '-I', HERE.parent/'record', '-I', SERVICE]
    bridge = original.original_bridge_flags(UP, OUT/'profile', CC,
        Path(config['namespace']).resolve())
    kernel_bridge = list(bridge)
    bridge = [v for v in bridge if v not in {'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}]+['-fPIC']
    bridge += ['-I',WORK/'overlay',
        '-I',REPO/'packages/nvidia-gsp-bootstrap/timers',*include]
    kernel_bridge += ['-I',WORK/'overlay','-I',REPO/'packages/nvidia-gsp-bootstrap/timers',*include]
    if config.get('host_control'):bridge += ['-U__linux__','-U__linux']
    report = {'format':1,'production_modified':False,'hardware_admission':False,
        'strong_record_integration':'separate-report-required','native':{},'sdk':[],'sdk_guard':sdk_guard,'execution':'host-control' if config.get('host_control') else 'native-intel-macos'}
    for mode in ['plain','fatal-sanitized']:
        san = ['-fsanitize=address,undefined,function','-fno-sanitize-recover=all',
            '-fno-omit-frame-pointer'] if mode != 'plain' else []
        common = ([] if config.get('host_control') else ['-arch','x86_64','-mmacosx-version-min=15.0'])+['-O1','-g','-Wall','-Wextra','-Werror',*san]
        queue = OUT/('queue-'+mode)
        run([CXX,'-std=c++17',*common,'-pthread',*include,HERE/'check_queue_hooks.cpp',
            SERVICE/'S540NvidiaDarwinPlatform.cpp',SERVICE/'S540NvidiaDarwinSync.cpp',
            '-o',queue], 'queue-'+mode+'-compile')
        q = json.loads(run([queue],'queue-'+mode).stdout)
        objects = []
        for name, source in [('port',WORK/'overlay/S540NvidiaGspTimersOriginal.c'),
                ('timer-control',HERE/'check_timer_hooks.c')]:
            obj = OUT/(name+'-'+mode+'.o');objects.append(obj)
            run([CC,*bridge,*common,'-mcmodel=small','-Wno-unused-parameter','-c',source,'-o',obj],name+'-'+mode+'-compile')
        timer = OUT/('timer-'+mode)
        run([CXX,'-std=c++17',*common,'-pthread',*(['-no-pie'] if sys.platform!='darwin' else []),*include,
            WORK/'overlay/S540NvidiaDarwinTimer.cpp',SERVICE/'S540NvidiaDarwinPlatform.cpp',
            WORK/'overlay/S540NvidiaDarwinWork.cpp',HERE/'S540NvidiaFirstTxnServices.cpp',
            SERVICE/'S540NvidiaDarwinSync.cpp',*objects,'-o',timer], 'timer-'+mode+'-link')
        t = json.loads(run([timer],'timer-'+mode).stdout)
        report['native'][mode]={'queue':q,'timer':t}
    if SDK is not None:
        kernel = ['-target','x86_64-apple-macos15','-mkernel','-fno-builtin','-ffreestanding',
            '-fno-common','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables',
            '-mno-red-zone','-DKERNEL','-D__KERNEL__','-O2','-Wall','-Wextra','-Werror',
            '-Wno-deprecated-declarations','-nostdinc','-isystem',SDK/'Headers',
            '-I',REPO/'packages/nvidia-os-adapter/upstream/include','-fapple-kext',
            '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-fno-use-cxa-atexit',
            '-mllvm','-disable-atexit-based-global-dtor-lowering','-nostdinc++','-std=c++17',
            '-Wframe-larger-than=4096','-Werror=frame-larger-than',*include]
        for name in ['S540NvidiaDarwinWork.cpp','S540NvidiaDarwinTimer.cpp','S540NvidiaFirstTxnServices.cpp']:
            path = HERE/name if name == 'S540NvidiaFirstTxnServices.cpp' else WORK/'overlay'/name
            command = [CXX,*kernel,'-c',path,'-o',OUT/('sdk-'+name+'.o')]
            run(command,'sdk-'+name)
            report['sdk'].append({'source':name,'command':[str(x) for x in command],'status':0})
        command=[CC,*kernel_bridge,'-target','x86_64-macos-none','-mkernel','-DKERNEL','-D__KERNEL__',
            '-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than',
            '-c',WORK/'overlay/S540NvidiaGspTimersOriginal.c','-o',OUT/'sdk-timer-port.o']
        run(command,'sdk-timer-port')
        report['sdk'].append({'source':'S540NvidiaGspTimersOriginal.c',
            'command':[str(x) for x in command],'status':0})
        command=[CC,*kernel_bridge,'-target','x86_64-macos-none','-mkernel','-DKERNEL','-D__KERNEL__',
            '-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than',
            '-I',REPO/'packages/nvidia-gsp-bootstrap/src',
            '-c',WORK/'overlay/S540NvidiaGspContext.c','-o',OUT/'sdk-first-txn-context.o']
        run(command,'sdk-first-txn-context')
        report['sdk'].append({'source':'S540NvidiaGspContext.c',
            'command':[str(x) for x in command],'status':0})
    report['source_sha256']={str(p.relative_to(WORK)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in WORK.glob('overlay/*') if p.suffix in ['.c','.cpp','.patch']}
    (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'native':report['native'],'sdk_compile_jobs':len(report['sdk']),
        'production_modified':False,'hardware_admission':False},indent=2))

    return report

if __name__=='__main__':check(arguments())
