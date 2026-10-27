#!/usr/bin/env python3
"""Execute actual post-wrapper C diagnostic helpers with typed CPU endpoints."""
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
HELPERS = ('s540LogFreshServiceCounters', 's540LogAllocationCounters',
           's540LogAttachFailureWitness', 's540LogRetainedProfileFailure')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def actual_function(text, name):
    first, last = prepare.function_span(text, name)
    return text[text.rfind('\n', 0, first) + 1:last] + '\n'


def run(args):
    require(args.host_control, 'Explicit --host-control required for synthetic endpoint controls')
    project = args.input_project.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(project) and
            not project.is_relative_to(output), 'Fresh nonoverlapping output required')
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_bytes())
    require(sha(project / RECORD) == contract['actual_record_header_sha256'], 'Actual record C header differs')
    require(sha(project / contract['witness_header']) == contract['witness_header_sha256'], 'Actual witness C header differs')
    original = {name: (project / name).read_text() for name in prepare.INPUTS}
    selected = prepare.transforms(original)
    if args.composed_project:
        composed = args.composed_project.resolve(strict=True)
        require(all((composed / name).read_text() == text for name, text in selected.items()),
                'Final counter sources differ from actual transform')
        require(sha(composed / contract['witness_header']) == contract['witness_header_sha256'],
                'Final witness companion differs')
    output.mkdir(parents=True)
    copy = output / 'project'
    shutil.copytree(project, copy)
    for name, source in prepare.COMPANIONS.items():
        path = copy / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
    for name, text in selected.items():
        (copy / name).write_text(text)
    context = selected[prepare.CONTEXT]
    helper = '\n'.join(actual_function(context, name) for name in HELPERS)
    initialize = actual_function(context, 's540GspContextInitializeAdapter')
    returned = '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);'
    call = 's540LogRetainedProfileFailure(context, profile);'
    require(initialize.count(returned) == initialize.count(call) == 1 and
            initialize.index(returned) < initialize.index(call), 'Real post-wrapper call boundary changed')
    files = [HERE / 'prepare.py', *(HERE / p for p in prepare.SOURCE_FILES), *prepare.COMPANIONS.values()]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in files}
    compiler = args.cc.expanduser().absolute()
    target = compiler.resolve(strict=True)
    include_dirs = [copy / 'packages', copy / 'packages/nvidia-gsp-bootstrap/src',
        copy / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        copy / 'packages/nvidia-gsp-bootstrap/prospective-fresh-failure-counters',
        copy / 'packages/nvidia-gsp-bootstrap/prospective-attach-failure-witness']
    flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
        *[part for directory in include_dirs for part in ('-I', str(directory))]]
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    variants, commands = {}, []

    def execute(label, body, sanitized=False, negative=False):
        work = output / label
        work.mkdir()
        (work / 'actual-context-failure.inc').write_text(body)
        (work / 'actual-initialize-adapter.inc').write_text(initialize)
        unit = work / 'control.c'
        unit.write_bytes((HERE / 'tests/check_context.c.inc').read_bytes())
        binary, dependency = work / 'control', work / 'control.d'
        command = [str(compiler), *flags]
        if sanitized:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command += ['-I', str(work), '-MD', '-MF', str(dependency), str(unit), '-o', str(binary)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=120, env=environment)
        (work / 'compile.log').write_text(built.stdout + built.stderr)
        require(built.returncode == 0, 'Actual C diagnostic fixture compilation failed: ' + label + '\n' + built.stderr[-6000:])
        commands.append(command)
        bindings = {str(Path(name).resolve(strict=True)): sha(Path(name).resolve(strict=True))
            for name in shlex.split(dependency.read_text().replace('\\\n', ' ').split(':', 1)[1])}
        for name in (RECORD, contract['witness_header'],
                     prepare.DIRECTORY + '/S540DeviceAllocationDiagnostics.h'):
            require(str((copy / name).resolve()) in bindings, 'Actual typed diagnostic header not compiled: ' + name)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30, env=environment)
        (work / 'run.log').write_text(result.stdout + result.stderr)
        row = dict(returncode=result.returncode, binary_sha256=sha(binary), dependency_sha256=bindings,
                   sanitized=sanitized, negative_control=negative)
        if negative:
            require(result.returncode != 0, 'Actual C diagnostic mutant survived: ' + label)
            row['killed'] = True
        else:
            require(result.returncode == 0, 'Actual C diagnostic fixture failed: ' + label + '\n' + result.stderr[-6000:])
            row.update(json.loads(result.stdout))
        variants[label] = row

    execute('selected', helper)
    execute('selected_sanitized', helper, sanitized=True)
    require(variants['selected']['checks'] == variants['selected_sanitized']['checks'], 'Plain/sanitized checks differ')
    mutations = {
        'lose_first_site': ('(NvU32)record.firstSite', '0U'),
        'reuse_cached_as_fresh': (
            'NV_STATUS status = s540FirstTxnOriginalReadServiceCounters(&context->nv, &fresh);',
            'S540FirstTxnSnapshot cached; NV_STATUS status = s540FirstTxnGetSnapshot(&context->nv, &cached); fresh = cached.counters;'),
        'skip_after_missing_cached_snapshot': ('    s540LogFreshServiceCounters(context);',
            '    if (snapshotStatus != NV_OK) return;\n    s540LogFreshServiceCounters(context);'),
        'invent_first_failure': ('if (allocation.observedMask & S540_DEVICE_ALLOC_DIAG_FIRST_FAILURE) {', 'if (1) {'),
        'lose_entry_rejection_count': ('allocation.allocationFailuresLifetime, allocation.entryRejectionsLifetime,',
            'allocation.allocationFailuresLifetime, 0U,'),
        'lose_failure_stage': ('allocation.firstFailure.stage, allocation.firstFailure.status,',
            '0U, allocation.firstFailure.status,'),
        'lose_CPU_mask': ('allocation.firstFailure.cpuObservedMask, allocation.firstFailure.maxBasic,',
            '0U, allocation.firstFailure.maxBasic,'),
        'lose_witness_instance': ('(unsigned long long)witness.firstInstance', '0ULL'),
        'invent_unobserved_missing': ('(witness.observedMask & S540_ATTACH_OBS_MISSING) ? witness.missing : 0U',
            'witness.missing'),
    }
    for name, (before, after) in mutations.items():
        require(helper.count(before) == 1, 'Exact diagnostic mutation anchor changed: ' + name)
        execute('mutant_' + name, helper.replace(before, after), negative=True)
    require({str(p.relative_to(ROOT)): sha(p) for p in files} == hashes, 'Diagnostic helper changed during controls')
    report = dict(format=1, status='passed-actual-post-wrapper-fresh-diagnostic-controls',
        exact_input_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in original.items()},
        exact_output_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in selected.items()},
        source_file_sha256=hashes, variants=variants, commands=commands,
        compiler_invocation_path=str(compiler), compiler_resolved_path=str(target), compiler_sha256=sha(target),
        actual_inserted_C_helpers=True, actual_unchanged_initialize_adapter_body=True,
        endpoints='explicit typed cached/fresh/allocation/witness/IRQ/original-return CPU endpoints',
        modeled_nv_layout=True, native_Darwin_compilation=False, actual_RM_execution=False,
        kernel_execution=False, hardware_execution=False, physical_release_authorized=False,
        sanitizer_policy=dict(address_and_undefined_fatal=True, leak_sanitizer_enabled=False,
            leak_sanitizer_reason='Explicit scalar fixture; managed host leak inventory unavailable.'))
    (output / 'context-results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-project', type=Path, required=True)
    p.add_argument('--composed-project', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cc', type=Path, required=True)
    p.add_argument('--host-control', action='store_true')
    result = run(p.parse_args())
    print(json.dumps(dict(status=result['status'], cases=result['variants']['selected']['cases'],
        checks=result['variants']['selected']['checks'], sanitized_checks=result['variants']['selected_sanitized']['checks'],
        mutants_killed=sum(bool(v.get('killed')) for v in result['variants'].values()))))
