#!/usr/bin/env python3
"""Execute the successor's real record/services and extracted original bodies.

The original API/GPU tokens, GPU-manager resolution and runtime stack are
explicit endpoint fixtures. No fixture substitutes the binding, work admission,
queue dispatch, cancellation, allocation retention or original function bodies.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import prepare as candidate


def run(args):
    top = candidate.parent_guard()
    sys.path.insert(0, str(candidate.PARENT / 'original'))
    import common
    cc, cxx = common.compiler(str(args.cc)), common.compiler(str(args.cxx))
    identity = common.execution_identity(cc, cxx, args.host_control)
    result = candidate.prepare(args.upstream, args.v3_root, args.output)
    output = Path(args.output).resolve()
    original = common.original
    project, services = result['project'], result['services']
    namespace = candidate.namespace_guard(args.namespace)
    host_builder = candidate.load('gpu_binding_host_prepare',
        candidate.PARENT.parent / 'prospective-host-retention/prepare_heap_retention.py')
    host_root = output / 'verified-host-overlay'
    host_root.mkdir(exist_ok=True)
    host_builder.prepare(candidate.REPO, host_root)
    if args.host_overlay is not None:
        supplied = Path(args.host_overlay).resolve(strict=True)
        if supplied.name == 'packages':
            supplied = supplied.parent
        if top.inventory(supplied) != top.inventory(host_root):
            raise ValueError('Supplied Host overlay is not the exact frozen replay')
    host = host_root / 'packages'
    extract = candidate.load('gpu_binding_body_extract',
        candidate.PARENT / 'record/prepare_actual_original.py')
    evidence = extract.prepare(args.upstream, output,
        project / 'S540NvidiaGspFirstTransactionOriginal.c')
    body_file = output / 'actual-original-bodies.inc'
    bodies = body_file.read_text()
    upstream_worker = extract.body((Path(args.upstream) / candidate.OSAPI).read_text(),
        'RmExecuteWorkItem')
    bodies = candidate.once(bodies, upstream_worker,
        extract.body((result['source'] / candidate.OSAPI).read_text(), 'RmExecuteWorkItem'))
    for function in ['osAttachGpu', 'RmClearPrivateState', 'RmFreePrivateState']:
        bodies += '\n' + extract.body((result['source'] / candidate.OSINIT).read_text(), function)
    body_file.write_text(bodies)
    support = (candidate.PARENT / 'record/check_actual_original.c').read_text().split('static void healthy(void)')[0]
    support = candidate.once(support,
        '#include "../original/S540NvidiaGspFirstTransactionOriginal.h"',
        '#include "S540NvidiaGspFirstTransactionOriginal.h"')
    support = candidate.once(support, 'static OBJGPU gpu;', 'static OBJGPU gpu, replacement;\nstatic nv_priv_t priv;')
    support = candidate.once(support, 'static __thread NvU32 lockDepth,runtimeDepth;',
        'static __thread NvU32 lockDepth,runtimeDepth;\n'
        'static NvU32 apiOwned=1, gpuToken=1, registryCalls, mutationCalls;\n'
        'static NvU32 lookupReplacement, lookupMissing, holdBeforeWorker, workerReady, releaseWorker;\n'
        'static NvU32 skipAttach, attachRefusal, actionStatus, apiQueryCount;\n'
        'static NvU32 pauseCommit, commitReady, releaseCommit;\n'
        'static void *lastAllocatedWork;')
    support = candidate.once(support,
        'static OBJGPU *fixtureGpu(NvU32 instance){require(instance==0);return &gpu;}',
        'static OBJGPU *fixtureGpu(NvU32 instance){require(instance==0);return lookupMissing?NULL:(lookupReplacement?&replacement:&gpu);}')
    support = candidate.once(support,
        'static nv_state_t *fixtureNv(OBJGPU *g){require(g==&gpu);return &nv;}\n', '')
    support = candidate.once(support,
        'static NvU32 fixtureInstance(OBJGPU *g){require(g==&gpu);return 0;}',
        'static NvU32 fixtureInstance(OBJGPU *g){require(g==&gpu);return g->gpuInstance;}')
    support = candidate.once(support,
        'static void *fixtureAllocate(NvU64 bytes){return s540GlobalRmHostAllocateOriginal(bytes);}',
        'static void *fixtureAllocate(NvU64 bytes){lastAllocatedWork=s540GlobalRmHostAllocateOriginal(bytes);return lastAllocatedWork;}')
    support = candidate.once(support,
        '#undef NV_GET_NV_STATE\n#define NV_GET_NV_STATE fixtureNv\n', '')
    support = candidate.once(support, '#include "actual-original-bodies.inc"',
        '#include "binding-fixture-endpoints.inc"\n#include "actual-original-bodies.inc"\n'
        '#include "original-gpu-control.inc"')
    support = candidate.once(support,
        'require(s540Darwin_os_get_current_thread(&workThread)==NV_OK);rm_execute_work_item(&stack,data);',
        'require(s540Darwin_os_get_current_thread(&workThread)==NV_OK);\n'
        ' if(holdBeforeWorker){__atomic_store_n(&workerReady,1U,__ATOMIC_RELEASE);require(waitFor(&releaseWorker));}\n'
        ' rm_execute_work_item(&stack,data);')
    support = candidate.once(support,
        'require(!lockDepth&&!runtimeDepth);require(s540FirstTxnWorkOriginalReturned(&nv,NV_OK)==NV_OK);',
        'require(!lockDepth&&!runtimeDepth);actionStatus=s540FirstTxnWorkOriginalReturned(&nv,NV_OK);')
    support = candidate.once(support,
        'require(s540FirstTxnOriginalEnter(&nv)==NV_OK);',
        'require(s540FirstTxnOriginalEnter(&nv)==NV_OK);\n'
        ' NV_SET_NV_PRIV(&nv,&priv);replacement.gpuInstance=0;NV_SET_NV_STATE(&replacement,&nv);\n'
        ' if(!skipAttach)require(osAttachGpu(&gpu,&nv)==NV_OK);')
    (output / 'parent-support.inc').write_text(support)
    (output / 'original-gpu-control.inc').write_text((candidate.HERE / 'original-gpu.c.inc').read_text())
    bridge = original.original_bridge_flags(Path(args.upstream).resolve(), output / 'profile', cc,
        namespace)
    kernel_only = {'-msoft-float', '-mno-red-zone', '-mcmodel=kernel', '-mno-mmx',
        '-mno-sse', '-mno-sse2', '-mno-3dnow', '-fno-pic'}
    bridge = [flag for flag in bridge if flag not in kernel_only]
    if args.host_control:
        bridge += ['-U__linux__', '-U__linux']
    real = candidate.REPO / 'packages/nvidia-darwin-services/src'
    includes = ['-I', output, '-I', candidate.HERE, '-I', project, '-I', services,
        '-I', candidate.PARENT / 'record', '-I', candidate.PARENT / 'services',
        '-I', real, '-I', host / 'nvidia-global-rm/src',
        '-I', candidate.REPO / 'packages/nvidia-gsp-bootstrap/timers',
        '-I', candidate.REPO / 'packages/nvidia-device-transport/src',
        '-I', candidate.REPO / 'packages/nvidia-global-rm-crypto/src']
    units = [host / 'nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.c',
        host / 'nvidia-device-transport/src/S540NvidiaUnsupportedMemory.c',
        project / 'S540NvidiaGspFirstTransaction.c',
        candidate.PARENT / 'record/deps/S540NvidiaGspCancellation.c',
        candidate.HERE / 'check_controls.c', services / 'S540NvidiaGspTimersOriginal.c',
        host / 'nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp',
        services / 'S540NvidiaDarwinWork.cpp', services / 'S540NvidiaDarwinTimer.cpp',
        candidate.PARENT / 'services/S540NvidiaFirstTxnServices.cpp']
    units += [real / ('S540NvidiaDarwin' + name + '.cpp') for name in
        ['Runtime', 'Sync', 'Process', 'UserCopy', 'Platform', 'Check']]
    tracked = [*units, *[p for p in candidate.HERE.iterdir() if p.is_file()],
        output / 'actual-original-bodies.inc', output / 'actual-original-metadata.inc',
        output / 'parent-support.inc', output / 'original-gpu-control.inc',
        project / 'S540NvidiaGspFirstTransaction.h', namespace]
    frozen = {str(p): common.sha(p.read_bytes()) for p in tracked}
    environment = os.environ.copy()
    if args.host_control:
        environment['ASAN_OPTIONS'] = 'detect_leaks=0'
    commands = []
    dependencies = {}
    def execute(command, name):
        command = [str(x) for x in command]
        process = subprocess.run(command, text=True, capture_output=True,
            env=environment, timeout=60)
        (output / (name + '.log')).write_text(process.stdout + process.stderr)
        commands.append({'name': name, 'command': command, 'status': process.returncode})
        if process.returncode:
            raise RuntimeError(name + '\n' + process.stdout + process.stderr)
        return process.stdout
    results = {}
    for mode, sanitizer in [('plain', []), ('fatal-sanitizers',
            ['-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
             '-fno-omit-frame-pointer'])]:
        folder = output / mode
        folder.mkdir(exist_ok=True)
        flags = ([] if args.host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0'])
        flags += ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-ffunction-sections', '-fdata-sections', *sanitizer, *includes]
        objects = []
        for index, source in enumerate(units):
            target = folder / (str(index) + '-' + source.stem + '.o')
            objects.append(target)
            actual = source.name in ['check_controls.c', 'S540NvidiaGspTimersOriginal.c',
                'S540NvidiaUnsupportedMemory.c']
            command = [cc if source.suffix == '.c' else cxx, *flags,
                '-std=gnu11' if source.suffix == '.c' else '-std=c++17']
            if actual:
                command += [*bridge, '-fPIC', '-mcmodel=small', '-Wno-unused-parameter',
                    '-Wno-missing-field-initializers']
            dependency_file = target.with_suffix('.d')
            execute([*command, '-MD', '-MF', dependency_file, '-c', source, '-o', target],
                mode + '-' + source.stem)
            for filename in shlex.split(dependency_file.read_text().replace('\\\n', ' ').split(':', 1)[1]):
                dependency = Path(filename).resolve(strict=True)
                digest = common.sha(dependency.read_bytes())
                if dependencies.setdefault(str(dependency), digest) != digest:
                    raise ValueError('Control dependency changed during compilation: ' + str(dependency))
        binary = folder / 'check'
        execute([cxx, *flags, *objects,
            '-Wl,--gc-sections' if args.host_control else '-Wl,-dead_strip', '-o', binary], mode + '-link')
        control = json.loads(execute([binary], mode + '-run'))
        if control.get('status') != 'passed' or control.get('failures') or control.get('cases') != 13:
            raise ValueError('Successor control inventory failed')
        results[mode] = control
    for path, digest in frozen.items():
        if common.sha(Path(path).read_bytes()) != digest:
            raise ValueError('Control source changed: ' + path)
    for path, digest in dependencies.items():
        if common.sha(Path(path).read_bytes()) != digest:
            raise ValueError('Control compile dependency changed: ' + path)
    candidate.parent_guard()
    report = {'format': 1, 'status': 'passed', **identity, 'results': results,
        'input_sha256': frozen, 'actual_dependency_sha256': dependencies,
        'commands': commands, 'parent_body_evidence': evidence,
        'additional_complete_bodies': ['osAttachGpu', 'RmClearPrivateState', 'RmFreePrivateState'],
        'modified_original_body': 'RmExecuteWorkItem', 'actual_strong_record': True,
        'actual_queues_timers_host': True, 'kernel_execution': 'not_tested',
        'gpu_access': False, 'production_modified': False, 'hardware_admission': False,
        'original_entry_admission': False, 'full_lock_capability_refused': True,
        'source_manifest_sha256': common.sha((output / 'source-manifest.json').read_bytes())}
    (output / 'control-results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['upstream', 'namespace', 'output', 'cc', 'cxx']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--host-overlay', type=Path)
    parser.add_argument('--v3-root', type=Path)
    parser.add_argument('--host-control', action='store_true')
    report = run(parser.parse_args())
    print(json.dumps({'status': report['status'], 'results': report['results'],
        'hardware_admission': False}))
