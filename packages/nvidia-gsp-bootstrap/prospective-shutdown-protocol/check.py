#!/usr/bin/env python3
"""Verify the exact source protocol, execute fixture controls, compile complete TUs."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIRST = HERE.parent / 'prospective-first-transaction/original'
sys.path.insert(0, str(FIRST))
from common import original, parser, resolve_arguments, sha, write_json, validate_sdk
from prepare import prepare
from prepare_controls import body

GPU = 'src/nvidia/src/kernel/gpu/gpu.c'

def inventory(root: Path) -> dict:
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Input trees must contain regular files/directories only.')
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()
            and '__pycache__' not in p.parts and 'evidence' not in p.parts
            and p.name != 'FROZEN-SHA256.json'}

def dependencies(path: Path, cwd: Path) -> dict:
    text = path.read_text().replace('\\\n', '')
    names = shlex.split(text.split(':', 1)[1])
    result = {}
    for name in names:
        p = Path(name)
        if not p.is_absolute(): p = cwd / p
        p = p.resolve(strict=True)
        result[str(p)] = sha(p.read_bytes())
    return result

def check_dependencies(values: dict) -> None:
    for name, digest in values.items():
        if sha(Path(name).read_bytes()) != digest:
            raise ValueError('A compiler-observed dependency changed: ' + name)

def execute_control(binary: Path, scenario: int) -> dict:
    environment = dict(os.environ)
    # LSan cannot inspect /proc/task in the hosted tracing environment. These
    # fixtures allocate no heap. Address/type/undefined checks remain fatal.
    environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
    environment['UBSAN_OPTIONS'] = 'halt_on_error=1:abort_on_error=1'
    result = subprocess.run([str(binary), str(scenario)], text=True,
        capture_output=True, timeout=60, env=environment)
    if result.returncode:
        raise RuntimeError('Protocol scenario ' + str(scenario) + ' failed:\n' + result.stdout + result.stderr)
    return json.loads(result.stdout)

def main() -> None:
    args = parser(__doc__, compile_only=True).parse_args()
    args, identity = resolve_arguments(args)
    sdk_path = args.sdk or os.environ.get('MAC_KERNEL_SDK') or os.environ.get('KERNEL_SDK')
    for value in (sdk_path, args.sdk_archive, args.namespace):
        if value is None: continue
        path = Path(value).resolve(strict=True)
        if path.is_relative_to(args.output) or args.output.is_relative_to(path):
            raise ValueError('Output overlaps an SDK or namespace input.')
    sdk = validate_sdk(args.sdk, args.sdk_archive, args.host_control)
    package_before = inventory(HERE)
    contract_bytes = (HERE / 'SOURCE-CONTRACT.json').read_bytes()
    contract = json.loads(contract_bytes)
    profile = sha(contract_bytes)
    if sha((FIRST / 'SOURCE-CONTRACT.json').read_bytes()) != contract['first_transaction_source_contract_sha256']:
        raise ValueError('The required first-transaction source contract changed.')
    if (HERE / 'SourceProfile.h').read_text() != (
        '/* SPDX-License-Identifier: MIT; immutable source-only profile. */\n'
        '#define S540_SHUTDOWN_SOURCE_PROFILE_SHA256 "' + profile + '"\n'):
        raise ValueError('The compiled immutable source profile differs from the contract.')
    prepared = prepare(args.upstream, args.v3_root, args.output / 'first-source')
    base_before = inventory(prepared['base_source'])
    guarded_before = inventory(prepared['source'])
    gpu_source = prepared['source'] / GPU
    gpu_bytes = gpu_source.read_bytes()
    if sha(gpu_bytes) != contract['gpu_source_sha256']:
        raise ValueError('The guarded source GPU TU differs from the frozen identity.')
    actual_body = body(gpu_bytes.decode(), 'gpuEnterShutdown_IMPL', 'NV_STATUS')
    if sha(actual_body.encode()) != contract['complete_function_body_sha256']:
        raise ValueError('The exact original shutdown-protocol body changed.')
    forbidden = ('gpuStateDestroy(', 'memdescFree(', 's540GspContextDestroy(',
                 's540GspContextValidateDmaStopReceipt(', 'confirmHardwareDmaStopped(')
    if any(value in actual_body for value in forbidden):
        raise ValueError('The selected original protocol contains destructive final cleanup.')
    body_path = args.output / 'actual-gpu-enter-shutdown.inc'
    body_path.write_text(actual_body)
    flags = original.original_bridge_flags(args.upstream, args.output / 'flags', args.cc, args.namespace)
    raw, base = str(args.upstream), str(prepared['base_source'])
    flags = [base + flag[len(raw):] if flag.startswith(raw + '/') else flag for flag in flags]
    includes = ['-I', str(HERE), '-I', str(FIRST), '-I', str(args.output),
                '-I', str(HERE.parent / 'cancellation')]
    cwd = prepared['base_source'] / 'src/nvidia'
    object_root = args.output / 'objects'
    object_root.mkdir(exist_ok=True)
    observed_dependencies = {}
    compiled = []
    # Both the complete unchanged guarded original GPU TU and the complete
    # successor TU use the original make-declared ABI, types and actual headers.
    for name, source in [('original-gpu', gpu_source), ('typed-protocol', HERE / 'S540NvidiaShutdownProtocol.c')]:
        target = object_root / (name + '.o')
        dep = object_root / (name + '.d')
        command = [str(args.cc), *flags, *includes,
            *(['-target', 'x86_64-macos-none'] if args.host_control else ['-arch', 'x86_64']),
            '-fPIC', '-Werror', '-Wframe-larger-than=4096', '-Werror=frame-larger-than',
            '-MMD', '-MF', str(dep), '-c', str(source), '-o', str(target)]
        original.execute(command, cwd=cwd, diagnostic_log=object_root / (name + '.log'))
        defined, undefined, sections = original.macho_symbols(target)
        imported = sorted(undefined)
        if name == 'typed-protocol' and any(
                term in symbol for symbol in imported
                for term in ('gpuStateDestroy', 'rm_shutdown_adapter', 'memdescFree', 'DmaStopReceipt')):
            raise ValueError('Typed protocol imports a destructive final-cleanup/stop-authority entry.')
        actual_deps = dependencies(dep, cwd)
        observed_dependencies.update(actual_deps)
        compiled.append({'source': str(source), 'source_sha256': sha(source.read_bytes()),
            'object': str(target), 'object_sha256': sha(target.read_bytes()),
            'command': command, 'cwd': str(cwd), 'definitions': sorted(defined),
            'imports': imported, 'sections': sections, 'dependencies': actual_deps})
    expected_entry = 's540Global_gpuEnterShutdown_IMPL'
    if expected_entry not in compiled[0]['definitions'] or expected_entry not in compiled[1]['imports']:
        raise ValueError('The typed successor does not call the actual namespaced original entry.')
    variants = {}
    for variant in ('plain', 'sanitized'):
        target = args.output / ('protocol-' + variant)
        dep = args.output / (variant + '.d')
        obj = args.output / (variant + '.o')
        sanitizer = [] if variant == 'plain' else [
            '-fsanitize=address,undefined,function', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command = [str(args.cc), *flags, *includes,
            '-fPIC', '-mcmodel=small', '-msse2', '-O1', '-g', '-Werror',
            '-Wno-unused-function', '-Wno-unused-parameter', *sanitizer,
            '-MMD', '-MF', str(dep), '-c', str(HERE / 'check_protocol.c'), '-o', str(obj)]
        original.execute(command, cwd=cwd, diagnostic_log=args.output / (variant + '-compile.log'))
        observed_dependencies.update(dependencies(dep, cwd))
        command = [str(args.cc), str(obj), *sanitizer,
            *(['-Wl,--gc-sections'] if args.host_control else ['-Wl,-dead_strip']), '-o', str(target)]
        original.execute(command, diagnostic_log=args.output / (variant + '-link.log'))
        if not args.host_control:
            original.execute(['codesign', '--force', '--sign', '-', str(target)])
        rows = []
        for scenario in range(24):
            row = execute_control(target, scenario)
            if row.get('scenario') != scenario or row.get('failures') != 0 or not row.get('checks'):
                raise ValueError('Unexpected source-boundary control result.')
            rows.append(row)
        variants[variant] = {'checks': sum(row['checks'] for row in rows), 'failures': 0,
                             'scenarios': rows, 'binary_sha256': sha(target.read_bytes()),
                             'sanitizers': [] if variant == 'plain' else ['address', 'undefined', 'function'],
                             'leak_sanitizer': False, 'sanitizer_failures_fatal': variant != 'plain'}
    if inventory(HERE) != package_before:
        raise ValueError('Package inputs changed during the run.')
    if inventory(prepared['base_source']) != base_before or inventory(prepared['source']) != guarded_before:
        raise ValueError('The immutable original source profile changed during compilation/execution.')
    check_dependencies(observed_dependencies)
    report = {'format': 1, 'status': 'passed-isolated-shutdown-protocol-controls-and-full-tu-compilation',
        **identity, 'sdk': sdk, 'source_profile_sha256': profile,
        'namespace_sha256': sha(args.namespace.read_bytes()),
        'full_v3_inventory_verified': True, 'complete_function_body_sha256': sha(actual_body.encode()),
        'full_original_translation_units': 1, 'full_typed_successor_translation_units': 1,
        'cross_compile_only': args.host_control, 'compilation': compiled, 'variants': variants,
        'package_inputs_sha256': sha(json.dumps(package_before, sort_keys=True).encode()),
        'compiler_observed_dependencies': observed_dependencies,
        'control_endpoints': ['hardware/engine unload and GSP shutdown',
            'first-transaction record and full lock capability', 'thread/runtime/API/GPU tokens',
            'cancellation scope and deadline'],
        'gpu_access': False, 'kernel_execution': False, 'runtime_shutdown_observed': False,
        'safe_gpu_destruction': False, 'dma_stop_receipt': False,
        'physical_reclamation_authorized': False, 'original_entry_admission': False,
        'production_candidate_allowed': False}
    write_json(args.output / 'results.json', report)
    print(json.dumps({'status': report['status'], 'checks_per_variant': variants['plain']['checks'],
        'authoritative_darwin_execution': report['authoritative_darwin_execution'],
        'cross_compile_only': args.host_control, 'original_entry_admission': False}))

if __name__ == '__main__':
    main()
