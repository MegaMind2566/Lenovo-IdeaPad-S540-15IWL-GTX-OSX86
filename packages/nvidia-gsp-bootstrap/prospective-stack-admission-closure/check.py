#!/usr/bin/env python3
"""Replay complete measured inputs and retain concrete stack-blocker witnesses.

This companion never grants original entry. Its graph frames describe the
recorded compiler profile; thread/IRQ headroom is a distinct missing contract.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOTS = {
    'dispatcher_thread_entry': '__ZN22S540NvidiaGspBootstrap10Dispatcher4Impl5entryEPvi',
    'dispatcher_action_prerequisite': '__ZN22S540NvidiaGspBootstrap5Owner4Impl6actionEPvj',
    'public_global_initialize': '_s540GlobalRmInitialize',
    'global_initialize_prerequisite': '_s540Global_coreInitializeRm',
    'global_shutdown_prerequisite': '_s540Global_coreShutdownRm',
    'public_context_prepare': '_s540GspContextPrepare',
    'public_context_initialize': '_s540GspContextInitializeAdapter',
    'adapter_initialize_prerequisite': '_s540Global_rm_init_adapter',
    'gsp_state_initialize_prerequisite': '_s540Global_kgspStateInitLocked_IMPL',
    'work_item_prerequisite': '_s540Global_rm_execute_work_item',
    'recovery_timer_prerequisite': '_s540Global_rm_run_rc_callback',
    'nano_timer_prerequisite': '_s540Global_rm_run_nano_timer_callback',
    'public_interrupt_top': '_s540GspContextInterruptTop',
    'interrupt_top_prerequisite': '_s540Global_rm_isr',
    'mmu_fault_prerequisite': '_s540Global_rm_gpu_handle_mmu_faults',
    'public_locked_bottom_half': '_s540GspContextLockedBottomHalf',
    'locked_bottom_half_prerequisite': '_s540Global_rm_isr_bh',
    'public_unlocked_bottom_half': '_s540GspContextUnlockedBottomHalf',
    'unlocked_bottom_half_prerequisite': '_s540Global_rm_isr_bh_unlocked',
    'public_context_disable': '_s540GspContextDisableAdapter',
    'public_context_shutdown': '_s540GspContextShutdownAdapter',
}
LOCAL_ROOT_LABELS = {'dispatcher_thread_entry', 'dispatcher_action_prerequisite'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def linked_edges(graphs):
    """Preserve only unique machine definitions, just as the frozen collector.

    Unknown/ambiguous edges never become leaves with zero cost. This mapping
    is used only for an explicit cycle witness; selected_roots owns admission
    semantics and retains every unresolved edge as a barrier.
    """
    nodes = {}
    definitions = defaultdict(list)
    for graph in graphs:
        for node in graph['nodes']:
            require(node['id'] not in nodes, 'Duplicate actual machine node.')
            nodes[node['id']] = node
            for symbol in node['external_symbols']:
                definitions[symbol].append(node['id'])
    edges = defaultdict(list)
    for identity, node in nodes.items():
        for site in node['calls']:
            target = site['target']
            candidates = ([target['node']] if 'node' in target else
                          definitions.get(target.get('symbol'), []))
            if len(candidates) == 1 and candidates[0] in nodes:
                edges[identity].append((candidates[0], site))
    return nodes, edges


def select_local_roots(graphs, roots):
    """Select actual unique internal entry functions without inventing edges.

    The frozen selector indexes public symbols only. Two reviewed callbacks are
    internalized by Apple Clang. Add their existing names to the root index only
    after proving no symbolic machine edge uses those names. Local direct edges
    already identify their actual object/node, and are unchanged.
    """
    selected = deepcopy(graphs)
    receipts = []
    for label in sorted(LOCAL_ROOT_LABELS & roots.keys()):
        symbol = roots[label]
        found = [(graph, node) for graph in selected for node in graph['nodes']
                 if symbol in node['symbols']]
        require(len(found) == 1, 'A reviewed local root must have one exact machine definition: ' + symbol)
        graph, node = found[0]
        if symbol in node['external_symbols']:
            continue
        require(not any(site['target'].get('symbol') == symbol
                        for value in selected for owner in value['nodes'] for site in owner['calls']),
                'Local root indexing would alter symbolic machine edge resolution.')
        node['external_symbols'].append(symbol)
        receipts.append({'label': label, 'symbol': symbol, 'node': node['id'],
            'object_sha256': graph['object_sha256'], 'source_sha256': graph['source_sha256'],
            'actual_linkage': 'internal', 'new_machine_edges': 0,
            'scope': 'root selection only; no external ABI definition asserted'})
    return selected, receipts


def rsp_lea_displacement(code):
    """Recognize only exact x86-64 LEA RSP,[RSP+constant] encodings."""
    if code[:4] == bytes.fromhex('488d6424') and len(code) >= 5:
        return int.from_bytes(code[4:5], 'little', signed=True), 5
    if code[:4] == bytes.fromhex('488da424') and len(code) >= 8:
        return int.from_bytes(code[4:8], 'little', signed=True), 8
    return None


def refine_constant_rsp_lea(graphs, units):
    """Constant base-only LEA has the same stack depth as accepted ADD/SUB.

    Require actual bytes, matching decoder text, and a static compiler frame.
    Indexing, alignment, data-dependent bases and missing/dynamic frame records
    remain barriers. No call, external function or recursive edge is removed.
    """
    images = {unit['unit']['object_sha256']: unit['image'] for unit in units}
    refined = deepcopy(graphs)
    receipts = []
    for graph in refined:
        image = images[graph['object_sha256']]
        text = [section for section in image.sections if section.name == '__text']
        if len(text) != 1:
            continue
        section = text[0]
        for node in graph['nodes']:
            retained = []
            for site in node['unknown_sites']:
                if site['reason'] != 'unreviewed-stack-pointer-write' or node['static_frame_bytes'] is None:
                    retained.append(site)
                    continue
                match = re.fullmatch(r'leaq\s+(-?(?:0x[0-9a-f]+|\d+))\(%rsp\), %rsp',
                                     site.get('instruction', ''))
                offset = site['address'] - section.address
                decoded = rsp_lea_displacement(image.data[section.offset + offset:section.offset + offset + 8])
                if not match or decoded is None or int(match[1], 0) != decoded[0] or not (
                        node['start'] <= site['address'] and site['address'] + decoded[1] <= node['end']):
                    retained.append(site)
                    continue
                displacement, width = decoded
                receipts.append({'node': node['id'], 'symbols': node['symbols'],
                    'object_sha256': graph['object_sha256'], 'machine_address': site['address'],
                    'instruction': site['instruction'],
                    'instruction_bytes': image.data[section.offset + offset:section.offset + offset + width].hex(),
                    'rsp_constant_delta_bytes': displacement,
                    'static_compiler_frame_bytes': node['static_frame_bytes'],
                    'resolved_reason': site['reason'],
                    'proof': 'Exact LEA RSP,[RSP+constant] equals constant ADD/SUB for stack depth; no register index or alignment.'})
            node['unknown_sites'] = retained
    return refined, receipts


def cycle_witness(members, nodes, edges):
    """Return an actual closed edge walk, not merely SCC member names."""
    allowed = set(members)
    require(allowed, 'Empty recursive component.')
    start = min(allowed)
    for child, first_site in edges[start]:
        if child not in allowed:
            continue
        if child == start:
            route = [(start, start, first_site)]
        else:
            parents = {child: None}
            queue = deque([child])
            while queue and start not in parents:
                current = queue.popleft()
                for target, site in edges[current]:
                    if target in allowed and target not in parents:
                        parents[target] = (current, site)
                        queue.append(target)
            if start not in parents:
                continue
            route = []
            current = start
            while parents[current] is not None:
                parent, site = parents[current]
                route.append((parent, current, site))
                current = parent
            route.reverse()
            route.insert(0, (start, child, first_site))
        return [{'caller': nodes[parent]['symbols'], 'callee': nodes[target]['symbols'],
                 'machine_address': site['address'], 'transfer_kind': site['kind']}
                for parent, target, site in route]
    raise ValueError('Reported recursive component lacks an actual closed edge witness.')


def compact_result(result, graphs):
    nodes, edges = linked_edges(graphs)
    roots = {}
    component_catalog = {}
    for label, root in result['roots'].items():
        groups = defaultdict(list)
        recursive = []
        for barrier in root['barriers']:
            groups[barrier['reason']].append(barrier)
            if barrier['reason'] == 'recursion-cycle':
                identities = sorted(value['id'] for value in barrier['component_members'])
                component_id = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
                component_catalog.setdefault(component_id, {
                    'member_count': len(identities),
                    'members': [{key: value[key] for key in ('id', 'symbols', 'static_frame_bytes')}
                                for value in barrier['component_members']],
                    'closed_machine_walk': cycle_witness(identities, nodes, edges)})
                recursive.append({
                    'component_id': component_id,
                    'entry_path': barrier['shortest_compiled_path'],
                    'member_count': len(identities),
                    'maximum_nested_activations': None,
                    'depth_bound_established': False})
        witnesses = {}
        for reason, values in sorted(groups.items()):
            witness = min(values, key=lambda value: (
                value.get('distance_from_root', -1),
                value.get('function', {}).get('id', ''), value.get('address', -1)))
            if reason == 'recursion-cycle':
                witness = {key: value for key, value in witness.items() if key != 'component_members'}
            witnesses[reason] = {'occurrences': len(values), 'witness': witness}
        roots[label] = {key: root[key] for key in (
            'symbol', 'definition_count', 'reachable_function_count', 'barrier_count',
            'barrier_reason_counts', 'compiled_subgraph_complete',
            'compiled_subgraph_upper_bound_bytes', 'recursive_component_count')}
        roots[label].update(blocker_witnesses=witnesses, recursive_components=recursive,
            diagnostic_acyclic_frame_sum=root['diagnostic_acyclic_frame_sum'],
            aggregate_upper_bound_bytes=None,
            target_stack_capacity_bytes=None,
            framework_entry_headroom_bytes=None,
            external_callback_reentry_bound_bytes=None,
            interrupt_nesting_headroom_bytes=None,
            original_entry_admission=False)
        require(root['barrier_count'] == sum(len(v) for v in groups.values()),
                'A stack blocker was lost while summarizing.')
        require(not root['barrier_count'] or root['compiled_subgraph_upper_bound_bytes'] is None,
                'Unknown contribution was assigned a finite compiled bound.')
    return {'format': 1, 'status': 'complete-input-machine-stack-replay',
        'decoded_object_count': result['object_count'], 'decoded_function_count': result['function_count'],
        'roots': roots, 'recursive_component_catalog': component_catalog,
        'aggregate_stack_proven': False, 'original_entry_admission': False,
        'hardware_execution': False, 'production_candidate_allowed': False,
        'interpretation': [
            'Roots are independently measured prerequisites; no path through a refusing public owner is invented.',
            'Sequential global and adapter stages require a maximum, not an arithmetic sum of stage peaks.',
            'Synchronous callback reentry and recursion need proven nested-activation bounds.',
            'A finite compiled subgraph alone does not establish target thread or IRQ stack headroom.',
            'Source defaults and allocated nvidia_stack_t buffers are not target stack-capacity measurements.',
            'No nonzero unknown contribution is substituted with zero.']}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def run(args):
    repository = args.repository.resolve(strict=True)
    sys.path.insert(0, str(repository / 'builders'))
    import nvidia_stack_root_closure as closure
    import nvidia_nvoc_definitions as binding
    import nvidia_stack_usage as stack
    import nvidia_metaclass_initializers as macho
    require(not args.output.exists(), 'Fresh stack evidence output directory required.')
    paths = binding.Paths([value.split('=', 1) for value in args.path_map])
    original_manifest = args.rm_manifest.resolve(strict=True)
    project_manifest = args.project_manifest.resolve(strict=True)
    # The combined-image builder stores this manifest one directory above its
    # original-objects. The old binder's layout-only same-parent rule predates
    # that packaging. Use the equally strict source/command/object/sidecar
    # verifier, then independently require the complete directory inventory.
    original_units, original_missing = closure.project_manifest(original_manifest, paths,
        expected_count=args.expected_original_units, allow_missing=False)
    require(not original_missing, 'Every original measured input is required.')
    object_parents = {unit['object'].parent for unit in original_units}
    require(len(object_parents) == 1, 'Original measured object directory is ambiguous.')
    require({path.resolve() for path in next(iter(object_parents)).glob('*.o')} ==
            {unit['object'].resolve() for unit in original_units},
            'Missing or extra original measured object files.')
    project_units, missing = closure.project_manifest(project_manifest, paths,
        expected_count=args.expected_project_units, allow_missing=False)
    require(len(original_units) == args.expected_original_units,
            'The complete original compilation inventory is required.')
    require(not missing, 'Every measured project source/object/sidecar is required.')
    units = original_units + project_units
    require(len({str(unit['object']) for unit in units}) == len(units),
            'The original/project measured inventories overlap.')
    decoder = [str(args.llvm_objdump.resolve(strict=True)), '--macho', '--disassemble',
               '--no-show-raw-insn', '--no-symbolic-operands']
    tools = {Path(module.__file__).name: sha(module.__file__)
             for module in (closure, binding, stack, macho)}
    roots = ROOTS if args.roots_json is None else json.loads(args.roots_json.read_text())
    require(isinstance(roots, dict) and roots and all(isinstance(k, str) and isinstance(v, str)
            for k, v in roots.items()), 'Exact named roots required.')
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        graphs = list(pool.map(lambda unit: closure.fresh_graph(unit, decoder), units))
    graphs, rsp_receipts = refine_constant_rsp_lea(graphs, units)
    selected, local_receipts = select_local_roots(graphs, roots)
    result = closure.selected_roots(selected, roots)
    compact = compact_result(result, graphs)
    paths.unchanged()
    require(all(sha(repository / 'builders' / name) == expected for name, expected in tools.items()),
            'A stack-analysis implementation changed during machine replay.')
    args.output.mkdir(parents=True)
    full = args.output / 'selected-roots.json.gz'
    raw = json.dumps(result, sort_keys=True).encode()
    with full.open('wb') as output:
        with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as archive:
            archive.write(raw)
    compact.update(rm_manifest_sha256=sha(original_manifest),
        project_manifest_sha256=sha(project_manifest), tool_sha256=tools,
        llvm_objdump_sha256=sha(args.llvm_objdump), verified_input_count=len(paths.checked),
        companion_sha256=sha(__file__),
        missing_project_input_count=0, typed_candidate_binding_applied=False,
        constant_rsp_lea_proofs=rsp_receipts, local_root_selections=local_receipts,
        source_profile='exact recorded native compiler commands, source bytes and stack sidecars',
        full_selected_root_evidence={'file': full.name, 'sha256': sha(full),
                                     'uncompressed_sha256': hashlib.sha256(raw).hexdigest()})
    write(args.output / 'stack-admission.json', compact)
    return compact


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'rm-manifest', 'project-manifest', 'llvm-objdump', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-original-units', type=int, default=1100)
    parser.add_argument('--expected-project-units', type=int, default=60)
    parser.add_argument('--path-map', action='append', default=[], metavar='OLD=NEW')
    parser.add_argument('--roots-json', type=Path)
    parser.add_argument('--jobs', type=int, default=6)
    outcome = run(parser.parse_args())
    print(json.dumps({'status': outcome['status'], 'objects': outcome['decoded_object_count'],
        'roots': {key: {'barriers': value['barrier_count'],
                       'reasons': value['barrier_reason_counts']}
                  for key, value in outcome['roots'].items()},
        'aggregate_stack_proven': False, 'original_entry_admission': False}))
