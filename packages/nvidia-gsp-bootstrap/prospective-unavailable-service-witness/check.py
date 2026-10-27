#!/usr/bin/env python3
"""Execute actual transformed Host and inserted C diagnostic code on CPU."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
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


def run(args):
    require(args.host_control, 'Explicit --host-control required for synthetic typed endpoints')
    project = args.input_project.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(project) and
            not project.is_relative_to(output), 'Fresh nonoverlapping output required')
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_bytes())
    require(sha(project / RECORD) == contract['actual_record_header_sha256'], 'Actual record header differs')
    original = {name: (project / name).read_text() for name in prepare.INPUTS}
    selected = prepare.transforms(original)
    if args.composed_project:
        composed = args.composed_project.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected.items()),
                'Final unavailable diagnostic sources differ from actual transforms')
        for name, path in prepare.COMPANIONS.items():
            require((composed / name).read_bytes() == path.read_bytes(), 'Final unavailable companion differs')
    # Explicit exact-source control of the real logging boundary. Existing
    # initialize-adapter code is deliberately unchanged by this profile.
    context = selected[prepare.CONTEXT]
    original_initialize = actual_function(original[prepare.CONTEXT], 's540GspContextInitializeAdapter')
    initialize = actual_function(context, 's540GspContextInitializeAdapter')
    require(initialize == original_initialize, 'Actual initialize-adapter body changed')
    returned = '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);'
    failure_call = 's540LogRetainedProfileFailure(context, profile);'
    require(initialize.count(returned) == initialize.count(failure_call) == 1 and
            initialize.index(returned) < initialize.index(failure_call), 'Post-wrapper failure call boundary changed')
    failure = actual_function(context, 's540LogRetainedProfileFailure')
    require(failure.count('s540LogUnavailableServiceWitness(context);') == 1,
            'Exactly one post-wrapper unavailable logger required')
    helper = actual_function(context, 's540LogUnavailableServiceWitness')
    output.mkdir(parents=True)
    copy = output / 'project'
    shutil.copytree(project, copy)
    for name, source in prepare.COMPANIONS.items():
        path = copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
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
        copy / prepare.DIRECTORY]
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    variants, commands = {}, []

    def execute(label, component, source, *, sanitized=False, negative=False):
        work = output / label
        work.mkdir()
        host = component == 'host'
        (work / ('actual-host.cpp' if host else 'actual-context.inc')).write_text(source)
        unit = work / ('control.cpp' if host else 'control.c')
        unit.write_bytes((HERE / ('tests/check_host.cpp.inc' if host else 'tests/check_context.c.inc')).read_bytes())
        binary, dependency = work / 'control', work / 'control.d'
        command = [str(compilers[component]), '-std=c++17' if host else '-std=c11',
            '-O1', '-g', '-Wall', '-Wextra', '-Werror',
            *[part for directory in includes for part in ('-I', str(directory))], '-I', str(work)]
        if host:
            command += ['-pthread']
        if sanitized:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command += ['-MD', '-MF', str(dependency), str(unit), '-o', str(binary)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=120, env=environment)
        (work / 'compile.log').write_text(built.stdout + built.stderr)
        require(built.returncode == 0, 'Actual diagnostic CPU compilation failed: ' + label + '\n' + built.stderr[-7000:])
        commands.append(command)
        bindings = {str(Path(name).resolve(strict=True)): sha(Path(name).resolve(strict=True))
            for name in shlex.split(dependency.read_text().replace('\\\n', ' ').split(':', 1)[1])}
        required = [prepare.DIRECTORY + '/S540HostUnavailableDiagnostics.h']
        if host:
            required += [RECORD, 'packages/nvidia-global-rm/src/S540NvidiaGlobalRm.h',
                         'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHostRetention.h']
        require(all(str((copy / name).resolve()) in bindings for name in required),
                'Actual typed source header omitted from CPU dependencies: ' + label)
        results = []
        for scenario in (range(16) if host else [None]):
            result = subprocess.run([str(binary), *([] if scenario is None else [str(scenario)])],
                capture_output=True, text=True, timeout=30, env=environment)
            (work / ('run-' + str(scenario) + '.log')).write_text(result.stdout + result.stderr)
            if negative:
                if result.returncode != 0:
                    results.append(dict(scenario=scenario, returncode=result.returncode, killed=True))
                    break
            else:
                require(result.returncode == 0, 'Actual diagnostic CPU run failed: ' + label + '\n' + result.stderr[-6000:])
                results.append(json.loads(result.stdout))
        if negative:
            require(results and results[-1].get('killed'), 'Actual diagnostic mutant survived: ' + label)
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
                'Plain and fatal-sanitized control check counts differ')
    mutations = {
        'host-lose-ordinary-guard': ('host',
            'if (!exactNv || !out) return NV_ERR_INVALID_ARGUMENT;\n    if (!s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_STATE;',
            'if (!exactNv || !out) return NV_ERR_INVALID_ARGUMENT;\n    if (false) return NV_ERR_INVALID_STATE;'),
        'host-weaken-return-boundary': ('host', 'if (!record.originalReturned || record.originalInFlight) return NV_ERR_NOT_READY;',
            'if (!record.originalReturned && record.originalInFlight) return NV_ERR_NOT_READY;'),
        'host-read-pending-first-tuple': ('host', 'if (captured.firstState == 2U)', 'if (captured.firstState != 0U)'),
        'host-lose-first-service': ('host', 'hostUnavailableObservation.firstService = service;',
            '(void)service; hostUnavailableObservation.firstService = 0U;'),
        'host-lose-free-permit-site': ('host', 'recordUnavailableAt(0, S540_HOST_UNAVAILABLE_FREE_PERMIT)',
            'recordUnavailableAt(0, S540_HOST_UNAVAILABLE_EXTERNAL)'),
        'host-double-original-aggregate': ('host', 'current + 1U, false,', 'current + 2U, false,'),
        'host-lose-site-mask': ('host', 'NvU32(1U) << site,', 'NvU32(0U) << site,'),
        'context-lose-first-site': ('context', 'firstObserved ? diagnostic.firstSite : 0U,',
            'firstObserved ? 0U : 0U,'),
        'context-invent-first-observation': ('context', '(diagnostic.observedMask & S540_HOST_UNAVAILABLE_DIAG_FIRST) != 0U;',
            '(diagnostic.observedMask | S540_HOST_UNAVAILABLE_DIAG_FIRST) != 0U;'),
        'context-lose-free-permit-count': ('context', 'diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_FREE_PERMIT],',
            'diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_EXTERNAL],'),
    }
    for name, (component, before, after) in mutations.items():
        body = selected[prepare.HOST] if component == 'host' else helper
        require(body.count(before) == 1, 'Exact negative diagnostic mutation anchor changed: ' + name)
        execute('mutant-' + name, component, body.replace(before, after), negative=True)
    require({str(p.relative_to(ROOT)): sha(p) for p in files} == hashes, 'Diagnostic source changed during controls')
    report = dict(format=1, status='passed-actual-unavailable-service-witness-controls',
        exact_input_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in original.items()},
        exact_output_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in selected.items()},
        source_file_sha256=hashes, variants=variants, commands=commands, compilers=compiler_bindings,
        actual_whole_transformed_host_cpp=True, actual_inserted_C_helper=True,
        actual_initialize_adapter_unchanged=True, actual_strong_record_executed=False,
        endpoints='explicit typed ordinary/thread/exact-nv/record snapshot/Host free-permit/crypto/memory CPU endpoints',
        concurrent_writers=8, events_per_concurrent_writer=1000,
        kernel_execution=False, actual_RM_execution=False, physical_release_authorized=False,
        production_reset_api=False, new_wire_protocol=False,
        sanitizer_policy=dict(address_and_undefined_fatal=True, leak_sanitizer_enabled=False,
            leak_sanitizer_reason='Retained Host fixture intentionally leaves denied allocations until process exit.'))
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
        checks=sum(v['checks'] for v in selected),
        sanitized_checks=sum(v['checks'] for v in result['variants'].values()
            if not v['negative_control'] and v['sanitized']),
        mutants_killed=sum(bool(v['killed']) for v in result['variants'].values()))))
