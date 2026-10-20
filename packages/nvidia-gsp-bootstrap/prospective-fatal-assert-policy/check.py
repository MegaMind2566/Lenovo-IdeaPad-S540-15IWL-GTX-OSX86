#!/usr/bin/env python3
"""Compile the actual fatal assertion successor and execute its real abort path."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import prepare

HERE, ROOT = prepare.HERE, prepare.ROOT
sys.path.insert(0, str(ROOT/'builders'))
import check_nvidia_execution as controls
import compile_nvidia_global_rm as original
import nvidia_stack_usage as stack
import nvidia_stack_root_closure as closure
import nvidia_nvoc_definitions as binding
import link_nvidia_first_transaction as linker


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def verify_fatal_node(node, target, image, *, defensive_trap=False):
    require(not node.get('non_strong_external_symbols') and node['static_frame_bytes'] is not None,
            'Fatal path contains an ambiguous or unmeasured definition')
    require(len(node['calls']) == 1 and node['calls'][0]['target'] == {'symbol': target},
            'Fatal path gained another call or branch')
    for unknown in node['unknown_sites']:
        require(defensive_trap and unknown['reason'] == 'unreviewed-special-control-transfer',
                'Fatal path gained an indirect/unknown control transfer')
        text = [s for s in image.sections if s.name == '__text']
        require(len(text) == 1 and 'address' in unknown, 'Defensive trap lacks an exact text location')
        offset = unknown['address']-text[0].address
        require(0 <= offset < text[0].size-1 and
                image.data[text[0].offset+offset:text[0].offset+offset+2] == b'\x0f\x0b',
                'Only the exact reviewed defensive ud2 is permitted')
    require(not defensive_trap or len(node['unknown_sites']) <= 1,
            'Fatal helper gained multiple special transfers')


def check(args):
    upstream = original._pinned_upstream(args.upstream)
    namespace = args.namespace.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(upstream) and not output.is_relative_to(HERE),
            'Fresh nonoverlapping output required')
    require(not output.is_relative_to(ROOT) or output.is_relative_to(ROOT/'build'), 'Repository output must be below build/')
    ns = json.loads((ROOT/'packages/nvidia-global-rm/upstream/adapted/SOURCE-CONTRACT.json').read_text())
    require(sha(namespace) == ns['namespace_sha256'], 'Original namespace changed')
    contract = json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    for name, expected in contract['repository_dependency_sha256'].items():
        require(sha(ROOT/name) == expected, 'Actual diagnostic provider changed: '+name)
    if not args.host_control:
        require('Apple clang version' in controls.commands.run('/usr/bin/xcrun', 'clang', '--version').stdout,
                'Native Apple compiler identity not established')
    output.mkdir(parents=True)
    controls.commands.run(sys.executable, str(HERE/'tests/test_source_contracts.py'), '--upstream', str(upstream),
                          diagnostic_log=output/'source-contracts.log')
    proposed = prepare.prepare(upstream, output/'overlay')
    header, source = output/'overlay'/prepare.HEADER, output/'overlay'/prepare.SOURCE
    flags = ['-D'+prepare.PROFILE+'=1', '-I', str(upstream/'src/nvidia/inc/libraries/utils'), '-include', str(header)]
    fixture = output/'selected_actual_bodies.c'
    pieces = ['#include "nv.h"\n#include "os-interface.h"\n#include "utils/nvassert.h"\n']
    for name in prepare.FUNCTIONS:
        start, end, _ = prepare.function_span(proposed[prepare.SOURCE], name)
        pieces.append(proposed[prepare.SOURCE][start:end])
    fixture.write_text('\n\n'.join(pieces)+'\n')
    native = controls.original_header_case(output, 'fatal-assert', upstream, namespace,
        [fixture, ROOT/'packages/nvidia-global-rm/src/S540NvidiaGlobalRmDiagnostics.c', HERE/'tests/check_fatal_assert.c'],
        [ROOT/'packages/nvidia-global-rm/src/S540NvidiaGlobalRmFormat.cpp'],
        {'component': 'fatal-rm-assert-policy', 'checks': 54, 'fatal_cases': 8},
        host_control=args.host_control, dead_strip=True,
        extra_c_flags=[*flags, '-std=gnu11', '-Wno-unused-parameter'])
    cc, cxx = controls.crypto.compiler_pair(args.host_control)
    bridge = original.original_bridge_flags(upstream, output, Path(cc[0]), namespace)
    target_flags = ['-target', 'x86_64-apple-macos15'] if args.host_control else ['-arch', 'x86_64', '-mmacosx-version-min=15.0']
    kernel = ['-mkernel', '-DKERNEL', '-D__KERNEL__', '-Wframe-larger-than=4096', '-Werror=frame-larger-than', '-fstack-usage']
    rows = []
    def compile_c(src, obj, options):
        command = [*cc, *bridge, *target_flags, *kernel, *options, '-c', str(src), '-o', str(obj)]
        controls.commands.run(*command, diagnostic_log=obj.with_suffix('.log'))
        rows.append(stack.capture_usage(src, obj, command, cwd=ROOT, native_apple=not args.host_control))
        return original.macho_symbols(obj)
    compile_c(source, output/'nvassert-kernel.o', flags)
    probe = output/'macro_probe.c'
    probe.write_text('''#include "nv.h"
#include "utils/nvassert.h"
void s540FatalMacroProbe(void) { NV_ASSERT(0); }
void s540FatalStatusProbe(void) { NV_ASSERT_OK_FAILED("status", 73); }
void s540FatalPrecompProbe(void) { NV_ASSERT_PRECOMP(0); }
void s540FatalFunctionProbe(void) { NV_ASSERT_FAILED_FUNC("function"); }
void s540FatalFunctionStatusProbe(void) { NV_ASSERT_OK_FAILED_FUNC("status", 91); }
''')
    _, imports, _ = compile_c(probe, output/'macro-probe.o', flags)
    require(imports == {original.PREFIX+name for name in prepare.FUNCTIONS},
            'Assertion macro probe gained pre-fatal logging/journaling or another dependency')
    compile_c(ROOT/'packages/nvidia-global-rm/src/S540NvidiaGlobalRmDiagnostics.c', output/'diagnostics.o', [])
    kernel_flags, cpp = linker.kernel_flags(args.sdk.resolve(strict=True))
    if args.host_control:
        kernel_flags = ['-target', 'x86_64-apple-macos15', *kernel_flags[3:]]
    format_source = ROOT/'packages/nvidia-global-rm/src/S540NvidiaGlobalRmFormat.cpp'
    format_obj = output/'format-kernel.o'
    command = [*cxx, *kernel_flags, *cpp, '-fstack-usage', '-c', str(format_source), '-o', str(format_obj)]
    controls.commands.run(*command, diagnostic_log=output/'format-kernel.log')
    rows.append(stack.capture_usage(format_source, format_obj, command, cwd=ROOT, native_apple=not args.host_control))
    require('panic' in original.macho_symbols(format_obj)[1], 'Actual KERNEL provider lacks the real panic import')
    manifest = output/'stack-usage-manifest.json'
    stack.usage_manifest(rows, manifest)
    paths = binding.Paths([])
    units, missing = closure.project_manifest(manifest, paths, expected_count=4)
    require(not missing, 'Actual policy objects missing')
    decoder = ([str(args.llvm_objdump), '--macho', '--disassemble', '--no-show-raw-insn', '--no-symbolic-operands']
               if args.llvm_objdump else ['/usr/bin/xcrun', 'otool', '-tv'])
    graphs = [closure.fresh_graph(unit, decoder) for unit in units]
    def exact_node(symbol):
        found = [(g, n) for g in graphs for n in g['nodes'] if symbol in n['external_symbols']]
        require(len(found) == 1, 'Fatal path requires one exact strong definition: '+symbol)
        graph, node = found[0]
        image = next(unit['image'] for unit in units if unit['unit']['object_sha256'] == graph['object_sha256'])
        return node, image
    for name in prepare.FUNCTIONS:
        node, image = exact_node('_'+original.PREFIX+name)
        verify_fatal_node(node, '_'+original.PREFIX+'os_bug_check', image, defensive_trap=True)
    for symbol, target in (('_'+original.PREFIX+'os_bug_check', '_s540GlobalRmBugCheck'), ('_s540GlobalRmBugCheck', '_panic')):
        node, image = exact_node(symbol)
        verify_fatal_node(node, target, image)
    macro_targets = {'_s540FatalMacroProbe': 'nvAssertFailedNoLog', '_s540FatalStatusProbe': 'nvAssertOkFailedNoLog',
        '_s540FatalPrecompProbe': 'nvAssertFailed', '_s540FatalFunctionProbe': 'nvAssertFailed',
        '_s540FatalFunctionStatusProbe': 'nvAssertOkFailed'}
    for symbol, target in macro_targets.items():
        node, image = exact_node(symbol)
        verify_fatal_node(node, '_'+original.PREFIX+target, image)
    roots = {name: '_'+original.PREFIX+name for name in prepare.FUNCTIONS}
    roots.update({name[1:]: name for name in macro_targets})
    measured = closure.selected_roots(graphs, roots)
    for label, root in measured['roots'].items():
        require(root['definition_count'] == 1 and root['recursive_component_count'] == 0,
                'Fatal assertion still reaches recursion: '+label)
        unavailable = [b for b in root['barriers'] if b['reason'] == 'external-stack-bound-unavailable']
        require([b['target'] for b in unavailable] == ['_panic'], 'Fatal path does not end at the real kernel panic: '+label)
        require(all(b['reason'] in ('external-stack-bound-unavailable', 'unreviewed-special-control-transfer')
                    for b in root['barriers']), 'Fatal path gained an unresolved barrier')
    paths.unchanged()
    negatives = []
    for index, options in enumerate(([], ['-D'+prepare.PROFILE+'=0'], ['-D'+prepare.PROFILE+'=2'],
                                    ['-D'+prepare.PROFILE+'=1', '-DNV_MODS=1'])):
        command = [*cc, *bridge, *target_flags, *kernel, *options, '-I', str(upstream/'src/nvidia/inc/libraries/utils'),
                   '-include', str(header), '-c', str(probe), '-o', str(output/'refused.o')]
        result = subprocess.run(command, text=True, capture_output=True)
        (output/f'negative-{index}.log').write_text(result.stdout+result.stderr)
        require(result.returncode != 0 and ('Fatal assertion' in result.stderr or 'fatal assertion' in result.stderr),
                'Invalid fatal policy was accepted')
        negatives.append({'options': options, 'rejected': True})
    evidence = {'format': 1, 'status': 'passed-isolated-fatal-assert-policy-controls',
        'native_apple_execution': not args.host_control, 'native_controls': native,
        'actual_selected_successor_helper_bodies_executed': list(prepare.FUNCTIONS),
        'actual_platform_bug_check_provider': 'S540NvidiaGlobalRmDiagnostics.c -> S540NvidiaGlobalRmFormat.cpp',
        'host_abort_is_real': True, 'kernel_panic_import_observed': True,
        'successor_source_sha256': {name: prepare.sha(text) for name, text in proposed.items()},
        'macro_probe_imports': sorted(imports), 'stack_path': measured,
        'configuration_negative_controls': negatives, 'aggregate_stack_proven': False,
        'panic_stack_bound': 'not_established', 'successful_oom_unwind_claimed': False,
        'ordinary_nv_check_bodies_changed': False,
        'assertion_diagnostics_lost': ['pre-fatal NVLOG', 'RCDB journal', 'backtrace', 'file/line output'],
        'kernel_execution': 'not_tested', 'gpu_access': False, 'original_entry_admission': False,
        'production_candidate_allowed': False, 'reconstruction_is_new_work': True}
    (output/'fatal-assert-checks.json').write_text(json.dumps(evidence, indent=2, sort_keys=True)+'\n')
    return evidence


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('upstream', 'namespace', 'output', 'sdk'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--host-control', action='store_true')
    p.add_argument('--llvm-objdump', type=Path)
    result = check(p.parse_args())
    print(json.dumps({'status': result['status'], 'fatal_cases_per_variant': 8, 'aggregate_stack_proven': False}))
