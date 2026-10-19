#!/usr/bin/env python3
"""Isolated original-ABI disabled-UVM candidate; never enters RM or loads code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'builders'))
import check_nvidia_execution as execution
import compile_nvidia_global_rm as original
import nvidia_metaclass_initializers as metaclass
from prepare_original_controls import prepare

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(condition, message):
    if not condition: raise ValueError(message)

def check(output, upstream, namespace, host_control):
    output.mkdir(parents=True, exist_ok=True)
    require(execution.commands.run('git', '-C', str(upstream), 'rev-parse', 'HEAD').stdout.strip() == original.COMMIT,
        'Pinned original identity changed.')
    require(not execution.commands.run('git', '-C', str(upstream), 'status', '--porcelain').stdout,
        'Pinned original tree must be clean.')
    namespace_contract = json.loads((ROOT / 'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    require(sha(namespace) == namespace_contract['namespace_sha256'], 'Original namespace changed.')
    execution.commands.run(sys.executable, str(HERE / 'tests/test_uvm_contracts.py'),
        '--upstream', str(upstream), diagnostic_log=output / 'source-contracts.log')
    fixture, reference = prepare(upstream, output / 'original-controls')
    source = HERE / 'S540ProspectiveUvmDisabled.c'
    native = execution.original_header_case(output, 'prospective-disabled-uvm', upstream,
        namespace, [source, fixture, HERE / 'tests/check_uvm_disabled_native.c'], [],
        {'component': 'nvidia-prospective-disabled-uvm', 'checks': 15,
         'actual_original_forwarding_bodies': 4, 'actual_original_disabled_bodies': 3,
         'uvm_interrupt_delivered': False, 'p2p_drain_implemented': False,
         'original_entry_admission': False}, host_control=host_control,
        extra_c_flags=['-std=gnu11', '-Werror', '-Wno-unused-parameter', '-DS540_NVIDIA_NO_UVM_BACKEND=1'])
    cc, _ = execution.crypto.compiler_pair(host_control)
    flags = original.original_bridge_flags(upstream, output, Path(cc[0]) if host_control else Path('/usr/bin/clang'), namespace)
    flags += ['--target=x86_64-apple-macos15.0', '-mkernel', '-DKERNEL', '-D__KERNEL__',
        '-std=gnu11', '-Werror', '-Wno-unused-parameter', '-Wframe-larger-than=4096']
    obj = output / 'disabled-uvm-kernel.o'
    execution.commands.run(*cc, *flags, '-DS540_NVIDIA_NO_UVM_BACKEND=1', '-c', str(source), '-o', str(obj),
        diagnostic_log=output / 'kernel-compile.log')
    defined, imported, _ = original.macho_symbols(obj)
    expected = {original.PREFIX + name for name in ('nv_schedule_uvm_isr', 'nv_schedule_uvm_drain_p2p', 'nv_schedule_uvm_resume_p2p')}
    require(defined == expected and not imported, 'Candidate gained a non-disabled operation/dependency.')
    metaclass.verify_no_initializers(obj)
    negatives = []
    for index, options in enumerate(([], ['-DS540_NVIDIA_NO_UVM_BACKEND=0'],
            ['-DS540_NVIDIA_NO_UVM_BACKEND=2'],
            ['-DS540_NVIDIA_NO_UVM_BACKEND=1', '-DNV_UVM_ENABLE=1'],
            ['-DS540_NVIDIA_NO_UVM_BACKEND=1', '-DNV_UVM_ENABLE=0'])):
        result = subprocess.run([*cc, *flags, *options, '-c', str(source), '-o', str(output / f'refused-{index}.o')],
            text=True, capture_output=True)
        diagnostic = result.stdout + result.stderr
        (output / f'negative-{index}.log').write_text(diagnostic)
        require(result.returncode != 0 and ('explicit selected no-UVM backend' in diagnostic or
            'cannot serve an enabled UVM backend' in diagnostic), 'Expected configuration was not explicitly rejected.')
        negatives.append({'flags': options, 'explicit_configuration_refused': True})
    result = {'format': 1, 'component': 'nvidia-prospective-disabled-uvm',
        'status': 'passed-isolated-source-candidate-controls', 'source_only': True,
        'native_controls': native, 'reference': reference,
        'kernel_compile': {'native_apple_compiler': not host_control,
            'object_sha256': sha(obj), 'definitions': sorted(defined), 'imports': [],
            'implicit_initializers': False, 'configuration_negative_controls': negatives},
        'source_sha256': {p.relative_to(HERE).as_posix(): sha(p) for p in sorted(HERE.rglob('*'))
            if p.suffix in ('.c', '.h', '.py')},
        'uvm_integration_implemented': False, 'p2p_drain_implemented': False,
        'production_default_changed': False, 'production_candidate_allowed': False,
        'kernel_execution': 'not_tested', 'gpu_access': False}
    (output / 'disabled-uvm-checks.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--namespace', type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    args = parser.parse_args()
    result = check(args.output.resolve(), args.upstream.resolve(strict=True),
        args.namespace.resolve(strict=True), args.host_control)
    print(json.dumps({'status': result['status'], 'checks_per_variant': 15,
        'configuration_negative_controls': 5, 'production_candidate_allowed': False}))
