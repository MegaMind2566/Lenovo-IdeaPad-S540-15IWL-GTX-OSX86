#!/usr/bin/env python3
"""Local selected-body SDK compile; never links, installs, or requests CI."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]
sys.path.insert(0,str(HERE))
import prepare
sys.path.insert(0,str(PROJECT/'builders'))
import compile_nvidia_integrated_successor as compiled_symbols
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    parent=args.parent.resolve(strict=True);output=args.output.resolve()
    if output.exists():raise ValueError('Fresh local check output required')
    contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    assert contract['production_sha256']=={name:sha(HERE/name) for name in prepare.PRODUCTION_FILES}
    old={k:(parent/'project'/k).read_text() for k in prepare.INPUTS}
    selected=prepare.transforms(old)
    # These exact public refusals/gates remain untouched by source selection.
    refusal=old[prepare.BOOT].split('    NV_STATUS initialize() {',1)[1].split('    NV_STATUS stop() {',1)[0]
    assert selected[prepare.BOOT].split('    NV_STATUS initialize() {',1)[1].split('    NV_STATUS stop() {',1)[0]==refusal
    for key in prepare.INPUTS:
        try:prepare.transforms({**old,key:selected[key]})
        except ValueError:pass
        else:raise ValueError('Non-idempotent anchor did not refuse '+key)
    shutil.copytree(parent/'project',output/'project')
    (output/'source').symlink_to(parent/'source',target_is_directory=True)
    shutil.copy2(parent/'S540ComposedNamespace.h',output/'S540ComposedNamespace.h')
    for key,value in selected.items():(output/'project'/key).write_text(value)
    for key,source in prepare.COMPANIONS.items():
        destination=output/'project'/key;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
    report={'format':1,'source_selection_only':True,'kernel_execution':False,'original_entry_admission':False,
        'full_hardware_cleanup_proven':False,'new_exports':prepare.EXPORTS,'results':[],
        'production_sha256':{name:sha(HERE/name) for name in prepare.SOURCE_FILES}}
    rows=json.loads((parent/'project-compilation.json').read_text())['results']
    for row in rows:
        if row['source'] not in prepare.COMPILE_DEFINITIONS:continue
        source=row['source'];command=[arg.replace(str(parent),str(output)) for arg in row['command']]
        command=command[:command.index('-c')]+['-DS540_NVIDIA_IRQ_INSTALLATION=1']+command[command.index('-c'):]
        obj=Path(command[command.index('-o')+1]);obj.parent.mkdir(parents=True,exist_ok=True)
        result=subprocess.run(command,cwd=output/'project',capture_output=True,text=True)
        log=obj.with_suffix('.log');log.write_text(result.stdout+result.stderr)
        definitions=compiled_symbols.project_definition_strength(obj,source) if not result.returncode else {}
        if not result.returncode:
            assert all(definitions.get(name)=='strong' for name in prepare.EXPORTS[source]), 'New export lacks actual strong Mach-O definition'
        report['results'].append({'source':source,'returncode':result.returncode,'command':command,
            'new_strong_definitions':{name:definitions[name] for name in prepare.EXPORTS[source]} if definitions else {},
            'source_sha256':sha(output/'project'/source),'log_sha256':sha(log)})
        if result.returncode:print(log.read_text(),file=sys.stderr);break
    report['status']='pass' if len(report['results'])==len(prepare.COMPILE_DEFINITIONS) and all(r['returncode']==0 for r in report['results']) else 'fail'
    (output/'selected-compilation.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'selected_units':len(report['results']),'report':str(output/'selected-compilation.json')}))
    return 0 if report['status']=='pass' else 1
if __name__=='__main__':sys.exit(main())
