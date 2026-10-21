#!/usr/bin/env python3
"""Complete GM107 config-write bodies and genuine PM cancellation CPU checks."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import prepare


def sha(path):
    if path.is_symlink():
        raise ValueError('GPU CPU input symlink refused: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(command, log, *, expected=0, environment=None):
    result = subprocess.run([str(value) for value in command], text=True,
        capture_output=True, timeout=180, env=environment)
    log.write_text(result.stdout + result.stderr)
    if result.returncode != expected:
        raise ValueError('Actual GPU CPU command failed: ' + str(log) + '\n' + result.stderr[-7000:])
    return result


def dep_hashes(path, cwd):
    result = {}
    for name in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1]):
        source = Path(name)
        source = (source if source.is_absolute() else cwd / source).resolve(strict=True)
        result[str(source)] = sha(source)
    return result


def run(args):
    base = args.base.resolve(strict=True)
    output = args.output.resolve()
    cc = args.cc.resolve(strict=True)
    if output.exists() or output.is_relative_to(HERE):
        raise ValueError('A fresh isolated GPU controls output is required')
    if sha(base / 'composition.json') != '40f0fd1fc279421464c14f9b98f7fa84f6850e6fafb61d46aa60663ce471dd4c':
        raise ValueError('Exact operational-successor-2 composition is required')
    if sha(base / 'project-compilation.json') != '5317a8cccf5189be42da338a8c0f7b2f1b0de30950c79d0679d59292b3f37a0e':
        raise ValueError('Authenticated operational-successor-2 compiler command report is required')
    output.mkdir(parents=True)
    parent_check = load('s540_dma_gpu_materializer', HERE / 'check.py')
    project, pm = parent_check.materialize(base, output)
    source = output / 'source' / prepare.GPU
    extractor = load('s540_dma_original_body_extractor',
        ROOT / 'packages/nvidia-gsp-bootstrap/prospective-irq-callback-closure/rc/check_actual_1hz.py')
    bodies = ''.join(extractor.body(source.read_text(), name) for name in (
        'gpuWriteBusConfigReg_GM107', 'gpuWriteFunctionConfigRegEx_GM107'))
    include = output / 'actual-gpu-config-bodies.inc'
    include.write_text(bodies)
    inputs = [Path(__file__), HERE / 'tests/check_gpu.c', HERE / 'check.py',
        HERE / 'prepare.py', HERE / 'cleanup-mask.c.inc', HERE / 'S540NvidiaDmaProducer.h',
        pm.HERE / 'prepare.py', pm.HERE / 'commit-api.c.inc', *pm.COMPANIONS.values(),
        base / 'composition.json', base / 'project-compilation.json',
        base / 'S540ComposedNamespace.h', extractor.HERE / 'check_actual_1hz.py']
    bindings = {str(path): sha(path) for path in inputs}
    generated = {str(source): sha(source), str(include): sha(include),
        str(project / pm.CANCEL): sha(project / pm.CANCEL)}
    before_project = parent_check.inventory(project)
    compiler_hash = sha(cc)
    composition = json.loads((base / 'composition.json').read_text())
    original_inventory = composition['original_files']
    manifest = json.loads((base / 'project-compilation.json').read_text())
    context = next(row for row in manifest['results'] if row['source'].endswith('/S540NvidiaGspContext.c'))
    if context['sha256'] != composition['project_files'][context['source']]['sha256']:
        raise ValueError('Recorded original-layout compiler row differs from the authenticated composition')
    command = context['command']
    if (Path(command[0]).resolve(strict=True) != cc or compiler_hash !=
            manifest['compiler_and_builder_file_sha256'][command[0]]):
        raise ValueError('GPU CPU compiler differs from the authenticated recorded original profile')
    boundary = command.index('-target')
    original_flags = command[1:boundary]
    # Keep the captured original profile and actual NVIDIA layout headers.
    # Relocate only project companions to this exact PM/DMA materialization.
    original_flags = [value.replace(str(base / 'project'), str(project)) for value in original_flags]
    remove = {'-msoft-float', '-mno-red-zone', '-mcmodel=kernel', '-mno-mmx',
        '-mno-sse', '-mno-sse2', '-mno-3dnow', '-fno-pic'}
    original_flags = [value for value in original_flags if value not in remove]
    original_flags += ['-fPIC', '-mcmodel=small', '-U__linux__', '-U__linux']
    directories = [project / prepare.PREFIX, project / pm.DIRECTORY, output,
        project / 'packages', project / 'packages/nvidia-darwin-services/src',
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps']
    shared = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
        '-Wno-missing-field-initializers',
        '-ffunction-sections', '-fdata-sections',
        *[flag for directory in directories for flag in ('-I', str(directory))]]
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    report = {'format': 1, 'status': 'running', 'source_sha256': bindings,
        'generated_source_sha256': generated, 'base_composition_sha256': sha(base / 'composition.json'),
        'original_context_compile_row_source_sha256': context['sha256'],
        'original_full_function_bodies': ['gpuWriteBusConfigReg_GM107', 'gpuWriteFunctionConfigRegEx_GM107'],
        'actual_original_layout_headers': True, 'actual_pm_cancellation_translation_unit': True,
        'explicit_fixtures': ['MMIO register store endpoint', 'log/assert endpoint',
            'current thread and clock endpoints', 'unused IRQ-record endpoint refusal'],
        'hardware_execution': False, 'whole_mmio_producer_closure_proven': False,
        'whole_dma_stop_proven': False, 'pm_30_second_shutdown_bound_proven': False,
        'original_entry_admission': False, 'native_darwin_compilation': False, 'variants': {}}
    write(output / 'gpu-controls.json', report)
    try:
        for variant in args.variants:
            work = output / variant
            work.mkdir()
            sanitizers = (['-fsanitize=address,undefined,function', '-fno-sanitize-recover=all',
                '-fno-omit-frame-pointer'] if variant == 'sanitized' else [])
            cancel_object = work / 'cancellation.o'
            cancel_dep = cancel_object.with_suffix('.d')
            cancel_command = [str(cc), '-std=c11', *shared, *sanitizers, '-MD', '-MF', str(cancel_dep),
                '-c', str(project / pm.CANCEL), '-o', str(cancel_object)]
            execute(cancel_command, work / 'cancellation-compile.log')
            cancellation_hash = sha(cancel_object)
            binary = work / 'gpu-body-check'
            gpu_dep = work / 'gpu.d'
            gpu_command = [str(cc), *original_flags, *shared, *sanitizers, '-MD', '-MF', str(gpu_dep),
                str(HERE / 'tests/check_gpu.c'), str(cancel_object), '-Wl,--gc-sections', '-o', str(binary)]
            execute(gpu_command, work / 'gpu-compile.log')
            binary_hash = sha(binary)
            observations = []
            for scenario in range(15):
                raw = execute([binary, scenario], work / ('scenario-%02d.log' % scenario), environment=environment)
                view = json.loads(raw.stdout)
                if view['failures']:
                    raise ValueError('Actual original GPU body assertions failed')
                observations.append(view)
            # Replace only the actual bus BME guard, leaving the genuine
            # cancellation implementation and function ABI unchanged.
            mutant = work / 'mutant'
            mutant.mkdir()
            anchor = '    if (s540DmaConfigWriteEnablesBusMaster(index, 4, value)) {'
            if bodies.count(anchor) != 1:
                raise ValueError('Exact guarded original bus body is required')
            (mutant / include.name).write_text(bodies.replace(anchor, '    if (NV_FALSE) {'))
            unsafe = work / 'unsafe-bme-enable'
            unsafe_dep = work / 'unsafe.d'
            unsafe_command = [str(cc), *original_flags, '-I', str(mutant), *shared, *sanitizers,
                '-MD', '-MF', str(unsafe_dep), str(HERE / 'tests/check_gpu.c'), str(cancel_object),
                '-Wl,--gc-sections', '-o', str(unsafe)]
            execute(unsafe_command, work / 'unsafe-compile.log')
            unsafe_hash = sha(unsafe)
            negative = execute([unsafe, 2], work / 'unsafe-regression.log', expected=1, environment=environment)
            negative_view = json.loads(negative.stdout)
            if not negative_view['failures']:
                raise ValueError('Required real BME guard mutation was not detected')
            dependency_bindings = {}
            for path in (cancel_dep, gpu_dep, unsafe_dep):
                dependency_bindings.update(dep_hashes(path, ROOT))
            for name, digest in dependency_bindings.items():
                path = Path(name)
                if path.is_relative_to(base / 'source'):
                    relative = path.relative_to(base / 'source').as_posix()
                    if relative not in original_inventory or original_inventory[relative]['sha256'] != digest:
                        raise ValueError('Compiler-observed original header differs from authenticated parent: ' + name)
            if (sha(binary) != binary_hash or sha(unsafe) != unsafe_hash or
                    sha(cancel_object) != cancellation_hash or sha(cc) != compiler_hash):
                raise ValueError('Executed GPU CPU binary/compiler/auxiliary changed')
            report['variants'][variant] = {'status': 'passed', 'scenarios': len(observations),
                'checks': sum(row['checks'] for row in observations), 'observations': observations,
                'binary_sha256': binary_hash, 'cancellation_object_sha256': cancellation_hash,
                'compiler_sha256': compiler_hash, 'commands': [cancel_command, gpu_command, unsafe_command],
                'dependencies_sha256': dependency_bindings, 'unsafe_guard_mutation_detected': True,
                'mutation_result': negative_view, 'mutation_binary_sha256': unsafe_hash,
                'original_header_dependencies_authenticated_against_composition': True,
                'compiler_binary_auxiliary_pre_and_post_bindings_verified': True}
            write(output / 'gpu-controls.json', report)
        if parent_check.inventory(project) != before_project:
            raise ValueError('PM/DMA materialized companion inputs changed during GPU controls')
        for name, digest in {**bindings, **generated}.items():
            if sha(Path(name)) != digest:
                raise ValueError('GPU body control source changed: ' + name)
        if sha(cc) != compiler_hash:
            raise ValueError('GPU CPU compiler changed during controls')
        for variant in report['variants'].values():
            for name, digest in variant['dependencies_sha256'].items():
                if sha(Path(name)) != digest:
                    raise ValueError('Compiler-observed GPU dependency changed: ' + name)
        report['status'] = 'passed-complete-original-gm107-bme-commit-bodies'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write(output / 'gpu-controls.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'output', 'cc'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--variants', nargs='+', choices=('plain', 'sanitized'), default=['plain', 'sanitized'])
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'variants': {
        key: {'checks': value['checks'], 'scenarios': value['scenarios']} for key, value in result['variants'].items()}}))
