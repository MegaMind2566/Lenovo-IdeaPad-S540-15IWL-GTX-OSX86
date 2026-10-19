#!/usr/bin/env python3
"""Isolated OS-event policy composition and CPU controls; no RM admission."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'builders'))
import check_nvidia_execution as execution
import compile_nvidia_global_rm as original
import nvidia_metaclass_initializers as metaclass
from prepare_event_policy import SOURCES, prepare

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(value, message):
    if not value: raise ValueError(message)

def controls(output, upstream, namespace, composition, host_control):
    common = ['-std=gnu11', '-Werror', '-Wno-unused-parameter', '-I', str(composition)]
    result = {}
    for name, checks, bodies, extra in [
        ('eventapi', 31, 2, {'kernel_callback_allocation_preserved': True}),
        ('semsurf', 28, 4, {'kernel_waiters_preserved': True})]:
        result[name] = execution.original_header_case(output, 'os-event-' + name,
            upstream, namespace, [HERE / ('tests/check_' + name + '_policy_bodies.c')], [],
            {'component': 'nvidia-os-event-' + ('api' if name == 'eventapi' else name) + '-policy',
             'checks': checks, 'complete_source_bodies': bodies, 'private_types_and_resource_helpers': 'explicit-cpu-fixtures',
             'baseline_os_event_acquisition_observed': True, **extra}, host_control=host_control,
            extra_c_flags=[*common, '-Wno-unused-variable', '-Wno-unused-function'])
    result['eventbuffer'] = execution.original_header_case(output, 'os-event-buffer',
        upstream, namespace, [HERE / 'tests/check_eventbuffer_policy_bodies.c',
            upstream / 'src/nvidia/src/libraries/eventbuffer/eventbufferproducer.c'], [],
        {'component': 'nvidia-os-event-buffer-policy', 'checks': 212,
         'full_original_constructor_bodies': 2, 'public_0x90cd_parameters': True,
         'original_producer_helpers': True, 'private_types_and_memory_helpers': 'explicit-cpu-fixtures',
         'production_candidate_allowed': False}, host_control=host_control,
        dead_strip=True, extra_c_flags=common)
    return result

def kernel_compile(output, upstream, namespace, v3, composition, host_control):
    output.mkdir(parents=True, exist_ok=True)
    cc, unused_cxx = execution.crypto.compiler_pair(host_control)
    v3_namespace = v3 / 'prospective-private-namespace.h'
    audit = json.loads((v3 / 'combined-profile-audit.json').read_text())
    require(audit['combined_tree_sha256'] == 'fa8498c3958a559a3466ef6dd4e541bfcea9f55d8809d0a422c784cacd703029',
        'Wrong V3 composition audit')
    expected_aliases = {name: original.PREFIX + name for name in (
        'RmDisableAdapterChecked', 'RmShutdownAdapterChecked', 's540RmAdapterHasResources',
        's540RmDisableAdapterChecked', 's540RmShutdownAdapterChecked')}
    require(audit['new_original_private_names'] == expected_aliases, 'V3 original aliases changed')
    expected_namespace = ('/* V3 original private aliases; project bridges remain strong. */\n#include "' +
        str(namespace) + '"\n' + ''.join('#define ' + key + ' ' + value + '\n'
            for key, value in audit['new_original_private_names'].items()))
    require(v3_namespace.read_text() == expected_namespace, 'V3 private namespace differs from exact composition')
    flags = original.original_bridge_flags(upstream, output,
        Path(cc[0]) if host_control else Path('/usr/bin/clang'), v3_namespace)
    flags = [value.replace(str(upstream), str(v3 / 'source')) for value in flags]
    flags += ['--target=x86_64-apple-macos15.0', '-mkernel', '-DKERNEL', '-D__KERNEL__',
        '-Werror', '-Wno-unused-parameter', '-Wframe-larger-than=4096']
    def unit(item):
        label, relative = item
        source = (v3 / 'source' if label == 'baseline' else composition / 'source') / relative
        obj = output / (label + '-' + source.stem + '.o')
        command = [*cc, *flags, '-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1', '-c', str(source), '-o', str(obj)]
        execution.commands.run(*command, diagnostic_log=output / (obj.stem + '.log'))
        defined, imports, unused = original.macho_symbols(obj)
        metaclass.verify_no_initializers(obj)
        return {'variant': label, 'source': relative, 'source_sha256': digest(source),
            'object': obj.name, 'object_sha256': digest(obj), 'defined': sorted(defined),
            'imports': sorted(imports), 'command': command, 'implicit_initializers': False}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        units = list(pool.map(unit, [(label, relative) for label in ('baseline', 'proposed') for relative in SOURCES]))
    for relative in SOURCES:
        base, changed = [row for row in units if row['source'] == relative]
        require(base['defined'] == changed['defined'], 'Guard changed original defined ABI: ' + relative)
        require(set(changed['imports']) <= set(base['imports']), 'Guard gained a new external dependency: ' + relative)
        changed['removed_imports'] = sorted(set(base['imports']) - set(changed['imports']))
    source = composition / 'source' / next(iter(SOURCES))
    negative = []
    for index, options in enumerate(([], ['-DS540_NVIDIA_NO_OS_EVENT_BACKEND=0'],
            ['-DS540_NVIDIA_NO_OS_EVENT_BACKEND=2'])):
        command = [*cc, *flags, *options, '-c', str(source), '-o', str(output / f'refused-{index}.o')]
        process = subprocess.run(command, text=True, capture_output=True)
        diagnostic = process.stdout + process.stderr
        (output / f'configuration-{index}.log').write_text(diagnostic)
        require(process.returncode != 0 and 'requires explicit S540_NVIDIA_NO_OS_EVENT_BACKEND=1' in diagnostic,
            'Invalid event backend selection was not explicitly refused')
        negative.append({'flags': options, 'explicit_configuration_refused': True})
    return {'status': 'six-full-original-units-compiled', 'native_apple_compiler': not host_control,
        'translation_units': units, 'configuration_negative_controls': negative,
        'v3_namespace_sha256': digest(v3_namespace), 'whole_program_link_checked': False,
        'kernel_execution': 'not_tested'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'upstream', 'namespace', 'v3-output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--host-control', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    upstream = args.upstream.resolve(strict=True); namespace = args.namespace.resolve(strict=True)
    v3 = args.v3_output.resolve(strict=True)
    require(execution.commands.run('git', '-C', str(upstream), 'rev-parse', 'HEAD').stdout.strip() == original.COMMIT,
        'Wrong original Git identity')
    require(not execution.commands.run('git', '-C', str(upstream), 'status', '--porcelain').stdout,
        'Original tree is dirty')
    source_contract = json.loads((ROOT / 'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    require(digest(namespace) == source_contract['namespace_sha256'], 'Original namespace changed')
    composition = output / 'composition'
    result = {'format': 1, 'component': 'nvidia-prospective-os-event-policy',
        'status': 'running', 'source_only': True, 'production_candidate_allowed': False,
        'original_callbacks_implemented': False, 'whole_bootstrap_exclusion_proven': False,
        'kernel_execution': 'not_tested', 'gpu_access': False}
    try:
        result['composition'] = prepare(v3 / 'source', composition)
        execution.commands.run(sys.executable, str(HERE / 'tests/test_event_policy_contracts.py'),
            '--upstream', str(upstream), '--v3-output', str(v3),
            diagnostic_log=output / 'source-contracts.log')
        result['native_controls'] = controls(output, upstream, namespace, composition, args.host_control)
        result['full_unit_compile'] = kernel_compile(output / 'kernel', upstream, namespace, v3, composition, args.host_control)
        result['source_sha256'] = {p.relative_to(HERE).as_posix(): digest(p) for p in sorted(HERE.rglob('*'))
            if p.suffix in ('.c', '.h', '.py')}
        result['status'] = 'passed-isolated-event-feature-guard-controls'
    except Exception as error:
        result.update(status='failed', error=str(error)); raise
    finally:
        (output / 'os-event-policy-checks.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'checks_per_variant': 271,
        'full_original_units': 6, 'production_candidate_allowed': False}))

if __name__ == '__main__': main()
