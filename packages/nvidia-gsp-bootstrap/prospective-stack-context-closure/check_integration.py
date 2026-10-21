#!/usr/bin/env python3
"""Replay actual global construction after changing only allocator codegen.

The already-bound genuine-record executable is relinked with one freshly
compiled memory TU per mode. All original observations must remain identical.
This Linux CPU reuse is explicitly not Apple native artifact eligibility.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import prepare
import check

PARENT = HERE.parent / 'prospective-allocator-stack-closure'
GENUINE_SHA = 'ee8adb1ef7cff89cda05c78af606aa403433aeea659fc0280ab6b0110b266a09'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old_prepare = load('stack_context_old_allocator_prepare', PARENT / 'prepare.py')
saved_prepare = sys.modules['prepare']
sys.modules['prepare'] = old_prepare
try:
    previous_checker = load('stack_context_previous_genuine_checker', PARENT / 'check_integration.py')
finally:
    sys.modules['prepare'] = saved_prepare
composer = previous_checker.composer
require, sha, execute, write = check.require, check.sha, check.execute, check.write


def run(args):
    require(sys.platform.startswith('linux'), 'Explicit Linux CPU controls only')
    base, genuine, cached = [path.resolve(strict=True) for path in
        (args.base, args.genuine_controls, args.cached_controls)]
    canonical = args.canonical_parent.resolve(strict=True)
    require(sha(base / 'composition.json') == check.COMPOSITION_SHA, 'Exact operational source parent required')
    require(sha(genuine / 'results.json') == GENUINE_SHA, 'Exact previously successful genuine integration required')
    old = json.loads((genuine / 'results.json').read_text())
    require(old['status'] == 'passed-genuine-global-owner-allocator-cpu-integration' and
        old['record_identity_fixture'] is False, 'A genuine record integration is required')
    historical, audit, audit_path = previous_checker.authenticate(cached, canonical)

    def verify_genuine_sources():
        require(composer.tree_sha(composer.inventory(genuine / 'project')) == old['project_inventory_sha256'] and
            composer.tree_sha(composer.inventory(genuine / 'source')) == old['changed_original_inventory_sha256'],
            'Prior genuine source/header tree changed')
        require(all(sha(Path(path)) == digest for path, digest in old['input_sha256'].items()),
            'Prior genuine integration bound inputs changed')
    verify_genuine_sources()
    output = args.output.resolve()
    require(not output.exists(), 'Fresh genuine stack-context output required')
    output.mkdir(parents=True)
    prepared = output / 'successor'
    preparation = prepare.prepare(base / 'source', prepared)
    candidate = prepared / 'source' / prepare.MEMORY
    inputs = {str(path): sha(path) for path in (Path(__file__), HERE / 'check.py', HERE / 'prepare.py',
        PARENT / 'check_integration.py', genuine / 'results.json', cached / 'results.json',
        base / 'composition.json', audit_path)}
    report = {'format': 1, 'status': 'running', 'preparation': preparation, 'input_sha256': inputs,
        'genuine_global_record_identity_required': True, 'record_identity_fixture': False,
        'privileged_cpu_and_platform_fixtures': True, 'historical_failed_report_preserved': True,
        'historical_compiler_executable_digest_available': False, 'native_cache_eligibility_established': False,
        'kernel_execution': False, 'gpu_access': False, 'original_entry_admission': False,
        'hardware_admission': False, 'kernel_stack_bound_proven': False,
        'native_ci_requested': False, 'variants': {}}
    write(output / 'results.json', report)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    try:
        for variant in ('plain', 'sanitized'):
            work = output / variant
            work.mkdir()
            before = old['variants'][variant]
            require(before['positive_cases'] == 168 and before['status'] == 'passed',
                'Complete prior allocation-ordinal coverage required')
            matrices = previous_checker.cached.matrix(cached, variant, historical)
            originals = before['freshly_compiled_units']
            memory = next(row for row in originals if row['source'].endswith('/' + prepare.MEMORY))
            require(memory['source_sha256'] == prepare.BASE_SHA256 and sha(Path(memory['source'])) == prepare.BASE_SHA256,
                'Genuine original memory body differs from selected production input')
            object_bindings = {row['object']: row['object_sha256'] for rows in matrices.values() for row in rows}
            for row in originals:
                require(sha(Path(row['source'])) == row['source_sha256'] and
                    sha(Path(row['object'])) == row['object_sha256'] and
                    sha(Path(row['command'][0])) == row['compiler_sha256'] and
                    sha(Path(row['dependency_file'])) == row['dependency_file_sha256'],
                    'Prior genuine fresh source/object/compiler/dependency binding changed')
                object_bindings[row['object']] = row['object_sha256']
            auxiliary = audit['variants'][variant]['additional_current_control_artifact_sha256']
            for name in ('epoch-original-control.o', 'native-unavailable-boundaries.o', 'nvswitch-assert-fixture.o'):
                path = cached / variant / name
                require(sha(path) == auxiliary[name], 'Authenticated auxiliary object changed')
                object_bindings[str(path)] = auxiliary[name]
            link = before['link_command'][:]
            linked = [value for value in link if value.endswith('.o')]
            require(len(linked) == len(set(linked)) == 1163 and
                all(path in object_bindings and sha(Path(path)) == object_bindings[path] for path in linked),
                'Prior genuine link inputs lack exact unique object bindings')
            require(sha(genuine / variant / 'allocator-global-check') == before['binary_sha256'],
                'Prior executed genuine binary changed')
            obj, dep = work / 'memory_tracking.o', work / 'memory_tracking.d'
            command = memory['command'][:]
            command[command.index('-c') + 1] = str(candidate)
            command[command.index('-o') + 1] = str(obj)
            command[command.index('-MF') + 1] = str(dep)
            compiler = Path(command[0])
            compiler_sha = sha(compiler)
            execute(command, work / 'compile.log', cwd=cached / 'source/src/nvidia')
            dependencies = check.dependency_hashes(dep, cached / 'source/src/nvidia')
            require(str(candidate) in dependencies, 'Fresh dependency capture omitted actual candidate source')
            binary = work / 'global-stack-context-check'
            require(link.count(memory['object']) == 1, 'Exact one-memory-object replacement required')
            link[link.index(memory['object'])] = str(obj)
            link[link.index('-o') + 1] = str(binary)
            execute(link, work / 'link.log')
            binary_sha, object_sha = sha(binary), sha(obj)
            observations = []
            for index, view in enumerate(before['observations']):
                actual = json.loads(execute([binary, *view['case']], work / ('case-%03d.log' % index),
                    environment=environment).stdout)
                require(actual == {key: value for key, value in view.items() if key != 'case'},
                    'Actual original constructor/OOM/result behavior changed at case ' + str(view['case']))
                observations.append({'case': view['case'], **actual})
            require(sha(binary) == binary_sha and sha(obj) == object_sha and sha(compiler) == compiler_sha and
                sha(candidate) == preparation['output_sha256'] and
                all(sha(Path(path)) == digest for path, digest in dependencies.items()),
                'Fresh source/object/compiler/binary/dependencies changed during actual execution')
            require(all(sha(Path(path)) == object_bindings[path] for path in linked),
                'Reused genuine link objects changed during execution')
            previous_checker.cached.matrix(cached, variant, historical)
            report['variants'][variant] = {'status': 'passed', 'positive_cases': len(observations),
                'assertions': sum(view['checks'] for view in observations),
                'all_original_observations_identical': True, 'fresh_original_units': 1,
                'reused_link_objects': len(linked) - 1, 'compiler_sha256': compiler_sha,
                'source_sha256': sha(candidate), 'object_sha256': object_sha, 'binary_sha256': binary_sha,
                'command': command, 'link_command': link, 'dependency_sha256': dependencies,
                'observations': observations}
            write(output / 'results.json', report)
        verify_genuine_sources()
        require(all(sha(Path(path)) == digest for path, digest in inputs.items()), 'Control inputs changed')
        report['status'] = 'passed-genuine-global-stack-context-observations-identical'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write(output / 'results.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'genuine-controls', 'cached-controls', 'canonical-parent', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'variants': {key: row['positive_cases']
        for key, row in result['variants'].items()}}, sort_keys=True))
