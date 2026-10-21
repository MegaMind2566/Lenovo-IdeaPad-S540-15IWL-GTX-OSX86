#!/usr/bin/env python3
"""Run genuine global construction with the current record/cancel/memory bodies.

Only those three CPU translation units are rebuilt per mode. The constructor,
retention guard, lifecycle hooks, assertion harness and all other linked objects
remain bound to the previous successful genuine execution. Privileged CPU and
platform endpoints remain the historical explicit fixtures. IRQ, cleanup-mask,
timer, PCI and GPU entrypoints are not exercised by this global-only check.
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
STACK = HERE.parent / 'prospective-stack-context-closure'
GSP = 'packages/nvidia-gsp-bootstrap/'
MEMORY = 'src/nvidia/src/libraries/nvport/memory/memory_tracking.c'
RECORD = GSP + 'prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
CANCEL = GSP + 'cancellation/S540NvidiaGspCancellation.c'
PARTICIPANTS = GSP + 'prospective-first-transaction/record/deps/Participants.h'
HEADERS = (PARTICIPANTS,
    GSP + 'prospective-irq-callback-closure/S540NvidiaIrqClosure.h',
    GSP + 'prospective-pm-revocation-closure/S540NvidiaGspCommit.h',
    GSP + 'prospective-dma-producer-closure/S540NvidiaDmaProducer.h')
CHILD_SHA = '72b7d5a5d93504218e8a7953d79c90c1609e4580c55922deb2ec5dab13de24d8'
STACK_SHA = '9352993631a9d9c8a1c4740c492a452c6ca9a95d11819d502a603a36408943d6'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


saved = {name: sys.modules.get(name) for name in ('prepare', 'check')}
sys.path.insert(0, str(STACK))
try:
    sys.modules['prepare'] = load('shutdown_global_stack_prepare', STACK / 'prepare.py')
    sys.modules['check'] = load('shutdown_global_stack_check', STACK / 'check.py')
    stack = load('shutdown_global_stack_integration', STACK / 'check_integration.py')
finally:
    for name, value in saved.items():
        if value is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = value
sys.path.insert(0, str(ROOT / 'builders'))
import prepare_nvidia_shutdown_successor as preparation

composer = stack.composer
require, sha, write, execute = stack.require, stack.sha, stack.write, stack.execute


def read(path):
    return json.loads(path.read_text())


def bindings(paths):
    return {str(path): sha(path) for path in paths}


def verify_bindings(values, reason):
    require(all(sha(Path(path)) == digest for path, digest in values.items()), reason)


def run(args):
    require(sys.platform.startswith('linux'), 'Explicit Linux CPU control only')
    child, base, integrated, canonical, previous, genuine, cached = [path.resolve(strict=True)
        for path in (args.composition, args.base, args.integrated_base, args.canonical_parent,
                     args.stack_controls, args.genuine_controls, args.cached_controls)]
    require(sha(child / 'composition.json') == CHILD_SHA, 'Exact frozen shutdown successor required')
    preparation.verify(canonical, integrated, base, child)
    require(sha(previous / 'results.json') == STACK_SHA, 'Exact passed genuine stack execution required')
    require(sha(genuine / 'results.json') == stack.GENUINE_SHA, 'Exact passed genuine allocator execution required')
    parent, old = read(previous / 'results.json'), read(genuine / 'results.json')
    require(parent['status'] == 'passed-genuine-global-stack-context-observations-identical' and
        old['status'] == 'passed-genuine-global-owner-allocator-cpu-integration' and
        parent['record_identity_fixture'] is False and old['record_identity_fixture'] is False,
        'Successful genuine-record CPU parents required')
    historical, audit, audit_path = stack.previous_checker.authenticate(cached, canonical)

    def verify_parents():
        require(composer.tree_sha(composer.inventory(genuine / 'project')) == old['project_inventory_sha256'] and
            composer.tree_sha(composer.inventory(genuine / 'source')) == old['changed_original_inventory_sha256'],
            'Authenticated CPU source/header trees changed')
        verify_bindings(old['input_sha256'], 'Genuine allocator control inputs changed')
        verify_bindings(parent['input_sha256'], 'Genuine stack control inputs changed')
    verify_parents()
    output = args.output.resolve()
    require(not output.exists(), 'Fresh global shutdown integration output required')
    output.mkdir(parents=True)
    project = output / 'project'
    shutil.copytree(genuine / 'project', project)
    copied = (RECORD, CANCEL, *HEADERS)
    source_bindings = {}
    for name in copied:
        source, destination = child / 'project' / name, project / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        source_bindings[str(source)] = sha(source)
    memory = output / 'source' / MEMORY
    memory.parent.mkdir(parents=True)
    memory.write_bytes((child / 'source' / MEMORY).read_bytes())
    source_bindings[str(child / 'source' / MEMORY)] = sha(memory)
    require(sha(memory) == parent['preparation']['output_sha256'],
        'Current child memory differs from the proven stack specialization')

    # The cached CPU record predates IRQ enrollment. The only existing header
    # delta adds these declarations, without changing any existing type/API.
    additions = ''.join(line + '\n' for line in (
        'NV_STATUS s540GspCancellationEnterIrqScope(const void *, NvU32 role, NvU32 inheritedOrigin);',
        'NV_STATUS s540GspCancellationLeaveIrqScope(const void *, NvU32 role);',
        'NvU32 s540GspCancellationIrqOrigin(NvU32 role);',
        'NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *, NvU32 role, NvU32 *actualOrigin);'))
    participants = (project / PARTICIPANTS).read_text()
    require(participants.count(additions) == 1 and participants.replace(additions, '') ==
        (genuine / 'project' / PARTICIPANTS).read_text(), 'Existing participant ABI/header changed')
    for name in (GSP + 'prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h',
                 GSP + 'cancellation/S540NvidiaGspCancellation.h'):
        require((child / 'project' / name).read_bytes() == (project / name).read_bytes(),
            'Existing public record/cancellation ABI changed')
    for name, row in composer.inventory(genuine / 'project').items():
        if name not in copied:
            require(sha(project / name) == row['sha256'], 'Unexpected CPU hook/header/companion change: ' + name)
    project_inventory = composer.inventory(project)
    inputs = bindings([Path(__file__), STACK / 'check_integration.py', STACK / 'check.py', STACK / 'prepare.py',
        previous / 'results.json', genuine / 'results.json', cached / 'results.json', audit_path,
        child / 'composition.json', ROOT / 'builders/prepare_nvidia_shutdown_successor.py'])
    inputs.update(source_bindings)
    report = dict(format=1, status='running', composition_sha256=CHILD_SHA,
        previous_genuine_stack_report_sha256=STACK_SHA, input_sha256=inputs,
        exact_child_record_cancellation_and_memory=True, genuine_record_identity=True,
        record_identity_fixture=False, privileged_cpu_and_platform_fixtures=True,
        historical_failed_report_preserved=True, historical_compiler_executable_digest_available=False,
        native_cache_eligibility_established=False, kernel_execution=False, gpu_access=False,
        original_entry_admission=False, hardware_admission=False, kernel_stack_bound_proven=False,
        pm_30_second_shutdown_bound_proven=False, whole_dma_stop_proven=False,
        physical_reclamation_authorized=False, native_ci_requested=False,
        fixture_header_delta='Four existing-ABI IRQ declarations only; no prior type or prototype changed.',
        copied_production_files={name: sha(project / name) for name in copied},
        cpu_project_inventory_sha256=composer.tree_sha(project_inventory),
        unexecuted_paths=['new cleanup-mask observer', 'IRQ controller/backend', 'timers',
                         'PCI/MMIO/BME', 'TX queue', 'GSP firmware', 'GPU initialization'], variants={})
    write(output / 'results.json', report)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    try:
        for variant in ('plain', 'sanitized'):
            work = output / variant
            work.mkdir()
            before, ancestor = parent['variants'][variant], old['variants'][variant]
            require(before['status'] == 'passed' and before['positive_cases'] == 168,
                'Complete successful parent observations required')
            matrices = stack.previous_checker.cached.matrix(cached, variant, historical)
            object_bindings = {row['object']: row['object_sha256'] for rows in matrices.values() for row in rows}
            for row in ancestor['freshly_compiled_units']:
                verify_bindings({row['source']: row['source_sha256'], row['object']: row['object_sha256'],
                    row['command'][0]: row['compiler_sha256'], row['dependency_file']: row['dependency_file_sha256']},
                    'Prior genuine fresh source/object/compiler/dependency changed')
                object_bindings[row['object']] = row['object_sha256']
            old_memory_obj = before['command'][before['command'].index('-o') + 1]
            require(sha(Path(old_memory_obj)) == before['object_sha256'] and
                sha(Path(before['command'][before['command'].index('-c') + 1])) == before['source_sha256'],
                'Passed stack memory source/object changed')
            verify_bindings(before['dependency_sha256'], 'Passed stack memory dependencies changed')
            object_bindings[old_memory_obj] = before['object_sha256']
            aux = audit['variants'][variant]['additional_current_control_artifact_sha256']
            for name in ('epoch-original-control.o', 'native-unavailable-boundaries.o', 'nvswitch-assert-fixture.o'):
                path = cached / variant / name
                require(sha(path) == aux[name], 'Bound CPU auxiliary object changed')
                object_bindings[str(path)] = aux[name]
            linked = [value for value in before['link_command'] if value.endswith('.o')]
            require(len(linked) == len(set(linked)) == 1163 and all(
                path in object_bindings and sha(Path(path)) == object_bindings[path] for path in linked),
                'Passed parent link inputs lack exact unique object bindings')
            require(sha(previous / variant / 'global-stack-context-check') == before['binary_sha256'],
                'Passed genuine parent executable changed')
            replacements = []
            includes = [flag for name in ('prospective-pm-revocation-closure', 'prospective-dma-producer-closure')
                        for flag in ('-I', str(project / GSP / name))]
            commands = [(MEMORY, memory, before['command'], old_memory_obj)]
            for name in (RECORD, CANCEL):
                row = next(row for row in matrices['project'] if row['source'] == name)
                commands.append((name, project / name, row['command'], row['object']))
            for name, source, original_command, old_object in commands:
                obj = work / (source.stem + '.o')
                dep = obj.with_suffix('.d')
                original_command = original_command[:]
                prefix = original_command[:original_command.index('-c')]
                if '-MD' in prefix:
                    prefix.remove('-MD')
                if '-MF' in prefix:
                    index = prefix.index('-MF'); del prefix[index:index + 2]
                prefix = [value.replace(str(genuine / 'project'), str(project)).replace(
                    str(cached / 'project'), str(project)) for value in prefix]
                command = [*prefix, *includes, '-MD', '-MF', str(dep), '-c', str(source), '-o', str(obj)]
                compiler_sha = sha(Path(command[0]))
                execute(command, obj.with_suffix('.log'), cwd=cached / 'source/src/nvidia')
                deps = stack.check.dependency_hashes(dep, cached / 'source/src/nvidia')
                require(str(source) in deps, 'Dependency capture omitted actual current source')
                replacements.append(dict(source=name, path=str(source), source_sha256=sha(source),
                    object=str(obj), object_sha256=sha(obj), old_object=old_object, command=command,
                    compiler_sha256=compiler_sha, dependency_sha256=deps))
            binary = work / 'shutdown-global-check'
            link = before['link_command'][:]
            for row in replacements:
                require(link.count(row['old_object']) == 1, 'A current source lacks one exact replaced object')
                link[link.index(row['old_object'])] = row['object']
            link[link.index('-o') + 1] = str(binary)
            execute(link, work / 'link.log')
            binary_sha = sha(binary)
            observations = []
            for index, view in enumerate(before['observations']):
                actual = json.loads(execute([binary, *view['case']], work / ('case-%03d.log' % index),
                    environment=environment).stdout)
                require(actual == {key: value for key, value in view.items() if key != 'case'},
                    'Genuine global constructor/allocation/result behavior changed: ' + str(view['case']))
                observations.append({'case': view['case'], **actual})
            for row in replacements:
                verify_bindings({row['path']: row['source_sha256'], row['object']: row['object_sha256'],
                    row['command'][0]: row['compiler_sha256'], **row['dependency_sha256']},
                    'Fresh current source/object/compiler/dependencies changed')
            require(sha(binary) == binary_sha, 'Executed current integration binary changed')
            verify_bindings({path: object_bindings[path] for path in linked}, 'Reused linked object changed')
            stack.previous_checker.cached.matrix(cached, variant, historical)
            report['variants'][variant] = dict(status='passed', positive_cases=len(observations),
                assertions=sum(view['checks'] for view in observations),
                all_original_observations_identical=True, freshly_compiled_units=replacements,
                fresh_units=3, reused_link_objects=len(linked) - 3, binary_sha256=binary_sha,
                link_command=link, observations=observations)
            write(output / 'results.json', report)
        verify_parents()
        verify_bindings(inputs, 'Current integration control inputs changed')
        require(composer.inventory(project) == project_inventory, 'CPU fixture project/header tree changed')
        preparation.verify(canonical, integrated, base, child)
        report['status'] = 'passed-current-shutdown-record-cancellation-global-cpu-integration'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write(output / 'results.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('composition', 'base', 'integrated-base', 'canonical-parent', 'stack-controls',
                 'genuine-controls', 'cached-controls', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'cases': {key: row['positive_cases']
        for key, row in result['variants'].items()}}))
