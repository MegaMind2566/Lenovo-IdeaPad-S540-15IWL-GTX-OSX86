#!/usr/bin/env python3
"""Genuine Protocol/cancellation CPU boundary with explicit platform fixtures."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import prepare_nvidia_shutdown_successor as plan

POWER = 'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp'
CANCEL = 'packages/nvidia-gsp-bootstrap/cancellation/S540NvidiaGspCancellation.c'

def require(value, reason):
    if not value:
        raise ValueError(reason)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def command(argv, log, environment, *, expected=0):
    result = subprocess.run([str(v) for v in argv], text=True, capture_output=True,
        env=environment, timeout=120)
    log.write_text(result.stdout + result.stderr)
    require(result.returncode == expected, 'PM boundary command failed: ' + str(log) + '\n' + result.stderr[-3000:])
    return result

def dependencies(path):
    result = {}
    for value in shlex.split(path.read_text().replace('\\\n', ' ').split(':', 1)[1]):
        source = Path(value).resolve(strict=True)
        result[str(source)] = sha(source)
    return result

def run(args):
    require(sys.platform.startswith('linux'), 'This is a Linux CPU control only')
    candidate = args.composition.resolve(strict=True)
    value = plan.verify(args.canonical_parent, args.integrated_base, args.base, candidate)
    require({'pm-revocation', 'dma-producer'} <= set(value['shutdown_successor']['selected_profiles']),
        'The complete reviewed PM/producer composition is required')
    output = args.output.resolve()
    require(not output.exists(), 'Fresh PM boundary output required')
    require(not output.is_relative_to(candidate) and not candidate.is_relative_to(output),
        'Control output must be isolated from source composition')
    output.mkdir(parents=True)
    project = candidate / 'project'
    power, cancel = project / POWER, project / CANCEL
    for name, path in ((POWER, power), (CANCEL, cancel)):
        require(sha(path) == value['project_files'][name]['sha256'], 'Declared source differs: ' + name)
    cc, cxx = args.cc.resolve(strict=True), args.cxx.resolve(strict=True)
    inputs = {str(p): sha(p) for p in (Path(__file__), HERE / 'check_pm_event_boundary.cpp',
        candidate / 'composition.json', power, cancel, cc, cxx)}
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
        UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    includes = [project / 'packages', project / 'packages/nvidia-darwin-services/src',
        project / 'packages/nvidia-gsp-bootstrap/platform',
        project / 'packages/nvidia-gsp-bootstrap/prospective-pm-revocation-closure',
        project / 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/deps']
    common = ['-O2', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
        '-ffunction-sections', '-fdata-sections', '-pthread', *[flag for p in includes for flag in ('-I', str(p))]]
    report = dict(format=1, status='running', composition_sha256=sha(candidate / 'composition.json'),
        input_sha256=inputs, variants={}, original_protocol_and_cancellation_bodies=True,
        platform_clock_thread_and_endpoint_return_fixtures=True,
        hardware_stop_proven=False, pm_30_second_shutdown_bound_proven=False,
        kernel_execution=False, gpu_access=False, native_ci_requested=False)
    write(output / 'results.json', report)
    try:
        for variant in ('plain', 'fatal-sanitized'):
            work = output / variant
            work.mkdir()
            flags = common + ([] if variant == 'plain' else ['-fsanitize=address,undefined,function', '-fno-sanitize-recover=all'])
            objects, artifacts = [], []
            def compile_one(source, name, compiler, language):
                obj = work / (name + '.o')
                dep = obj.with_suffix('.d')
                argv = [compiler, *flags, '-std=' + language, '-MD', '-MF', dep, '-c', source, '-o', obj]
                command(argv, obj.with_suffix('.log'), environment)
                artifacts.append(dict(source=str(source), source_sha256=sha(source), object=str(obj),
                    object_sha256=sha(obj), command=list(map(str, argv)), dependency_sha256=dependencies(dep)))
                return obj
            objects.append(compile_one(power, 'power', cxx, 'c++17'))
            objects.append(compile_one(HERE / 'check_pm_event_boundary.cpp', 'control', cxx, 'c++17'))
            actual = compile_one(cancel, 'cancellation', cc, 'c11')
            binary = work / 'pm-event-boundary'
            link = [cxx, *flags, *objects, actual, '-Wl,--gc-sections', '-o', binary]
            command(link, binary.with_suffix('.link.log'), environment)
            binary_hash = sha(binary)
            observations = []
            for schedule in (0, 1):
                completed = command([binary, schedule], work / ('schedule-%d.log' % schedule), environment)
                observation = json.loads(completed.stdout)
                require(observation['status'] == 'passed' and not observation['failures'], 'Boundary observation failed')
                observations.append(observation)
            # Remove only Finish's actual busy-reservation check. The public
            # pending counter still sees the reservation: these are distinct guards.
            mutant = work / 'cancellation-finish-mutant.c'
            text = cancel.read_text()
            before = 'if(value&(CAPTURE_BUSY|PUBLISHING|COMMIT_BUSY))'
            require(text.count(before) == 1, 'Exact Finish busy guard required for negative control')
            mutant.write_text(text.replace(before, 'if(value&(CAPTURE_BUSY|PUBLISHING))'))
            bad_obj = compile_one(mutant, 'finish-mutant', cc, 'c11')
            negative = work / 'pm-event-finish-mutant'
            command([cxx, *flags, *objects, bad_obj, '-Wl,--gc-sections', '-o', negative],
                negative.with_suffix('.link.log'), environment)
            negative_hash = sha(negative)
            failed = command([negative, 0], work / 'negative-schedule.log', environment, expected=1)
            negative_result = json.loads(failed.stdout)
            require(negative_result['failures'] and 'held endpoint prevents Finish' in failed.stderr,
                'Critical Finish mutation was not detected')
            for artifact in artifacts:
                require(sha(Path(artifact['source'])) == artifact['source_sha256'] and
                    sha(Path(artifact['object'])) == artifact['object_sha256'], 'Compiled boundary artifact changed')
                for name, digest in artifact['dependency_sha256'].items():
                    require(sha(Path(name)) == digest, 'Bound dependency changed: ' + name)
            require(sha(binary) == binary_hash and sha(negative) == negative_hash, 'Executed boundary binary changed')
            report['variants'][variant] = dict(status='passed', observations=observations,
                assertions=sum(row['checks'] for row in observations), artifacts=artifacts,
                binary_sha256=binary_hash, negative_binary_sha256=negative_hash,
                finish_guard_mutation_detected=True, negative_result=negative_result)
            write(output / 'results.json', report)
        require(all(sha(Path(name)) == digest for name, digest in inputs.items()), 'Boundary control inputs changed')
        plan.verify(args.canonical_parent, args.integrated_base, args.base, candidate)
        report['status'] = 'passed-genuine-protocol-cancellation-event-boundary'
        return report
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        write(output / 'results.json', report)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('canonical-parent', 'integrated-base', 'base', 'composition', 'cc', 'cxx', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    outcome = run(parser.parse_args())
    print(json.dumps({'status': outcome['status'], 'assertions': {
        name: value['assertions'] for name, value in outcome['variants'].items()}}))
