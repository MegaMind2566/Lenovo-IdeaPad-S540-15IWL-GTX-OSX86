#!/usr/bin/env python3
"""Link genuine global-owner record and allocator successor using bound CPU cache.

Rebuild only two actual NVIDIA originals, the guard, lifecycle and harness per
variant. Historical fixtures and unchanged objects stay byte-identical. This is
Linux CPU execution, with no GPU, kernel entry or native-cache admission.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import prepare as allocator


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RESULT_DIR = HERE.parent / 'prospective-global-result-closure'
result_profile = load('allocator_actual_result_prepare', RESULT_DIR / 'prepare.py')
saved_prepare = sys.modules['prepare']
sys.modules['prepare'] = result_profile
try:
    cached = load('allocator_actual_result_cache', RESULT_DIR / 'check.py')
finally:
    sys.modules['prepare'] = saved_prepare
composer, require, sha, write, execute = (cached.composer, cached.require,
    cached.sha, cached.write, cached.execute)


def harness_source():
    text = cached.harness()
    text = cached.once(text, 'extern "C" {',
        'extern "C" {\n#include "S540NvidiaAllocatorEpoch.h"')
    text = cached.once(text,
        'if(scenario==5)expect(s540GlobalEpochControlStartPort()==NV_OK,"real foreign portable epoch is created before global claim");',
        'if(scenario==5){\n'
        '        S540NvidiaGlobalRmHostSnapshot beforePort={},afterPort={};\n'
        '        s540GlobalRmHostSnapshot(&beforePort);\n'
        '        expect(s540GlobalEpochControlStartPort()!=NV_OK&&!s540GlobalEpochControlPortLive(),\n'
        '            "raw portable entry before genuine IN_CORE refuses without readiness");\n'
        '        s540GlobalRmHostSnapshot(&afterPort);\n'
        '        expect(beforePort.allocations==afterPort.allocations&&!s540GlobalEpochControlCoreReturns,\n'
        '            "raw portable refusal has no original allocation or core side effect");\n    }')
    text = cached.once(text,
        'if(scenario<3||scenario==9||(scenario==6&&!host.allocationFailures)){',
        'if(scenario<3||scenario==5||scenario==9||(scenario==6&&!host.allocationFailures)){')
    text = cached.once(text, '    expect(!s540GlobalRmHostShutdown(),',
        '    S540AllocatorEpochSnapshot allocator={};\n'
        '    s540AllocatorEpochSnapshot(&allocator);\n'
        '    expect(!allocator.portableBusy&&!allocator.memoryBusy&&!allocator.invalidCompletions,\n'
        '        "genuine global path finishes actual allocator guards without invalid completion");\n'
        '    if(s540GlobalRmIsInitialized())expect(allocator.portableReady&&allocator.memoryReady,\n'
        '        "published real global result retains completed original allocator initialization");\n'
        '    if(scenario==5)expect(allocator.refusedInitializations==1,\n'
        '        "genuine pre-core raw entry is counted once");\n'
        '    expect(!s540GlobalRmHostShutdown(),')
    text = cached.once(text, r'\"kernel_execution\":false,\"gpu_access\":false',
        r'\"allocator_ready\":%s,\"allocator_refusals\":%llu,\"allocator_shutdown_refusals\":%llu,\"kernel_execution\":false,\"gpu_access\":false')
    return cached.once(text,
        's540RetainedControlCleanupAfterClaim,s540GlobalEpochControlHookStatus);',
        's540RetainedControlCleanupAfterClaim,s540GlobalEpochControlHookStatus,\n'
        '        allocator.memoryReady?"true":"false",\n'
        '        static_cast<unsigned long long>(allocator.refusedInitializations),\n'
        '        static_cast<unsigned long long>(allocator.refusedShutdowns));')


def authenticate(controls, parent):
    composer.verify_composition(parent)
    require(sha(controls / 'results.json') == cached.REPORT_SHA256,
        'Reviewed historical failed CPU report required unchanged')
    audit_path = cached.OLD / 'LOCAL-CONTROL-VALIDATION.json'
    require(sha(audit_path) == cached.AUDIT_SHA256, 'Reviewed CPU auxiliary audit changed')
    previous = json.loads((controls / 'results.json').read_text())
    require(previous['status'] == 'failed' and previous['failure'] ==
        'Actual original source changed during retained-construction checks',
        'Only reviewed historical final-inventory defect is eligible')
    require(composer.tree_sha(composer.inventory(controls / 'source')) == cached.ORIGINAL_TREE_SHA256,
        'Original CPU source tree changed')
    require(composer.tree_sha(composer.inventory(controls / 'project')) == cached.PROJECT_TREE_SHA256,
        'CPU companion/header tree changed')
    for name in ('check_epoch.cpp', 'check_original.c', 'prepare.py',
                 'construction-api.c.inc', 'construction-api.h.inc'):
        require(sha(cached.OLD / name) == previous['control_source_sha256'][name],
            'Actual CPU control changed: ' + name)
    require(sha(parent / 'composition.json') == previous['composition_sha256'], 'Canonical parent changed')
    return previous, json.loads(audit_path.read_text()), audit_path


def run(args):
    require(sys.platform.startswith('linux'), 'Explicit Linux CPU control only')
    controls, parent = args.controls.resolve(strict=True), args.composition.resolve(strict=True)
    previous, audit, audit_path = authenticate(controls, parent)
    output = composer.new_output(args.output, [controls, parent, HERE])
    output.mkdir(parents=True)
    project = output / 'project'
    shutil.copytree(controls / 'project', project)
    canonical = (parent / 'project' / result_profile.LIFECYCLE).read_text()
    require(cached.prepared_cpu_source(canonical) ==
        (controls / 'project' / result_profile.LIFECYCLE).read_text(),
        'Cached lifecycle differs from exact genuine postcore hook')
    lifecycle = project / result_profile.LIFECYCLE
    lifecycle.write_text(cached.prepared_cpu_source(
        result_profile.transforms({result_profile.LIFECYCLE: canonical})[result_profile.LIFECYCLE]))
    changed = allocator.original_transforms({name: (controls / 'source' / name).read_text()
                                           for name in allocator.ORIGINAL_INPUTS})
    changed_paths = {}
    for name, text in changed.items():
        path = output / 'source' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        changed_paths[name] = path
    for name, original in allocator.COMPANIONS.items():
        destination = project / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original.read_bytes())
    harness = output / 'allocator-global-harness.cpp'
    harness.write_text(harness_source())
    for name, row in composer.inventory(controls / 'project').items():
        if name != result_profile.LIFECYCLE:
            require(sha(project / name) == row['sha256'], 'Unchanged CPU companion changed: ' + name)
    bound_inputs = [Path(__file__), HERE / 'prepare.py', *allocator.COMPANIONS.values(),
        RESULT_DIR / 'check.py', RESULT_DIR / 'prepare.py', cached.OLD / 'check_epoch.cpp',
        cached.OLD / 'check_postcore.py', controls / 'results.json', audit_path]
    initial_inputs = {str(p): sha(p) for p in bound_inputs}
    project_inventory = composer.inventory(project)
    source_inventory = composer.inventory(output / 'source')
    report = {'format': 1, 'status': 'running', 'input_sha256': initial_inputs,
        'historical_failed_report_preserved': True, 'historical_results_sha256': cached.REPORT_SHA256,
        'genuine_global_record_reused': True, 'genuine_in_core_identity_required': True,
        'record_identity_fixture': False, 'privileged_cpu_fixture': True, 'platform_facts_fixture': True,
        'historical_compiler_executable_digest_available': False,
        'kernel_execution': False, 'gpu_access': False, 'original_entry_admission': False,
        'production_candidate_allowed': False, 'aggregate_stack_proven': False,
        'project_inventory_sha256': composer.tree_sha(project_inventory),
        'changed_original_inventory_sha256': composer.tree_sha(source_inventory),
        'variants': {}}
    write(output / 'results.json', report)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    try:
        for variant in args.variants:
            work = output / variant
            work.mkdir()
            old = controls / variant
            rows = cached.matrix(controls, variant, previous)
            aux = audit['variants'][variant]['additional_current_control_artifact_sha256']
            extra = [old / name for name in ('epoch-original-control.o',
                'native-unavailable-boundaries.o', 'nvswitch-assert-fixture.o')]
            require(all(sha(p) == aux[p.name] for p in extra), 'Bound CPU auxiliary object changed')
            cpp = next(r for r in rows['project'] if r['source'].endswith('/S540NvidiaGlobalRmHost.cpp'))
            bridge = next(r for r in rows['project'] if r['source'] == result_profile.LIFECYCLE)
            originals = {name: next(r for r in rows['original'] if
                r['compiled_source'] == str(controls / 'source' / name)) for name in allocator.ORIGINAL_INPUTS}

            def prefix(row):
                return [v.replace(str(controls / 'project'), str(project))
                    for v in row['command'][:row['command'].index('-c')]]

            compiled = []
            def compile_one(path, obj, flags, cwd=None):
                dep = obj.with_suffix('.d')
                argv = [*flags, '-MD', '-MF', str(dep), '-c', str(path), '-o', str(obj)]
                compiler_hash = sha(Path(argv[0]))
                execute(argv, obj.with_suffix('.log'), cwd=cwd)
                require(sha(Path(argv[0])) == compiler_hash, 'Fresh compiler changed')
                compiled.append({'source': str(path), 'source_sha256': sha(path), 'object': str(obj),
                    'object_sha256': sha(obj), 'command': argv, 'compiler_sha256': compiler_hash,
                    'dependency_file': str(dep), 'dependency_file_sha256': sha(dep)})
            include = ['-I', str(project / allocator.DIRECTORY)]
            fresh = []
            for name, row in originals.items():
                obj = work / (Path(name).stem + '.o')
                compile_one(changed_paths[name], obj, [*prefix(row), *include],
                    controls / 'source/src/nvidia')
                fresh.append(obj)
            guard = work / 'allocator-epoch.o'
            compile_one(project / allocator.UNIT, guard, [*prefix(originals[allocator.CORE]), *include],
                controls / 'source/src/nvidia')
            fresh.append(guard)
            current = work / 'lifecycle.o'
            compile_one(lifecycle, current, prefix(bridge))
            fresh.append(current)
            assertion = work / 'harness.o'
            compile_one(harness, assertion, [*prefix(cpp), *include])
            replaced = {r['object'] for r in originals.values()}
            reused = [Path(r['object']) for r in rows['original'] if r['object'] not in replaced] + [
                Path(r['object']) for r in rows['project'] if r['source'] != result_profile.LIFECYCLE]
            binary = work / 'allocator-global-check'
            link = [*prefix(cpp), str(assertion), *map(str, reused), *map(str, fresh),
                *map(str, extra), '-Wl,--gc-sections', '-o', str(binary)]
            execute(link, binary.with_suffix('.link.log'))
            binary_hash = sha(binary)
            positions = previous['variants'][variant]['all_allocation_positions_tested']
            with_api = previous['variants'][variant]['observations'][7]['allocations']
            require(positions == 154 and with_api == 156, 'Bound measured allocation range changed')
            cases = [(str(i),) for i in range(10)] + [('6', str(i)) for i in range(1, positions + 2)] + [
                ('7', str(i)) for i in range(positions + 1, with_api + 2)]
            observations = []
            for index, case in enumerate(cases):
                completed = execute([binary, *case], work / ('case-%03d.log' % index), environment=environment)
                view = json.loads(completed.stdout)
                require(view['failures'] == 0 and view['startup_status'] == view['status'],
                    'Genuine allocator/global result failed')
                if len(case) == 2:
                    expected = int(case[1]) <= (positions if case[0] == '6' else with_api)
                    require(bool(view['allocation_failures']) == expected, 'Measured allocation not exercised')
                observations.append({'case': list(case), **view})
            for row in compiled:
                require(all(sha(Path(path)) == digest for path, digest in (
                    (row['source'], row['source_sha256']), (row['object'], row['object_sha256']),
                    (row['command'][0], row['compiler_sha256']),
                    (row['dependency_file'], row['dependency_file_sha256']))), 'Fresh runtime artifact changed')
            require(sha(binary) == binary_hash and all(sha(p) == aux[p.name] for p in extra),
                'Executed binary or reused auxiliary artifact changed')
            cached.matrix(controls, variant, previous)
            report['variants'][variant] = {'status': 'passed', 'positive_cases': len(observations),
                'freshly_compiled_units': compiled, 'reused_original_units': len(rows['original']) - 2,
                'reused_project_units': len(rows['project']) - 1, 'reused_auxiliary_units': len(extra),
                'binary_sha256': binary_hash, 'link_command': link, 'observations': observations}
            write(output / 'results.json', report)
        authenticate(controls, parent)
        require(composer.inventory(project) == project_inventory and
            composer.inventory(output / 'source') == source_inventory and
            all(sha(Path(p)) == digest for p, digest in initial_inputs.items()),
            'Bound source/project/control changed during execution')
        report['status'] = 'passed-genuine-global-owner-allocator-cpu-integration'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write(output / 'results.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('controls', 'composition', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--variants', nargs='+', choices=('plain', 'sanitized'), default=['plain', 'sanitized'])
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'cases': {
        name: data['positive_cases'] for name, data in result['variants'].items()}}))
