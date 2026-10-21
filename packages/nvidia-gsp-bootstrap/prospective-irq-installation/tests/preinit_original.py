#!/usr/bin/env python3
"""Pin and execute genuine original pre-adapter IRQ branches and Context wrappers."""
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
ORIGINALS={
    'src/nvidia/arch/nvalloc/unix/src/unix_intr.c':'952e1ccb8b3214c83cfb54748324131900eaff68986169ad7e794be29ef86819',
    'src/nvidia/arch/nvalloc/unix/src/osinit.c':'dda3b014833c2e94680e5adea152011ffce72c8067782aceeecaefc28b7394d3',
    'kernel-open/nvidia/nv.c':'ce04946d288cf0251668a2d847acceb2a39af9dac2f13bb005f53759c774dbf7',
    'src/nvidia/arch/nvalloc/unix/include/nv-priv.h':'6d1978f87474a13f1bf3c4836aeca6855dff03f04e9f5fa18897e440acd84b50',
    'kernel-open/common/inc/nv.h':'ae47af242f37db76255094628d79c31ac0a63906452a71a4df6390f76f7585d2',
}
CONTEXT='packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
CONTEXT_SHA='9f8fee42cd2e9ffb2c86a0de368d259fa8879b70398becf7c508887dd941181f'
ORIGINAL_BODIES=('rm_isr','rm_isr_bh','rm_isr_bh_unlocked','rm_gpu_handle_mmu_faults')
CONTEXT_BODIES=('s540GspContextInterruptTop','s540GspContextLockedBottomHalf','s540GspContextUnlockedBottomHalf')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def check(args):
    upstream=args.upstream.resolve(strict=True);composition=args.composition.resolve(strict=True)
    namespace=composition/'S540ComposedNamespace.h'
    if not namespace.is_file():raise ValueError('Composed namespace required')
    sources={}
    for name,digest in ORIGINALS.items():
        path=upstream/name
        if path.is_symlink() or sha(path)!=digest:raise ValueError('Pinned original changed: '+name)
        sources[name]=path.read_text()
    context=ROOT/CONTEXT
    if context.is_symlink() or sha(context)!=CONTEXT_SHA:raise ValueError('Pinned baseline Context changed')
    context_text=context.read_text()
    spec=importlib.util.spec_from_file_location('preinit_extract',ROOT/'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/rc/check_actual_1hz.py')
    extract=importlib.util.module_from_spec(spec);spec.loader.exec_module(extract)
    unix=sources['src/nvidia/arch/nvalloc/unix/src/unix_intr.c']
    linux=sources['kernel-open/nvidia/nv.c']
    linux_start=linux[linux.index('int nv_start_device('):linux.index('\n}',linux.index('int nv_start_device('))+2]
    register_anchor='rc = request_threaded_irq(nv->interrupt_line, nvidia_isr,'
    init_anchor='if (!rm_init_adapter(sp, nv))'
    if linux_start.count(register_anchor)!=1 or linux_start.count(init_anchor)!=1 or linux_start.index(register_anchor)>linux_start.index(init_anchor):
        raise ValueError('Original Linux controller registration-before-init order changed')
    private=extract.body(sources['src/nvidia/arch/nvalloc/unix/src/osinit.c'],'RmInitPrivateState')
    if private.count('os_mem_set(nvp, 0, sizeof(*nvp));')!=1 or private.count('NV_SET_NV_PRIV(pNv, nvp);')!=1 or private.index('os_mem_set(nvp, 0, sizeof(*nvp));')>private.index('NV_SET_NV_PRIV(pNv, nvp);'):
        raise ValueError('Original private zero-before-publication order changed')
    context_bodies={name:extract.body(context_text,name) for name in CONTEXT_BODIES}
    if args.context_source:
        selected=args.context_source.resolve(strict=True)
        if selected.is_symlink():raise ValueError('Selected Context symlink refused')
        selected_text=selected.read_text()
        if any(extract.body(selected_text,name)!=text for name,text in context_bodies.items()):
            raise ValueError('Selected Context changed an authenticated IRQ wrapper')
    else:selected=context;selected_text=context_text
    # Identical wrapper bodies must also be compiled against the selected
    # Context's actual storage: composed epochs can add fields to that struct.
    layout=selected_text[selected_text.index('struct nv_dma_device {'):selected_text.index('// One S540 adapter')]
    notice=unix[:unix.index('*/')+2]
    bodies=notice+'\n'+''.join(extract.body(unix,name) for name in ORIGINAL_BODIES)
    bodies+='\n'+''.join(context_bodies.values())
    sys.path.insert(0,str(ROOT/'builders'))
    import compile_nvidia_global_rm as original
    with tempfile.TemporaryDirectory(prefix='s540-preinit-irq-') as temporary:
        work=Path(temporary);(work/'actual-preinit-bodies.inc').write_text(bodies)
        (work/'actual-context-layout.inc').write_text(layout)
        if args.bridge_command:
            # Reuse a recorded original-ABI bridge command when supplied. Its
            # actual flags and digest remain in this control report; only the
            # selected namespace path changes to the current composition.
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
        else:
            bridge=original.original_bridge_flags(upstream,work/'profile',args.cc,namespace)
        host=[flag for flag in bridge if flag not in {'-msoft-float','-mno-red-zone','-mcmodel=kernel','-mno-mmx','-mno-sse','-mno-sse2','-mno-3dnow','-fno-pic'}]
        host+=['-fPIC','-mcmodel=small','-U__linux__','-U__linux']
        include=['-I'+str(work),'-I'+str(ROOT/'packages/nvidia-gsp-bootstrap/src'),
            '-I'+str(ROOT/'packages/nvidia-darwin-services/src')]
        results={};commands=[];environment=dict(os.environ)
        environment['ASAN_OPTIONS']=environment.get('ASAN_OPTIONS','')+':detect_leaks=0'
        for mode,sanitizers in [('plain',[]),('fatal-sanitized',['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'])]:
            command=[str(args.cc),*host,'-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-missing-field-initializers',*include,*sanitizers,str(HERE/'preinit_original.c'),'-o',str(work/mode)]
            commands.append(command)
            built=subprocess.run(command,capture_output=True,text=True,timeout=60)
            if built.returncode:raise RuntimeError(mode+' compile:\n'+built.stdout+built.stderr)
            ran=subprocess.run([str(work/mode)],capture_output=True,text=True,timeout=20,env=environment)
            if ran.returncode or ran.stderr:raise RuntimeError(mode+' execution:\n'+ran.stdout+ran.stderr)
            results[mode]=json.loads(ran.stdout)
        report={'format':1,'status':'passed','profile':'original-preinit-irq-wrapper-control','upstream_sha256':ORIGINALS,
            'baseline_context_sha256':CONTEXT_SHA,'selected_context_sha256':sha(selected),
            'source_bodies_sha256':hashlib.sha256(bodies.encode()).hexdigest(),'context_layout_sha256':hashlib.sha256(layout.encode()).hexdigest(),
            'namespace_sha256':sha(namespace),'fixture_sha256':sha(HERE/'preinit_original.c'),'checker_sha256':sha(HERE/'preinit_original.py'),
            'results':results,'commands':commands,'linux_registration_before_rm_init_adapter':True,'original_private_zero_before_publication':True,
            'mandatory_precondition':'actual nonnull nv->priv; rm_isr dereferences its flags before any null check',
            'controller_registration_execution':False,'hardware_irq_execution':False,'whole_irq_admission':False,
            'nvidia_layouts_and_context_layout':'complete original headers and exact selected Context struct',
            'dependencies':'explicit runtime/TLS allocator/HAL/spinlock fixtures; original private constructor not executed',
            'cpu_stack_switch_proved':False,'gpu_initialization_proved':False}
        if args.bridge_command:report['recorded_bridge_command_sha256']=sha(args.bridge_command)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--composition',type=Path,required=True);parser.add_argument('--context-source',type=Path)
    parser.add_argument('--cc',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--bridge-command',type=Path,help='Recorded original-ABI bridge command JSON; avoids repeated 1100-unit make dry-run parsing')
    print(json.dumps(check(parser.parse_args()),indent=2,sort_keys=True))
