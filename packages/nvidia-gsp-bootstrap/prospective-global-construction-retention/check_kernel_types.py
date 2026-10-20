#!/usr/bin/env python3
"""Compile the three complete successor C TUs with original kernel types.

This is an explicit non-Apple Mach-O cross probe. It does not link or execute.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import prepare as candidate
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'builders'))
import compile_nvidia_global_rm as original
import compose_nvidia_first_transaction as composition

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(args):
    upstream=original._pinned_upstream(args.upstream)
    composed=args.composition.resolve(strict=True);manifest=composition.verify_composition(composed)
    if not all(manifest.get('fixed_source_profiles',{}).get(k) for k in ('retained_diagnostic','retained_backends','global_epoch')):
        raise ValueError('Exact retained predecessor composition required')
    output=composition.new_output(args.output,[upstream,composed,HERE]);output.mkdir(parents=True)
    source=output/'source';project=output/'project'
    shutil.copytree(composed/'source',source);shutil.copytree(composed/'project',project)
    for names,base,transform in ((candidate.PROJECT_INPUTS,project,candidate.project_transforms),
            (candidate.ORIGINAL_INPUTS,source,candidate.original_transforms)):
        for name,text in transform({n:(base/n).read_text() for n in names}).items():(base/name).write_text(text)
    for name in candidate.ORIGINAL_INPUTS:
        values={n:(composed/'source'/n).read_text() for n in candidate.ORIGINAL_INPUTS}
        values[name]+='\n'
        try:candidate.original_transforms(values)
        except ValueError:pass
        else:raise ValueError('Changed original input was accepted: '+name)
    namespace=composed/manifest['namespace'];cc=args.cc.resolve(strict=True)
    commands=original.original_commands(upstream,output/'make-plan',cc)
    by_source={row[row.index('-c')+1]:row for row in commands}
    includes=composition.include_flags(output)
    defines=['-D'+k+'='+v for k,v in sorted(manifest['fixed_source_profiles']['required_compile_definitions'].items())]
    target=['-target','x86_64-macos-none','-fPIC']
    rows=[]
    for index,name in enumerate((*candidate.ORIGINAL_INPUTS,candidate.RECORD)):
        is_original=name in candidate.ORIGINAL_INPUTS
        compiled=source/name if is_original else project/name
        cwd=source/'src/nvidia' if is_original else project
        if is_original:
            relative=Path(name).relative_to('src/nvidia').as_posix();entry=by_source[relative]
            flags=[*entry[1:entry.index('-c')],'-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__',
                '-DNV_VERSION_STRING="615.78.08"','-include',str(namespace),*target,*defines,*includes]
        else:
            flags=[*target,'-ffreestanding','-fno-builtin','-fno-common','-mno-red-zone',
                '-DKERNEL=1','-D__KERNEL__=1','-std=c11','-Wall','-Wextra','-Werror',*defines,*includes]
        obj=output/('kernel-types-%u.o'%index);dep=obj.with_suffix('.d')
        argv=[str(cc),*flags,'-MD','-MF',str(dep),'-c',str(compiled),'-o',str(obj)]
        result=subprocess.run(argv,cwd=cwd,text=True,capture_output=True,timeout=180)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('Complete C TU cross probe failed: '+name+'\n'+result.stderr[-5000:])
        dependencies={}
        for value in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=Path(value);path=path.resolve(strict=True) if path.is_absolute() else (cwd/path).resolve(strict=True)
            dependencies[str(path)]=sha(path)
        defined,imports,_=original.macho_symbols(obj)
        rows.append({'source':name,'source_sha256':sha(compiled),'command':argv,'cwd':str(cwd),
            'object':obj.name,'object_sha256':sha(obj),'dependency_sha256':dependencies,
            'definitions':sorted(defined),'imports':sorted(imports)})
    composition.verify_composition(composed)
    for row in rows:
        for name,digest in row['dependency_sha256'].items():
            if sha(Path(name))!=digest:raise ValueError('Actual cross compile dependency changed: '+name)
    report={'format':1,'status':'passed-complete-constructor-c-type-cross-probe',
        'compiler':str(cc),'compiler_sha256':sha(cc),'composition_sha256':sha(composed/'composition.json'),
        'translation_units':rows,'changed_original_input_negative_controls':len(candidate.ORIGINAL_INPUTS),
        'native_apple_compiler':False,'cross_compile_probe':True,'code_executed':False,
        'original_entry_admission':False,'production_candidate_allowed':False}
    (output/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:report[k] for k in ('status','code_executed','original_entry_admission')}))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('upstream','composition','output','cc'):parser.add_argument('--'+name,type=Path,required=True)
    run(parser.parse_args())
