#!/usr/bin/env python3
"""Fault genuine postcore API-lock TLS allocations using authenticated objects.

Reuses every actual original/project object from completed constructor controls;
only the small CPU observer/fixture/boundary/harness units are compiled afresh.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import prepare as candidate

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def harness_source():
    text=(candidate.HERE/'check_epoch.cpp').read_text()
    # Exact C declaration from the sealed ownership header. Its original
    # rmconfig include is not part of the plain C++ Host harness ABI.
    text=candidate.once(text,'extern "C" {',
        'extern "C" {\nNV_STATUS s540ProspectiveOriginalApiOwnership(NvBool *);')
    text=candidate.once(text,'if(scenario>9||(argc==3&&scenario!=6))return 2;',
        'if(scenario>9||(argc==3&&scenario!=6&&scenario!=7))return 2;')
    text=candidate.once(text,'    S540NvidiaGlobalRmResult result={};\n    const NV_STATUS status=',
        '    if(scenario==7&&argc==3)S540NvidiaGlobalRmNative::failAllocationAt(\n'
        '        std::strtoull(argv[2],nullptr,10));\n'
        '    S540NvidiaGlobalRmResult result={};\n    const NV_STATUS status=')
    text=candidate.once(text,'        }else{\n            expect(s540GlobalEpochControlHookStatus==NV_OK',
        '        }else if(scenario==7&&host.allocationFailures){\n'
        '            expect(s540GlobalEpochControlHookStatus==NV_ERR_INSUFFICIENT_RESOURCES&&\n'
        '                status==NV_ERR_NO_MEMORY&&epoch.firstStatus==NV_ERR_NO_MEMORY&&\n'
        '                epoch.originalStatus==NV_OK&&!epoch.validationStatus,\n'
        '                "real postcore TLS failure preserves successful original return and sticky OOM");\n'
        '            NvBool api=NV_TRUE;\n'
        '            expect(s540ProspectiveOriginalApiOwnership(&api)==NV_OK&&!api,\n'
        '                "actual TLS probe reports no current-thread API ownership after failed acquire");\n'
        '            expect(epoch.originalReturned&&!epoch.validated&&\n'
        '                epoch.state==S540_FIRST_GLOBAL_RETAINED,\n'
        '                "postcore refusal retains completed original globals without publication");\n'
        '        }else{\n            expect(s540GlobalEpochControlHookStatus==NV_OK')
    text=candidate.once(text,r'\"cleanup_after_claim\":%u,\"kernel_execution\":false',
        r'\"cleanup_after_claim\":%u,\"postcore_hook_status\":%u,\"kernel_execution\":false')
    text=candidate.once(text,'s540RetainedControlClaims,s540RetainedControlCleanupAfterClaim);',
        's540RetainedControlClaims,s540RetainedControlCleanupAfterClaim,s540GlobalEpochControlHookStatus);')
    return text

def run(args):
    sys.path.insert(0,str(candidate.ROOT/'builders'))
    import compose_nvidia_first_transaction as composer
    import check_nvidia_global_lifecycle as lifecycle
    controls=args.controls.resolve(strict=True)
    previous=json.loads((controls/'results.json').read_text())
    if previous.get('status')!='passed-actual-original-retained-construction-allocation-closure':
        raise ValueError('Completed full constructor controls are required for object reuse')
    if previous.get('kernel_execution') or previous.get('gpu_access'):
        raise ValueError('Only actual CPU-control object profiles are eligible')
    for name,digest in previous['control_source_sha256'].items():
        if sha(candidate.HERE/name)!=digest:raise ValueError('Constructor control changed: '+name)
    if composer.tree_sha(composer.inventory(controls/'source'))!=previous['original_source_inventory_sha256']:
        raise ValueError('Actual original companion source changed before reuse')
    ownership=controls/'project/packages/nvidia-gsp-bootstrap/prospective-rm-lock-ownership/S540ProspectiveRmLockOwnership.h'
    if ownership.read_text().count('NV_STATUS s540ProspectiveOriginalApiOwnership(NvBool *);')!=1:
        raise ValueError('Actual original ownership probe declaration changed')
    old=controls/args.variant
    output=composer.new_output(args.output,[controls,candidate.HERE]);output.mkdir(parents=True)
    originals=json.loads((old/'original-compilation.json').read_text())
    projects=json.loads((old/'project-compilation.json').read_text())
    if len(originals)!=1100:raise ValueError('Complete actual original object inventory required')
    bindings=[]
    for kind,rows in [('original',originals),('project',projects)]:
        for row in rows:
            obj=Path(row['object'])
            source=Path(row['compiled_source']) if kind=='original' else controls/'project'/row['source']
            if sha(obj)!=row['object_sha256'] or sha(source)!=row['source_sha256']:
                raise ValueError('Authenticated '+kind+' source/object changed: '+row['source'])
            bindings.append({'kind':kind,'source':row['source'],'object':str(obj),'object_sha256':sha(obj)})
    variant=previous['variants'][args.variant]
    if sha(old/'global-epoch-check')!=variant['binary_sha256']:
        raise ValueError('Completed constructor-control executable changed')
    initial=variant['observations'][0]['allocations']
    with_api=variant['observations'][7]['allocations']
    if initial!=variant['all_allocation_positions_tested'] or with_api<=initial:
        raise ValueError('Actual postcore path does not expose a separate allocation range')
    def flags(relative):
        row=next(r for r in projects if r['source']==relative)
        return row['command'][:row['command'].index('-c')]
    cpp=flags('packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp')
    bridge=flags('packages/nvidia-global-rm/src/S540NvidiaGlobalRmLifecycle.c')
    compiled=[]
    def compile_one(source,obj,prefix):
        argv=[*prefix,'-c',str(source),'-o',str(obj)]
        result=subprocess.run(argv,text=True,capture_output=True,timeout=120)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('Postcore CPU control compile failed: '+result.stderr)
        compiled.append({'source':str(source),'source_sha256':sha(source),'object':str(obj),
            'object_sha256':sha(obj),'command':argv})
    source=output/'postcore-harness.cpp';source.write_text(harness_source())
    harness=output/'postcore-harness.o';compile_one(source,harness,cpp)
    original_control=output/'original-control.o'
    compile_one(candidate.HERE/'check_original.c',original_control,bridge)
    provided=set().union(*(lifecycle._symbols(Path(r['object']),previous['host_control'])[0] for r in projects))
    boundaries=lifecycle._private_boundaries(output,provided)
    if boundaries!=variant['boundaries']:raise ValueError('Actual unavailable-boundary inventory changed')
    boundary=output/'native-unavailable-boundaries.o'
    compile_one(output/'native-unavailable-boundaries.c',boundary,bridge)
    assertion=output/'nvswitch-assert-fixture.o'
    compile_one(lifecycle.PACKAGE/'tests/fixtures/nvswitch_assert_fixture.c',assertion,bridge)
    binary=output/'postcore-check'
    link=[*cpp,str(harness),*[r['object'] for r in originals],*[r['object'] for r in projects],
        str(original_control),str(boundary),str(assertion),
        '-Wl,--gc-sections' if previous['host_control'] else '-Wl,-dead_strip','-o',str(binary)]
    result=subprocess.run(link,text=True,capture_output=True,timeout=300)
    (output/'link.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Postcore CPU control link failed: '+result.stderr[-6000:])
    environment=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    observations=[]
    for ordinal in range(initial+1,with_api+2):
        result=subprocess.run([str(binary),'7',str(ordinal)],text=True,capture_output=True,
            timeout=30,env=environment)
        (output/('postcore-%04d.log'%ordinal)).write_text(result.stdout+result.stderr)
        try:view=json.loads(result.stdout)
        except json.JSONDecodeError:raise RuntimeError('Actual postcore fault did not return: '+str(ordinal))
        view.update(ordinal=ordinal,process_status=result.returncode);observations.append(view)
        if result.returncode or view['failures']:raise RuntimeError('Actual postcore fault failed: '+str(ordinal))
        if ordinal<=with_api and not view['allocation_failures']:
            raise RuntimeError('Actual postcore allocation was not faulted: '+str(ordinal))
        if ordinal==with_api+1 and view['allocation_failures']:
            raise RuntimeError('Terminal postcore control reached an unexpected allocation')
    for row in bindings:
        if sha(Path(row['object']))!=row['object_sha256']:raise ValueError('Reused actual object changed')
    report={'format':1,'status':'passed-actual-postcore-api-lock-allocation-faults',
        'variant':args.variant,'constructor_results_sha256':sha(controls/'results.json'),
        'constructor_allocation_positions':initial,'postcore_only_allocation_positions':list(range(initial+1,with_api+1)),
        'terminal_unreached_postcore_ordinal':with_api+1,'observations':observations,
        'all_original_objects_reused_byte_identically':True,'reused_objects':bindings,
        'small_control_compilation':compiled,'link_command':link,'binary_sha256':sha(binary),
        'constructor_control_source_sha256':previous['control_source_sha256'],
        'postcore_control_source_sha256':sha(Path(__file__)),
        'kernel_execution':False,'gpu_access':False,'original_entry_admission':False,
        'production_candidate_allowed':False,'privileged_cpu_fixture':True,'platform_facts_fixture':True}
    write(output/'results.json',report)
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('controls','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--variant',choices=('plain','sanitized'),required=True)
    print(json.dumps({'status':run(p.parse_args())['status']}))
