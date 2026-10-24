#!/usr/bin/env python3
"""Real LLVM driver-alias regression, followed by the complete collector controls.

This requires an existing clang++ symlink whose resolved ELF binary is clang.
Both driver modes compile the same real C++ source; no failure stub is used.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import subprocess
import sys

HERE=Path(__file__).resolve().parent
CHECKER=HERE.parent/'check.py'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)
def run(args):
    require(args.host_control,'Explicit local CPU --host-control required')
    compiler=args.cxx.expanduser().absolute();target=compiler.resolve(strict=True)
    require('clang++' in compiler.name and compiler.is_symlink(),
        'A real clang++ invocation symlink is required to exercise this regression')
    require(re.fullmatch(r'clang(?:-[0-9]+)?',target.name) and target.read_bytes()[:4]==b'\x7fELF' and os.access(compiler,os.X_OK),
        'The alias must resolve to the actual executable LLVM clang ELF binary, never a wrapper or failure stub')
    output=args.output.resolve();require(not output.exists(),'Fresh real-driver regression output required')
    output.mkdir(parents=True);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    source=output/'driver-mode.cpp'
    source.write_text('#include <vector>\n#include <iostream>\nint main() { std::vector<int> values; '
        'values.push_back(7); values.push_back(9); std::cout << values[0] << ":" << values[1] << "\\n"; '
        'return values[0]==7 && values[1]==9 ? 0 : 1; }\n')
    commands=[]
    for label,driver,should_link in (('resolved-C-driver',target,False),('preserved-C++-alias',compiler,True)):
        executable=output/label;command=[str(driver),'-std=c++17','-O1',str(source),'-o',str(executable)]
        built=subprocess.run(command,capture_output=True,text=True,timeout=120)
        (output/(label+'-compile.log')).write_text(built.stdout+built.stderr)
        if should_link:
            require(built.returncode==0,'The real clang++ alias did not link its C++ standard library: '+built.stderr[-3000:])
            ran=subprocess.run([str(executable)],check=True,capture_output=True,text=True,timeout=30)
            require(ran.stdout=='7:9\n','The real C++ driver control executable returned unexpected output')
        else:
            require(built.returncode!=0 and 'undefined reference' in built.stderr and
                ('operator new' in built.stderr or 'std::' in built.stderr),
                'The actual resolved C driver did not reproduce the expected missing C++ standard-library link')
        commands.append(dict(label=label,command=command,returncode=built.returncode,
            compiler_resolved_sha256=sha(target),expected_cpp_autolink=should_link))
    require('compiler=args.cxx.expanduser().absolute()' in CHECKER.read_text(),
        'The collector checker must preserve the lexical compiler invocation alias')
    controls=output/'complete-collector-controls'
    command=[sys.executable,'-B',str(CHECKER),'--input-project',str(args.input_project.resolve(strict=True)),
        '--output',str(controls),'--cxx',str(compiler),'--host-control']
    if args.composed_project:command+=['--composed-project',str(args.composed_project.resolve(strict=True))]
    if args.registry_dump:command+=['--registry-dump',str(args.registry_dump.resolve(strict=True))]
    checked=subprocess.run(command,capture_output=True,text=True,timeout=240)
    (output/'complete-controls.stdout.log').write_text(checked.stdout)
    (output/'complete-controls.stderr.log').write_text(checked.stderr)
    require(checked.returncode==0,'The actual clang++ symlink failed the full collector controls: '+checked.stderr[-5000:])
    report=controls/'results.json';value=json.loads(report.read_text())
    require(value['status']=='passed-registry-derived-actual-collector-and-two-boundary-controls' and
        value['variants']['combined']['case_count']==52 and value['variants']['combined_sanitized']['case_count']==52 and
        sum(bool(row.get('killed')) for row in value['variants'].values())==6,
        'The real-driver alias regression must complete all 52 cases and six meaningful mutants')
    require(Path(value['compiler_invocation_path']).name==compiler.name and
        Path(value['compiler_resolved_path'])==target and value['compiler_sha256']==sha(target),
        'The full collector report did not bind the preserved alias to its actual resolved compiler')
    result=dict(format=1,status='passed-real-LLVM-symlink-C++-driver-regression-and-full-collector-controls',
        invocation_path=str(compiler),resolved_binary=str(target),resolved_binary_sha256=sha(target),
        actual_elf_binary_verified=True,fake_failure_stub=False,
        source_sha256=sha(source),checker_sha256=sha(CHECKER),regression_helper_sha256=sha(__file__),
        driver_mode_controls=commands,complete_checker_command=command,
        complete_controls_report=str(report),complete_controls_report_sha256=sha(report),
        target_regression_status_predicates=value['target_regression_status_predicates'],
        combined_checks=value['variants']['combined']['checks'],combined_cases=52,
        fatal_asan_ubsan_checks=value['variants']['combined_sanitized']['checks'],mutants_killed=6,
        sanitizer_policy=value['sanitizer_policy'],native_darwin_compilation=False,hardware_executed=False,
        original_rm_executed=False,github_workflows_started=0)
    (output/'results.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-project',type=Path,required=True);parser.add_argument('--composed-project',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cxx',type=Path,required=True)
    parser.add_argument('--registry-dump',type=Path);parser.add_argument('--host-control',action='store_true')
    value=run(parser.parse_args());print(json.dumps({key:value[key] for key in ('status','invocation_path','resolved_binary','combined_checks','combined_cases','fatal_asan_ubsan_checks','mutants_killed')}))
