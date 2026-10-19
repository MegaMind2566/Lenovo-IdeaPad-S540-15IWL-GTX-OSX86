#!/usr/bin/env python3
"""Typed seven-callback source candidate; no hardware entry or successful stub."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO/'builders'))
import check_nvidia_execution as execution
import compile_nvidia_global_rm as original
import nvidia_metaclass_initializers as metaclass
from prepare_original_controls import prepare

CALLBACKS = ['os_get_is_openrm', 'nv_dynamic_power_available', 'os_get_tegra_platform',
             'nvlink_strcpy', 'nvlink_strlen', 'nvlink_strcmp', 'nvlink_get_platform_time']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def check(args):
    upstream = args.upstream.resolve(strict=True)
    namespace = args.namespace.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists(), 'Fresh output directory required.')
    require(not output.is_relative_to(HERE) and not output.is_relative_to(upstream), 'Output overlaps source input.')
    require(not output.is_relative_to(REPO) or output.is_relative_to(REPO/'build'), 'Repo output allowed only under build/.')
    require(execution.commands.run('git', '-C', str(upstream), 'rev-parse', 'HEAD').stdout.strip() == original.COMMIT,
            'Wrong original source commit.')
    require(not execution.commands.run('git', '-C', str(upstream), 'status', '--porcelain').stdout,
            'Original source tree is dirty.')
    ns = json.loads((REPO/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    require(sha(namespace) == ns['namespace_sha256'], 'Wrong original private namespace.')
    output.mkdir(parents=True)
    compiler_identity = None
    if not args.host_control:
        compiler_identity = execution.commands.run('/usr/bin/xcrun', 'clang', '--version').stdout
        require('Apple clang version' in compiler_identity, 'Native Apple compiler identity not established.')
    execution.commands.run(sys.executable, str(HERE/'tests/test_source_contracts.py'), '--upstream', str(upstream),
                           diagnostic_log=output/'source-contracts.log')
    fixture, reference = prepare(upstream, output/'original-controls')
    profile = '-DS540_NVIDIA_DARWIN_PLATFORM_CLOSURE=1'
    native = execution.original_header_case(output, 'platform-closure', upstream, namespace,
        [HERE/'S540ProspectivePlatformClosure.c', fixture, HERE/'tests/check_platform_closure.c'],
        [execution.SERVICES/('src/S540NvidiaDarwin'+name+'.cpp') for name in execution.SERVICE_NAMES],
        {'component': 'nvidia-prospective-platform-closure', 'checks': 36, 'actual_original_query_callers': 3,
         'official_branch_bodies': 3, 'callbacks': 7, 'real_monotonic_backend': True,
         'host_observer_fixture': True, 'original_entry_admission': False},
        host_control=args.host_control,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter',
                       '-DNV_SUPPORTS_PLATFORM_DEVICE=0', '-DNV_SUPPORTS_PLATFORM_DISPLAY_DEVICE=0', profile])
    cc, _ = execution.crypto.compiler_pair(args.host_control)
    compiler = Path(cc[0]) if args.host_control else Path('/usr/bin/clang')
    flags = original.original_bridge_flags(upstream, output, compiler, namespace)
    flags += ['--target=x86_64-apple-macos15.0', '-mkernel', '-DKERNEL', '-D__KERNEL__',
              '-std=gnu11', '-Werror', '-Wno-unused-parameter', '-Wframe-larger-than=4096',
              '-Werror=frame-larger-than', '-fstack-usage', '-DNV_SUPPORTS_PLATFORM_DEVICE=0',
              '-DNV_SUPPORTS_PLATFORM_DISPLAY_DEVICE=0']
    obj = output/'platform-closure-kernel.o'
    command = [*cc, *flags, profile, '-c', str(HERE/'S540ProspectivePlatformClosure.c'), '-o', str(obj)]
    execution.commands.run(*command, diagnostic_log=output/'kernel-compile.log')
    defined, imported, _ = original.macho_symbols(obj)
    expected_imports = {'s540GlobalRmRecordServiceName', 's540GlobalRmRecordUnavailable',
                        's540Darwin_os_get_monotonic_time_ns_hr'}
    require(defined == {original.PREFIX+name for name in CALLBACKS} and imported == expected_imports,
            'Candidate gained unreviewed exports or imports.')
    metaclass.verify_no_initializers(obj)
    negatives = []
    configurations = [[], ['-DS540_NVIDIA_DARWIN_PLATFORM_CLOSURE=0'],
        ['-DS540_NVIDIA_DARWIN_PLATFORM_CLOSURE=2'], [profile, '-DNV_PM_RUNTIME_AVAILABLE=0'],
        [profile, '-DNV_PM_RUNTIME_AVAILABLE=1'], [profile, '-DNV_SUPPORTS_PLATFORM_DEVICE=1'],
        [profile, '-DNV_SUPPORTS_PLATFORM_DISPLAY_DEVICE=1']]
    for index, options in enumerate(configurations):
        result = subprocess.run([*cc, *flags, *options, '-c', str(HERE/'S540ProspectivePlatformClosure.c'),
                                 '-o', str(output/f'refused-{index}.o')], text=True, capture_output=True)
        diagnostic = result.stdout+result.stderr
        (output/f'negative-{index}.log').write_text(diagnostic)
        require(result.returncode != 0 and ('Explicit selected Darwin platform closure required' in diagnostic or
            'cannot serve an enabled runtime-PM backend' in diagnostic or 'cannot serve a Tegra platform backend' in diagnostic),
            'Contradictory configuration was not explicitly refused.')
        negatives.append({'flags': options, 'rejected': True})
    record = {'format': 1, 'status': 'passed-isolated-source-candidate-controls', 'callbacks': CALLBACKS,
        'native_controls': native, 'original_reference': reference,
        'kernel_target_compile': {'source': str(HERE/'S540ProspectivePlatformClosure.c'),
            'source_sha256': sha(HERE/'S540ProspectivePlatformClosure.c'), 'object': str(obj),
            'object_sha256': sha(obj), 'command': command, 'definitions': sorted(defined), 'imports': sorted(imported),
            'implicit_initializers': False},
        'configuration_negative_controls': negatives,
        'native_apple_execution': not args.host_control, 'compiler_identity': compiler_identity,
        'host_observer_fixture': True, 'final_link_proven': False,
        'runtime_power_implemented': False, 'tegra_platform_implemented': False, 'nvlink_hardware_implemented': False,
        'production_default_changed': False, 'production_candidate_allowed': False, 'original_entry_admission': False,
        'kernel_execution': 'not_tested', 'gpu_access': False}
    (output/'platform-closure-checks.json').write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream', 'namespace', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    result = check(parser.parse_args())
    print(json.dumps({'status': result['status'], 'callbacks': len(CALLBACKS),
                      'checks_per_variant': 36, 'production_candidate_allowed': False}))
