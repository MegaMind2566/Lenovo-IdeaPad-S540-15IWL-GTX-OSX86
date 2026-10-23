#!/usr/bin/env python3
"""Execute actual retained stop dispatch/helper and complete CPU Services TU."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as composer


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(directory):
    spec = importlib.util.spec_from_file_location(directory.replace('-', '_'), HERE.parent / directory / 'prepare.py')
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


def materialize(base, project):
    shutil.copytree(base / 'project', project)
    modules = (module('prospective-pm-event-closure'), module('prospective-runtime-coordinator'), prepare)
    for transform in modules:
        changed = transform.transforms({n: (project / n).read_text() for n in transform.INPUTS})
        for name, text in changed.items(): (project / name).write_text(text)
        for name, source in transform.COMPANIONS.items():
            path = project / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(source.read_bytes())


def run(args):
    base = args.base.resolve(strict=True); composer.verify_composition(base)
    if sha(base / 'composition.json') != '72b7d5a5d93504218e8a7953d79c90c1609e4580c55922deb2ec5dab13de24d8':
        raise ValueError('Exact reviewed shutdown parent required')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('Fresh isolated retained stop control directory required')
    output.mkdir(parents=True); project = output / 'project'; materialize(base, project)
    includes = [project / 'packages', project / prepare.DIRECTORY,
        project / 'packages/nvidia-darwin-services/src',
        project / 'packages/nvidia-gsp-bootstrap/src',
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record',
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/services']
    flags = ['-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-ffunction-sections', '-fdata-sections', *[p for path in includes for p in ('-I', str(path))]]
    report = dict(format=1, status='running', parent_composition_sha256=sha(base / 'composition.json'),
        source_sha256={str(path.relative_to(ROOT)): sha(path) for path in sorted(HERE.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts},
        compiler_sha256={str(args.cxx.resolve(strict=True)): sha(args.cxx.resolve(strict=True))},
        output_source_sha256={name: sha(project / name) for name in prepare.INPUTS},
        commands=[], dependency_sha256={}, variants={}, negative_controls={},
        native_darwin_compilation=False, hardware_executed=False,
        physical_release_authorized=False, pm_acknowledgement_authorized=False)
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')

    def record(): (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def execute(command, log, expected=0):
        result = subprocess.run([str(x) for x in command], text=True, capture_output=True, timeout=180, env=environment)
        log.write_text(result.stdout + result.stderr); report['commands'].append([str(x) for x in command])
        if expected is not None and result.returncode != expected:
            raise ValueError('Retained stop control failed: ' + str(log) + '\n' + result.stderr[-4000:])
        return result

    def compile_one(source, obj, selected):
        dep = obj.with_suffix('.d')
        execute([args.cxx, *selected, '-MD', '-MF', dep, '-c', source, '-o', obj], obj.with_suffix('.compile.log'))
        for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve(strict=True); digest = sha(path)
            if report['dependency_sha256'].setdefault(str(path), digest) != digest:
                raise ValueError('Control dependency changed: ' + str(path))

    def variant(label, instrumentation, expected=0):
        work = output / label; work.mkdir()
        boot = (project / prepare.BOOT).read_text()
        begin = boot.index('    void publishRetainedStop(')
        end = boot.index('    NV_STATUS stop() {', begin)
        (work / 'actual-owner-stop.inc').write_text(boot[begin:end])
        first, last = prepare.function_span(boot, 'stop')
        body = boot[first:last]; marker = '        const auto cancellation ='
        if body.count(marker) != 1: raise ValueError('Exact normal-stop boundary changed')
        # The retained dispatch prefix is actual source. The unrelated ordinary
        # release path is deliberately outside this CPU retained-only fixture.
        prefix = body[:body.index(marker)]
        (work / 'actual-retained-dispatch.inc').write_text('NV_STATUS ' + prefix + '        return status;\n    }\n')
        objects = []
        for name, source in [('services', project / prepare.SERVICES), ('control', HERE / 'tests/check_stop.cpp')]:
            obj = work / (name + '.o'); compile_one(source, obj, [*flags, '-I', str(work), *instrumentation]); objects.append(obj)
        binary = work / 'control'
        execute([args.cxx, *instrumentation, '-pthread', *objects, '-Wl,--gc-sections', '-o', binary], binary.with_suffix('.link.log'))
        result = execute([binary], binary.with_suffix('.run.log'), expected=expected)
        return binary, result

    record()
    try:
        for label, instrumentation in [('plain', []), ('sanitized', [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])]:
            binary, result = variant(label, instrumentation)
            view = json.loads(result.stdout)
            if view['status'] != 'passed' or not view['checks']: raise ValueError('No successful actual stop-body observations')
            report['variants'][label] = dict(view, binary_sha256=sha(binary))
        mutants = [
            ('old_retention_early_return', prepare.BOOT, 'return stopRetainedExperiment();', 'return NV_ERR_IN_USE;'),
            ('service_first_failure_skips_other_producers', prepare.SERVICES,
                '    observe(s540FirstTxnQueueSeal(binding.device, nv, generation));',
                '    if (first != NV_OK) return first;\n    observe(s540FirstTxnQueueSeal(binding.device, nv, generation));'),
            ('missing_post_protocol_lock_observation', prepare.BOOT,
                'result.locksStatus = s540FirstTxnOriginalLocksReleased(nv);\n            result.locksReleased = result.locksStatus == NV_OK;\n            observe(result.locksStatus);\n            if (result.locksReleased) {\n            result.closingStatus',
                'result.locksStatus = NV_OK;\n            result.locksReleased = true;\n            observe(result.locksStatus);\n            if (result.locksReleased) {\n            result.closingStatus'),
            ('false_physical_release_after_stop', prepare.BOOT,
                '        result.status = result.firstError != NV_OK ?',
                '        result.physicalReleaseAuthorized = NV_TRUE;\n        result.status = result.firstError != NV_OK ?')]
        for label, name, before, after in mutants:
            source = project / name; original = source.read_text()
            if original.count(before) != 1: raise ValueError('Exact stop mutation point changed: ' + label)
            source.write_text(original.replace(before, after))
            successful = report['dependency_sha256']; report['dependency_sha256'] = {}
            try:
                binary, result = variant('negative-' + label, [], expected=None)
                if result.returncode == 0: raise ValueError('Retained stop mutant escaped: ' + label)
                report['negative_controls'][label] = dict(rejected=True, returncode=result.returncode,
                    binary_sha256=sha(binary), dependency_sha256=report['dependency_sha256'])
            finally:
                source.write_text(original); report['dependency_sha256'] = successful
        for name, digest in report['dependency_sha256'].items():
            if sha(name) != digest: raise ValueError('Bound stop control source changed: ' + name)
        report['status'] = 'passed-actual-retained-stop-and-services-controls'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error)); raise
    finally:
        record()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cxx', required=True, type=Path)
    args = parser.parse_args(); result = run(args)
    print(json.dumps(dict(status=result['status'], variants=result['variants'], negative_controls=list(result['negative_controls']))))
