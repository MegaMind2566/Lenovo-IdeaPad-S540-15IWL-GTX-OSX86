#!/usr/bin/env python3
"""Original live ABI closure with explicit refusals and fail-stop boundaries."""
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

CALLBACKS = ['os_is_bif_reset_supported', 'os_allocate_temporary_file', 'os_close_file',
             'os_read_file', 'os_write_file', 'os_disable_console_access', 'os_enable_console_access']
PROFILES = ['S540_NVIDIA_LIVE_PLATFORM_CLOSURE', 'S540_NVIDIA_MANUAL_ADAPTER_START',
            'S540_NVIDIA_NO_FILE_BACKEND', 'S540_NVIDIA_NO_NVIDIA_CONSOLE']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def check(args):
    upstream, namespace = args.upstream.resolve(strict=True), args.namespace.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists(), 'Fresh output required.')
    require(not output.is_relative_to(HERE) and not output.is_relative_to(upstream), 'Output overlaps source.')
    require(not output.is_relative_to(REPO) or output.is_relative_to(REPO/'build'), 'Repo output allowed only under build/.')
    require(execution.commands.run('git', '-C', str(upstream), 'rev-parse', 'HEAD').stdout.strip() == original.COMMIT,
            'Wrong original commit.')
    require(not execution.commands.run('git', '-C', str(upstream), 'status', '--porcelain').stdout, 'Dirty original source.')
    ns = json.loads((REPO/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    require(sha(namespace) == ns['namespace_sha256'], 'Private namespace changed.')
    output.mkdir(parents=True)
    compiler_identity = None
    if not args.host_control:
        compiler_identity = execution.commands.run('/usr/bin/xcrun', 'clang', '--version').stdout
        require('Apple clang version' in compiler_identity, 'Apple compiler identity not established.')
    execution.commands.run(sys.executable, str(HERE/'tests/test_source_contracts.py'), '--upstream', str(upstream),
                           diagnostic_log=output/'source-contracts.log')
    fixture, reference = prepare(upstream, output/'original-controls')
    profile_flags = ['-D'+name+'=1' for name in PROFILES]
    common = ['-std=gnu11', '-Werror', '-Wno-unused-parameter', '-DNV_FILESYSTEM_ACCESS_AVAILABLE=0']
    native = execution.original_header_case(output, 'live-platform', upstream, namespace,
        [HERE/'S540ProspectiveLivePlatformClosure.c', fixture, HERE/'tests/check_live_platform.c'], [],
        {'component': 'nvidia-prospective-live-platform-closure', 'checks': 31, 'official_bodies': 5,
         'actual_callers': 7, 'callbacks': 7, 'fail_stop_cases': 7,
         'linux_layout_and_transaction_identity_fixtures': True, 'console_metadata_fixture': True,
         'original_entry_admission': False}, host_control=args.host_control,
        extra_c_flags=common+profile_flags)
    cc, _ = execution.crypto.compiler_pair(args.host_control)
    compiler = Path(cc[0]) if args.host_control else Path('/usr/bin/clang')
    flags = original.original_bridge_flags(upstream, output, compiler, namespace)
    flags += ['--target=x86_64-apple-macos15.0', '-mkernel', '-DKERNEL', '-D__KERNEL__',
              '-Wframe-larger-than=4096', '-Werror=frame-larger-than', '-fstack-usage', *common]
    source = HERE/'S540ProspectiveLivePlatformClosure.c'; obj = output/'live-platform-kernel.o'
    command = [*cc, *flags, *profile_flags, '-c', str(source), '-o', str(obj)]
    execution.commands.run(*command, diagnostic_log=output/'kernel-compile.log')
    defined, imported, _ = original.macho_symbols(obj)
    expected_imports = {'s540GlobalRmRecordServiceName', 's540GlobalRmRecordUnavailable',
                        's540FirstTxnGetSnapshot', original.PREFIX+'os_bug_check'}
    require(defined == {original.PREFIX+name for name in CALLBACKS} and imported == expected_imports,
            'Candidate gained unreviewed symbols.')
    metaclass.verify_no_initializers(obj)
    negatives = []
    configurations = [[]]
    for name in PROFILES:
        configurations.append(['-D'+other+'=1' for other in PROFILES if other != name])
        configurations.append(['-D'+other+'='+('0' if other == name else '1') for other in PROFILES])
    configurations.append([*profile_flags, '-UNV_FILESYSTEM_ACCESS_AVAILABLE', '-DNV_FILESYSTEM_ACCESS_AVAILABLE=1'])
    for index, options in enumerate(configurations):
        result = subprocess.run([*cc, *flags, *options, '-c', str(source), '-o', str(output/f'refused-{index}.o')],
                                text=True, capture_output=True)
        diagnostic = result.stdout+result.stderr; (output/f'negative-{index}.log').write_text(diagnostic)
        require(result.returncode != 0 and ('Explicit sealed manual-adapter-start platform profile required' in diagnostic or
            'Explicit no-file/no-NVIDIA-console profile required' in diagnostic or
            'no-file profile cannot serve enabled filesystem access' in diagnostic), 'Required profile refusal absent.')
        negatives.append({'flags': options, 'rejected': True})
    result = {'format': 1, 'status': 'passed-isolated-live-platform-controls', 'callbacks': CALLBACKS,
        'native_controls': native, 'original_reference': reference, 'native_apple_execution': not args.host_control,
        'compiler_identity': compiler_identity,
        'kernel_target_compile': {'source': str(source), 'source_sha256': sha(source), 'object': str(obj),
            'object_sha256': sha(obj), 'command': command, 'definitions': sorted(defined), 'imports': sorted(imported)},
        'configuration_negative_controls': negatives, 'file_operations_implemented': False,
        'console_backend_implemented': False, 'bif_hardware_reset_safety_proved': False,
        'manual_start_policy_is_not_hardware_admission': True, 'transaction_identity_endpoint_fixture': True,
        'production_default_changed': False, 'production_candidate_allowed': False,
        'original_entry_admission': False, 'kernel_execution': 'not_tested', 'gpu_access': False}
    (output/'live-platform-checks.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream', 'namespace', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    record = check(parser.parse_args())
    print(json.dumps({'status': record['status'], 'callbacks': 7, 'checks_per_variant': 31,
                      'production_candidate_allowed': False}))
