#!/usr/bin/env python3
"""Strong record + real services/Host; typed original metadata are TEST controls."""
from pathlib import Path
import hashlib, json, subprocess, sys, platform, argparse
from prepare_services import HERE, REPO, SERVICE, prepare as prepare_work
import prepare_timers
sys.path.insert(0,str(REPO/'builders'))
import compile_nvidia_global_rm as original
def arguments():
    parser=argparse.ArgumentParser()
    for name in ['upstream','namespace','output','cc','cxx','host-overlay','services-overlay']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--host-control',action='store_true')
    return vars(parser.parse_args())
def run(command,name,timeout=45):
    result=subprocess.run([str(x) for x in command],text=True,capture_output=True,timeout=timeout)
    (OUT/(name+'.log')).write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(name+'\n'+result.stdout+result.stderr)
    return result
def check(config):
    global OUT
    if not config.get('host_control') and (sys.platform!='darwin' or platform.machine()!='x86_64'):
        raise ValueError('Authoritative native checks require Intel macOS; --host-control is explicitly limited')
    OUT=Path(config['output']).resolve();OUT.mkdir(parents=True,exist_ok=True)
    CC=Path(config['cc']).absolute();CXX=Path(config['cxx']).absolute();UP=Path(config['upstream']).resolve()
    RECORD=HERE.parent/'record';HOST=Path(config['host_overlay']).resolve()
    if (HOST/'packages').is_dir():HOST=HOST/'packages'
    OVERLAY=Path(config['services_overlay']).resolve()
    bridge=original.original_bridge_flags(UP,OUT/'profile',CC,Path(config['namespace']).resolve())
    bridge=[v for v in bridge if v not in {'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}]+['-fPIC']
    if config.get('host_control'):bridge += ['-U__linux__','-U__linux']
    include=['-I',HERE,'-I',RECORD,'-I',SERVICE,
        '-I',OVERLAY,
        '-I',REPO/'packages/nvidia-gsp-bootstrap/timers',
        '-I',HOST/'nvidia-global-rm/src','-I',HOST/'nvidia-global-rm-crypto/src',
        '-I',REPO/'packages/nvidia-global-rm-crypto/src',
        '-I',REPO/'packages/nvidia-device-transport/src']
    report={'format':1,'production_modified':False,'hardware_admission':False,'variants':{}}
    sources=[('record',RECORD/'S540NvidiaGspFirstTransaction.c',False),
        ('participants',RECORD/'deps/S540NvidiaGspCancellation.c',False),
        ('typed-port',OVERLAY/'S540NvidiaGspTimersOriginal.c',True),
        ('crypto',HOST/'nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',False),
        ('memory',HOST/'nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c',True),
        ('joint',HERE/'check_strong_joint.c',True)]
    for mode in ['plain','fatal-sanitized']:
        common=([] if config.get('host_control') else ['-arch','x86_64','-mmacosx-version-min=15.0'])+['-O1','-g','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections']
        if mode!='plain':common+=['-fsanitize=address,undefined,function','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        objects=[]
        for name,path,typed in sources:
            output=OUT/(name+'-'+mode+'.o');objects.append(output)
            flags=bridge if typed else ['-std=c11']
            run([CC,*flags,*common,'-mcmodel=small','-Wno-unused-parameter',*include,
                '-c',path,'-o',output],name+'-'+mode)
        executable=OUT/mode
        cxxsources=[HOST/'nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp',
            HERE/'S540NvidiaFirstTxnServices.cpp',OVERLAY/'S540NvidiaDarwinWork.cpp',
            OVERLAY/'S540NvidiaDarwinTimer.cpp',SERVICE/'S540NvidiaDarwinPlatform.cpp',
            SERVICE/'S540NvidiaDarwinSync.cpp']
        run([CXX,'-std=c++17',*common,'-pthread',*(['-Wl,-dead_strip'] if sys.platform=='darwin' else ['-no-pie','-Wl,--gc-sections']),*include,
            *cxxsources,*objects,'-o',executable],'link-'+mode)
        result=json.loads(run([executable],'run-'+mode).stdout)
        if result['failures']:raise RuntimeError('Joint controls failed')
        report['variants'][mode]=result
    report['source_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
        for _,path,_ in sources}
    report['source_sha256'].update({str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in cxxsources})
    (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['variants'],indent=2))
    return report

if __name__=='__main__':check(arguments())
