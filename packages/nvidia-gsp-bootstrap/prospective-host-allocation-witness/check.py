#!/usr/bin/env python3
"""Execute actual Host/facade producer and allocation observations on Linux CPU."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def actual_function(text, name):
    first, last = prepare.function_span(text, name)
    return text[text.rfind('\n', 0, first) + 1:last] + '\n'


def policy_checks(original, selected):
    old, new = original[prepare.HOST], selected[prepare.HOST]
    for name in ('s540GlobalRmRecordUnavailable', 'recordUnavailableAt',
                 's540GlobalRmReadUnavailableDiagnostics', 'freeTracked',
                 's540GlobalRmHostSnapshot', 's540GlobalRmHostShutdown'):
        require(actual_function(old, name) == actual_function(new, name),
                'Existing Host policy or B9 observer changed: ' + name)
    failure = actual_function(new, 'allocationFailure').replace(
        'NvU32 site, NvU64 bytes, bool original)', 'NvU32 site)').replace(
        '    observeHostAllocation(status, site, bytes, original);\n', '')
    require(failure == actual_function(old, 'allocationFailure'),
            'Original allocation failure publication changed')
    allocation = actual_function(new, 'allocateTracked')
    require(allocation.count(', bytes, original)') == 10, 'Exactly ten actual allocation failure branches required')
    require(allocation.replace(', bytes, original)', ')') == actual_function(old, 'allocateTracked'),
            'Original Host allocation guards, backing or counters changed')
    before, after = actual_function(original[prepare.OS], 'os_alloc_mem'), actual_function(selected[prepare.OS], 'os_alloc_mem')
    after = after.replace('s540GlobalRmRecordUnavailableProducer(CALL_ALLOC, S540_HOST_ALLOCATION_PRODUCER_OS_ALLOC_CONTEXT);',
                          's540GlobalRmRecordUnavailable(CALL_ALLOC);')
    require(before == after, 'Original Os allocation context guard or status changed')
    initialize = actual_function(selected[prepare.CONTEXT], 's540GspContextInitializeAdapter')
    require(initialize == actual_function(original[prepare.CONTEXT], 's540GspContextInitializeAdapter'),
            'Actual initialize-adapter function changed')
    returned = '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);'
    call = 's540LogRetainedProfileFailure(context, profile);'
    require(initialize.count(returned) == initialize.count(call) == 1 and
            initialize.index(returned) < initialize.index(call), 'Actual post-wrapper failure boundary changed')
    failure = actual_function(selected[prepare.CONTEXT], 's540LogRetainedProfileFailure')
    require(failure.count('    s540LogHostAllocationWitness(context);\n') == 1,
            'Exactly one post-wrapper Host allocation logger required')
    require(failure.replace('    s540LogHostAllocationWitness(context);\n', '') ==
            actual_function(original[prepare.CONTEXT], 's540LogRetainedProfileFailure'),
            'Existing failure logger changed')


def actual_os_body(text):
    start = text.index('enum {\n    CALL_ALLOC,')
    end = text.index('#define STATUS_BRIDGE', start)
    return text[start:end] + '\n' + actual_function(text, 'os_alloc_mem')


def run(args):
    require(args.host_control, 'Explicit --host-control required for typed CPU endpoints')
    require(sys.platform.startswith('linux'), 'Linux CPU linker malloc interposition required by actual stage10 control')
    project = args.input_project.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(project) and
            not project.is_relative_to(output), 'Fresh nonoverlapping output required')
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_bytes())
    require(sha(project / RECORD) == contract['actual_record_header_sha256'], 'Actual record header differs')
    original = {name: (project / name).read_text() for name in prepare.INPUTS}
    selected = prepare.transforms(original)
    policy_checks(original, selected)
    if args.composed_project:
        composed = args.composed_project.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected.items()),
                'Final Host allocation diagnostic inputs differ from actual transforms')
        require(all((composed / name).read_bytes() == path.read_bytes()
                    for name, path in prepare.COMPANIONS.items()), 'Final Host allocation companion differs')
    helper = actual_function(selected[prepare.CONTEXT], 's540LogHostAllocationWitness')
    output.mkdir(parents=True)
    copy = output / 'project'
    shutil.copytree(project, copy)
    for name, source in prepare.COMPANIONS.items():
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    for name, text in selected.items():
        (copy / name).write_text(text)
    files = [HERE / 'prepare.py', *(HERE / p for p in prepare.SOURCE_FILES), *prepare.COMPANIONS.values()]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in files}
    compilers = {key: path.expanduser().absolute() for key, path in (('host', args.cxx), ('context', args.cc))}
    compiler_bindings = {name: dict(invocation_path=str(path), resolved_path=str(path.resolve(strict=True)),
                                   sha256=sha(path.resolve(strict=True))) for name, path in compilers.items()}
    includes = [copy / 'packages', copy / 'packages/nvidia-global-rm/src',
        copy / 'packages/nvidia-global-rm-crypto/src', copy / 'packages/nvidia-device-transport/src',
        copy / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        copy / prepare.DIRECTORY, HERE / 'tests']
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    variants, commands = {}, []

    def execute(label, component, body, *, sanitized=False, negative=False, facade=None):
        work = output / label
        work.mkdir()
        host = component == 'host'
        if host:
            (work / 'actual-host.cpp').write_text(body)
            (work / 'actual-acpi.c').write_text(selected[prepare.ACPI] if facade is None else facade)
            (work / 'actual-os.inc').write_text(actual_os_body(selected[prepare.OS]))
        else:
            (work / 'actual-context.inc').write_text(body)
        unit = work / ('control.cpp' if host else 'control.c')
        unit.write_bytes((HERE / ('tests/check_host.cpp.inc' if host else 'tests/check_context.c.inc')).read_bytes())
        binary, dependency = work / 'control', work / 'control.d'
        command = [str(compilers[component]), '-std=c++17' if host else '-std=c11',
            '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            *[part for directory in includes for part in ('-I', str(directory))], '-I', str(work)]
        if host:
            command += ['-pthread', '-Wl,--wrap=malloc']
        if sanitized:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command += ['-MD', '-MF', str(dependency), str(unit), '-o', str(binary)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=120, env=environment)
        (work / 'compile.log').write_text(built.stdout + built.stderr)
        require(built.returncode == 0, 'Actual Host allocation control compilation failed: ' + label + '\n' + built.stderr[-7000:])
        commands.append(command)
        bindings = {str(Path(name).resolve(strict=True)): sha(Path(name).resolve(strict=True))
            for name in shlex.split(dependency.read_text().replace('\\\n', ' ').split(':', 1)[1])}
        required = [copy / prepare.DIRECTORY / 'S540HostAllocationDiagnostics.h']
        if host:
            required += [copy / RECORD, copy / 'packages/nvidia-global-rm/src/S540NvidiaGlobalRm.h',
                copy / 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHostRetention.h', HERE / 'tests/nv.h']
        require(all(str(path.resolve()) in bindings for path in required),
                'Actual typed header absent from CPU dependencies: ' + label)
        results = []
        for scenario in (range(24) if host else [None]):
            result = subprocess.run([str(binary), *([] if scenario is None else [str(scenario)])],
                capture_output=True, text=True, timeout=45, env=environment)
            (work / ('run-' + str(scenario) + '.log')).write_text(result.stdout + result.stderr)
            if negative:
                if result.returncode != 0:
                    results.append(dict(scenario=scenario, returncode=result.returncode, killed=True))
                    break
            else:
                require(result.returncode == 0, 'Actual Host allocation CPU run failed: ' + label + '\n' + result.stderr[-6000:])
                results.append(json.loads(result.stdout))
        if negative:
            require(results and results[-1].get('killed'), 'Actual Host allocation mutant survived: ' + label)
        variants[label] = dict(component=component, sanitized=sanitized, negative_control=negative,
            killed=negative, binary_sha256=sha(binary), dependency_sha256=bindings,
            cases=sum(row.get('cases', 0) for row in results),
            checks=sum(row.get('checks', 0) for row in results), results=results)

    execute('host-selected', 'host', selected[prepare.HOST])
    execute('host-selected-sanitized', 'host', selected[prepare.HOST], sanitized=True)
    execute('context-selected', 'context', helper)
    execute('context-selected-sanitized', 'context', helper, sanitized=True)
    for component in ('host', 'context'):
        require(variants[component + '-selected']['checks'] == variants[component + '-selected-sanitized']['checks'],
                'Plain and fatal-sanitized check counts differ')
    mutations = {
        'host-lose-ordinary-guard': ('reader',
            'if (!exactNv || !out) return NV_ERR_INVALID_ARGUMENT;\n    if (!s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_STATE;',
            'if (!exactNv || !out) return NV_ERR_INVALID_ARGUMENT;\n    if (false) return NV_ERR_INVALID_STATE;'),
        'host-weaken-return-boundary': ('reader', 'if (!record.originalReturned || record.originalInFlight) return NV_ERR_NOT_READY;',
            'if (!record.originalReturned && record.originalInFlight) return NV_ERR_NOT_READY;'),
        'host-producer-before-refusal': ('host',
            '    s540GlobalRmRecordUnavailable(service);\n    observeHostProducer(service, producer);',
            '    observeHostProducer(service, producer);\n    s540GlobalRmRecordUnavailable(service);'),
        'host-read-pending-producer': ('host', 'if (captured.producerFirstState == 2U)', 'if (captured.producerFirstState != 0U)'),
        'host-read-pending-allocation': ('host', 'if (captured.allocationFirstState == 2U)', 'if (captured.allocationFirstState != 0U)'),
        'host-lose-first-bytes': ('host', 'hostAllocationObservation.allocationFirstBytes = bytes;',
            '(void)bytes; hostAllocationObservation.allocationFirstBytes = 0ULL;'),
        'host-lose-first-status': ('host', 'hostAllocationObservation.allocationFirstStatus = status;',
            '(void)status; hostAllocationObservation.allocationFirstStatus = 0U;'),
        'host-lose-producer-service': ('host', 'hostAllocationObservation.producerFirstService = service;',
            '(void)service; hostAllocationObservation.producerFirstService = 0U;'),
        'host-wrap-saturated-counter': ('increment', 'value != ~0U && !__atomic_compare_exchange_n',
            'true && !__atomic_compare_exchange_n'),
        'host-lose-original-flag': ('host', 'hostAllocationObservation.allocationFirstOriginal = original ? 1U : 0U;',
            '(void)original; hostAllocationObservation.allocationFirstOriginal = 0U;'),
        'host-lose-allocation-stage-mask': ('host', 'NvU32(1U) << (stage - 1U),', 'NvU32(0U) << (stage - 1U),'),
        'host-lose-producer-mask': ('host', 'NvU32(1U) << producer,', 'NvU32(0U) << producer,'),
        'acpi-wrong-producer': ('acpi', 'unavailable(__func__, S540_HOST_ALLOCATION_PRODUCER_ACPI_DSM)',
            'unavailable(__func__, S540_HOST_ALLOCATION_PRODUCER_ACPI_DOD)'),
        'context-lose-first-allocation-status': ('context', 'allocationFirst ? diagnostic.allocationFirstStatus : 0U,',
            'allocationFirst ? 0U : 0U,'),
        'context-invent-first-producer': ('context', '(diagnostic.observedMask & S540_HOST_ALLOCATION_DIAG_PRODUCER_FIRST) != 0U;',
            '(diagnostic.observedMask | S540_HOST_ALLOCATION_DIAG_PRODUCER_FIRST) != 0U;'),
        'context-lose-os-alloc-count': ('context', 'diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_OS_ALLOC_CONTEXT],',
            'diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_UNKNOWN],'),
    }
    for name, (component, before, after) in mutations.items():
        body = (actual_function(selected[prepare.HOST], 'hostAllocationIncrement')
                if component == 'increment' else actual_function(selected[prepare.HOST], 's540GlobalRmReadAllocationDiagnostics')
                if component == 'reader' else selected[prepare.HOST] if component == 'host'
                else selected[prepare.ACPI] if component == 'acpi' else helper)
        require(body.count(before) == 1, 'Exact negative mutation anchor changed: ' + name)
        if component in ('reader', 'increment'):
            require(selected[prepare.HOST].count(body) == 1, 'Actual reader span differs')
            execute('mutant-' + name, 'host', selected[prepare.HOST].replace(body, body.replace(before, after)), negative=True)
        elif component == 'acpi':
            execute('mutant-' + name, 'host', selected[prepare.HOST], facade=body.replace(before, after), negative=True)
        else:
            execute('mutant-' + name, component, body.replace(before, after), negative=True)
    require({str(p.relative_to(ROOT)): sha(p) for p in files} == hashes, 'Host allocation source changed during controls')
    report = dict(format=1, status='passed-actual-host-allocation-and-producer-controls',
        exact_input_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in original.items()},
        exact_output_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in selected.items()},
        source_file_sha256=hashes, variants=variants, commands=commands, compilers=compiler_bindings,
        actual_whole_transformed_host=True, actual_whole_transformed_ACPI_facade=True,
        actual_Os_enum_MARK_and_allocation_body=True, actual_inserted_C_logger=True,
        actual_initialize_adapter_unchanged=True, actual_B9_unavailable_observer_unchanged=True,
        actual_strong_record_executed=False, actual_RM_execution=False, kernel_execution=False,
        endpoints='Explicit typed ordinary/thread/exact-nv/record snapshot/capture/free-permit/crypto/memory/nv.h CPU endpoints',
        linux_existing_CPU_backend_malloc_interposition=True, concurrent_writers=8, events_per_writer=1000,
        physical_release_authorized=False, production_reset_api=False, new_wire_protocol=False,
        sanitizer_policy=dict(address_and_undefined_fatal=True, leak_sanitizer_enabled=False,
            leak_sanitizer_reason='Denied Host allocations intentionally remain retained until CPU fixture process exit.'))
    (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-project', type=Path, required=True)
    parser.add_argument('--composed-project', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', type=Path, required=True)
    parser.add_argument('--cc', type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    result = run(parser.parse_args())
    selected = [v for v in result['variants'].values() if not v['negative_control'] and not v['sanitized']]
    print(json.dumps(dict(status=result['status'], cases=sum(v['cases'] for v in selected),
        checks=sum(v['checks'] for v in selected), sanitized_checks=sum(v['checks']
        for v in result['variants'].values() if not v['negative_control'] and v['sanitized']),
        mutants_killed=sum(bool(v['killed']) for v in result['variants'].values()))))
