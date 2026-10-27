#!/usr/bin/env python3
"""Run actual transformed attach/constructor bodies and the private witness TU."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import resource
import shlex
import shutil
import subprocess
import sys
import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHARED = ROOT / 'packages/nvidia-gsp-bootstrap/cancellation/prepare_wait_candidates.py'
SHARED_SHA = 'f8e0099f904b5e1a756e628985ef991c9a09475214f52a38c921ccc5df6de471'
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record'
CASES = ('gpu_skip', 'class_info', 'dynamic_create', 'concrete_null', 'child_cast',
    'engstate_cast', 'base86', 'engine86', 'engine86_not_gsp', 'missing', 'child_success',
    'gpu_foreign_nv', 'gpu_null_nv',
    'attach_create', 'dpc', 'os', 'caps', 'post', 'conf', 'attach_success',
    'nested_first', 'lifecycle_unbegun', 'active_read', 'early_original_read',
    'sticky_read', 'repeated_begin', 'foreign_update', 'irq_update', 'stale_update',
    'wrong_nv_update', 'stale_read', 'foreign_read', 'irq_read', 'bad_getter',
    'invalid_notes', 'engine_error_missing')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text, name, declaration):
    first, last = prepare.function_span(text, name)
    require(text[:first].endswith(declaration + '\n'), 'Actual return declaration changed: ' + name)
    return declaration + '\n' + text[first:last] + '\n'


def deps(path):
    return {str(Path(p).resolve(strict=True)): sha(Path(p).resolve(strict=True))
        for p in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1])}


def changed(text, before, after, count=1):
    require(text.count(before) == count, 'Actual mutation anchor changed: ' + before)
    return text.replace(before, after)


def run(args):
    require(args.host_control, 'Explicit --host-control is required for CPU endpoints')
    require(sha(SHARED) == SHARED_SHA, 'Shared function-span parser changed')
    source = args.input_source.resolve(strict=True)
    project = args.input_project.resolve(strict=True)
    out = args.output.absolute()
    require(not out.exists() and not out.is_relative_to(source) and
        not source.is_relative_to(out) and not out.is_relative_to(project) and
        not project.is_relative_to(out), 'A fresh nonoverlapping witness output is required')
    originals = {name: (source / name).read_text() for name in prepare.ORIGINAL_INPUTS}
    transformed = prepare.original_transforms(originals)
    if args.composed_source:
        final = args.composed_source.resolve(strict=True)
        require(all((final / name).read_text() == body for name, body in transformed.items()),
                'Actual final sources differ from exact witness transforms')
    refused = []
    for variant in ({}, dict(originals, unknown='extra'),
                    dict(originals, **{prepare.GPU: originals[prepare.GPU] + '\n'})):
        try:
            prepare.original_transforms(variant)
        except ValueError:
            refused.append(True)
        else:
            raise ValueError('An altered witness source input was accepted')
    contract = json.loads((HERE / 'SOURCE-CONTRACT.json').read_bytes())
    for name, digest in contract['CPU_header_sha256'].items():
        require(sha(project / name) == digest, 'Actual CPU witness header changed: ' + name)
    mode = contract['GSP_mode_macro_source']
    require(sha(source / mode['path']) == mode['sha256'] and
            mode['actual_macro'] in (source / mode['path']).read_text().splitlines(),
            'The actual CPU-field-only GSP mode macro changed')
    require(sha(source / mode['feature_path']) == mode['feature_sha256'] and
            mode['feature_macro'] in (source / mode['feature_path']).read_text().splitlines(),
            'The actual selected GSP mode feature changed')
    identity = contract['OS_identity_source']
    require(sha(source / identity['macro_path']) == identity['macro_sha256'] and
            identity['actual_macro'] in (source / identity['macro_path']).read_text(),
            'The actual Unix GPU-to-OS identity macro changed')
    require(sha(source / identity['field_path']) == identity['field_sha256'] and
            identity['actual_field'] in [line.strip() for line in
                (source / identity['field_path']).read_text().splitlines()],
            'The actual generic GPU OS identity field changed')
    compiler = args.cc.expanduser().absolute()
    target = compiler.resolve(strict=True)
    require(target.is_file() and os.access(compiler, os.X_OK), 'Executable C compiler required')
    helper_hashes = {str(p.relative_to(ROOT)): sha(p) for p in
        (HERE / 'prepare.py', *(HERE / n for n in prepare.SOURCE_FILES),
         *prepare.COMPANIONS.values())}
    out.mkdir(parents=True)
    fixture_project = out / 'fixture-project'
    shutil.copytree(project, fixture_project)
    for name, path in prepare.COMPANIONS.items():
        p = fixture_project / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(path.read_bytes())
    gpu = function(transformed[prepare.GPU], 'gpuCreateObject', 'static NV_STATUS')
    manager = function(transformed[prepare.MANAGER], 'gpumgrAttachGpu', 'NV_STATUS')
    witness = (HERE / 'S540AttachFailureWitness.c').read_text()
    template = (HERE / 'tests/check_witness.c.inc').read_text()
    require('#define NV_GET_NV_STATE' not in template,
            'The CPU fixture must not mask an unavailable Unix platform macro')
    require(identity['observer_expression'] in gpu and 'NV_GET_NV_STATE' not in gpu,
            'The actual generic GPU witness must use its OS identity field')
    template = changed(template, '#define IS_GSP_CLIENT(gpu) ((gpu)->isGspClient)',
                       mode['feature_macro'] + '\n' + mode['actual_macro'])
    record = dict(format=1, status='running',
        scope='actual-transformed-original-C-bodies-and-separate-private-witness-TU-with-CPU-endpoints',
        original_input_sha256={name: sha(source / name) for name in originals},
        transformed_sha256={name: hashlib.sha256(body.encode()).hexdigest()
                            for name, body in transformed.items()},
        helper_sha256=helper_hashes, exact_input_refusals=len(refused),
        compiler_invocation_path=str(compiler), compiler_path=str(target), compiler_sha256=sha(target),
        variants={}, negative_controls={}, commands=[], dependency_sha256={},
        actual_selected_C_bodies_executed=True, full_original_driver_execution=False,
        native_Darwin_compilation=False, GPU_execution=False, physical_release_authorized=False,
        admission_or_retention_relaxed=False, leak_sanitizer_enabled=False,
        leak_sanitizer_reason='Managed host task inventory unavailable; explicit endpoint ownership is checked.')
    report_path = out / 'results.json'
    environment = dict(os.environ,
        ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def write():
        report_path.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')

    def execute(command, log):
        result = subprocess.run([str(p) for p in command], capture_output=True,
            text=True, env=environment, timeout=120)
        log.write_text(result.stdout + result.stderr)
        record['commands'].append([str(p) for p in command])
        return result

    def variant(label, selected_gpu, selected_manager, selected_witness, instrumentation, cases, negative=False):
        work = out / label
        work.mkdir()
        unit = template
        for marker, body in (('@GPU_BODY@', selected_gpu), ('@GPUMGR_BODY@', selected_manager)):
            require(unit.count(marker) == 1, 'Exactly one actual body marker required')
            unit = unit.replace(marker, body)
        fixture = work / 'check-witness.c'
        fixture.write_text(unit)
        production = fixture_project / prepare.UNIT
        saved = production.read_bytes()
        try:
            production.write_text(selected_witness)
            binary = work / 'check-witness'
            include = [fixture_project / 'packages', fixture_project / RECORD,
                       fixture_project / prepare.DIRECTORY]
            flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                     '-Wno-unused-function', *instrumentation,
                     *[x for p in include for x in ('-I', str(p))]]
            objects = []
            for basename, input_path in (('fixture', fixture), ('production', production)):
                obj, dep = work / (basename + '.o'), work / (basename + '.d')
                result = execute([compiler, *flags, '-MD', '-MF', dep, '-c', input_path, '-o', obj],
                                 work / (basename + '-compile.log'))
                require(result.returncode == 0, 'Witness CPU compile failed: ' + str(work) + '\n' + result.stderr[-4000:])
                record['dependency_sha256'][label + '-' + basename] = deps(dep)
                objects.append(obj)
            result = execute([compiler, *instrumentation, *objects, '-o', binary], work / 'link.log')
            require(result.returncode == 0, 'Witness CPU link failed: ' + result.stderr[-2000:])
            checks = 0
            for case in cases:
                result = execute([binary, case], work / (case + '.log'))
                if negative:
                    require(result.returncode != 0, 'Actual witness mutant survived: ' + label)
                    return dict(killed=True, case=case, returncode=result.returncode,
                                binary_sha256=sha(binary))
                require(result.returncode == 0, 'Actual witness case failed: ' + case + '\n' + result.stderr[-2000:])
                view = json.loads(result.stdout)
                require(view['status'] == 'passed' and view['checks'] > 0,
                        'No successful witness observations: ' + case)
                checks += view['checks']
            return dict(status='passed', cases=len(cases), checks=checks, binary_sha256=sha(binary))
        finally:
            production.write_bytes(saved)

    write()
    try:
        record['variants']['plain'] = variant('plain', gpu, manager, witness, [], CASES)
        record['variants']['fatal-sanitizers'] = variant('fatal-sanitizers', gpu, manager, witness,
            ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'], CASES)
        require(record['variants']['plain']['checks'] == record['variants']['fatal-sanitizers']['checks'],
                'Plain and fatal sanitizer observations differ')
        mutants = (
            ('lost-first-class', gpu, manager, changed(witness, 'witness.firstClassId = classId;', 'witness.firstClassId = (classId ^ classId);'), 'base86'),
            ('lost-first-constructor-stage', gpu, manager, changed(witness, 'witness.firstCtorStage = stage;', 'witness.firstCtorStage = 0U;'), 'base86'),
            ('lost-first-status', gpu, manager, witness.replace('witness.firstStatus = status;', 'witness.firstStatus = NV_OK;', 1), 'engine86'),
            ('outer-overwrites-first', gpu, manager, changed(witness, 'status == NV_OK || witness.firstFailureValid ||', 'status == NV_OK ||', 2), 'engine_error_missing'),
            ('stale-update-accepted', gpu, manager, witness.replace('current.generation != witness.generation ||', 'NV_FALSE ||', 1), 'stale_update'),
            ('early-getter-accepted', gpu, manager, changed(witness, '!current.originalReturned ||\n        current.originalInFlight ||', 'NV_FALSE ||'), 'early_original_read'),
            ('forged-missing-observation', gpu, manager, changed(witness, 'witness.observedMask = mask;', 'witness.observedMask = mask | S540_ATTACH_OBS_MISSING;'), 'base86'),
            ('unsupported-normalized', changed(gpu, '        // Retain the published child slot and its parent ownership.\n        return status;',
                '        // Retain the published child slot and its parent ownership.\n        return status == NV_ERR_NOT_SUPPORTED ? NV_OK : status;'), manager, witness, 'base86'),
            ('failed-attach-not-completed', gpu, changed(manager, '    s540AttachWitnessComplete(pAttachArg->pOsAttachArg);\n    return status;', '    return status;'), witness, 'post'),
            ('foreign-update-accepted', gpu, manager, changed(witness, 'current.state != S540_FIRST_GLOBAL_READY || !ordinaryMaster(current.masterThread))', 'current.state != S540_FIRST_GLOBAL_READY)'), 'foreign_update'),
            ('gpu-identity-forged', changed(gpu, identity['observer_expression'], '(&nvIdentity)',
                gpu.count(identity['observer_expression'])), manager, witness, 'gpu_foreign_nv'))
        for label, selected_gpu, selected_manager, selected_witness, case in mutants:
            record['negative_controls'][label] = variant(label, selected_gpu, selected_manager,
                selected_witness, [], (case,), True)
        for name, digest in helper_hashes.items():
            require(sha(ROOT / name) == digest, 'Bound witness helper changed during controls')
        for bindings in record['dependency_sha256'].values():
            # Mutant production copies are restored; the originals are bound above.
            for name, digest in bindings.items():
                if name != str((fixture_project / prepare.UNIT).resolve()):
                    require(sha(name) == digest, 'Bound witness header/fixture changed during controls')
        record['status'] = 'passed-actual-attach-constructor-and-private-witness-CPU-controls'
        return record
    except Exception as error:
        record.update(status='failed', error=str(error))
        raise
    finally:
        write()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input-source', 'input-project', 'output', 'cc'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--composed-source', type=Path)
    parser.add_argument('--host-control', action='store_true')
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], variants=result['variants'],
        mutants_killed=len(result['negative_controls']))))
