#!/usr/bin/env python3
"""Check real RM result consistency using unchanged, bound CPU-control objects.

Only the lifecycle implementation and assertion harness are rebuilt. Existing
originals, headers, privileged-CPU/platform fixtures and auxiliary controls stay
byte-identical. These Linux CPU controls never load or initialize a GPU.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import prepare as result_profile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = HERE.parent/'prospective-retained-construction-closure'
sys.path.insert(0, str(ROOT/'builders'))
import compose_nvidia_first_transaction as composer

REPORT_SHA256 = '9bd1e8a7c92f5139104aadec7adb13c50c0378368676f2a86b0a143f26e6663f'
PROJECT_TREE_SHA256 = '3d7199aaea983dbd018d4e3f1a01763c18d9da35290a46a2ba2d80caccc07d13'
ORIGINAL_TREE_SHA256 = '458cd1993eda75f83f91c2ba13609b0efe01073f5b29653785f9f60c6a224dda'
AUDIT_SHA256 = '383bedf5a847a3fb90d6585c879065c853b18f7591507493688f9b6c80351a11'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    require(not path.is_symlink(), 'Symlink input refused: '+str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def once(text, before, after):
    require(text.count(before) == 1, 'Actual harness anchor changed: '+before[:80])
    return text.replace(before, after)


def prepared_cpu_source(canonical):
    text = once(canonical, '    status=coreInitializeRm();',
        '    status=coreInitializeRm();\n    s540GlobalEpochControlAfterCore();')
    return once(text, 'extern RsServer g_resServ;',
        'extern void s540GlobalEpochControlAfterCore(void);\nextern RsServer g_resServ;')


def harness():
    old_prepare = load('s540_retained_result_parent_prepare', OLD/'prepare.py')
    postcore = load('s540_retained_result_postcore_controls', OLD/'check_postcore.py')
    postcore.candidate = old_prepare
    text = postcore.harness_source()
    text = once(text, '    const NV_STATUS status=s540GlobalRmInitialize(&result);',
        '    const NV_STATUS status=s540GlobalRmInitialize(&result);\n'
        '    expect(result.startupStatus==status,"public startupStatus equals actual returned status");')
    text = once(text, 'expect(s540GlobalRmInitialize(&duplicate)!=NV_OK,',
        'const NV_STATUS duplicateStatus=s540GlobalRmInitialize(&duplicate);\n'
        '        expect(duplicateStatus!=NV_OK&&duplicate.startupStatus==duplicateStatus,')
    text = once(text, 'expect(s540GlobalRmInitialize(&retry)!=NV_OK&&',
        'const NV_STATUS retryStatus=s540GlobalRmInitialize(&retry);\n'
        '    expect(retryStatus!=NV_OK&&retry.startupStatus==retryStatus&&')
    text = once(text, r'\"status\":%u,', r'\"status\":%u,\"startup_status\":%u,')
    return once(text, 'scenario,checks,failures,status,epoch.state,',
        'scenario,checks,failures,status,result.startupStatus,epoch.state,')


def execute(argv, log, *, cwd=None, expected=0, environment=None):
    completed = subprocess.run([str(x) for x in argv], cwd=cwd, text=True,
        capture_output=True, timeout=180, env=environment)
    log.write_text(completed.stdout+completed.stderr)
    if expected is not None:
        require(completed.returncode == expected,
            'Local control command failed: '+str(log)+'\n'+completed.stderr[-3000:])
    return completed


def matrix(controls, variant, report):
    work = controls/variant
    record = report['variants'][variant]
    rows = {}
    for kind, count in [('original', 1100), ('project', 58)]:
        manifest = work/(kind+'-compilation.json')
        require(sha(manifest) == record[kind+'_compilation_sha256'], 'CPU compilation matrix changed')
        values = json.loads(manifest.read_text())
        require(len(values) == count, 'CPU compilation matrix incomplete')
        for row in values:
            obj = Path(row['object'])
            source = Path(row['compiled_source']) if kind == 'original' else controls/'project'/row['source']
            require(obj.resolve().is_relative_to(work), 'CPU object escapes its authenticated variant')
            require(sha(source) == row['source_sha256'] and sha(obj) == row['object_sha256'],
                'Bound CPU source/object changed: '+row['source'])
        rows[kind] = values
    require(sha(work/'global-epoch-check') == record['binary_sha256'], 'Existing CPU executable changed')
    return rows


def run(args):
    require(sys.platform.startswith('linux'), 'This checker is explicitly a Linux CPU control')
    controls = args.controls.resolve(strict=True)
    parent = args.composition.resolve(strict=True)
    composer.verify_composition(parent)
    require(sha(controls/'results.json') == REPORT_SHA256,
        'The reviewed historical CPU report is required; failed status must not be rewritten')
    audit_path = OLD/'LOCAL-CONTROL-VALIDATION.json'
    require(sha(audit_path) == AUDIT_SHA256, 'Reviewed auxiliary-object audit changed')
    audit = json.loads(audit_path.read_text())
    previous = json.loads((controls/'results.json').read_text())
    require(previous['status'] == 'failed' and previous['failure'] ==
        'Actual original source changed during retained-construction checks',
        'Only the reviewed final inventory-variable defect is eligible')
    require(composer.tree_sha(composer.inventory(controls/'source')) == ORIGINAL_TREE_SHA256,
        'Original CPU source tree changed')
    require(composer.tree_sha(composer.inventory(controls/'project')) == PROJECT_TREE_SHA256,
        'CPU project/header tree changed')
    for name in ('check_epoch.cpp', 'check_original.c', 'prepare.py',
                 'construction-api.c.inc', 'construction-api.h.inc'):
        require(sha(OLD/name) == previous['control_source_sha256'][name], 'Actual CPU control source changed')
    require(sha(parent/'composition.json') == previous['composition_sha256'], 'CPU canonical parent changed')
    canonical = (parent/'project'/result_profile.LIFECYCLE).read_text()
    changed = result_profile.transforms({result_profile.LIFECYCLE: canonical})[result_profile.LIFECYCLE]
    existing = controls/'project'/result_profile.LIFECYCLE
    require(prepared_cpu_source(canonical) == existing.read_text(), 'Existing CPU lifecycle differs from exact hooks')
    output = composer.new_output(args.output, [controls, parent, HERE])
    output.mkdir(parents=True)
    project = output/'project'
    shutil.copytree(controls/'project', project)
    lifecycle = project/result_profile.LIFECYCLE
    lifecycle.write_text(prepared_cpu_source(changed))
    # All headers and all other companion implementations remain identical.
    for name, row in composer.inventory(controls/'project').items():
        if name != result_profile.LIFECYCLE:
            require(sha(project/name) == row['sha256'], 'Unexpected CPU companion change: '+name)
    source = output/'result-harness.cpp'
    source.write_text(harness())
    project_inventory = composer.inventory(project)
    initial_inputs = {str(path): sha(path) for path in [Path(__file__), HERE/'prepare.py',
        OLD/'check_epoch.cpp', OLD/'check_postcore.py', controls/'results.json', audit_path]}
    fresh_inputs = {str(lifecycle): sha(lifecycle), str(source): sha(source)}
    report = {'format': 1, 'status': 'running', 'scope': 'Actual original CPU result consistency and measured allocation positions only',
        'historical_report_status_preserved': 'failed', 'historical_results_sha256': REPORT_SHA256,
        'canonical_lifecycle_sha256': result_profile.INPUT_SHA256,
        'production_lifecycle_sha256': result_profile.digest(changed),
        'cpu_lifecycle_sha256': sha(lifecycle), 'harness_sha256': sha(source),
        'input_sha256': initial_inputs, 'variants': {}, 'kernel_execution': False,
        'gpu_access': False, 'original_entry_admission': False, 'production_candidate_allowed': False,
        'whole_original_pipeline_reexecuted': False,
        'historical_compiler_executable_digest_available': False}
    write(output/'results.json', report)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    try:
        for variant in ('plain', 'sanitized'):
            work = output/variant
            work.mkdir()
            old = controls/variant
            rows = matrix(controls, variant, previous)
            aux = audit['variants'][variant]['additional_current_control_artifact_sha256']
            extra = [old/name for name in ('epoch-original-control.o', 'native-unavailable-boundaries.o',
                                           'nvswitch-assert-fixture.o')]
            require(all(sha(path) == aux[path.name] for path in extra), 'Auxiliary CPU object changed')
            auxiliary_hashes = {str(path): aux[path.name] for path in extra}
            selected = next(row for row in rows['project'] if row['source'] == result_profile.LIFECYCLE)
            cpp = next(row for row in rows['project'] if row['source'].endswith('/S540NvidiaGlobalRmHost.cpp'))

            def prefix(row):
                return [value.replace(str(controls/'project'), str(project))
                    for value in row['command'][:row['command'].index('-c')]]

            compiled = []
            def compile_one(path, obj, flags):
                dep = obj.with_suffix('.d')
                argv = [*flags, '-MD', '-MF', str(dep), '-c', str(path), '-o', str(obj)]
                compiler_hash = sha(Path(argv[0]))
                execute(argv, obj.with_suffix('.log'))
                require(sha(Path(argv[0])) == compiler_hash, 'CPU compiler changed during compilation')
                compiled.append({'source': str(path), 'source_sha256': sha(path), 'object_sha256': sha(obj),
                    'object': str(obj), 'dependency_file': str(dep),
                    'command': argv, 'compiler_sha256': compiler_hash, 'dependencies_sha256': sha(dep)})
            current = work/'lifecycle.o'
            assertion = work/'harness.o'
            compile_one(lifecycle, current, prefix(selected))
            compile_one(source, assertion, prefix(cpp))
            reused = [Path(row['object']) for row in rows['original']]+[
                Path(row['object']) for row in rows['project'] if row['source'] != result_profile.LIFECYCLE]

            def link(binary, implementation):
                argv = [*prefix(cpp), str(assertion), *map(str, reused), str(implementation),
                    *map(str, extra), '-Wl,--gc-sections', '-o', str(binary)]
                execute(argv, binary.with_suffix('.link.log'))
                return argv
            binary = work/'result-check'
            link_command = link(binary, current)
            binary_hash = sha(binary)
            observations = []
            positions = previous['variants'][variant]['all_allocation_positions_tested']
            with_api = previous['variants'][variant]['observations'][7]['allocations']
            require(positions == 154 and with_api == 156, 'Reviewed allocation positions changed')
            cases = [(str(scenario),) for scenario in range(10)]
            cases += [('6', str(ordinal)) for ordinal in range(1, positions+2)]
            cases += [('7', str(ordinal)) for ordinal in range(positions+1, with_api+2)]
            for index, case in enumerate(cases):
                completed = execute([binary, *case], work/('case-%03d.log'%index), environment=environment)
                view = json.loads(completed.stdout)
                require(view['failures'] == 0 and view['startup_status'] == view['status'], 'Returned result status diverged')
                if len(case) == 2:
                    ordinal = int(case[1])
                    expected_failure = ordinal <= (positions if case[0] == '6' else with_api)
                    require(bool(view['allocation_failures']) == expected_failure, 'Allocation position was not exercised')
                observations.append({'case': list(case), **view})
            negative = work/'legacy-result-check'
            link(negative, Path(selected['object']))
            negative_hash = sha(negative)
            ordinal = next(index+1 for index, view in enumerate(previous['variants'][variant]['allocation_faults'])
                if view['original_status'] != view['status'])
            failed = execute([negative, '6', str(ordinal)], work/'legacy-regression.log',
                expected=1, environment=environment)
            bad = json.loads(failed.stdout)
            require(bad['failures'] == 1 and bad['startup_status'] != bad['status'],
                'Actual legacy status mismatch was not detected by the new assertion')
            for row in compiled:
                require(sha(Path(row['object'])) == row['object_sha256'] and
                    sha(Path(row['source'])) == row['source_sha256'] and
                    sha(Path(row['command'][0])) == row['compiler_sha256'] and
                    sha(Path(row['dependency_file'])) == row['dependencies_sha256'],
                    'Fresh CPU source/object/compiler/dependency changed during runtime controls')
            require(sha(binary) == binary_hash and sha(negative) == negative_hash,
                'Executed CPU binary changed during controls')
            require(all(sha(Path(path)) == digest for path, digest in auxiliary_hashes.items()),
                'Auxiliary CPU object changed during controls')
            matrix(controls, variant, previous)
            report['variants'][variant] = {'status': 'passed', 'positive_cases': len(observations),
                'constructor_allocation_positions': positions, 'postcore_allocation_positions': [155, 156],
                'unreached_terminal_ordinals': [155, 157], 'legacy_regression_detected': True,
                'legacy_regression_ordinal': ordinal, 'legacy_regression_result': bad,
                'reused_original_units': len(rows['original']), 'reused_project_units': len(rows['project'])-1,
                'reused_auxiliary_units': len(extra), 'freshly_compiled_units': compiled,
                'binary_sha256': binary_hash, 'legacy_binary_sha256': negative_hash,
                'auxiliary_object_sha256': auxiliary_hashes,
                'fresh_artifact_and_compiler_final_bindings_verified': True,
                'link_command': link_command, 'observations': observations}
            write(output/'results.json', report)
        require(composer.tree_sha(composer.inventory(controls/'source')) == ORIGINAL_TREE_SHA256 and
            composer.tree_sha(composer.inventory(controls/'project')) == PROJECT_TREE_SHA256,
            'Authenticated CPU inputs changed during result controls')
        for path, digest in initial_inputs.items():
            require(sha(Path(path)) == digest, 'Result control source changed during execution')
        require(composer.inventory(project) == project_inventory and
            all(sha(Path(path)) == digest for path, digest in fresh_inputs.items()),
            'Fresh CPU project/header tree or harness changed during controls')
        report['status'] = 'passed-actual-original-global-result-consistency'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write(output/'results.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('controls', 'composition', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    value = run(args)
    print(json.dumps({'status': value['status'], 'cases': {
        name: data['positive_cases'] for name, data in value['variants'].items()}}))
