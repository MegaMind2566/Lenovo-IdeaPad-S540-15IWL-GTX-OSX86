#!/usr/bin/env python3
"""Actual Owner method bodies with injected CPU-only platform/cleanup faults."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fragment(text, signature):
    if text.count(signature) != 1:
        raise ValueError('One exact actual method signature required: ' + signature)
    begin = text.index(signature)
    brace = text.index('{', begin)
    depth = 1
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for token in tokens.finditer(text, brace + 1):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
        if not depth:
            return text[begin:token.end()]
    raise ValueError('Unclosed actual method: ' + signature)


def fixture_source(text, *, observed):
    template = (HERE / 'tests/check_owner.cpp.inc').read_text()
    helpers = ''
    if observed:
        start = text.index('static void s540PreparationReset(')
        helpers = text[start:text.index('struct Owner::Impl {', start)]
    fields = {
        'HEADER': str(HERE / 'S540PreparationObservation.h'),
        'STATUS': str(ROOT / 'packages/nvidia-os-adapter/upstream/include/nvstatus.h'),
        'HELPERS': helpers,
        'DISPATCH_RETURN': fragment(text, '    void observePreparationDispatchReturn(') if observed else '',
        'READ': fragment(text, '    Snapshot read() const {'),
        'FAILED': fragment(text, '    NV_STATUS failed(NV_STATUS failure) {'),
        'PREPARE': fragment(text, '    NV_STATUS prepare() {'),
        'COMMON': fragment(text, 'NV_STATUS Owner::prepareCommon('),
        'STOP': fragment(text, 'NV_STATUS Owner::stop() {'),
    }
    for name, value in fields.items():
        marker = '@' + name + '@'
        if template.count(marker) != 1:
            raise ValueError('Fixture marker missing or repeated: ' + name)
        template = template.replace(marker, value)
    if re.search(r'@[A-Z_]+@', template):
        raise ValueError('Unexpanded actual-body fixture marker')
    return template


def run(args):
    source_project = args.input_project.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Fresh preparation observation control output required')
    output.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location('s540_preparation_observation_controls', HERE / 'prepare.py')
    prepare = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = prepare
    spec.loader.exec_module(prepare)
    original = {name: (source_project / name).read_text() for name in prepare.INPUTS}
    transformed = prepare.transforms(original)
    checks = []
    for name in prepare.INPUTS:
        changed = dict(original)
        changed[name] += '\n'
        try:
            prepare.transforms(changed)
        except ValueError:
            checks.append('changed-prerequisite-refused-' + name)
        else:
            raise AssertionError('Changed prerequisite accepted: ' + name)
    for changed in ({k: v for k, v in original.items() if k != prepare.INPUTS[0]},
                    dict(original, unreviewed='unreviewed')):
        try:
            prepare.transforms(changed)
        except ValueError:
            checks.append('missing-or-extra-prerequisite-refused')
        else:
            raise AssertionError('Incomplete or extended prerequisite set accepted')

    def compile_run(label, text, observed, *, sanitize=False, must_fail=False):
        source = output / (label + '.cpp')
        source.write_text(fixture_source(text, observed=observed))
        executable = output / label
        command = [str(args.cxx), '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-function', '-DOBSERVATIONS=' + str(int(observed))]
        if sanitize:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command += [str(source), '-o', str(executable)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (output / (label + '-compile.log')).write_text(built.stdout + built.stderr)
        if built.returncode:
            raise ValueError('Actual-body CPU fixture compile failed: ' + built.stderr[-7000:])
        environment = dict(os.environ)
        if sanitize:
            # LeakSanitizer cannot enumerate /proc tasks in this traced host.
            # Address/undefined checks remain fatal; fixture lifetimes are also
            # observed through the actual facade-stop deletion path.
            environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1'
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30, env=environment)
        (output / (label + '.stdout')).write_text(result.stdout)
        (output / (label + '.stderr')).write_text(result.stderr)
        if must_fail:
            if not result.returncode:
                raise AssertionError('Mutated observation unexpectedly passed: ' + label)
        elif result.returncode:
            raise AssertionError('Actual-body CPU fixture failed: ' + label + ': ' + result.stderr)
        return result

    before = compile_run('actual-B3-bodies', original[prepare.BOOT], False)
    after = compile_run('actual-observed-bodies', transformed[prepare.BOOT], True)
    if before.stdout != after.stdout:
        raise AssertionError('Observation transform changed actual preparation call/cleanup/return behavior')
    checks += ['33-actual-body-fault-cases-identical-original-call-order-status-cleanup',
               'first-preparation-failure-preserved-after-real-facade-stop-and-Impl-deletion',
               'host85-missing-mask-and-device85-computed-predicates-preserved',
               'failed-cleanup-return-kept-with-earlier-preparation-failure',
               'early-collection-refusal-does-not-invent-observed-zero-facts',
               'unexecuted-dispatch-preparation-refusal-survives-later-stop']
    sanitized = compile_run('actual-observed-bodies-sanitized', transformed[prepare.BOOT], True, sanitize=True)
    if sanitized.stdout != after.stdout:
        raise AssertionError('Sanitized actual-body behavior differs')
    checks.append('actual-bodies-fatal-ASAN-UBSAN')
    mutant = transformed[prepare.BOOT].replace(
        'value.firstFailureStage = value.stage; value.firstFailureStatus = status;',
        'value.firstFailureStage = value.stage; value.firstFailureStatus = NV_OK;')
    if mutant == transformed[prepare.BOOT]:
        raise ValueError('First-failure negative control anchor changed')
    compile_run('lost-first-failure-mutant', mutant, True, must_fail=True)
    checks.append('actual-body-mutant-losing-first-failure-is-rejected')
    report = dict(format=1, status='passed-preparation-observation-CPU-controls',
        host_control=True, native_darwin_compilation=False, module_loaded=False,
        gpu_access=False, hardware_admission=False, original_entry_admission=False,
        acceleration_test=False, production_candidate_allowed=False,
        actual_method_fragments=('Owner::prepareCommon', 'Impl::prepare', 'Impl::failed',
            'Impl::read', 'Impl::observePreparationDispatchReturn', 'Owner::stop'),
        fault_case_count=33, checks=checks, check_count=len(checks),
        leak_sanitizer='disabled because traced host cannot enumerate /proc tasks',
        assertions=after.stderr.strip(), observed_header_bytes=104,
        original_behavior_sha256=hashlib.sha256(before.stdout.encode()).hexdigest(),
        observed_behavior_sha256=hashlib.sha256(after.stdout.encode()).hexdigest(),
        transformed_source_sha256={name: hashlib.sha256(value.encode()).hexdigest() for name, value in transformed.items()},
        source_sha256={str(path.relative_to(ROOT)): sha(path) for path in
            (Path(__file__), HERE / 'tests/check_owner.cpp.inc', HERE / 'prepare.py',
             HERE / 'owner-observation.cpp.inc', HERE / 'S540PreparationObservation.h', HERE / 'power.py',
             HERE / 'BASE-SHA256.json', HERE / 'SOURCE-CONTRACT.json')})
    (output / 'results.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', type=Path, default=Path('/usr/bin/c++'))
    args = parser.parse_args()
    print(json.dumps(run(args), sort_keys=True))


if __name__ == '__main__':
    main()
