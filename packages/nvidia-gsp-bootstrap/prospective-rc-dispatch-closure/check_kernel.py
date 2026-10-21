#!/usr/bin/env python3
"""Fresh complete changed-original-TU kernel crosscompile; no link or runtime."""
from pathlib import Path
import argparse
import json
import shlex
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));import check as controls;import prepare
def main(args):
    args.cc=args.cc.resolve(strict=True);args.upstream=args.upstream.resolve(strict=True)
    base=args.composition.resolve(strict=True);manifest=controls.composer.verify_composition(base)
    output=controls.composer.new_output(args.output,[base,HERE,args.upstream]);output.mkdir(parents=True)
    changed=prepare.original_transforms({name:(base/'source'/name).read_text() for name in prepare.ORIGINAL_INPUTS})
    flags=controls.original_flags(args,base,manifest,output)
    flags+=['-I',str(HERE/'include'),'-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1',
        '-target','x86_64-macos-none','-mkernel','-DKERNEL','-D__KERNEL__','-fPIC',
        '-Wframe-larger-than=4096','-Werror=frame-larger-than','-fstack-usage']
    rows=[]
    for name,text in changed.items():
        path=output/Path(name).name;path.write_text(text);obj=path.with_suffix('.o');dep=obj.with_suffix('.d')
        command=[args.cc,*flags,'-MD','-MF',dep,'-c',path,'-o',obj]
        controls.run(command,output,obj.with_suffix('.log'))
        definitions,imports,sections=controls.composer.original.macho_symbols(obj)
        expected=set(prepare.EXPORTS.get(name,()))
        if not expected<=definitions:raise ValueError('Missing actual original export owner')
        deps={}
        for token in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            p=Path(token);p=p.resolve(strict=True) if p.is_absolute() else (output/p).resolve(strict=True)
            deps[str(p)]=controls.sha(p)
        rows.append({'source':name,'source_sha256':controls.sha(path),'object_sha256':controls.sha(obj),
            'command':[str(x) for x in command],'cwd':str(output),'dependency_sha256':deps,
            'definitions':sorted(definitions),'imports':sorted(imports),
            'stack_usage':obj.with_suffix('.su').read_text()})
    if controls.composer.verify_composition(base)!=manifest:raise ValueError('Parent source changed')
    for row in rows:
        for name,digest in row['dependency_sha256'].items():
            if controls.sha(Path(name))!=digest:raise ValueError('Compiler dependency changed')
    report={'format':1,'status':'compiled-original-subset-source-only','results':rows,
        'composition_sha256':controls.sha(base/'composition.json'),'complete_changed_original_tus':2,
        'kernel_definitions':['KERNEL','__KERNEL__','PORT_IS_KERNEL_BUILD'],
        'full_original_profile_validated':False,'header_abi_changed':False,
        'native_darwin_compilation':False,'final_link':'not_performed','kernel_execution':'not_tested',
        'hardware_admission':False,'original_entry_admission':False,'pm_30_second_shutdown_bound_proven':False}
    (output/'complete-original-crosscompile.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'complete_changed_original_tus':2,'header_abi_changed':False}))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('composition','upstream','output','cc'):parser.add_argument('--'+name,type=Path,required=True)
    main(parser.parse_args())
