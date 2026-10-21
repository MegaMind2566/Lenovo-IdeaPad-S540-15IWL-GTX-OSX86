#!/usr/bin/env python3
"""Compile uninstrumented retained construction under the actual KERNEL ABI.

The composed project compilation supplies its authenticated Darwin SDK plan;
the two changed original units use the pinned make profile. No body executes.
"""
from pathlib import Path
import argparse
import json
import shlex
import shutil
import subprocess
import sys
import prepare as candidate

def run(args):
    sys.path.insert(0,str(candidate.ROOT/'builders'))
    import compose_nvidia_first_transaction as composer
    import compile_nvidia_global_rm as original
    composed=args.composition.resolve(strict=True)
    manifest=composer.verify_composition(composed)
    for name in ('retained_diagnostic','retained_backends','global_epoch'):
        if manifest.get('fixed_source_profiles',{}).get(name) is not True:
            raise ValueError('Exact retained construction prerequisite missing: '+name)
    upstream=original._pinned_upstream(args.upstream)
    compiled=json.loads((composed/'project-compilation.json').read_text())
    if compiled.get('status')!='compiled-project-source-only':
        raise ValueError('A completed composed Darwin project compile plan is required')
    output=composer.new_output(args.output,[composed,candidate.HERE,upstream]);output.mkdir(parents=True)
    for scope,names,transform in [('project',candidate.INPUTS,candidate.transforms),
                                  ('source',candidate.ORIGINAL_INPUTS,candidate.original_transforms)]:
        shutil.copytree(composed/scope,output/scope)
        values={name:(output/scope/name).read_text() for name in names}
        for name,text in transform(values).items():(output/scope/name).write_text(text)
    snapshots={scope:composer.inventory(output/scope) for scope in ('project','source')}
    rows=[];dependencies={}
    def compile_one(scope,relative,argv,cwd):
        path=output/scope/relative;obj=output/(path.stem+'.o');dep=obj.with_suffix('.d')
        result=subprocess.run(argv,text=True,capture_output=True,timeout=120,cwd=cwd)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('Actual KERNEL successor compile failed: '+result.stderr)
        if obj.read_bytes()[:4]!=b'\xcf\xfa\xed\xfe':raise ValueError('Expected complete x86_64 Mach-O object')
        defined,imports,_=original.macho_symbols(obj)
        if any(name.startswith(('s540RetainedControl','s540GlobalEpochControl')) for name in imports|defined):
            raise ValueError('Observation fixture leaked into the actual KERNEL compile')
        if relative==candidate.RECORD and not set(candidate.EXPORTS)<=defined:
            raise ValueError('Strong record omitted an exact construction export')
        required_imports={candidate.SYSTEM:{candidate.EXPORTS[0]},
                          candidate.GENERATED:{candidate.EXPORTS[1]}}.get(relative,set())
        if not required_imports<=imports:
            raise ValueError('Original construction guards are missing from complete KERNEL object')
        for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            dependency=Path(name)
            if not dependency.is_absolute():dependency=cwd/dependency
            dependency=dependency.resolve(strict=True);digest=candidate.sha(dependency)
            if dependencies.setdefault(str(dependency),digest)!=digest:
                raise ValueError('Dependency changed: '+str(dependency))
        rows.append({'scope':scope,'source':relative,'source_sha256':candidate.sha(path),
            'object_sha256':candidate.sha(obj),'command':[str(v) for v in argv],
            'definitions':sorted(defined),'imports':sorted(imports),'format':'Mach-O x86_64',
            'kernel_definitions_required':['KERNEL','__KERNEL__']})
    selected={candidate.RECORD,'packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c'}
    for row in compiled['results']:
        if row['source'] not in selected:continue
        path=output/'project'/row['source'];obj=output/(path.stem+'.o');dep=obj.with_suffix('.d')
        argv=[str(v).replace(str(composed/'project'),str(output/'project')).replace(
            str(composed/'source'),str(output/'source')) for v in row['command']]
        argv[argv.index('-c')+1]=str(path);argv[argv.index('-o')+1]=str(obj)
        argv[argv.index('-MF')+1]=str(dep)
        if not all('-D'+name in argv or any(v.startswith('-D'+name+'=') for v in argv)
            for name in ('KERNEL','__KERNEL__')):
            raise ValueError('Project plan does not compile the actual KERNEL branch')
        compile_one('project',row['source'],argv,output/'project')
    source_root=output/'source/src/nvidia'
    entries=original.original_commands(upstream,output/'make-plan',args.cc)
    found=set()
    for row in entries:
        relative=row[row.index('-c')+1]
        if Path(relative).is_absolute():continue
        relative=(source_root/relative).resolve().relative_to(output/'source').as_posix()
        if relative not in candidate.ORIGINAL_INPUTS:continue
        if relative in found:raise ValueError('Duplicate original source in actual make profile')
        found.add(relative)
        path=output/'source'/relative;obj=output/(path.stem+'.o');dep=obj.with_suffix('.d')
        argv=list(row);argv[argv.index('-c')+1]=str(path);argv[argv.index('-o')+1]=str(obj)
        argv+=['-target','x86_64-macos-none','-fPIC','-mkernel','-DKERNEL','-D__KERNEL__',
            '-DNV_UNIX=1','-D__NV_UNIX_VERSION_H__','-DNV_VERSION_STRING="615.78.08"',
            '-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1','-include',str(composed/manifest['namespace']),
            *composer.original_source_flags(manifest,relative),
            *[v.replace(str(composed/'project'),str(output/'project')) for v in composer.include_flags(composed)],
            '-Wframe-larger-than=4096','-Werror=frame-larger-than','-fstack-usage','-MD','-MF',str(dep)]
        compile_one('source',relative,argv,source_root)
    if len(rows)!=4 or found!=set(candidate.ORIGINAL_INPUTS):
        raise ValueError('Missing complete original/project KERNEL translation unit')
    for scope,snapshot in snapshots.items():
        if snapshot!=composer.inventory(output/scope):raise ValueError('Kernel companion changed: '+scope)
    for path,digest in dependencies.items():
        if candidate.sha(Path(path))!=digest:raise ValueError('Compile dependency changed: '+path)
    composer.verify_composition(composed)
    report={'format':1,'status':'passed-uninstrumented-retained-construction-kernel-cross-compilation',
        'composition_sha256':candidate.sha(composed/'composition.json'),
        'project_compilation_sha256':candidate.sha(composed/'project-compilation.json'),
        'complete_translation_units':rows,'actual_dependency_sha256':dependencies,
        'kernel_execution':False,'gpu_access':False,'native_apple_validation':False,
        'global_kernel_gate_preserved':True,'original_entry_admission':False,
        'production_candidate_allowed':False}
    (output/'results.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('composition','output','upstream','cc'):p.add_argument('--'+name,type=Path,required=True)
    print(json.dumps({'status':run(p.parse_args())['status']}))
