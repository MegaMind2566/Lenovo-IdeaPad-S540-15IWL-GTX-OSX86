#!/usr/bin/env python3
"""Compile the exact three-original-TU successor and real project backends."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import sys
import prepare as candidate

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args):
    candidate.parent_guard()
    sys.path.insert(0,str(candidate.PARENT/'original'))
    import common
    original=common.original
    cc,cxx=common.compiler(str(args.cc)),common.compiler(str(args.cxx))
    identity=common.execution_identity(cc,cxx,args.host_control)
    sdk_path=Path(args.sdk).resolve(strict=True)
    sdk=common.validate_sdk(sdk_path,args.sdk_archive,args.host_control)
    args.output=Path(args.output).resolve()
    if args.output.is_relative_to(sdk_path) or sdk_path.is_relative_to(args.output):
        raise ValueError('Output overlaps the SDK input')
    result=candidate.prepare(args.upstream,args.v3_root,args.output)
    output=args.output;project=result['project'];services=result['services']
    namespace=candidate.namespace_guard(args.namespace)
    upstream=Path(args.upstream).resolve(strict=True)
    frozen={str(path):sha(path) for path in candidate.HERE.glob('*')
        if path.is_file() and path.suffix in ('.py','.inc')}
    dependencies={}
    def compile(command,source,target,cwd):
        dep=target.with_suffix('.d')
        command += ['-MD','-MF',str(dep),'-c',str(source),'-o',str(target)]
        original.execute([str(x) for x in command],cwd=cwd,
            diagnostic_log=target.with_suffix('.log'))
        for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=Path(name)
            path=(cwd/path).resolve(strict=True) if not path.is_absolute() else path.resolve(strict=True)
            digest=sha(path)
            if dependencies.setdefault(str(path),digest)!=digest:
                raise ValueError('Compile dependency changed: '+str(path))
        defined,undefined,sections=original.macho_symbols(target)
        return {'source':str(source),'source_sha256':sha(source),'object':target.name,
            'object_sha256':sha(target),'status':0,'definitions':sorted(defined),
            'imports':sorted(undefined),'sections':sections,'cwd':str(cwd),
            'command':[str(x) for x in command]}
    objects=output/'objects';objects.mkdir(exist_ok=True)
    includes=['-I',project,'-I',candidate.PARENT/'record','-I',candidate.PARENT/'services',
        '-I',candidate.REPO/'packages/nvidia-global-rm/src',
        '-I',candidate.REPO/'packages/nvidia-global-rm-crypto/src',
        '-I',candidate.REPO/'packages/nvidia-device-transport/src',
        '-I',candidate.REPO/'packages/nvidia-darwin-services/src',
        '-I',candidate.REPO/'packages/nvidia-gsp-bootstrap/src',
        '-I',services,'-I',candidate.REPO/'packages/nvidia-gsp-bootstrap/timers']
    commands=original.original_commands(upstream,output/'original-commands',cc)
    source_root=result['base_source']/'src/nvidia'
    rows=[]
    for relative in [candidate.OSINIT,candidate.OSAPI,candidate.GPUMGR]:
        matches=[c for c in commands if
            (upstream/'src/nvidia'/c[c.index('-c')+1]).resolve()==upstream/relative]
        if len(matches)!=1:raise ValueError('No unique original compile command: '+relative)
        command=matches[0][:matches[0].index('-c')]+[
            '-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__','-DNV_VERSION_STRING="615.78.08"',
            '-include',namespace,*includes,'-I',candidate.REPO/'packages/nvidia-gsp-bootstrap/cancellation',
            *(['-target','x86_64-macos-none'] if args.host_control else ['-arch','x86_64']),
            '-fPIC','-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than']
        rows.append(compile(command,result['source']/relative,objects/(Path(relative).stem+'.o'),source_root))
    bridge=original.original_bridge_flags(upstream,output/'bridge-profile',cc,namespace)
    bridge += [*includes,'-target','x86_64-apple-macos15','-mkernel','-DKERNEL','-D__KERNEL__',
        '-Werror','-Wframe-larger-than=4096','-Werror=frame-larger-than']
    for name in ['S540NvidiaGspFirstTransactionOriginal.c','S540NvidiaGspContext.c']:
        rows.append(compile([cc,*bridge],project/name,objects/(Path(name).stem+'.o'),candidate.REPO))
    kernel=['-target','x86_64-apple-macos15','-mkernel','-DKERNEL','-D__KERNEL__',
        '-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin',
        '-fno-common','-fno-stack-protector','-fno-asynchronous-unwind-tables',
        '-fno-unwind-tables','-mno-red-zone','-msoft-float','-mno-mmx','-mno-sse',
        '-mno-sse2','-mno-3dnow','-nostdinc','-isystem',sdk_path/'Headers',
        '-I',candidate.REPO/'packages/nvidia-os-adapter/upstream/include',*includes,
        '-Wframe-larger-than=4096','-Werror=frame-larger-than']
    row=compile([cc,*kernel,'-std=c11'],project/'S540NvidiaGspFirstTransaction.c',
        objects/'strong-record.o',candidate.REPO)
    if any('gpumgrGetGpu' in symbol for symbol in row['imports']):
        raise ValueError('Strong record must not look up GPUs under service guards')
    rows.append(row)
    for name,source in [
        ('S540NvidiaDarwinWork.cpp',services/'S540NvidiaDarwinWork.cpp'),
        ('S540NvidiaDarwinTimer.cpp',services/'S540NvidiaDarwinTimer.cpp'),
        ('S540NvidiaFirstTxnServices.cpp',candidate.PARENT/'services/S540NvidiaFirstTxnServices.cpp')]:
        rows.append(compile([cxx,*kernel,'-std=c++17','-fapple-kext','-fno-exceptions','-fno-rtti',
            '-fno-threadsafe-statics','-fno-use-cxa-atexit','-mllvm',
            '-disable-atexit-based-global-dtor-lowering','-nostdinc++','-Wno-deprecated-declarations'],
            source,objects/(Path(name).stem+'.o'),candidate.REPO))
    for path,digest in frozen.items():
        if sha(Path(path))!=digest:raise ValueError('Candidate source changed during compile')
    for path,digest in dependencies.items():
        if sha(Path(path))!=digest:raise ValueError('Compile dependency changed during validation')
    candidate.parent_guard()
    report={'format':1,'status':'passed-kernel-target-compilation',**identity,
        'sdk':sdk,'results':rows,'original_translation_units':3,'kernel_target_compile_actions':len(rows),
        'actual_dependency_sha256':dependencies,'candidate_input_sha256':frozen,
        'source_manifest_sha256':sha(output/'source-manifest.json'),
        'production_modified':False,'original_entry_admission':False,'hardware_admission':False,
        'kernel_execution':'not_tested','gpu_access':False,'full_lock_capability_refused':True,
        'descriptor_rows_unchanged':True,'final_release_issuer':False}
    (output/'full-tu-compilation.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['upstream','namespace','output','cc','cxx','sdk']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--v3-root',type=Path)
    parser.add_argument('--sdk-archive',type=Path)
    parser.add_argument('--host-control',action='store_true')
    result=run(parser.parse_args())
    print(json.dumps({'status':result['status'],'compile_actions':len(result['results']),
        'original_translation_units':3,'hardware_admission':False}))

if __name__=='__main__':main()
