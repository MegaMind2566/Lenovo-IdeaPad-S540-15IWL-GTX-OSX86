#!/usr/bin/env python3
"""Compile six actual frontend/reference units against the pinned kernel SDK.

This is a Linux Mach-O source/ABI control, not native linking or target loading.
It binds every real compiler dependency and keeps the same15.0 SDK availability
profile as the subsequent actual Apple compile.
"""
import argparse,hashlib,json,shlex,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'builders'))
import compose_nvidia_first_transaction as composer
import link_nvidia_first_transaction as linker
FRONT=HERE.relative_to(ROOT).as_posix()+'/'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('composition','kernel-sdk','cc','cxx','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    composed=args.composition.resolve(strict=True);sdk=args.kernel_sdk.resolve(strict=True)
    output=args.output.absolute()
    if output.exists():raise ValueError('Fresh actual SDK control output required')
    value=composer.verify_composition(composed)
    units=[(FRONT+'S540ExperimentalTargetState.c','c'),(FRONT+'S540ExperimentalTargetKernel.cpp','cpp'),
        ('packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKmod.cpp','cpp'),
        (FRONT+'tests/sdk_experimental_metaclass_reference.cpp','cpp'),
        (FRONT+'tests/sdk_experimental_operations_reference.cpp','cpp'),
        (FRONT+'tests/sdk_experimental_protocol_reference.c','c')]
    flags,cpp=linker.kernel_flags(sdk)
    index=flags.index('-arch');del flags[index:index+2]
    flags.remove('-mmacosx-version-min=15.0')
    flags=['-target','x86_64-apple-macos15.0',*flags]
    include=[*composer.include_flags(composed),*[part for relative in value['retained_trial']['include_directories']
        for part in ('-I',str(composed/'project'/relative))]]
    common=composer.load('s540_frontend_sdk_common',composer.FIRST/'original/common.py')
    sdk_record=common.validate_sdk(sdk,None,True)
    cc,cxx=args.cc.resolve(strict=True),args.cxx.resolve(strict=True)
    identities=common.execution_identity(cc,cxx,True)
    output.mkdir(parents=True)
    rows=[]
    for index,(relative,kind) in enumerate(units):
        source=composed/'project'/relative
        if relative.startswith(FRONT) and source.read_bytes()!=(ROOT/relative).read_bytes():
            raise ValueError('Current authored frontend bytes differ from this materialized source candidate:'+relative)
        obj=output/('sdk-%02d.o'%index);dependency=obj.with_suffix('.d')
        command=[str(cxx if kind=='cpp' else cc),*flags,*(['-fcheck-new',*cpp] if kind=='cpp' else ['-std=c11']),
            *include,'-MD','-MF',str(dependency),'-c',str(source),'-o',str(obj)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=180)
        (output/('sdk-%02d.log'%index)).write_text(result.stdout+result.stderr)
        if result.returncode:raise ValueError('Actual current SDK unit failed:'+relative+'\n'+result.stderr)
        reviewed=relative.endswith(('TargetKernel.cpp','metaclass_reference.cpp'))
        definitions,imports,sections=composer.original.macho_symbols(obj,reviewed_project_initializers=reviewed)
        dependencies={str(Path(name).resolve(strict=True)):composer.sha(Path(name).resolve(strict=True))
            for name in shlex.split(dependency.read_text().replace('\\\n',' ').split(':',1)[1])}
        if str(source.resolve()) not in dependencies:raise ValueError('Actual SDK compiler dependency list omitted source')
        rows.append(dict(source=relative,source_sha256=composer.sha(source),object=obj.name,
            object_sha256=composer.sha(obj),command=command,dependency_sha256=dependencies,
            imports=sorted(imports),definitions=sorted(definitions)))
    for row in rows:
        if composer.sha(composed/'project'/row['source'])!=row['source_sha256'] or any(
            composer.sha(Path(name))!=digest for name,digest in row['dependency_sha256'].items()):
            raise ValueError('Actual SDK source/dependency changed during control')
    if common.validate_sdk(sdk,None,True)!=sdk_record:raise ValueError('Pinned SDK changed during actual compilation')
    report=dict(format=1,status='actual-experimental-frontend-sdk-cross-compiled',translation_units=len(rows),results=rows,
        sdk=sdk_record,compiler_identity=identities,compiler_sha256={str(path):composer.sha(path) for path in (cc,cxx)},
        candidate_composition_sha256=composer.sha(composed/'composition.json'),
        helper_sha256=composer.sha(Path(__file__)),complete_current_source_replay_verified=False,
        native_darwin_compilation=False,host_control=True,kernel_execution='not_tested',gpu_access=False)
    (output/'results.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],translation_units=len(rows),report_sha256=composer.sha(output/'results.json'))))
if __name__=='__main__':main()
