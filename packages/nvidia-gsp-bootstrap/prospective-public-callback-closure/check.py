#!/usr/bin/env python3
"""Exercise transformed production KERNEL branches against concurrent IOKit fixtures."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    parser.add_argument('--source-root',type=Path,default=ROOT,
        help='Source tree containing actual composed Timer/Work inputs')
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('public_callout_prepare',HERE/'prepare.py')
    prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
    source_root=args.source_root.resolve()
    before={name:(source_root/name).read_bytes() for name in prepare.INPUTS}
    composed=all(b'BackendConstruction construction;' in value for value in before.values())
    compiler=shutil.which('clang++') or shutil.which('g++')
    if not compiler: raise RuntimeError('A C++17 compiler is required')
    with tempfile.TemporaryDirectory(prefix='s540-public-callout-') as temporary:
        work=Path(temporary)
        contract=prepare.prepare(source_root,work/'overlay')
        sources=work/'overlay/packages/nvidia-darwin-services/src'
        # A changed or duplicated anchor must refuse composition.
        for name in prepare.INPUTS:
            inputs={key:value.decode() for key,value in before.items()}
            inputs[name]=inputs[name].replace('    thread_call_t call;','    thread_call_t changed;')
            try: prepare.transforms(inputs)
            except ValueError: pass
            else: raise AssertionError('Changed input anchor was accepted')
            inputs={key:value.decode() for key,value in before.items()}
            inputs[name]+='\n    thread_call_t call;\n'
            try: prepare.transforms(inputs)
            except ValueError: pass
            else: raise AssertionError('Duplicated input anchor was accepted')
        flags=['-std=c++17','-pthread','-Wall','-Wextra','-Werror']
        if composed: flags+=['-DS540_TEST_COMPOSED_SERVICES=1']
        if args.sanitize: flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        command=[compiler,*flags,'-I'+str(HERE/'tests/mock'),'-I'+str(sources),
            str(HERE/'tests/check_kernel.cpp'),'-o',str(work/'check-kernel')]
        subprocess.run(command,check=True)
        environment=dict(os.environ)
        if args.sanitize:
            # This managed host forbids LeakSanitizer's /proc task inventory.
            # ASan/UBSan remain enabled; fixture owners have explicit counts.
            environment['ASAN_OPTIONS']=environment.get('ASAN_OPTIONS','')+':detect_leaks=0'
        run=subprocess.run([str(work/'check-kernel')],capture_output=True,text=True,timeout=30,env=environment)
        if run.returncode or run.stderr:
            raise RuntimeError('KERNEL fixture failed:\n'+run.stdout+run.stderr)
        result=json.loads(run.stdout)
        result.update({'profile':'public-callback-closure','compiler':compiler,
            'sanitizers':args.sanitize,'leak_sanitizer':False,
            'leak_sanitizer_limitation':'Managed host denies /proc task inventory; owner counts checked explicitly',
            'source_contract':contract,
            'real_iokit_execution':False,'kernel_loading':False})
        result['composed_sources']=composed
        result['transaction_record_execution']=False
        result['retained_backend_policy']='explicit test fixture' if composed else 'not present in base input'
        result['composition_negative_controls']=4
        fixture_files=[HERE/'check.py',*sorted((HERE/'tests').rglob('*'))]
        result['fixture_sha256']={str(path.relative_to(HERE)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in fixture_files if path.is_file()}
    if any((source_root/name).read_bytes()!=value for name,value in before.items()):
        raise AssertionError('Frozen source modified')
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
