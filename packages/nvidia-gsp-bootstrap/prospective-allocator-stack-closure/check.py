#!/usr/bin/env python3
"""Actual allocator/core bodies, negative controls and narrow Mach-O replay."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import prepare
sys.path.insert(0, str(ROOT / 'builders'))
import check_nvidia_global_lifecycle as lifecycle
import nvidia_stack_usage as stack
import nvidia_stack_root_closure as closure
import nvidia_metaclass_initializers as macho


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def command(argv, cwd, log):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, text=True,
        capture_output=True, timeout=180)
    log.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError('Actual allocator command failed: ' + str(log) + '\n' + result.stderr[-4000:])
    return result


def flags(capture, base, *, host=False):
    old = capture['cwd'].split('/composition/source/')[0] + '/composition'
    values, result, index = capture['command'][1:], [], 0
    # Compilation policy can occur after -c/-o in an actual captured command.
    # Preserve every flag irrespective of operand position.
    while index < len(values):
        value = values[index]
        if value in ('-c', '-o', '-MF', '-arch', '-target'):
            index += 2
            continue
        if value in ('-MD', '-MMD', '-fstack-usage') or value.startswith('-mmacosx-version-min'):
            index += 1
            continue
        result.append(value.replace(old, str(base)))
        index += 1
    if host:
        result = lifecycle._user_flags([v for v in result if v != '-mkernel'], [], True)
    return result


def run(args):
    base = args.base.resolve(strict=True)
    native = args.native.resolve(strict=True)
    cc, decoder = args.cc.resolve(strict=True), args.llvm_objdump.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Fresh allocator controls output required.')
    output.mkdir(parents=True)
    successor = output / 'successor'
    preparation = prepare.prepare(base / 'source', successor)
    cwd = base / 'source/src/nvidia'
    captures = {name: json.loads((native / ('original-objects/' + stem + '.stack.json')).read_text())
                for name, stem in ((prepare.CORE, 'core'), (prepare.MEMORY, 'memory_tracking'))}
    for name, capture in captures.items():
        if capture['source_sha256'] != prepare.BASE_SHA256[name]:
            raise ValueError('The native measured source differs from reviewed base: ' + name)
    include = ['-I', str(HERE), '-I', str(base / 'project/packages/nvidia-gsp-bootstrap/prospective-first-transaction/record'),
        '-I', str(base / 'project/packages/nvidia-darwin-services/src'),
        '-I', str(base / 'project/packages/nvidia-os-adapter/upstream/include')]
    host_flags = [*flags(captures[prepare.CORE], base, host=True), *include,
        '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-format-nonliteral', '-pthread',
        '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
    controls = {}
    for variant in ('actual', 'mutable-global-callback-mutant', 'foreign-entry-mutant', 'tracking-public-bypass-mutant'):
        work = output / variant
        work.mkdir()
        core = successor / 'source' / prepare.CORE
        memory = successor / 'source' / prepare.MEMORY
        guard = HERE / 'S540NvidiaAllocatorEpoch.c'
        if variant == 'mutable-global-callback-mutant':
            memory = work / 'memory_tracking.c'
            text = (successor / 'source' / prepare.MEMORY).read_text()
            beginning = text.index('        /* Global identities use their immutable original implementations.')
            end = text.index('    }\n    if (pMem == NULL', beginning)
            memory.write_text(text[:beginning] + '        pMem = pAlloc->_portAlloc(pAlloc, paddedLength);\n' + text[end:])
        if variant == 'foreign-entry-mutant':
            guard = work / 'S540NvidiaAllocatorEpoch.c'
            text = (HERE / guard.name).read_text()
            text = prepare.modify_function(text, 'authorize', lambda body:
                'authorize(NvU64 *thread)\n{ *thread = 1; return NV_OK; }')
            guard.write_text(text)
        if variant == 'tracking-public-bypass-mutant':
            memory = work / 'memory_tracking.c'
            text = (successor / 'source' / prepare.MEMORY).read_text()
            text = prepare.modify_function(text, 'portMemInitializeAllocatorTracking', lambda body:
                body[:body.index('{')] + '{\n'
                '    s540AllocatorInitializeTracking(pAlloc, pTracking PORT_MEM_CALLERINFO_COMMA_PARAM);\n}')
            memory.write_text(text)
        binary = work / 'check'
        argv = [str(cc), *host_flags,
            '-DMEMORY_SOURCE="' + str(memory) + '"', '-DCORE_SOURCE="' + str(core) + '"',
            str(HERE / 'tests/check_actual.c'), str(guard), '-Wl,--gc-sections', '-o', str(binary)]
        command(argv, cwd, work / 'compile.log')
        observations = []
        scenarios = range(13) if variant == 'actual' else [0 if variant.startswith('mutable') else
            10 if variant.startswith('tracking') else 1]
        for scenario in scenarios:
            result = subprocess.run([str(binary), str(scenario)], text=True, capture_output=True,
                timeout=60, env=environment)
            (work / ('scenario-%d.log' % scenario)).write_text(result.stdout + result.stderr)
            try:
                observed = json.loads(result.stdout)
            except json.JSONDecodeError:
                raise ValueError('Allocator body control did not return a structured result: ' + result.stderr[-3000:])
            observed['exit_code'] = result.returncode
            observations.append(observed)
            if variant == 'actual' and (result.returncode or observed['failures']):
                raise ValueError('Actual allocator control failed: ' + str(work))
            if variant != 'actual' and (result.returncode == 0 or not observed['failures']):
                raise ValueError('Required allocator mutation was not detected: ' + variant)
        controls[variant] = {'observations': observations,
                             'binary_sha256': stack.sha(binary), 'command': argv}

    cross = output / 'cross'
    cross.mkdir()
    sdk = args.sdk.resolve(strict=True)
    cross_units, graphs = [], {}
    selected = [('baseline-memory', base / 'source' / prepare.MEMORY, captures[prepare.MEMORY]),
        ('candidate-memory', successor / 'source' / prepare.MEMORY, captures[prepare.MEMORY]),
        ('candidate-core', successor / 'source' / prepare.CORE, captures[prepare.CORE]),
        ('candidate-epoch', HERE / 'S540NvidiaAllocatorEpoch.c', captures[prepare.CORE])]
    for label, source, capture in selected:
        obj = cross / (label + '.o')
        dep = obj.with_suffix('.d')
        argv = [str(cc), *flags(capture, base), *include,
            '-target', 'x86_64-apple-macos15', '-DKERNEL', '-D__KERNEL__',
            '-isystem', str(sdk / 'Headers'), '-Werror', '-fstack-usage',
            '-MMD', '-MF', str(dep), '-c', str(source), '-o', str(obj)]
        command(argv, cwd, obj.with_suffix('.log'))
        reference = stack.capture_usage(source, obj, argv, cwd=cwd, native_apple=False)
        unit = stack.load_capture(reference)
        measured = {'capture': Path(reference['path']), 'unit': unit, 'object': obj,
                    'image': macho.Object(obj, allow_empty_code_without_symbols=True)}
        graph = closure.fresh_graph(measured, [str(decoder), '--macho', '--disassemble',
            '--no-show-raw-insn', '--no-symbolic-operands'])
        definitions = sorted(symbol.name for symbol in measured['image'].symbols
                             if symbol.section and symbol.kind & 1)
        if label == 'candidate-epoch':
            expected = sorted('_' + name for name in prepare.EXPORTS[prepare.UNIT])
            if definitions != expected or any(section.size and section.name in
                    ('__mod_init_func', '__mod_term_func', '__constructor', '__destructor')
                    for section in measured['image'].sections):
                raise ValueError('Allocator guard export/implicit-lifecycle contract changed.')
        graphs[label] = graph
        dependencies = {}
        for name in shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name); path = path if path.is_absolute() else cwd / path
            dependencies[str(path.resolve(strict=True))] = stack.sha(path)
        cross_units.append({'label': label, 'source_sha256': stack.sha(source),
            'object_sha256': stack.sha(obj), 'capture': reference,
            'command': argv, 'dependency_sha256': dependencies,
            'defined_external_symbols': definitions})
    def named(label, symbol):
        nodes = [node for node in graphs[label]['nodes'] if symbol in node['symbols']]
        if len(nodes) != 1:
            raise ValueError('Expected one exact actual allocator machine function: ' + symbol)
        return nodes[0]
    summary = {}
    for name in ('portMemAllocNonPaged', 'portMemAllocPaged', 'portMemFree'):
        symbol = '_s540Global_' + name
        before, after = named('baseline-memory', symbol), named('candidate-memory', symbol)
        before_indirect = [s for s in before['unknown_sites'] if s['reason'] == 'indirect-control-transfer']
        after_indirect = [s for s in after['unknown_sites'] if s['reason'] == 'indirect-control-transfer']
        if not before_indirect or after_indirect:
            raise ValueError('Global allocator indirect site was not actually removed: ' + name)
        summary[name] = {'baseline_static_frame_bytes': before['static_frame_bytes'],
            'candidate_static_frame_bytes': after['static_frame_bytes'],
            'baseline_indirect_sites': before_indirect,
            'candidate_indirect_sites': after_indirect,
            'candidate_calls': after['calls']}
        summary[name]['scope'] = 'Immediate machine function only; callees and context-sensitive generic dispatch remain separate.'
    generic = named('candidate-memory', '_s540Global__portMemAllocatorAlloc')
    if not any(s['reason'] == 'indirect-control-transfer' for s in generic['unknown_sites']):
        raise ValueError('Generic dynamic allocator fallback was unexpectedly erased.')
    guard_graph = closure.selected_roots([graphs['candidate-epoch']],
        {'global_use': '_s540AllocatorGlobalUse'})['roots']['global_use']
    if not guard_graph['compiled_subgraph_complete']:
        raise ValueError('The readiness guard did not retain its finite compiled local graph.')
    result = {'format': 1, 'status': 'actual-global-allocator-sites-closed; aggregate-stack-unproven',
        'preparation': preparation, 'controls': controls, 'cross_units': cross_units,
        'global_allocator_machine_sites': summary,
        'global_use_guard_compiled_bound_bytes': guard_graph['compiled_subgraph_upper_bound_bytes'],
        'global_use_guard_scope': 'Compiled local graph only; target stack admission remains false.',
        'generic_dynamic_allocator_indirect_fallback_preserved': True,
        'cpu_fixture_scope': 'Complete transformed NVIDIA core/memory_tracking bodies and real guard; record identity, raw allocation, tracking lock and other port module implementations are explicit host fixtures.',
        'native_apple_compilation': False, 'aggregate_stack_proven': False,
        'original_entry_admission': False, 'hardware_execution': False,
        'production_candidate_allowed': False}
    write(output / 'results.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'native', 'cc', 'llvm-objdump', 'sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    outcome = run(parser.parse_args())
    print(json.dumps({'status': outcome['status'], 'machine_sites': outcome['global_allocator_machine_sites']}))
