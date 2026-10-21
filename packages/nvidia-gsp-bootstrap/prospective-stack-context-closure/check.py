#!/usr/bin/env python3
"""Replay real allocator specialization, machine edges and isolated controls.

This checker never prunes an OOM, generic callback, external or recursive
barrier to manufacture an aggregate bound. Its finite contract is the actual
immediate global allocator machine function and its exact direct callees.
"""
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
sys.path.insert(0, str(HERE))
import prepare
sys.path.insert(0, str(ROOT / 'builders'))
import nvidia_stack_usage as stack
import nvidia_stack_root_closure as closure
import nvidia_metaclass_initializers as macho

COMPOSITION_SHA = '40f0fd1fc279421464c14f9b98f7fa84f6850e6fafb61d46aa60663ce471dd4c'
SUBSET_SHA = '513b16a89c3789b8a1ce88442e161a762ebdea86d40defc2544278ecfeed8e2f'
ISOLATED_SHA = '12a52386ade3c4e4acd4777786f5195ad7309a4e5109fbc673a1d75fb1ed41ce'
EXPECTED = {
    '_s540Global_portMemAllocNonPaged': {'_s540AllocatorGlobalUse',
        '_s540Global__portMemAllocNonPagedUntracked', '_s540Global_portMemReportOom'},
    '_s540Global_portMemAllocPaged': {'_s540AllocatorGlobalUse',
        '_s540Global__portMemAllocPagedUntracked', '_s540Global_portMemReportOom'},
    '_s540Global_portMemFree': {'_s540AllocatorGlobalUse', '_s540Global__portMemFreeUntracked'}}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    path = Path(path)
    require(not path.is_symlink(), 'Symlink input refused: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def execute(argv, log, *, cwd=None, environment=None, expected=0):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, text=True,
        capture_output=True, timeout=180, env=environment)
    log.write_text(result.stdout + result.stderr)
    require(result.returncode == expected, 'Actual command failed: ' + str(log) + '\n' + result.stderr[-3000:])
    return result


def dependency_hashes(dep, cwd):
    values = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
    return {str((Path(value) if Path(value).is_absolute() else cwd / value).resolve(strict=True)):
            sha((Path(value) if Path(value).is_absolute() else cwd / value).resolve(strict=True))
            for value in values}


def named(graph, symbol):
    nodes = [node for node in graph['nodes'] if symbol in node['symbols']]
    require(len(nodes) == 1, 'Exact compiled function owner missing/ambiguous: ' + symbol)
    return nodes[0]


def direct_global_contract(graph):
    result = {}
    for symbol, targets in EXPECTED.items():
        node = named(graph, symbol)
        require(not node['unknown_sites'], 'Actual global function has unresolved machine transfers: ' + symbol)
        actual = {edge['target'].get('symbol') for edge in node['calls']}
        require(actual == targets, 'Actual global dispatch differs from reviewed concrete callees: ' + symbol)
        require(isinstance(node['static_frame_bytes'], int) and node['static_frame_bytes'] <= 4096,
            'Global function frame is missing/dynamic/oversized: ' + symbol)
        result[symbol] = {'static_frame_bytes': node['static_frame_bytes'],
            'direct_callees': sorted(actual), 'calls': node['calls'], 'unknown_sites': node['unknown_sites']}
    return result


def machine_graph(source, obj, command, cwd, decoder):
    reference = stack.capture_usage(source, obj, command, cwd=cwd, native_apple=False)
    unit = stack.load_capture(reference)
    graph = closure.fresh_graph({'unit': unit, 'object': obj,
        'image': macho.Object(obj, allow_empty_code_without_symbols=True), 'capture': Path(reference['path'])},
        [str(decoder), '--macho', '--disassemble', '--no-show-raw-insn', '--no-symbolic-operands'])
    return graph, reference


def run(args):
    base, isolated = args.base.resolve(strict=True), args.isolated_controls.resolve(strict=True)
    cc, decoder = args.cc.resolve(strict=True), args.decoder.resolve(strict=True)
    require(sha(base / 'composition.json') == COMPOSITION_SHA, 'Exact selected operational composition required')
    require(sha(base / 'changed-original-compilation.json') == SUBSET_SHA, 'Exact original subset receipt required')
    subset = json.loads((base / 'changed-original-compilation.json').read_text())
    row = next(row for row in subset['results'] if row['source'] == prepare.MEMORY)
    source = base / 'source' / prepare.MEMORY
    require(sha(source) == row['source_sha256'] == prepare.BASE_SHA256, 'Actual final source differs')
    require(all(sha(Path(path)) == digest for path, digest in row['dependency_sha256'].items()),
        'Bound SDK source dependencies changed')
    require(sha(isolated / 'results.json') == ISOLATED_SHA, 'Exact completed isolated controls required')
    old_controls = json.loads((isolated / 'results.json').read_text())
    output = args.output.resolve()
    require(not output.exists(), 'Fresh stack context controls output required')
    output.mkdir(parents=True)
    prepared = output / 'successor'
    preparation = prepare.prepare(base / 'source', prepared)
    candidate = prepared / 'source' / prepare.MEMORY
    inputs = {str(path): sha(path) for path in (Path(__file__), HERE / 'prepare.py', HERE / 'tests/check_oom.c',
        base / 'composition.json', base / 'changed-original-compilation.json', isolated / 'results.json', cc, decoder)}
    results = {'format': 1, 'status': 'running', 'input_sha256': inputs,
        'preparation': preparation, 'kernel_execution': False, 'gpu_access': False,
        'original_entry_admission': False, 'hardware_admission': False,
        'kernel_stack_bound_proven': False, 'production_candidate_allowed': False,
        'native_darwin_compilation': False, 'native_ci_requested': False}
    write(output / 'results.json', results)
    try:
        old_body = old_controls['controls']['actual']
        argv = old_body['command'][:]
        require(Path(argv[0]).resolve(strict=True) == cc, 'Isolated compiler differs from requested compiler')
        matches = [i for i, value in enumerate(argv) if value.startswith('-DMEMORY_SOURCE=')]
        require(len(matches) == 1, 'Exact isolated actual memory source operand required')
        argv[matches[0]] = '-DMEMORY_SOURCE="' + str(candidate) + '"'
        binary = output / 'actual-body-check'
        argv[argv.index('-o') + 1] = str(binary)
        # The previous fixture source and actual other bodies/guard are pinned
        # through their compact source contract before being reused.
        contract = json.loads((HERE.parent / 'prospective-allocator-stack-closure/VALIDATION.json').read_text())
        for name, digest in contract['code_sha256'].items():
            require(sha(HERE.parent / 'prospective-allocator-stack-closure' / name) == digest,
                    'Existing actual-body fixture/guard changed: ' + name)
        execute(argv, output / 'actual-body-compile.log', cwd=base / 'source/src/nvidia')
        body_binary_sha = sha(binary)
        environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
            UBSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
        observations = []
        for previous in old_body['observations']:
            observed = json.loads(execute([binary, str(previous['scenario'])],
                output / ('actual-body-%02d.log' % previous['scenario']), environment=environment).stdout)
            observed['exit_code'] = 0
            require(observed == previous, 'Algorithm-preservation actual-body regression detected')
            observations.append(observed)
        results['isolated_actual_body'] = {'fatal_sanitized_scenarios': len(observations),
            'assertions': sum(v['checks'] for v in observations), 'binary_sha256': body_binary_sha,
            'actual_observations_identical': True, 'command': argv, 'observations': observations,
            'fixture_scope': old_controls['cpu_fixture_scope']}
        oom_observations = {}
        for label, memory in (('baseline', source), ('candidate', candidate)):
            oom_binary = output / (label + '-oom-check')
            oom_command = argv[:]
            oom_command[oom_command.index('-o') + 1] = str(oom_binary)
            fixture_indices = [i for i, value in enumerate(oom_command) if value.endswith('/tests/check_actual.c')]
            require(len(fixture_indices) == 1, 'Exact original fixture source required')
            oom_command[fixture_indices[0]] = str(HERE / 'tests/check_oom.c')
            oom_command[matches[0]] = '-DMEMORY_SOURCE="' + str(memory) + '"'
            execute(oom_command, output / (label + '-oom-compile.log'), cwd=base / 'source/src/nvidia')
            observation = json.loads(execute([oom_binary], output / (label + '-oom.log'), environment=environment).stdout)
            require(observation['failures'] == 0 and observation['reports'] == 2 and observation['oom_count'] == 10,
                'Registered original OOM callback/rate behavior changed')
            oom_observations[label] = {'observation': observation, 'binary_sha256': sha(oom_binary), 'command': oom_command}
        require(oom_observations['baseline']['observation'] == oom_observations['candidate']['observation'],
            'Registered original OOM reporting no longer matches the baseline')
        results['registered_oom_behavior'] = oom_observations
        graphs, compiled = {}, []
        for label in ('baseline', 'candidate', 'noinline-mutant'):
            selected = source if label == 'baseline' else candidate
            if label == 'noinline-mutant':
                selected = output / 'noinline-mutant.c'
                text = candidate.read_text()
                require(text.count('__attribute__((always_inline)) inline') == 2, 'Exact helper pair required')
                selected.write_text(text.replace('__attribute__((always_inline)) inline', '__attribute__((noinline))'))
            obj, dep = output / (label + '.o'), output / (label + '.d')
            command = row['command'][:]
            require(Path(command[0]).resolve(strict=True) == cc, 'SDK compiler differs from requested compiler')
            command[command.index('-c') + 1] = str(selected)
            command[command.index('-o') + 1] = str(obj)
            command[command.index('-MF') + 1] = str(dep)
            execute(command, output / (label + '-compile.log'), cwd=Path(row['cwd']))
            graph, capture = machine_graph(selected, obj, command, Path(row['cwd']), decoder)
            write(output / (label + '-graph.json'), graph)
            graphs[label] = graph
            definitions = sorted(symbol.name for symbol in macho.Object(obj).symbols if symbol.section and symbol.kind & 1)
            require(definitions == sorted('_' + name for name in row['definitions']),
                'Exported generic ABI or external symbol set changed')
            compiled.append({'label': label, 'source': str(selected), 'source_sha256': sha(selected),
                'object': str(obj), 'object_sha256': sha(obj), 'capture': capture,
                'command': command, 'dependency_sha256': dependency_hashes(dep, Path(row['cwd']))})
        results['immediate_global_machine_contract'] = direct_global_contract(graphs['candidate'])
        rejected = []
        for label in ('baseline', 'noinline-mutant'):
            try:
                direct_global_contract(graphs[label])
            except ValueError as error:
                rejected.append({'variant': label, 'reason': str(error)})
            else:
                raise ValueError('Required unspecialized machine regression was not detected: ' + label)
        results['machine_negative_controls'] = rejected
        generic = named(graphs['candidate'], '_s540Global__portMemAllocatorAlloc')
        oom = named(graphs['candidate'], '_s540Global_portMemReportOom')
        require(any(v['reason'] == 'indirect-control-transfer' for v in generic['unknown_sites']),
            'Generic dynamic allocator fallback was erased')
        require(any(v['reason'] == 'indirect-control-transfer' for v in oom['unknown_sites']),
            'Genuine original OOM callback barrier was erased')
        # Include the entire actual memory graph. No diagnostic, callback or
        # downstream external edge is cut to produce this incomplete result.
        aggregate = closure.selected_roots([graphs['candidate']],
            {name.removeprefix('_s540Global_'): name for name in EXPECTED})
        write(output / 'local-aggregate-barriers.json', aggregate)
        require(all(not value['compiled_subgraph_complete'] for value in aggregate['roots'].values()),
            'An incomplete memory-only inventory was incorrectly certified')
        results['local_aggregate_barriers'] = {'path': str(output / 'local-aggregate-barriers.json'),
            'sha256': sha(output / 'local-aggregate-barriers.json'), 'scope': 'Memory TU only; every outgoing edge/barrier retained.'}
        results['preserved_barriers'] = {'generic_allocator': generic['unknown_sites'], 'oom_callback': oom['unknown_sites']}
        results['compiled_units'] = compiled
        for entry in compiled:
            require(sha(Path(entry['object'])) == entry['object_sha256'] and
                    sha(Path(entry['source'])) == entry['source_sha256'] and
                    all(sha(Path(p)) == h for p, h in entry['dependency_sha256'].items()),
                    'Fresh SDK source/object/dependencies changed')
        require(sha(binary) == body_binary_sha, 'Executed actual-body binary changed')
        require(all(sha(Path(p)) == h for p, h in inputs.items()), 'Bound inputs changed during checks')
        results['status'] = 'passed-immediate-global-dispatch-specialization-aggregate-unproven'
        return results
    except Exception as error:
        results.update(status='failed', error=str(error))
        raise
    finally:
        write(output / 'results.json', results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'isolated-controls', 'cc', 'decoder', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'actual_body_scenarios': result['isolated_actual_body']['fatal_sanitized_scenarios'],
        'machine_negative_controls': len(result['machine_negative_controls'])}, sort_keys=True))
