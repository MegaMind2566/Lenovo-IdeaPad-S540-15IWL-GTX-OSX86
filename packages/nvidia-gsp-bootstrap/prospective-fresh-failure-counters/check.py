#!/usr/bin/env python3
"""Run complete kernel-branch Services and Session on explicit CPU endpoints."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import resource
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'packages/nvidia-gsp-bootstrap/cancellation'))
from prepare_wait_candidates import function_span


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module():
    spec = importlib.util.spec_from_file_location('s540_fresh_counters', HERE / 'prepare.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def dependencies(path):
    return {str(Path(name).resolve(strict=True)): sha(Path(name).resolve(strict=True))
            for name in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1])}


def fixture(project, device):
    first, last = function_span(device, 'unprotectedCpuid')
    body = device.index('{', first)
    device = device[:body] + '{\n    MemoryFixture::cpuid(leaf,subleaf,out.eax,out.ebx,out.ecx,out.edx);\n}' + device[last:]
    text = (HERE / 'tests/check_allocation.cpp.inc').read_text()
    for key, value in {
        'SERVICE_HEADER': str(project / 'packages/nvidia-device-transport/src/nv_device_services.h'),
        'COMMIT_HEADER': str(project / 'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure/S540NvidiaGspCommit.h'),
        'ALLOCATION_HEADER': str(project / 'packages/nvidia-gsp-bootstrap/prospective-fresh-failure-counters/S540DeviceAllocationDiagnostics.h'),
        'RECORD_HEADER': str(project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'),
        'SERVICES_BODY': device,
    }.items():
        marker = '@' + key + '@'
        require(text.count(marker) == 1, 'Exact allocation fixture token required: ' + key)
        text = text.replace(marker, value)
    return text


def run(args):
    require(args.host_control, 'Explicit --host-control required for synthetic resource controls')
    project = args.input_project.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(project) and
            not project.is_relative_to(output), 'Fresh nonoverlapping controls output required')
    prepare = module()
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_bytes())
    for name, digest in contract['unchanged_actual_dependencies'].items():
        require(sha(project / name) == digest, 'Actual unchanged dependency differs: ' + name)
    original = {name: (project / name).read_text() for name in prepare.INPUTS}
    selected = prepare.transforms(original)
    if args.composed_project:
        composed = args.composed_project.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected.items()),
                'Exact final fresh-counter source comparison failed')
        for name, source in prepare.COMPANIONS.items():
            require((composed / name).read_bytes() == source.read_bytes(), 'Final companion differs')
    refusal_count = 0
    for invalid in ({}, dict(original, unknown='invalid'),
                    dict(original, **{prepare.DEVICE: original[prepare.DEVICE] + '\n'}),
                    dict(original, **{prepare.CONTEXT: original[prepare.CONTEXT] + '\n'})):
        try:
            prepare.transforms(invalid)
        except ValueError:
            refusal_count += 1
        else:
            raise ValueError('Changed exact source accepted')
    files = [HERE / 'prepare.py', *(HERE / p for p in prepare.SOURCE_FILES),
             *prepare.COMPANIONS.values()]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in files}
    output.mkdir(parents=True)
    copy = output / 'project'
    shutil.copytree(project, copy)
    for name, text in selected.items():
        (copy / name).write_text(text)
    for name, source in prepare.COMPANIONS.items():
        path = copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    compiler = args.cxx.expanduser().absolute()  # Preserve lexical C++ alias.
    target = compiler.resolve(strict=True)
    require(target.is_file() and os.access(compiler, os.X_OK), 'Executable C++ compiler required')
    flags = ['-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-DKERNEL', '-pthread',
        '-I' + str(HERE / 'tests/mock'),
        '-I' + str(copy / 'packages/nvidia-device-transport/src'),
        '-I' + str(copy / 'packages/nvidia-gsp-bootstrap/prospective-dma-producer-closure')]
    variants, commands = {}, []

    def execute(label, device, sanitized=False, negative=False):
        unit = output / (label + '.cpp')
        unit.write_text(fixture(copy, device))
        session = copy / 'packages/nvidia-device-transport/src/S540NvidiaDeviceTransport.cpp'
        command = [str(compiler), *flags]
        if sanitized:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        objects, deps, logs = [], [], []
        for source, suffix in ((unit, 'services'), (session, 'session')):
            obj, dep = output / (label + '-' + suffix + '.o'), output / (label + '-' + suffix + '.d')
            argv = command + ['-MD', '-MF', str(dep), '-c', str(source), '-o', str(obj)]
            built = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            logs.append(built.stdout + built.stderr)
            require(built.returncode == 0, 'Whole actual Services/Session compile failed: ' + label + '\n' + built.stderr[-6000:])
            commands.append(argv)
            objects.append(obj)
            deps.append(dep)
        binary = output / label
        argv = command + [str(p) for p in objects] + ['-o', str(binary)]
        built = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        logs.append(built.stdout + built.stderr)
        (output / (label + '-compile.log')).write_text(''.join(logs))
        require(built.returncode == 0, 'Whole actual Services/Session link failed: ' + built.stderr[-6000:])
        commands.append(argv)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
        modes = [[], ['--concurrency'], ['--reserved'], *[['--stage-' + str(i)] for i in range(1, 7)]]
        runs, observations = [], {}
        for index, mode in enumerate(modes):
            result = subprocess.run([str(binary), *mode], capture_output=True, text=True, timeout=30, env=env)
            (output / (label + '-run-' + str(index) + '.log')).write_text(result.stdout + result.stderr)
            runs.append(dict(arguments=mode, returncode=result.returncode))
            if result.returncode:
                if negative: break
                raise ValueError('Actual allocation fixture failed: ' + label + '\n' + result.stderr[-6000:])
            observations[str(index)] = json.loads(result.stdout)
        row = dict(runs=runs, binary_sha256=sha(binary), sanitized=sanitized, negative_control=negative,
            dependency_sha256={k: v for p in deps for k, v in dependencies(p).items()})
        if negative:
            require(any(r['returncode'] for r in runs), 'Production allocation diagnostic mutant survived: ' + label)
            row['killed'] = True
        else:
            row.update(status='passed', cases=sum(r['cases'] for r in observations.values()),
                checks=sum(r['checks'] for r in observations.values()), modes=observations)
        variants[label] = row

    device = selected[prepare.DEVICE]
    execute('selected', device)
    execute('selected_sanitized', device, sanitized=True)
    require(variants['selected']['checks'] == variants['selected_sanitized']['checks'], 'Plain/sanitized observations differ')
    mutations = {
        'skip_returned_wrapper_guard': ('if (!record.originalReturned || record.originalInFlight)',
            'if (false && (!record.originalReturned || record.originalInFlight))'),
        'skip_master_thread_guard': ('if (!thread || thread != record.masterThread)',
            'if (false && (!thread || thread != record.masterThread))'),
        'lose_failure_count': ('observeAllocationIncrement(allocationObservation.failures);',
            'if (false) observeAllocationIncrement(allocationObservation.failures);'),
        'lose_attempt_count': ('observeAllocationIncrement(allocationObservation.attempts);',
            'if (false) observeAllocationIncrement(allocationObservation.attempts);'),
        'lose_entry_rejection': ('        recordAllocationEntryRejection();', '        if (false) recordAllocationEntryRejection();'),
        'wrap_lifetime_counters': ('while (count != ~NvU32(0) && !__atomic_compare_exchange_n(', 'while (!__atomic_compare_exchange_n('),
        'read_unpublished_first_tuple': ('if (captured.firstFailureState == 2U)', 'if (captured.firstFailureState != 0U)'),
        'overwrite_first_tuple': ('NvU32 empty = 0;', 'NvU32 empty = __atomic_load_n(&allocationObservation.firstFailureState, __ATOMIC_RELAXED);'),
        'lose_failure_page_bytes': ('failure.pageBytes = pageBytes;', 'failure.pageBytes = pageBytes ? 4096U : 4096U;'),
        'lose_failure_stage': ('failure.stage = stage;', 'failure.stage = stage ? static_cast<NvU32>(S540_ALLOC_FAILURE_SESSION) : 0U;'),
        'lose_unprotected_request': ('failure.unprotected = unprotected;', 'failure.unprotected = unprotected ? 0U : 0U;'),
        'lose_CPU_observation': ('failure.cpuObservedMask = cpu.observedMask;', 'failure.cpuObservedMask = cpu.observedMask ? 0U : 0U;'),
    }
    for name, (before, after) in mutations.items():
        require(device.count(before) == 1, 'Exact production mutation anchor changed: ' + name)
        execute('mutant_' + name, device.replace(before, after), negative=True)
    require({str(p.relative_to(ROOT)): sha(p) for p in files} == hashes, 'Profile helper changed during controls')
    report = dict(format=1, status='passed-actual-kernel-branch-allocation-diagnostics-controls',
        input_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in original.items()},
        output_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in selected.items()},
        source_file_sha256=hashes, exact_source_refusals=refusal_count, variants=variants, commands=commands,
        compiler_invocation_path=str(compiler), compiler_resolved_path=str(target), compiler_sha256=sha(target),
        kernel_primitives='explicit CPU-only ordinary/interrupt/logger/fatal endpoints, not Darwin',
        actual_Kernel_branch_services=True, actual_whole_Session=True,
        concurrent_observer_writers=8, counter_reads_independently_sampled=True,
        first_failure_publication="single reservation winner; immutable release/acquire tuple",
        CPU_observation='only private CPUID body replaced with explicit raw-register endpoint',
        sanitizer_policy=dict(address_and_undefined_fatal=True, leak_sanitizer_enabled=False,
            leak_sanitizer_reason='Explicit tracked endpoint resources reach zero; traced host leak inventory unavailable.'),
        native_Darwin_compilation=False, IOKit_execution=False, GPU_execution=False,
        physical_release_authorized=False, system_security_changed=False)
    (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-project', type=Path, required=True)
    p.add_argument('--composed-project', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cxx', type=Path, required=True)
    p.add_argument('--host-control', action='store_true')
    result = run(p.parse_args())
    print(json.dumps(dict(status=result['status'], cases=result['variants']['selected']['cases'],
        checks=result['variants']['selected']['checks'],
        sanitized_checks=result['variants']['selected_sanitized']['checks'],
        mutants_killed=sum(bool(v.get('killed')) for v in result['variants'].values()))))
