#!/usr/bin/env python3
"""Regenerate and execute exact epoch/log/timer bodies with explicit fixtures.

Native user space by default; --host-control explicitly labels a non-Apple run.
No fixture establishes hardware stopping, PM acknowledgement or entry admission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--namespace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    parser.add_argument('--cc', default='/usr/bin/clang')
    parser.add_argument('--cxx', default='/usr/bin/clang++')
    args = parser.parse_args()
    if not args.host_control and (sys.platform != 'darwin' or platform.machine() != 'x86_64'):
        raise ValueError('Native body controls require Intel macOS; use --host-control explicitly elsewhere.')
    if args.output.exists():
        raise ValueError('Use a fresh body-control output directory.')
    args.output.mkdir(parents=True)
    contract = json.loads((HERE / 'PROSPECTIVE-SOURCE-PROFILE.json').read_text())
    for name, expected in contract['project_input_sha256'].items():
        if digest(REPO / name) != expected:
            raise ValueError('Frozen v2 input changed: ' + name)
    if args.host_control:
        os.environ['CC'], os.environ['CXX'] = args.cc, args.cxx
    sys.path.insert(0, str(REPO / 'builders'))
    import check_nvidia_execution as execution
    sys.path.insert(0, str(REPO / 'packages/nvidia-gsp-bootstrap/cancellation'))
    from prepare_wait_candidates import function_span
    original = execution.original
    port_prefix = 'packages/nvidia-gsp-bootstrap/cancellation/'
    port_raw = {port_prefix + name: (REPO / port_prefix / name).read_bytes()
                for name in ('S540NvidiaGspCancellation.c', 'S540NvidiaGspCancellation.h')}
    project = args.output / 'project-overlay'
    for name in contract['base_project_input_sha256']:
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / name).read_bytes())
    changed = original._strict_patch(port_raw, (HERE / 'inputs/cancellation-log-prospective/optional-log-port-prospective.patch').read_bytes())
    for name, value in changed.items():
        (project / name).write_bytes(value)
    port = project / port_prefix
    cases = [
        ('epoch', 'cancellation-epoch-prospective', 'gsp-bootstrap-stop-epoch-prospective.patch',
         [('src/nvidia/src/kernel/gpu/gsp/arch/turing/kernel_gsp_tu102.c', 'kgspBootstrap_TU102', 'NV_STATUS')],
         'body', 'check_body.c', 'S540_EPOCH_BASELINE', 'nvidia-gsp-bootstrap-stop-epoch', 90, 46),
        ('logs', 'cancellation-log-prospective', 'optional-log-cancellation-prospective.patch',
         [('src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c', 'kgspDumpGspLogs_IMPL', 'void'),
          ('src/common/uproc/os/libos-v3.1.0/lib/liblogdecode.c', 'libosExtractLogs_decode', 'static void'),
          ('src/common/uproc/os/libos-v3.1.0/lib/liblogdecode.c', 'libosMergeNvlog', 'static void'),
          ('src/common/uproc/os/libos-v3.1.0/lib/liblogdecode.c', 'libosExtractLogs', 'void')],
         'bodies', 'check_bodies.c', 'S540_LOG_BASELINE', 'nvidia-gsp-optional-log-cancellation', 37, 9),
        ('timers', 'cancellation-timer-status-prospective', 'timer-cancel-status-prospective.patch',
         [('src/nvidia/src/kernel/gpu/timer/timer.c', 'tmrStateUnload_IMPL', 'NV_STATUS'),
          ('src/nvidia/src/kernel/gpu/timer/timer_ostimer.c', 'tmrEventCancelOSTimer_OSTIMER', 'NV_STATUS')],
         'bodies', 'check_bodies.c', 'S540_TIMER_BASELINE', 'nvidia-gsp-timer-cancel-status', 49, 10),
    ]
    results = {}
    normal_expect = execution.expect
    for label, directory, patch, functions, suffix, fixture, macro, component, count, baseline_failures in cases:
        source = HERE / 'inputs' / directory
        work = args.output / label
        work.mkdir()
        manifest = json.loads((source / 'source-manifest.json').read_text())
        expected = manifest['original_sha256']
        if isinstance(expected, str):
            expected = {manifest['source']: expected}
        raw = {name: (args.upstream / name).read_bytes() for name in expected}
        for name, value in raw.items():
            if hashlib.sha256(value).hexdigest() != expected[name]:
                raise ValueError('Original body input changed: ' + name)
        proposed = original._strict_patch(raw, (source / patch).read_bytes())
        for version, sources in (('baseline', raw), ('proposed', proposed)):
            bodies = []
            for name, function, result_type in functions:
                text = sources[name].decode()
                start, end = function_span(text, function)
                bodies.append(result_type + '\n' + text[start:end] + '\n')
            (work / (version + '-' + suffix + '.inc')).write_text('\n'.join(bodies))
        services = [execution.SERVICES / ('src/S540NvidiaDarwin' + name + '.cpp')
                    for name in execution.SERVICE_NAMES] if label == 'logs' else []
        c_sources = ([port / 'S540NvidiaGspCancellation.c'] if label == 'logs' else []) + [source / fixture]
        cpp_sources = [source / 'check_native.cpp', *services]
        records = {}
        for baseline in (False, True):
            failures = baseline_failures if baseline else 0
            def expected_result(record, wanted, description, *, expected_failures=failures):
                normal_expect(record, {**wanted, 'status': 'failed' if expected_failures else 'passed',
                                       'failures': expected_failures}, description)
            execution.expect = expected_result
            try:
                records['baseline' if baseline else 'candidate'] = execution.original_header_case(
                    work, label + ('-baseline' if baseline else '-candidate'), args.upstream, args.namespace,
                    c_sources, cpp_sources, {'component': component, 'checks': count},
                    host_control=args.host_control, dead_strip=True,
                    extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter',
                                   '-I', str(work), '-I', str(port),
                                   '-I', str(execution.SERVICES / 'src'), '-D' + macro + '=' + str(int(baseline))],
                    extra_cpp_flags=['-I', str(port), '-I', str(execution.SERVICES / 'src')])
            finally:
                execution.expect = normal_expect
        results[label] = {'source_manifest_sha256': digest(source / 'source-manifest.json'),
                          'patch_sha256': digest(source / patch), 'variants': records,
                          'scope': 'Complete original bodies with modeled dependencies; not a combined adapter execution.'}
    memory_output = args.output / 'memory'
    command = [sys.executable, str(REPO / 'packages/nvidia-device-transport/prospective/check_memory_unwind_bodies.py'),
               '--upstream', str(args.upstream), '--output', str(memory_output), '--cc', args.cc]
    completed = subprocess.run(command, capture_output=True, text=True)
    (args.output / 'memory-command.log').write_text(completed.stdout + completed.stderr)
    completed.check_returncode()
    results['memory'] = json.loads((memory_output / 'memory-unwind-body-checks.json').read_text())
    for version, failures in (('candidate', 0), ('baseline', 23)):
        for result in results['memory']['results'][version]['variants'].values():
            normal_expect(result, {'checks': 127, 'failures': failures,
                                   'status': 'failed' if failures else 'passed'}, 'memory/' + version)
    for name, expected in contract['project_input_sha256'].items():
        if digest(REPO / name) != expected:
            raise ValueError('A frozen input changed during body controls: ' + name)
    report = {'format': 1, 'status': 'passed', 'component': 'nvidia-prospective-v2-body-controls',
              'authoritative_native_apple': not args.host_control, 'kernel_execution': 'not_tested',
              'gpu_access': False, 'approved_profile': False, 'production_candidate_allowed': False,
              'actual_dependency_models': True, 'results': results}
    (args.output / 'v2-body-controls.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': 'passed', 'epoch': 90, 'logs': 37, 'timers': 49, 'memory': 127,
                      'each_variant': ['plain', 'fatal-sanitizers'], 'kernel_execution': 'not_tested'}))

if __name__ == '__main__':
    main()
