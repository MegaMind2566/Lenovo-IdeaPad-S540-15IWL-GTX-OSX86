#!/usr/bin/env python3
"""Exercise the actual inserted diagnostic and adapter boundary on the CPU."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as composer

HELPER = 's540LogRetainedProfileFailure'
CONTEXT = 'packages/nvidia-gsp-bootstrap/src/S540NvidiaGspContext.c'
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def actual_function(text, name):
    first, last = prepare.function_span(text, name)
    first = text.rfind('\n', 0, first) + 1
    return text[first:last] + '\n'


def run(args):
    base = args.base.resolve(strict=True)
    composer.verify_composition(base)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('A fresh nonoverlapping context-control output is required')
    output.mkdir(parents=True)
    source = {name: (base / 'project' / name).read_text() for name in prepare.INPUTS}
    transformed = prepare.transforms(source)
    if CONTEXT not in transformed:
        raise ValueError('The actual GSP context must be transformed by this profile')
    context = transformed[CONTEXT]
    helper = actual_function(context, HELPER)
    initialize = actual_function(context, 's540GspContextInitializeAdapter')
    snippet = (HERE / 'context-failure.c.inc').read_text()
    if helper.strip() not in snippet or context.count(helper.strip()) != 1:
        raise ValueError('The exact diagnostic helper was not inserted once')
    wrapper = '    profile = s540FirstTxnOriginalWrapperReturned(&context->nv);'
    call = 's540LogRetainedProfileFailure(context, profile);'
    if initialize.count(wrapper) != 1 or initialize.count(call) != 1 or initialize.index(call) < initialize.index(wrapper):
        raise ValueError('The diagnostic must follow the actual wrapper-return boundary once')
    (output / 'candidate-context.c').write_text(context)
    fixture = HERE / 'tests/check_context.c.inc'
    cc = args.cc.resolve(strict=True)
    packages = base / 'project/packages'
    include_dirs = [packages,
        packages / 'nvidia-gsp-bootstrap/src',
        packages / 'nvidia-gsp-bootstrap/prospective-first-transaction/record']
    flags = ['-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
        *[item for directory in include_dirs for item in ('-I', str(directory))]]
    environment = dict(os.environ,
        ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    report = dict(format=1, status='running',
        scope='actual-inserted-C-diagnostic-and-adapter-boundary-with-explicit-CPU-endpoints',
        parent_composition_sha256=sha(base / 'composition.json'),
        original_context_sha256=sha(base / 'project' / CONTEXT),
        candidate_context_sha256=sha(output / 'candidate-context.c'),
        actual_record_header_sha256=sha(base / 'project' / RECORD),
        helper_sha256=sha(HERE / 'context-failure.c.inc'), fixture_sha256=sha(fixture),
        compiler_sha256={str(cc): sha(cc)}, commands=[], variants={}, negative_controls={},
        dependency_sha256={}, native_darwin_compilation=False, actual_rm_execution=False,
        kernel_execution=False, hardware_execution=False, physical_release_authorized=False,
        leak_sanitizer_enabled=False,
        leak_sanitizer_reason='Managed host task inventory is unavailable; explicit endpoint counters are checked.')

    def record():
        (output / 'context-results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def execute(command, log, expected=0):
        command = [str(item) for item in command]
        result = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=120)
        log.write_text(result.stdout + result.stderr)
        report['commands'].append(command)
        if expected is not None and result.returncode != expected:
            raise ValueError('Context diagnostic control failed: ' + str(log) + '\n' + result.stderr[-3000:])
        return result

    def variant(label, selected_helper, selected_initialize, instrumentation, expected=0):
        work = output / label
        work.mkdir()
        (work / 'actual-context-failure.inc').write_text(selected_helper)
        (work / 'actual-initialize-adapter.inc').write_text(selected_initialize)
        unit = work / 'check-context.c'
        unit.write_bytes(fixture.read_bytes())
        binary, dependency = work / 'control', work / 'control.d'
        execute([cc, *flags, *instrumentation, '-I', work, '-MD', '-MF', dependency,
            unit, '-o', binary], work / 'compile.log')
        bindings = {}
        for name in shlex.split(dependency.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve(strict=True)
            bindings[str(path)] = sha(path)
        if str((base / 'project' / RECORD).resolve()) not in bindings:
            raise ValueError('The actual composed first-transaction header was not compiled')
        report['dependency_sha256'][label] = bindings
        result = execute([binary], work / 'run.log', expected)
        return result, binary

    record()
    try:
        for label, instrumentation in [('plain', []), ('fatal-sanitizers', [
                '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])]:
            result, binary = variant(label, helper, initialize, instrumentation)
            view = json.loads(result.stdout)
            if view.get('status') != 'passed' or not view.get('checks'):
                raise ValueError('Context controls did not produce successful observations')
            report['variants'][label] = dict(view, binary_sha256=sha(binary))
        if report['variants']['plain']['checks'] != report['variants']['fatal-sanitizers']['checks']:
            raise ValueError('Plain and instrumented context observations differ')
        mutants = [
            ('lost-first-site', '(NvU32)record.firstSite', '0U'),
            ('wrong-snapshot-availability', 'if (snapshotStatus != NV_OK)', 'if (snapshotStatus == NV_OK)')]
        for label, before, after in mutants:
            if helper.count(before) != 1:
                raise ValueError('Actual diagnostic mutation anchor changed: ' + label)
            result, binary = variant('negative-' + label, helper.replace(before, after), initialize, [], None)
            if result.returncode == 0:
                raise ValueError('Actual diagnostic mutant survived: ' + label)
            report['negative_controls'][label] = dict(rejected=True, returncode=result.returncode,
                binary_sha256=sha(binary))
        for bindings in report['dependency_sha256'].values():
            for path, digest in bindings.items():
                if sha(path) != digest:
                    raise ValueError('Bound context-control dependency changed: ' + path)
        report['status'] = 'passed-actual-context-diagnostic-controls'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        record()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cc', required=True, type=Path)
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], variants=result['variants'],
        negative_controls=list(result['negative_controls']))))
