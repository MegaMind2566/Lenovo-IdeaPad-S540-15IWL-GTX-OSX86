#!/usr/bin/env python3
"""Compile the typed helper and run its exact production body with original HAL callers."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ORIGINALS = {
    'src/nvidia/src/kernel/gpu/intr/intr.c': '6f3896ff07219abe6fd6616ca53ea176898a725fbd2e1fe0991057055213b39b',
    'src/nvidia/arch/nvalloc/unix/src/unix_intr.c': '952e1ccb8b3214c83cfb54748324131900eaff68986169ad7e794be29ef86819',
}


def check(args):
    upstream = args.upstream.resolve(strict=True)
    composition = args.composition.resolve(strict=True)
    namespace = composition/'S540ComposedNamespace.h'
    record = composition/'project/packages/nvidia-gsp-bootstrap/prospective-first-transaction/record'
    if not namespace.is_file() or not record.is_dir():
        raise ValueError('Complete source-only composition with namespace required')
    for name, expected in ORIGINALS.items():
        path = upstream/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Pinned original interrupt body changed: '+name)
    spec = importlib.util.spec_from_file_location('irq_actual_1hz', HERE/'check_actual_1hz.py')
    extract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extract)
    sys.path.insert(0, str(ROOT/'builders'))
    import compile_nvidia_global_rm as original
    own = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in HERE.iterdir() if path.is_file() and path.suffix in {'.c', '.h', '.py'}}
    with tempfile.TemporaryDirectory(prefix='s540-irq-original-') as temporary:
        work = Path(temporary)
        intr_source = (upstream/next(iter(ORIGINALS))).read_text()
        unix_source = (upstream/list(ORIGINALS)[1]).read_text()
        notice = intr_source[:intr_source.index('*/')+2]
        bodies = notice+'\n'+''.join(extract.body(intr_source, name)
            for name in ['intrSetIntrEn_IMPL', 'intrGetIntrEn_IMPL'])
        bodies += ''.join(extract.body(unix_source, name)
            for name in ['osEnableInterrupts', 'osDisableInterrupts'])
        (work/'actual-mask-bodies.inc').write_text(bodies)
        bridge = original.original_bridge_flags(upstream, work/'profile', args.cc, namespace)
        include = ['-I'+str(work), '-I'+str(HERE), '-I'+str(record),
            '-I'+str(ROOT/'packages/nvidia-gsp-bootstrap/prospective-rm-lock-ownership')]
        defines = ['-DS540_NVIDIA_NO_LEGACY_RM_SEMAPHORE=1', '-DS540_NVIDIA_IRQ_CALLBACK_CLOSURE=1']
        host_flags = [flag for flag in bridge if flag not in {'-msoft-float', '-mno-red-zone',
            '-mcmodel=kernel', '-mno-mmx', '-mno-sse', '-mno-sse2', '-mno-3dnow', '-fno-pic'}]
        host_flags += ['-fPIC', '-mcmodel=small', '-U__linux__', '-U__linux']
        environment = dict(os.environ)
        environment['ASAN_OPTIONS'] = environment.get('ASAN_OPTIONS', '')+':detect_leaks=0'
        results = {}
        commands = []
        for mode, sanitize in [('plain', []), ('fatal-sanitized',
                ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])]:
            command = [str(args.cc), *host_flags, '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-Wno-missing-field-initializers', *defines, *include, *sanitize,
                str(HERE/'check_irq_original.c'), '-o', str(work/mode)]
            commands.append(command)
            built = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if built.returncode:
                raise RuntimeError(mode+' compile failed:\n'+built.stdout+built.stderr)
            ran = subprocess.run([str(work/mode)], capture_output=True, text=True,
                timeout=20, env=environment)
            if ran.returncode or ran.stderr:
                raise RuntimeError(mode+' execution failed:\n'+ran.stdout+ran.stderr)
            results[mode] = json.loads(ran.stdout)
        kernel = [str(args.cc), *bridge, '-target', 'x86_64-apple-macos15',
            '-mkernel', '-DKERNEL', '-D__KERNEL__', '-Werror', '-Wframe-larger-than=4096',
            '-Werror=frame-larger-than', *defines, *include, '-c',
            str(HERE/'S540NvidiaIrqOriginal.c'), '-o', str(work/'production.o')]
        compiled = subprocess.run(kernel, capture_output=True, text=True, timeout=60)
        if compiled.returncode:
            raise RuntimeError('Typed kernel compile failed:\n'+compiled.stdout+compiled.stderr)
        definitions, imports, sections = original.macho_symbols(work/'production.o')
        if definitions != {'s540FirstTxnIrqMaskHardware', 's540FirstTxnDrainQueued1Hz'}:
            raise ValueError('Typed helper exact strong definitions changed')
        report = {'status': 'passed', 'profile': 'typed-original-irq-pending-helper',
            'results': results, 'original_source_sha256': ORIGINALS,
            'candidate_sha256': own, 'namespace_sha256': hashlib.sha256(namespace.read_bytes()).hexdigest(),
            'original_layout_headers_used': True, 'complete_original_mask_enable_bodies': 4,
            'kernel_target_compilation': {'definitions': sorted(definitions), 'imports': sorted(imports),
                'sections': sections, 'object_sha256': hashlib.sha256((work/'production.o').read_bytes()).hexdigest()},
            'strong_record_and_lock_adapters': 'explicit typed fixtures in CPU controls',
            'hardware_hals': 'explicit fixtures', 'native_apple_execution': False,
            'hardware_admission': False, 'dma_stop_receipt': False, 'final_release_receipt': False}
    for name, expected in own.items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Helper input changed during controls: '+name)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--composition', type=Path, required=True)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    print(json.dumps(check(parser.parse_args()), indent=2, sort_keys=True))
