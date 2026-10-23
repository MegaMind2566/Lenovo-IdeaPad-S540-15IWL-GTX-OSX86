#!/usr/bin/env python3
"""Execute whole actual cancellation/Power TUs with genuine PM ordering controls."""
from pathlib import Path
import argparse
import hashlib
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    base = args.base.resolve(strict=True)
    composer.verify_composition(base)
    if sha(base / 'composition.json') != '72b7d5a5d93504218e8a7953d79c90c1609e4580c55922deb2ec5dab13de24d8':
        raise ValueError('Exact reviewed shutdown parent required')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(base) or base.is_relative_to(output):
        raise ValueError('Fresh isolated PM event control output required')
    output.mkdir(parents=True)
    values = {name: (base / 'project' / name).read_text() for name in prepare.INPUTS}
    changed = prepare.transforms(values)
    project = output / 'project'
    shutil.copytree(base / 'project', project)
    for name, text in changed.items():
        (project / name).write_text(text)
    for name, source in prepare.COMPANIONS.items():
        path = project / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
    includes = [project / 'packages', project / 'packages/nvidia-gsp-bootstrap/platform',
        project / prepare.DIRECTORY,
        project / 'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure',
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps']
    common = ['-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-DS540_GSP_BOOTSTRAP_NATIVE_TEST=1', '-ffunction-sections', '-fdata-sections',
        *[part for directory in includes for part in ('-I', str(directory))]]
    report = dict(format=1, status='running', parent_composition_sha256=sha(base / 'composition.json'),
        source_sha256={str(path.relative_to(ROOT)): sha(path) for path in sorted(HERE.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts},
        output_source_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in changed.items()},
        compiler_sha256={str(p.resolve(strict=True)): sha(p.resolve(strict=True)) for p in (args.cc, args.cxx)},
        commands=[], dependency_sha256={}, variants={}, negative_controls={},
        original_entry_admission=False, hardware_stop_proven=False, physical_release_authorized=False,
        pm_acknowledgement_authorized=False, kernel_execution='not_tested')
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')

    def record():
        (output / 'results.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def execute(command, log, *, expected=0):
        result = subprocess.run([str(x) for x in command], text=True, capture_output=True,
            timeout=180, env=environment)
        log.write_text(result.stdout + result.stderr)
        report['commands'].append([str(x) for x in command])
        if expected is not None and result.returncode != expected:
            raise ValueError('PM control failed: ' + str(log) + '\n' + result.stderr[-4000:])
        return result

    def compile_one(source, obj, compiler, flags):
        dep = obj.with_suffix('.d')
        execute([compiler, *flags, '-MD', '-MF', dep, '-c', source, '-o', obj], obj.with_suffix('.compile.log'))
        for item in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(item).resolve(strict=True); digest = sha(path)
            if report['dependency_sha256'].setdefault(str(path), digest) != digest:
                raise ValueError('Compiler dependency changed during controls: ' + str(path))

    def variant(label, instrumentation, cancellation=None, power=None, expected=0):
        work = output / label; work.mkdir()
        # Compile the exact live kernel callback body as well as the complete
        # native Power TU. Only IOKit lock/wakeup primitives are fixture seams.
        callback_text = Path(power or project / prepare.POWER).read_text()
        first, last = prepare.function_span(callback_text, 'S540NvidiaGspPowerService::setPowerState')
        callback = 'IOReturn ' + callback_text[first:last].replace(
            'S540NvidiaGspPowerService::setPowerState', 'CallbackFixture::setPowerState', 1) + '\n'
        (work / 'actual-callback.inc').write_text(callback)
        sources = [('cancellation', cancellation or project / prepare.CANCEL, args.cc, '-std=c11'),
            ('power', power or project / prepare.POWER, args.cxx, '-std=c++17'),
            ('control', HERE / 'tests/check_pm_event.cpp', args.cxx, '-std=c++17')]
        objects = []
        for name, source, compiler, language in sources:
            obj = work / (name + '.o')
            compile_one(source, obj, compiler, [language, *common, '-I', str(work), *instrumentation]); objects.append(obj)
        binary = work / 'control'
        execute([args.cxx, *instrumentation, '-pthread', *objects, '-Wl,--gc-sections', '-o', binary],
            binary.with_suffix('.link.log'))
        result = execute([binary], binary.with_suffix('.run.log'), expected=expected)
        return binary, result

    record()
    try:
        for label, instrumentation in [('plain', []), ('sanitized', [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'])]:
            binary, result = variant(label, instrumentation)
            observed = json.loads(result.stdout)
            if observed['status'] != 'passed' or not observed['checks']:
                raise ValueError('PM fixture did not report successful real-body checks')
            report['variants'][label] = dict(observed, binary_sha256=sha(binary))
        negatives = [
            ('unbind_without_pm_hold', prepare.CANCEL,
                'CAPTURE_BUSY | COMMIT_BUSY | POWER_COUPLED)', 'CAPTURE_BUSY | COMMIT_BUSY)'),
            ('delayed_hook_without_atomic_close', prepare.POWER,
                'closed = data->protocol.closeCancellation(eventNs);', '(void)eventNs; closed = NV_OK;'),
            ('actual_kernel_callback_without_atomic_close', prepare.POWER,
                'const NV_STATUS closed = post ? protocol.closeCancellation(eventNs) : NV_STATUS(NV_OK);',
                'const NV_STATUS closed = NV_OK;'),
            ('invented_invalid_clock_deadline', prepare.CANCEL,
                'deadline = !clockValid ? 0 :', 'deadline = !clockValid ? PM_BUDGET_NS :'),
            ('destroy_coupled_power_owner', prepare.POWER,
                ' || impl_->protocol.cancellationCoupled()', '')]
        for label, name, before, after in negatives:
            source = project / name
            original = source.read_text()
            if original.count(before) != 1: raise ValueError('Exact mutation point changed: ' + label)
            source.write_text(original.replace(before, after))
            # This changed file is compiled again; its previous dependency
            # digest is deliberately isolated from the successful run binding.
            successful_dependencies = report['dependency_sha256']
            report['dependency_sha256'] = {}
            try:
                binary, result = variant('negative-' + label, [], expected=None)
                if result.returncode == 0: raise ValueError('Mutant escaped actual-body controls: ' + label)
                report['negative_controls'][label] = dict(rejected=True, returncode=result.returncode,
                    binary_sha256=sha(binary), dependency_sha256=report['dependency_sha256'])
            finally:
                source.write_text(original)
                report['dependency_sha256'] = successful_dependencies
        # A changed ancestor must be refused before source replacement.
        drift = dict(values); drift[prepare.POWER] += '\n'
        try:
            prepare.transforms(drift)
        except ValueError:
            report['negative_controls']['changed_parent_bytes'] = dict(rejected=True)
        else:
            raise ValueError('PM transform accepted changed ancestor bytes')
        for name, digest in report['dependency_sha256'].items():
            if sha(Path(name)) != digest: raise ValueError('Control dependency changed: ' + name)
        report['status'] = 'passed-actual-cancellation-and-power-controls'
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
    parser.add_argument('--cxx', required=True, type=Path)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(dict(status=result['status'], variants=result['variants'],
        negative_controls=list(result['negative_controls']))))
