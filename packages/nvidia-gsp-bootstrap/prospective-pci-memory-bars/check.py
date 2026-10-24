#!/usr/bin/env python3
"""Execute exact PCI collector bodies with explicit registry-derived CPU fixtures."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import resource
import shlex
import struct
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)
def load_prepare():
    spec=importlib.util.spec_from_file_location('s540_pci_memory_bar_controls',HERE/'prepare.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def body(text):
    first,last=function_span(text,'S540NvidiaGspPlatform::Context::collectDeviceFacts')
    first=text.rfind('\n',0,first)+1
    result=text[first:last]
    require(result.startswith('NV_STATUS S540NvidiaGspPlatform::Context::collectDeviceFacts('),'Exact actual kernel collector signature required')
    return result
def records(hexadecimal):
    data=bytes.fromhex(hexadecimal);require(len(data)==100,'Exact five target resource records required')
    return [dict(register=hex(first&255),space=(first>>24)&3,address=hex((middle<<32)|low),bytes=hex((sizehi<<32)|sizelo))
        for first,middle,low,sizehi,sizelo in struct.iter_unpack('<5I',data)]
def target_fixture(path=None):
    fixture=json.loads((HERE/'tests/target-registry-fixture.json').read_text())
    require(fixture['format']==1 and fixture['pci_express_capabilities_property']==18,
        'Authentic target legacy endpoint observation must remain 0x12')
    canonical=lambda rows:[{k:(int(v,0) if isinstance(v,str) else v) for k,v in row.items()} for row in rows]
    require(canonical(records(fixture['assigned_addresses_hex']))==canonical(fixture['records']),
        'Registry-derived resource fixture differs from actual record bytes')
    resources=canonical(fixture['records']);memory=[r for r in resources if r['register'] in (0x10,0x14,0x1c)]
    require([r['register'] for r in memory]==[0x10,0x14,0x1c] and all(r['space']==2 for r in memory),
        'Three actual memory resources must remain distinct from I/O and ROM')
    require(resources[3]==dict(register=0x24,space=1,address=0x3000,bytes=0x80) and resources[4]['register']==0x30,
        'Actual optional I/O BAR and expansion ROM observations changed')
    described=fixture['io_device_memory']
    require([(r['address'],r['bytes']) for r in memory]==[(int(described[i]['address'],0),int(described[i]['bytes'],0)) for i in range(3)],
        'Actual memory descriptors must match the target assigned addresses')
    authenticated=False
    if path:
        path=path.resolve(strict=True)
        require(sha(path)==fixture['source_capture_sha256'],'A different registry capture cannot replace the reviewed correct-EFI evidence')
        blocks=[b for b in re.split(r'(?m)^\+-o ',path.read_text()) if '"pcidebug" = "2:0:0"' in b and '"vendor-id" = <de100000>' in b]
        require(blocks,'Target GPU block absent from authentic registry capture')
        for block in blocks:
            assigned=re.search(r'"assigned-addresses"\s*=\s*<([0-9a-f]+)>',block)
            flags=re.search(r'"IOPCIExpressCapabilities"\s*=\s*([0-9]+)',block)
            require(assigned and assigned.group(1)==fixture['assigned_addresses_hex'] and flags and int(flags.group(1))==18,
                'Authentic GPU resources/capability property differ from the fixture')
        authenticated=True
    return fixture,resources,memory,authenticated
def fixture_source(project,function,assignment,resources,memory):
    text=(HERE/'tests/check_platform.cpp.inc').read_text()
    config=[]
    for row in memory:
        kind='memory64' if row['address']>0xffffffff else 'memory32'
        config.append('    provider.%s(0x%x,0x%xULL,0x%xULL);'%(kind,row['register'],row['address'],row['bytes']))
    config+=['    provider.fixture32(0x24,0x3001U);',
        '    provider.fixture32(0x30,0x%xU);'%resources[4]['address']]
    values=dict(PLATFORM_HEADER=str(project/'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPlatform.hpp'),
        OBSERVATION_HEADER=str(project/'packages/nvidia-gsp-bootstrap/prospective-preparation-observation/S540PreparationObservation.h'),
        ACTUAL_BODY=function,PREDICATE_ASSIGNMENT=assignment,TARGET_CONFIG='\n'.join(config),
        MEMORY0=hex(memory[0]['address']),MEMORY1=hex(memory[1]['address']),MEMORY2=hex(memory[2]['address']))
    for key,value in values.items():
        marker='@'+key+'@';require(text.count(marker)>=1,'Missing actual-body fixture marker '+key);text=text.replace(marker,value)
    require(not re.search(r'@[A-Z_0-9]+@',text),'Unexpanded actual-body fixture token')
    return text
def dependencies(path):
    return {str(Path(name).resolve(strict=True)):sha(Path(name).resolve(strict=True))
        for name in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1])}

def run(args):
    require(args.host_control,'Explicit --host-control is required; these are CPU fixtures')
    project=args.input_project.resolve(strict=True);composed=args.composed_project.resolve(strict=True) if args.composed_project else project
    output=args.output.resolve();require(not output.exists(),'Fresh PCI controls output required')
    require(not output.is_relative_to(HERE) and not HERE.is_relative_to(output),'Controls must not overwrite their source package')
    prepare=load_prepare();original={name:(project/name).read_text() for name in prepare.INPUTS}
    fixed=prepare.transforms(original);require(set(fixed)==set(original),'Exact single-source profile required')
    if args.composed_project:
        require(all((composed/name).read_text()==text for name,text in fixed.items()),'Current composed collector differs from the exact full selected profile')
    observer=composed/'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp'
    observer_text=observer.read_text();anchor='            state.preparation.devicePredicates ='
    require(observer_text.count(anchor)==1,'One actual production predicate observation required')
    first=observer_text.index(anchor);assignment=observer_text[first:observer_text.index(';',first)+1]
    old_source=original[prepare.PLATFORM];new_source=fixed[prepare.PLATFORM]
    require(old_source.count(prepare.BEFORE)==1,'One exact intermediate BAR insertion boundary required')
    intermediate=old_source.replace(prepare.BEFORE,prepare.AFTER)
    source_bodies=dict(baseline=body(old_source),io_only=body(intermediate),combined=body(new_source))
    fixture,resources,memory,authenticated=target_fixture(args.registry_dump)
    source_checks=[]
    for malformed in ({prepare.PLATFORM:old_source+'\n'},{},dict(original,unreviewed='unreviewed')):
        try:prepare.transforms(malformed)
        except ValueError:source_checks.append('changed/missing/extra-source-refused')
        else:raise ValueError('Unreviewed source prerequisite accepted')
    require(new_source.replace(prepare.AFTER,prepare.BEFORE).replace(prepare.ENDPOINT_AFTER,prepare.ENDPOINT_BEFORE)==old_source,
        'Combined profile contains a change beyond the two reviewed boundaries')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));output.mkdir(parents=True)
    compiler=args.cxx.resolve(strict=True)
    flags=['-std=c++17','-O1','-g','-Wall','-Wextra','-Werror']
    runs={};commands=[]
    def execute(label,function,mode,sanitize=False,must_fail=False):
        path=output/(label+'.cpp');path.write_text(fixture_source(composed,function,assignment,resources,memory))
        executable=output/label;dep=output/(label+'.d')
        command=[str(compiler),*flags,'-DPROFILE_MODE='+str(mode)]
        if sanitize:command+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        command+=['-MD','-MF',str(dep),str(path),'-o',str(executable)]
        built=subprocess.run(command,capture_output=True,text=True,timeout=120)
        (output/(label+'-compile.log')).write_text(built.stdout+built.stderr)
        require(built.returncode==0,'Actual collector CPU fixture did not compile: '+label+' '+built.stderr[-4000:])
        env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
        result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=30,env=env)
        (output/(label+'-run.log')).write_text(result.stdout+result.stderr)
        commands.append(command)
        row=dict(source_sha256=sha(path),binary_sha256=sha(executable),dependency_sha256=dependencies(dep),
            returncode=result.returncode,sanitized=sanitize,negative_control=must_fail)
        if must_fail:
            require(result.returncode!=0,'Actual-body mutant survived: '+label);row['killed']=True
        else:
            require(result.returncode==0,'Actual collector CPU fixture failed: '+label+' '+result.stderr[-3000:])
            row.update(json.loads(result.stdout));(output/(label+'-results.json')).write_text(result.stdout)
        runs[label]=row
    for label,mode in (('baseline',0),('io_only',1),('combined',2)):
        execute(label,source_bodies[label],mode)
        execute(label+'_sanitized',source_bodies[label],mode,True)
        require(runs[label]['cases']==runs[label+'_sanitized']['cases'],'Plain/sanitized actual-body results differ')
    require(runs['baseline']['cases'][0]['trace']==runs['io_only']['cases'][0]['trace']==runs['combined']['cases'][0]['trace'],
        'Authentic target metadata call order changed across the two narrow predicate fixes')
    mutations={
        'missing_io_skip':('if (low & 1U) continue;',''),
        'io_counted_as_memory':('if (low & 1U) continue;','if (low & 1U) { ++bar; continue; }'),
        'allow_nonendpoint_types':('express = type == 0 || type == 1;','express = (static_cast<void>(type), true);'),
        'ignore_descriptor_address':('address == physical','(static_cast<void>(address), true)'),
        'lose_64bit_pairing':('if (kind == 4) offset += 4;',''),
        'accept_wrong_vendor':('facts.vendor == 0x10de','true')}
    for name,(before,after) in mutations.items():
        require(source_bodies['combined'].count(before)==1,'Exact actual-body mutation anchor changed: '+name)
        execute('mutant_'+name,source_bodies['combined'].replace(before,after),2,must_fail=True)
    hashes={str(p.relative_to(ROOT)):sha(p) for p in [HERE/'prepare.py',HERE/'check.py',HERE/'tests/check_platform.cpp.inc',HERE/'tests/target-registry-fixture.json']}
    report=dict(format=1,status='passed-registry-derived-actual-collector-and-two-boundary-controls',
        exact_input_sha256={name:hashlib.sha256(text.encode()).hexdigest() for name,text in original.items()},
        exact_output_sha256={name:hashlib.sha256(text.encode()).hexdigest() for name,text in fixed.items()},
        source_body_sha256={name:hashlib.sha256(text.encode()).hexdigest() for name,text in source_bodies.items()},
        actual_predicate_assignment_sha256=hashlib.sha256(assignment.encode()).hexdigest(),
        observer_source_sha256=sha(observer),source_file_sha256=hashes,
        target_registry_fixture=fixture,authentic_registry_capture_verified_this_run=authenticated,
        exact_source_refusal_controls=source_checks,intermediate_io_fix_is_not_full_target_success=True,
        target_regression_status_predicates=[dict(variant=name,status=runs[name]['cases'][0]['status'],predicates=runs[name]['cases'][0]['predicates']) for name in ('baseline','io_only','combined')],
        actual_target_dependency_call_trace_unchanged=True,all_endpoint_configuration_writes=0,
        variants=runs,commands=commands,compiler_sha256=sha(compiler),
        sanitizer_policy=dict(address_and_undefined_fatal=True,leak_sanitizer_enabled=False,
            leak_sanitizer_reason='This traced host cannot enumerate /proc tasks; LeakSanitizer is explicitly disabled, not reported as passed.'),
        native_darwin_compilation=False,whole_kernel_translation_unit_compiled=False,
        hardware_executed=False,original_rm_executed=False,gpu_initialization_proven=False,
        system_security_changed=False,github_workflows_started=0)
    require({str(p.relative_to(ROOT)):sha(p) for p in [HERE/'prepare.py',HERE/'check.py',HERE/'tests/check_platform.cpp.inc',HERE/'tests/target-registry-fixture.json']}==hashes,
        'A checked production/helper source changed during the control')
    (output/'results.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-project',type=Path,required=True)
    parser.add_argument('--composed-project',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cxx',type=Path,required=True)
    parser.add_argument('--registry-dump',type=Path);parser.add_argument('--host-control',action='store_true')
    result=run(parser.parse_args())
    print(json.dumps(dict(status=result['status'],regression=result['target_regression_status_predicates'],
        combined_checks=result['variants']['combined']['checks'],combined_cases=result['variants']['combined']['case_count'],
        sanitized_checks=result['variants']['combined_sanitized']['checks'],mutants_killed=sum(bool(v.get('killed')) for v in result['variants'].values()))))
