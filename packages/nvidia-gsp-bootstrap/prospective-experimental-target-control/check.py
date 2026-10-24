#!/usr/bin/env python3
"""Actual C state controls; no IOKit/hardware success is inferred."""
import argparse,hashlib,json,subprocess,os
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Fresh control output required')
    args.output.mkdir(parents=True)
    rows=[]
    for mode,flags in [('plain',[]),('sanitized',['-fsanitize=address,undefined','-fno-sanitize-recover=all'])]:
        binary=args.output/mode
        command=[str(args.cc.resolve()),'-std=c11','-O1','-g','-Wall','-Wextra','-Werror',*flags,
            str(HERE/'S540ExperimentalTargetState.c'),str(HERE/'tests/check_state.c'),'-o',str(binary)]
        subprocess.run(command,check=True,capture_output=True)
        environment=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
        result=subprocess.run([str(binary.resolve())],check=True,capture_output=True,text=True,env=environment)
        rows.append(dict(mode=mode,command=command,result=json.loads(result.stdout)))
    mutations={
        'contract-comparison-removed':('!equal(request->nativeCodeContractSha256,contract,32)','0'),
        'once-guard-removed':('if (state->snapshot.requestConsumed) return NV_ERR_STATE_IN_USE;',''),
        'capacity-floor-removed':('request->observedKernelStackBytes < worker','0')}
    text=(HERE/'S540ExperimentalTargetState.c').read_text()
    mutants=[]
    for name,(before,after) in mutations.items():
        if text.count(before)!=1:raise ValueError('Mutation anchor changed')
        source=args.output/(name+'.c');source.write_text(text.replace(before,after))
        binary=args.output/name
        subprocess.run([str(args.cc.resolve()),'-std=c11','-O1','-I',str(HERE),str(source),
            str(HERE/'tests/check_state.c'),'-o',str(binary)],check=True,capture_output=True)
        result=subprocess.run([str(binary.resolve())],capture_output=True,text=True)
        if not result.returncode: raise ValueError('Actual state controls did not kill '+name)
        mutants.append(dict(name=name,rejected=True))
    sources={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [
        HERE/'S540ExperimentalTargetState.c',HERE/'S540ExperimentalTargetState.h',
        HERE/'S540ExperimentalTargetProtocol.h',HERE/'tests/check_state.c',HERE/'check.py',
        HERE.parent/'prospective-preparation-observation/S540PreparationObservation.h']}
    report=dict(format=1,status='actual-c-state-controls-passed',controls=rows,mutants=mutants,
        source_sha256=sources,kernel_execution='not_tested',gpu_access=False)
    (args.output/'results.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
