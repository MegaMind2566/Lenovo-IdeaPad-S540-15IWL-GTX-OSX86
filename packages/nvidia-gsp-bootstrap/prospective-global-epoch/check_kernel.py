#!/usr/bin/env python3
"""Cross-compile complete successor TUs using the composed Darwin SDK plan."""
from pathlib import Path
import argparse
import json
import shlex
import shutil
import subprocess
import sys
import prepare as candidate

def run(composed,output):
    sys.path.insert(0,str(candidate.ROOT/'builders'))
    import compose_nvidia_first_transaction as composer
    composed=composed.resolve(strict=True)
    manifest=composer.verify_composition(composed)
    compiled=json.loads((composed/'project-compilation.json').read_text())
    output=composer.new_output(output,[composed,candidate.HERE]);output.mkdir(parents=True)
    project=output/'project';shutil.copytree(composed/'project',project)
    before={name:(project/name).read_text() for name in candidate.INPUTS}
    for name,text in candidate.transforms(before).items():(project/name).write_text(text)
    snapshot=composer.inventory(project)
    rows=[];dependencies={}
    for row in compiled['results']:
        if row['source'] not in (candidate.RECORD,candidate.LIFECYCLE):continue
        obj=output/(Path(row['source']).stem+'.o');dep=obj.with_suffix('.d')
        argv=[str(v).replace(str(composed/'project'),str(project)) for v in row['command']]
        argv[argv.index('-c')+1]=str(project/row['source'])
        argv[argv.index('-o')+1]=str(obj)
        argv[argv.index('-MF')+1]=str(dep)
        result=subprocess.run(argv,text=True,capture_output=True,timeout=120)
        (output/(obj.stem+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('Complete kernel successor compile failed: '+result.stderr)
        if obj.read_bytes()[:4]!=b'\xcf\xfa\xed\xfe':raise ValueError('Expected complete Mach-O x86_64 object')
        for name in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=Path(name).resolve(strict=True);digest=candidate.sha(path)
            if dependencies.setdefault(str(path),digest)!=digest:raise ValueError('Dependency changed: '+str(path))
        rows.append({'source':row['source'],'source_sha256':candidate.sha(project/row['source']),
            'object_sha256':candidate.sha(obj),'command':argv,'format':'Mach-O x86_64'})
    if len(rows)!=2:raise ValueError('Missing actual successor kernel translation unit')
    if snapshot!=composer.inventory(project):raise ValueError('Kernel companion changed during compilation')
    for path,digest in dependencies.items():
        if candidate.sha(Path(path))!=digest:raise ValueError('Compile dependency changed: '+path)
    composer.verify_composition(composed)
    report={'format':1,'status':'passed-complete-kernel-successor-cross-compilation',
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
    p.add_argument('--composition',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps({'status':run(a.composition,a.output)['status']}))
