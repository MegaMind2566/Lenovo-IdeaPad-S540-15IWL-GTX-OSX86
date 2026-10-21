#!/usr/bin/env python3
"""Execute unchanged IRQ identity production bodies with exact original layouts."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PACKAGE=HERE.parent
CONTEXT='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
CONTEXT_LAYOUT_SHA='f51fa31f0df651535f9f7e8d208fec3873eea1b17158f9fcf156133cbcbc23cf'
CONTEXT_OWNER_SHA='f516fb0b819006672f53f9060faaa3b46358bb7745cadb9b935b2e5626b76c9b'
ORIGINALS={
    'src/nvidia/arch/nvalloc/unix/include/nv-priv.h':'6d1978f87474a13f1bf3c4836aeca6855dff03f04e9f5fa18897e440acd84b50',
    'kernel-open/common/inc/nv.h':'ae47af242f37db76255094628d79c31ac0a63906452a71a4df6390f76f7585d2',
}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(text):return hashlib.sha256(text.encode()).hexdigest()

def check(args):
    upstream=args.upstream.resolve(strict=True);composition=args.composition.resolve(strict=True)
    namespace=composition/'S540ComposedNamespace.h'
    if not namespace.is_file():raise ValueError('Composed namespace required')
    for name,expected in ORIGINALS.items():
        path=upstream/name
        if path.is_symlink() or sha(path)!=expected:raise ValueError('Pinned original header changed: '+name)
    context=args.context_source.resolve(strict=True) if args.context_source else composition/'project'/CONTEXT
    if context.is_symlink():raise ValueError('Selected Context symlink refused')
    context_text=context.read_text()
    spec=importlib.util.spec_from_file_location('identity_extract',ROOT/'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/rc/check_actual_1hz.py')
    extract=importlib.util.module_from_spec(spec);spec.loader.exec_module(extract)
    layout=context_text[context_text.index('struct nv_dma_device {'):context_text.index('// One S540 adapter')]
    owner=extract.body(context_text,'owner')
    if digest(layout)!=CONTEXT_LAYOUT_SHA or digest(owner)!=CONTEXT_OWNER_SHA:
        raise ValueError('Exact selected Context storage or ordinary owner implementation changed')
    if context_text.count('static S540GspContext *metadataContext;')!=1:
        raise ValueError('Exact original metadata registry declaration changed')
    production=PACKAGE/'context-identity.c.inc';identity_header=PACKAGE/'S540NvidiaGspIrqIdentity.h'
    production_sha=sha(production);header_sha=sha(identity_header)
    sys.path.insert(0,str(ROOT/'builders'));import compile_nvidia_global_rm as original
    with tempfile.TemporaryDirectory(prefix='s540-irq-identity-') as temporary:
        work=Path(temporary);(work/'actual-context-layout.inc').write_text(layout)
        (work/'actual-context-owner.inc').write_text(owner)
        if args.bridge_command:
            cached=json.loads(args.bridge_command.read_text())
            if not isinstance(cached,list) or len(cached)<20 or cached.count('-target')!=1:
                raise ValueError('Recorded original bridge command required')
            boundary=cached.index('-target')
            if cached[boundary+1]!='x86_64-apple-macos15' or Path(cached[0]).resolve()!=args.cc.resolve():
                raise ValueError('Recorded bridge compiler/target differ')
            bridge=cached[1:boundary]
            includes=[i for i,item in enumerate(bridge) if item=='-include']
            if not includes or Path(bridge[includes[0]+1]).resolve()!=upstream/'src/common/sdk/nvidia/inc/cpuopsys.h':
                raise ValueError('Recorded original CPU/profile preinclude differs')
            bridge[includes[-1]+1]=str(namespace)
        else:bridge=original.original_bridge_flags(upstream,work/'profile',args.cc,namespace)
        host=[flag for flag in bridge if flag not in {'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}]
        host+=['-fPIC','-mcmodel=small','-U__linux__','-U__linux']
        packages=composition/'project/packages'
        include=['-I'+str(work),'-I'+str(packages),'-I'+str(packages/'nvidia-gsp-bootstrap/src'),
            '-I'+str(packages/'nvidia-gsp-bootstrap/prospective-first-transaction/record'),
            '-I'+str(packages/'nvidia-darwin-services/src')]
        results={};commands=[];environment=dict(os.environ)
        environment['ASAN_OPTIONS']=environment.get('ASAN_OPTIONS','')+':detect_leaks=0'
        for mode,sanitizers in [('plain',[]),('fatal-sanitized',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
            command=[str(args.cc),*host,'-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                '-Wno-missing-field-initializers',*include,*sanitizers,str(HERE/'context_identity.c'),'-o',str(work/mode)]
            commands.append(command)
            built=subprocess.run(command,capture_output=True,text=True,timeout=60)
            if built.returncode:raise RuntimeError(mode+' compile:\n'+built.stdout+built.stderr)
            ran=subprocess.run([str(work/mode)],capture_output=True,text=True,timeout=20,env=environment)
            if ran.returncode or ran.stderr:raise RuntimeError(mode+' execution:\n'+ran.stdout+ran.stderr)
            results[mode]=json.loads(ran.stdout)
        if sha(production)!=production_sha or sha(identity_header)!=header_sha:
            raise ValueError('Production identity source changed during controls')
        report={'format':1,'status':'passed','profile':'actual-context-irq-identity-and-mode-control',
            'original_header_sha256':ORIGINALS,'selected_context_sha256':sha(context),
            'context_layout_sha256':digest(layout),'context_owner_body_sha256':digest(owner),
            'production_identity_sha256':production_sha,'production_identity_header_sha256':header_sha,
            'namespace_sha256':sha(namespace),'fixture_sha256':sha(HERE/'context_identity.c'),
            'checker_sha256':sha(HERE/'context_identity.py'),'results':results,'commands':commands,
            'production_include_executed_unchanged':True,'context_layout':'exact selected composed Context struct; complete original NVIDIA headers',
            'dependencies':'explicit metadata registry, ordinary/thread, strong global-master and actual backend-mode observation fixtures',
            'backend_observation_execution':False,'controller_registration_execution':False,
            'hardware_irq_execution':False,'whole_irq_admission':False,'gpu_initialization_proved':False,
            'cpu_stack_switch_proved':False,'original_adapter_initialization_calls':0}
        if args.bridge_command:report['recorded_bridge_command_sha256']=sha(args.bridge_command)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--composition',type=Path,required=True);parser.add_argument('--context-source',type=Path)
    parser.add_argument('--cc',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--bridge-command',type=Path,help='Recorded original-ABI bridge command JSON; avoids repeated make dry-run parsing')
    print(json.dumps(check(parser.parse_args()),indent=2,sort_keys=True))
