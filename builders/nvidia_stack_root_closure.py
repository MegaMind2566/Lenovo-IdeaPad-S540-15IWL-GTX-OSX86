#!/usr/bin/env python3
"""Exact selected-root stack barriers, never guessed external/indirect bounds.

Re-decodes every measured Mach-O rather than trusting archived graph JSON.
Selected RM roots describe prerequisites, including code not currently admitted
by the public owner. A finite compiled graph is not a kernel stack certificate.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess

import nvidia_metaclass_initializers as macho
import nvidia_nvoc_definitions as binding
import nvidia_stack_usage as stack

ROOTS = {
    'global_initialize_prerequisite': '_s540Global_coreInitializeRm',
    'adapter_initialize_prerequisite': '_s540Global_rm_init_adapter',
    'gpu_enter_shutdown_isolated_prerequisite': '_s540Global_gpuEnterShutdown_IMPL',
    'current_adapter_disable_prerequisite': '_s540Global_rm_disable_adapter',
    'current_adapter_shutdown_prerequisite': '_s540Global_rm_shutdown_adapter',
}
PROJECT_ROOTS = {
    'public_global_initialize': '_s540GlobalRmInitialize',
    'public_context_initialize': '_s540GspContextInitializeAdapter',
    'public_context_disable': '_s540GspContextDisableAdapter',
    'public_context_shutdown': '_s540GspContextShutdownAdapter',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def fresh_graph(checked, decoder):
    """Frozen collector semantics, independently replayed on verified inputs.

    The original collector is deliberately left byte-identical because the
    first-transaction source profile pins it. This read-only companion repeats
    its conservative transfer decoding and adds source/capture provenance.
    """
    unit, obj, image = checked['unit'], checked['object'], checked['image']
    require(stack.sha(obj) == unit['object_sha256'] and
            hashlib.sha256(image.data).hexdigest() == unit['object_sha256'],
            'Measured object changed before decoding.')
    texts = [(index, section) for index, section in enumerate(image.sections, 1)
             if section.name == '__text']
    require(len(texts) <= 1, 'Ambiguous executable text sections.')
    record = {'object': str(obj), 'object_sha256': unit['object_sha256'],
              'source': unit['source'], 'source_sha256': unit['source_sha256'],
              'capture_sha256': stack.sha(checked['capture']), 'nodes': []}
    if not texts or not texts[0][1].size:
        return record
    section_index, section = texts[0]
    definitions = image._defined(section_index)
    usage = {value['symbol']: value for value in unit['functions']}
    groups = defaultdict(list)
    for symbol in definitions:
        groups[symbol.value].append(symbol)
    positions = sorted(groups)
    nodes, at_address = [], {}
    for index, address in enumerate(positions):
        symbols = groups[address]
        aliases = sorted(symbol.name for symbol in symbols)
        reported = [usage[name] for name in aliases if name in usage]
        if not reported:
            frame, unknown = None, [{'reason': 'missing-compiler-stack-record'}]
        elif any(not value['static_frame_known'] for value in reported):
            frame, unknown = None, [{'reason': 'dynamic-compiler-stack-frame', 'records': reported}]
        elif len({value['reported_bytes'] for value in reported}) != 1:
            frame, unknown = None, [{'reason': 'conflicting-stack-record-aliases'}]
        else:
            frame, unknown = reported[0]['reported_bytes'], []
        node = {'id': unit['object_sha256'] + ':' + aliases[0], 'symbols': aliases,
                'external_symbols': sorted(symbol.name for symbol in symbols if symbol.kind & 1),
                'non_strong_external_symbols': sorted(symbol.name for symbol in symbols if symbol.kind & 1 and
                    (symbol.kind != 15 or binding.descriptors(image)[next(i for i, candidate in
                        enumerate(image.symbols) if candidate is symbol)] != 0)),
                'object': str(obj), 'start': address,
                'end': positions[index + 1] if index + 1 < len(positions) else section.address + section.size,
                'static_frame_bytes': frame, 'compiler_records': reported,
                'calls': [], 'unknown_sites': unknown}
        nodes.append(node)
        at_address[address] = node
    require(nodes, 'Actual executable text lacks named stack graph owners.')
    run = subprocess.run([*decoder, str(obj)], text=True, capture_output=True, timeout=180)
    require(not run.returncode, 'Actual Mach-O disassembly failed: ' + run.stderr[-1000:])
    require(stack.sha(obj) == unit['object_sha256'], 'Measured object changed during decoding.')
    instructions = stack.parse_disassembly(run.stdout)
    addresses = [value['address'] for value in instructions]
    by_offset = {value.offset: value for value in image.relocations(section)}

    def destination(address, relative):
        relocation = by_offset.get(address - section.address + relative)
        if relocation:
            if relocation.kind != 2 or not relocation.pc_relative or relocation.width != 4:
                return {'unresolved': 'unsupported-direct-branch-relocation'}
            try:
                target, function = image.target(section, relocation)
            except ValueError as error:
                return {'unresolved': str(error)}
            if function:
                # A same-TU function can still have external/weak linkage.
                # Preserve the actual relocation symbol for global uniqueness
                # checks instead of silently turning it into a private edge.
                if relocation.external and image.symbols[relocation.symbol].kind & 1:
                    return {'symbol': image.symbols[relocation.symbol].name}
                return {'local': function.value}
            if 'external' in target and target['addend'] == 0:
                return {'symbol': target['external']}
            return {'unresolved': 'non-code-or-interior-direct-call-target'}
        offset = address - section.address
        opcode = image.data[section.offset + offset]
        width = 1 if opcode == 0xeb or 0x70 <= opcode <= 0x7f else 4
        raw_start = section.offset + offset + relative
        raw = int.from_bytes(image.data[raw_start:raw_start + width], 'little', signed=True)
        return {'local': address + relative + width + raw}

    for node in nodes:
        owned = instructions[bisect_left(addresses, node['start']):bisect_left(addresses, node['end'])]
        if not owned or owned[0]['address'] != node['start']:
            node['unknown_sites'].append({'reason': 'missing-decoder-function-entry'})
        for instruction in owned:
            address, name, operands = instruction['address'], instruction['mnemonic'], instruction['operands']
            offset = address - section.address
            code = image.data[section.offset + offset:section.offset + min(offset + 8, section.size)]
            if name == '<undecoded>':
                node['unknown_sites'].append({'reason': 'undecoded-instruction', 'address': address})
                continue
            if name.startswith(('call', 'jmp', 'j')):
                if '*' in operands or operands.lstrip().startswith('%'):
                    node['unknown_sites'].append({'reason': 'indirect-control-transfer',
                        'address': address, 'instruction': name + ' ' + operands})
                    continue
                if code[:1] in (b'\xe8', b'\xe9', b'\xeb') or (code and 0x70 <= code[0] <= 0x7f):
                    relative = 1
                elif len(code) >= 2 and code[0] == 0x0f and 0x80 <= code[1] <= 0x8f:
                    relative = 2
                else:
                    node['unknown_sites'].append({'reason': 'unsupported-direct-branch-encoding', 'address': address})
                    continue
                target = destination(address, relative)
                if 'local' in target and node['start'] <= target['local'] < node['end'] and not name.startswith('call'):
                    continue
                if 'local' in target:
                    owner = at_address.get(target['local'])
                    target = {'node': owner['id']} if owner else {'unresolved': 'interior-or-unnamed-code-target'}
                node['calls'].append({'address': address, 'kind': 'call' if name.startswith('call') else 'branch',
                                      'target': target})
            elif name in ('lcall', 'ljmp', 'ljmpq', 'lret', 'iret', 'iretq', 'syscall', 'sysenter',
                          'sysret', 'sysretq', 'int', 'int3', 'into', 'ud2') or (
                    name in ('rep', 'repe', 'repne', 'bnd', 'data16', 'notrack') and
                    re.search(r'\b(?:call|jmp|ret|iret)[qlw]?\b', operands)):
                node['unknown_sites'].append({'reason': 'unreviewed-special-control-transfer', 'address': address})
            if operands.endswith(', %rsp') and not (
                    re.fullmatch(r'\$-?(?:0x[0-9a-f]+|\d+), %rsp', operands) and name in ('addq', 'subq') or
                    name == 'movq' and operands == '%rbp, %rsp'):
                node['unknown_sites'].append({'reason': 'unreviewed-stack-pointer-write',
                                              'address': address, 'instruction': name + ' ' + operands})
    record.update(nodes=nodes, decoder_output_sha256=hashlib.sha256(run.stdout.encode()).hexdigest())
    return record


def project_manifest(path, paths, *, expected_count=42, allow_missing=False):
    """Project manifests share directories with auxiliary linked SDK objects.

    Check the exact recorded units without pretending those auxiliary objects
    were measured. Missing archived inputs are an explicit diagnostic-only
    mode; native CI requires all original source/object/sidecar bytes.
    """
    paths.checked_file(str(path), stack.sha(path))
    manifest = json.loads(path.read_text())
    require(manifest.get('format') == 1 and manifest.get('status') == 'compiler-stack-usage-collected' and
            manifest.get('unit_count') == expected_count and len(manifest['units']) == expected_count,
            'Expected the complete measured project manifest.')
    captures, objects, units, missing = set(), set(), [], []
    for reference in manifest['units']:
        capture = paths.checked_file(reference['path'], reference['sha256'])
        require(capture not in captures, 'Repeated project capture.')
        captures.add(capture)
        unit = json.loads(capture.read_text())
        require(unit.get('format') == 1 and unit.get('status') == 'compiler-stack-usage-captured',
                'Unsupported measured project unit.')
        command = unit['command']
        require(isinstance(command, list) and all(isinstance(v, str) for v in command) and
                command.count('-fstack-usage') == command.count('-c') == command.count('-o') == 1 and
                '-fno-stack-usage' not in command and
                hashlib.sha256(json.dumps(command).encode()).hexdigest() == unit['command_sha256'],
                'Measured project compiler command identity changed.')
        missing_paths = []
        resolved = {}
        for key, hash_key in (('source', 'source_sha256'), ('object', 'object_sha256'),
                              ('usage_file', 'usage_sha256')):
            if unit[key] is None:
                continue
            try:
                resolved[key] = paths.checked_file(unit[key], unit[hash_key])
            except FileNotFoundError:
                if not allow_missing:
                    raise
                missing_paths.append(unit[key])
        if 'usage_file' in resolved:
            require(stack.parse_usage(resolved['usage_file'].read_text()) == unit['functions'],
                    'Measured project frame records changed.')
        if missing_paths:
            missing.append({'capture': reference, 'source': unit['source'], 'object': unit['object'],
                            'object_sha256': unit['object_sha256'], 'missing_paths': missing_paths,
                            'reason': 'actual-project-input-not-retained; no stack bound admitted'})
            continue
        source, obj = resolved['source'], resolved['object']

        def operand(option):
            index = command.index(option)+1
            require(index < len(command), 'Measured project compile operand missing.')
            value = Path(command[index])
            if not value.is_absolute():
                require(unit.get('cwd') and Path(unit['cwd']).is_absolute(),
                        'Relative project operand lacks an absolute recorded working directory.')
                value = Path(unit['cwd']) / value
            return paths.path(str(value))
        require(operand('-c') == source and operand('-o') == obj and capture == obj.with_suffix('.stack.json'),
                'Project command/capture does not identify its exact source/object.')
        require(obj not in objects, 'Repeated project object.')
        objects.add(obj)
        image = macho.Object(obj, allow_empty_code_without_symbols=True)
        if unit['usage_file'] is not None:
            require(resolved['usage_file'] == obj.with_suffix('.su'), 'Project stack output is not the actual sidecar.')
            definitions = {symbol.name for symbol in image.symbols if symbol.section and
                image.sections[symbol.section-1].name == '__text' and
                symbol.kind & 0xe0 == 0 and symbol.kind & 0x0e == 0x0e}
            require(all(row['symbol'] in definitions for row in unit['functions']),
                    'Project stack record lacks an actual text definition.')
        else:
            require(unit.get('usage_emission') == 'not-emitted-for-object-without-executable-code' and
                    unit['usage_sha256'] is None and not unit['functions'] and not obj.with_suffix('.su').exists() and
                    not any(s.size and (s.name == '__text' or s.flags & 0x80000400) for s in image.sections),
                    'Project absent stack records lack empty-object evidence.')
        units.append({'capture': capture, 'unit': unit, 'object': obj, 'image': image})
    return units, missing


def components(reached, adjacency):
    """Iterative SCC extraction: recursion in the input cannot exhaust Python."""
    seen, finish = set(), []
    for start in sorted(reached):
        if start in seen:
            continue
        todo = [(start, False)]
        while todo:
            node, leaving = todo.pop()
            if leaving:
                finish.append(node)
            elif node not in seen:
                seen.add(node)
                todo.append((node, True))
                todo.extend((child, False) for child in reversed(adjacency[node]) if child not in seen)
    reverse = defaultdict(list)
    for parent in reached:
        for child in adjacency[parent]:
            reverse[child].append(parent)
    seen, result = set(), []
    for start in reversed(finish):
        if start in seen:
            continue
        todo, group = [start], []
        seen.add(start)
        while todo:
            node = todo.pop()
            group.append(node)
            for parent in reverse[node]:
                if parent not in seen:
                    seen.add(parent)
                    todo.append(parent)
        result.append(sorted(group))
    return result


def selected_roots(graphs, roots, *, inventory_barriers=()):
    """Report every barrier; a missing edge or recursive component never costs 0."""
    nodes, provenance, definitions = {}, {}, defaultdict(list)
    non_strong = set()
    for graph in graphs:
        for raw in graph['nodes']:
            require(raw['id'] not in nodes, 'Duplicate measured graph identity is ambiguous.')
            node = deepcopy(raw)
            nodes[node['id']] = node
            provenance[node['id']] = {k: graph[k] for k in ('object', 'object_sha256', 'source',
                                                          'source_sha256', 'capture_sha256')}
            for name in node['external_symbols']:
                definitions[name].append(node['id'])
            non_strong.update(node.get('non_strong_external_symbols', []))
    adjacency = {}
    for identity, node in nodes.items():
        for name in node.get('non_strong_external_symbols', []):
            node['unknown_sites'].append({'reason': 'non-strong-code-definition', 'target': name})
        for name in node['external_symbols']:
            if len(definitions[name]) != 1:
                node['unknown_sites'].append({'reason': 'ambiguous-code-definition', 'target': name})
        edges = []
        for edge in node['calls']:
            target = edge['target']
            if 'node' in target:
                targets = [target['node']] if target['node'] in nodes else []
                if not targets:
                    node['unknown_sites'].append({'reason': 'missing-local-code-target', 'address': edge['address']})
            elif 'symbol' in target:
                targets = definitions[target['symbol']]
                if len(targets) != 1:
                    node['unknown_sites'].append({'reason': 'external-stack-bound-unavailable' if not targets else
                        'ambiguous-external-definition', 'address': edge['address'], 'target': target['symbol']})
                elif target['symbol'] in non_strong:
                    node['unknown_sites'].append({'reason': 'non-strong-external-definition',
                        'address': edge['address'], 'target': target['symbol']})
            else:
                targets = []
                node['unknown_sites'].append({'reason': target['unresolved'], 'address': edge['address']})
            edges.extend(targets)
        adjacency[identity] = sorted(set(edges))

    def describe(identity):
        node = nodes[identity]
        return {'id': identity, 'symbols': node['symbols'], 'static_frame_bytes': node['static_frame_bytes'],
                'compiler_source_locations': [value['source_location'] for value in node['compiler_records']],
                **provenance[identity]}

    results = {}
    for label, symbol in roots.items():
        candidates = sorted(definitions[symbol])
        parents = {identity: None for identity in candidates}
        depths = {identity: 0 for identity in candidates}
        queue = deque(candidates)
        while queue:
            identity = queue.popleft()
            for child in adjacency[identity]:
                if child not in parents:
                    parents[child], depths[child] = identity, depths[identity] + 1
                    queue.append(child)
        reached = set(parents)

        def route(identity):
            path = []
            while identity is not None:
                path.append(nodes[identity]['symbols'][0])
                identity = parents[identity]
            return list(reversed(path))

        barriers = [dict(value, function=describe(identity), shortest_compiled_path=route(identity),
                         distance_from_root=depths[identity])
                    for identity in sorted(reached) for value in nodes[identity]['unknown_sites']]
        # Missing objects could contain another external definition, even when
        # this retained root appears to be a leaf. Never certify a partial
        # inventory just because no currently visible direct edge escapes it.
        barriers.extend(deepcopy(inventory_barriers))
        recursive = [group for group in components(reached, adjacency)
                     if len(group) > 1 or group[0] in adjacency[group[0]]]
        recursive_nodes = {identity for group in recursive for identity in group}
        for group in recursive:
            first = min(group, key=lambda identity: (depths[identity], identity))
            barriers.append({'reason': 'recursion-cycle', 'function': describe(first),
                'component_members': [describe(identity) for identity in group],
                'shortest_compiled_path': route(first), 'distance_from_root': depths[first]})
        if not candidates:
            barriers.append({'reason': 'missing-root-definition', 'target': symbol})
        elif len(candidates) != 1:
            barriers.append({'reason': 'ambiguous-root-definition', 'target': symbol})
        elif symbol in non_strong:
            barriers.append({'reason': 'non-strong-root-definition', 'target': symbol})

        # Stop the diagnostic path before traversing recursion. The remaining
        # DAG has exact edges, but its largest frame sum is still not a runtime
        # peak/lower bound: branches are conservative and call-site live stack
        # depth and control-flow feasibility are not proven here.
        successors = {identity: [] if identity in recursive_nodes else adjacency[identity] for identity in reached}
        counts = {identity: len(successors[identity]) for identity in reached}
        reverse = defaultdict(list)
        for parent in reached:
            for child in successors[parent]:
                reverse[child].append(parent)
        queue = deque(sorted(identity for identity in reached if not counts[identity]))
        best, chosen = {}, {}
        while queue:
            identity = queue.popleft()
            node = nodes[identity]
            children = [child for child in successors[identity] if best.get(child) is not None]
            child = max(children, key=lambda child: (best[child], child)) if children else None
            chosen[identity] = child
            frame = node['static_frame_bytes']
            best[identity] = None if frame is None else frame + 8 + (best[child] if child else 0)
            for parent in reverse[identity]:
                counts[parent] -= 1
                if not counts[parent]:
                    queue.append(parent)
        require(len(best) == len(reached), 'Internal diagnostic DAG still contains a cycle.')
        known = [identity for identity in candidates if best.get(identity) is not None]
        start = max(known, key=lambda identity: (best[identity], identity)) if known else None
        path, current = [], start
        while current is not None:
            path.append(describe(current))
            current = chosen[current]
        source_counts = defaultdict(Counter)
        for value in barriers:
            if 'function' in value:
                source_counts[value['function']['source']][value['reason']] += 1
        ranked = [{'source': source, 'barrier_count': sum(counts.values()), 'reason_counts': dict(counts)}
                  for source, counts in source_counts.items()]
        ranked.sort(key=lambda value: (-value['barrier_count'], value['source']))
        complete = len(candidates) == 1 and not barriers and all(nodes[i]['static_frame_bytes'] is not None for i in reached)
        results[label] = {'symbol': symbol, 'definition_count': len(candidates),
            'reachable_function_count': len(reached), 'barrier_count': len(barriers),
            'barrier_reason_counts': dict(Counter(value['reason'] for value in barriers)),
            'compiled_subgraph_complete': complete,
            'compiled_subgraph_upper_bound_bytes': best[candidates[0]] if complete else None,
            'recursive_component_count': len(recursive), 'ranked_barrier_sources': ranked,
            'barriers': sorted(barriers, key=lambda value: (value.get('distance_from_root', -1), value['reason'],
                value.get('function', {}).get('id', ''), value.get('address', -1))),
            'largest_reachable_static_frames': [describe(identity) for identity in sorted(reached,
                key=lambda identity: (-(nodes[identity]['static_frame_bytes'] or 0), identity))[:25]],
            'diagnostic_acyclic_frame_sum': {'bytes': best[start] if start else None, 'path': path,
                'cycle_entry_treated_as_terminal': True, 'tail_branch_frames_conservatively_added': True,
                'runtime_peak_or_lower_bound': False, 'is_complete_bound': complete}}
    return {'function_count': len(nodes), 'object_count': len(graphs), 'roots': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rm-manifest', type=Path, required=True)
    parser.add_argument('--project-manifest', type=Path)
    parser.add_argument('--project-unit-count', type=int, default=42)
    parser.add_argument('--allow-missing-project-inputs', action='store_true',
                        help='Diagnostic archive replay only; missing inputs remain explicit barriers.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--path-map', action='append', default=[], metavar='OLD=NEW')
    parser.add_argument('--llvm-objdump', type=Path)
    parser.add_argument('--root', action='append', default=[], metavar='LABEL=SYMBOL')
    args = parser.parse_args()
    require(not args.allow_missing_project_inputs or args.project_manifest,
            'Missing-input diagnostic mode requires an explicit project manifest.')
    paths = binding.Paths([value.split('=', 1) for value in args.path_map])
    tool_hashes = {Path(module.__file__).name: stack.sha(Path(module.__file__))
                  for module in (stack, macho, binding)}
    tool_hashes[Path(__file__).name] = stack.sha(Path(__file__))
    manifest = args.rm_manifest.resolve(strict=True)
    paths.checked_file(str(manifest), stack.sha(manifest))
    units = binding.load_manifest(manifest, paths)
    project_path, missing_project = None, []
    if args.project_manifest:
        project_path = args.project_manifest.resolve(strict=True)
        project_units, missing_project = project_manifest(project_path, paths,
            expected_count=args.project_unit_count, allow_missing=args.allow_missing_project_inputs)
        units += project_units
    decoder = ([str(args.llvm_objdump), '--macho', '--disassemble', '--no-show-raw-insn', '--no-symbolic-operands']
               if args.llvm_objdump else ['/usr/bin/xcrun', 'otool', '-tv'])
    with ThreadPoolExecutor(max_workers=6) as pool:
        graphs = list(pool.map(lambda unit: fresh_graph(unit, decoder), units))
    roots = dict(value.split('=', 1) for value in args.root) if args.root else {**ROOTS, **PROJECT_ROOTS}
    require(all(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', label) and re.fullmatch(r'_[A-Za-z_0-9]+', symbol)
                for label, symbol in roots.items()), 'Root label/symbol must have exact identifier spelling.')
    inventory_barriers = ([{'reason': 'incomplete-project-input-inventory',
        'missing_unit_count': len(missing_project)}] if missing_project else [])
    result = selected_roots(graphs, roots, inventory_barriers=inventory_barriers)
    paths.unchanged()
    for name, expected in tool_hashes.items():
        require(stack.sha(Path(__file__).parent/name) == expected, 'Root closure tool changed during analysis.')
    result.update(format=1, status='selected-root-stack-barriers-measured',
        rm_manifest_sha256=stack.sha(manifest), verified_input_count=len(paths.checked),
        project_manifest_sha256=stack.sha(project_path) if project_path else None,
        missing_project_inputs=missing_project,
        graph_sha256=hashlib.sha256(json.dumps(graphs, sort_keys=True).encode()).hexdigest(),
        tool_sha256=tool_hashes, root_closure_tool_sha256=tool_hashes[Path(__file__).name],
        typed_candidate_binding_applied=False,
        typed_binding_reason='No receiver initialization/lifetime/alias-closure evidence supplied; no indirect target set installed.',
        project_wrapper_stack=('not supplied' if not project_path else
            'incomplete; retained archive lacks original inputs' if missing_project else 'included exact measured project inputs'),
        actual_target_stack_bytes=None, framework_entry_headroom_bytes=None,
        interrupt_nesting_budget_bytes=None, inline_assembly_stack_contract='not_established',
        aggregate_stack_proven=False, kernel_execution='not_tested', production_candidate_allowed=False,
        limitations=['Selected RM roots are analyzed independently; reachability through the public owner is not inferred.',
            'An isolated gpuEnterShutdown root does not establish that public shutdown invokes it.',
            'No unknown external/indirect/recursive/dynamic contribution receives a guessed zero.',
            'Static frame sums are diagnostic compiled paths, not demonstrated runtime peaks or lower bounds.',
            'Typed target identities alone do not prove receiver initialization, lifetime or alias closure.'])
    output = args.output.resolve()
    require(not output.exists(), 'Fresh evidence output required.')
    output.parent.mkdir(parents=True, exist_ok=True)
    stack.write(output, result)
    print(json.dumps({'path': str(output), 'sha256': stack.sha(output), 'function_count': result['function_count'],
        'roots': {label: {key: value[key] for key in ('reachable_function_count', 'barrier_count',
            'barrier_reason_counts', 'compiled_subgraph_upper_bound_bytes')} for label, value in result['roots'].items()},
        'aggregate_stack_proven': False}))


if __name__ == '__main__':
    main()
