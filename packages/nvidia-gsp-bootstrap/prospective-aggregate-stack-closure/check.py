#!/usr/bin/env python3
"""Fresh measured call graphs for one exact experimental native source plan.

Unknown machine, callback, external and recursive contributions remain visible.
The resulting diagnostic frame sums are inputs to an explicitly experimental
allowance policy; this module never issues a formal kernel-stack certificate.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shlex
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'builders'))
import compose_nvidia_first_transaction as composer
import link_nvidia_first_transaction as linker
import nvidia_metaclass_initializers as macho
import nvidia_stack_root_closure as closure
import nvidia_stack_usage as stack

ROOT_SYMBOLS = {
    'global_initialize': '_s540Global_coreInitializeRm',
    'adapter_initialize': '_s540Global_rm_init_adapter',
    'context_initialize_wrapper': '_s540GspContextInitializeAdapter',
    'interrupt_top': '_s540Global_rm_isr',
    'interrupt_context_top': '_s540GspContextInterruptTop',
    'interrupt_mmu_fault': '_s540Global_rm_gpu_handle_mmu_faults',
    'interrupt_locked_bottom': '_s540Global_rm_isr_bh',
    'interrupt_unlocked_bottom': '_s540Global_rm_isr_bh_unlocked',
    'context_locked_bottom': '_s540GspContextLockedBottomHalf',
    'context_unlocked_bottom': '_s540GspContextUnlockedBottomHalf',
    'recovery_timer': '_s540Global_rm_run_rc_callback',
    'nano_timer': '_s540Global_rm_run_nano_timer_callback',
    'work_item_execute': '_s540Global_rm_execute_work_item',
    'gpu_enter_shutdown': '_s540Global_gpuEnterShutdown_IMPL',
    'adapter_disable': '_s540Global_rm_disable_adapter',
    'adapter_shutdown': '_s540Global_rm_shutdown_adapter',
}
CALLBACK_ROOTS = (
    ('packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp',
     'worker_owner_dispatch', '5Owner4Impl6actionE'),
    ('packages/nvidia-gsp-bootstrap/src/S540NvidiaGspDispatcher.cpp',
     'worker_dispatch_prefix', '10Dispatcher4Impl5entryE'),
    ('packages/nvidia-darwin-services/src/S540NvidiaDarwinTimer.cpp',
     'callout_timer_prefix', '13timerCallbackE'),
    ('packages/nvidia-darwin-services/src/S540NvidiaDarwinWork.cpp',
     'callout_work_prefix', '12workCallbackE'),
    ('packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp',
     'interrupt_backend_prefix', '9interruptE'),
    ('packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp',
     'deferred_bottom_prefix', '10bottomHalfE'),
    ('packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp',
     'interrupt_bound_top', '7Binding3topE'),
)
NATIVE_STATUSES = (
    'compiled-current-full-original-native-source-only',
    'compiled-current-project-native-source-only',
)
GENERATED_SOURCE = 'generated/g_nvid_string.c'
GENERATED_BYTES = (b'const char NVRM_ID[] = "nvidia id: NVIDIA UNIX Open Kernel Module for x86_64 '
    b'615.78.08 Release Build (build@ci)";\nconst char *const pNVRM_ID = NVRM_ID + 11;\n')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def verify_source_plan(value, callback):
    actual = callback()
    if isinstance(actual, tuple):
        actual = actual[-1]
    require(actual == value, 'The measured source plan differs from its independent exact replay')


class Bindings:
    def __init__(self):
        self.files = {}

    def file(self, path, digest=None):
        path = Path(path).resolve(strict=True)
        require(path.is_file(), 'A bound input must be a regular file: ' + str(path))
        digest = digest or sha(path)
        require(sha(path) == digest, 'Measured input changed: ' + str(path))
        require(self.files.setdefault(str(path), digest) == digest,
                'Conflicting input identity: ' + str(path))
        return path

    def unchanged(self):
        for path, digest in self.files.items():
            require(sha(path) == digest, 'Measured input changed during graph construction: ' + path)


def command_operand(command, option, cwd):
    require(command.count(option) == 1, 'One actual compile operand required: ' + option)
    index = command.index(option) + 1
    require(index < len(command), 'Missing compile operand: ' + option)
    path = Path(command[index])
    return (path if path.is_absolute() else cwd / path).resolve(strict=True)


def read_dependencies(dep, cwd):
    text = dep.read_text().replace('\\\n', ' ')
    require(':' in text, 'Compiler dependency output is malformed')
    return {(Path(name) if Path(name).is_absolute() else cwd / name).resolve(strict=True)
            for name in shlex.split(text.split(':', 1)[1])}


def checked_rows(args, value, report_path, project, bound):
    report_path = bound.file(report_path)
    report = json.loads(report_path.read_text())
    require(report.get('status') == NATIVE_STATUSES[1 if project else 0] and
            report.get('native_darwin_compilation') is True and report.get('host_control') is False,
            'Only complete current native Apple reports may establish the native profile')
    composition = Path(args.composition).resolve(strict=True)
    require(report.get('composition_sha256') == sha(composition / 'composition.json'),
            'Native measured report belongs to another composition')
    rows = report.get('results', [])
    require(isinstance(rows, list), 'Missing measured unit matrix')
    expected = {row['source']: row for row in value['project_translation_units']} if project else None
    if project:
        require(len(rows) == len(expected) and {r['source'] for r in rows} == set(expected),
                'The actual complete current project translation-unit inventory is required')
    else:
        require(len(rows) == 1100 and len({r['source'] for r in rows}) == 1100,
                'All 1100 current original make units are required')
        source_root = composition / 'source/src/nvidia'
        declared = composer.original.original_commands(Path(args.upstream).resolve(strict=True),
            Path(args.native_compilation).resolve(strict=True) / 'original-objects', Path(rows[0]['command'][0]))
        actual_declared = set()
        for command in declared:
            name = Path(command[command.index('-c') + 1])
            if name.is_absolute():
                require(name == Path(args.native_compilation).resolve(strict=True) /
                    'original-objects/g_nvid_string.c',
                    'An unreviewed generated original source entered the make profile')
                actual_declared.add(GENERATED_SOURCE)
            else:
                actual_declared.add((source_root / name).resolve(strict=True).relative_to(
                    composition / 'source').as_posix())
        require(actual_declared == {r['source'] for r in rows},
                'Native original unit matrix differs from the pinned actual make profile')
    objects_dir = Path(args.native_compilation).resolve(strict=True) / (
        'project-objects' if project else 'original-objects')
    units, seen = [], set()
    for row in rows:
        source_name = composer.checked_relative(row['source'])
        generated = not project and source_name.as_posix() == GENERATED_SOURCE
        source = bound.file((objects_dir / 'g_nvid_string.c') if generated else
            composition / ('project' if project else 'source') / source_name,
            row.get('source_sha256', row.get('sha256')))
        inventory = value['project_files' if project else 'original_files']
        if generated:
            require(source.read_bytes() == GENERATED_BYTES,
                    'The one deterministic make-generated original string source changed')
        else:
            require(source_name.as_posix() in inventory and
                    sha(source) == inventory[source_name.as_posix()]['sha256'],
                    'Measured translation unit differs from the source plan')
        if project:
            require(row.get('kind') == expected[row['source']]['kind'],
                    'Measured project language kind changed')
        obj_name = composer.checked_relative(row['object'])
        require(len(obj_name.parts) == 1, 'An object name must be one exact basename')
        obj = bound.file(objects_dir / obj_name, row['object_sha256'])
        require(obj not in seen, 'Repeated measured object')
        seen.add(obj)
        command = row['command']
        require(isinstance(command, list) and all(isinstance(v, str) for v in command) and
                command.count('-fstack-usage') == 1 and '-fno-stack-usage' not in command,
                'The actual measured compiler command is required')
        cwd = Path(row['cwd']).resolve(strict=True)
        require(cwd.is_dir(), 'Measured compiler working directory is absent')
        require(command_operand(command, '-c', cwd) == source and
                command_operand(command, '-o', cwd) == obj,
                'Measured compiler operands do not identify the actual source/object')
        bound.file(Path(command[0]).resolve(strict=True))
        dep = bound.file(command_operand(command, '-MF', cwd))
        require(dep == obj.with_suffix('.d'), 'Actual object dependency sidecar is required')
        dependency_paths = read_dependencies(dep, cwd)
        require(source in dependency_paths and
                {str(p) for p in dependency_paths} == set(row['dependency_sha256']),
                'The full actual compiler dependency inventory differs from the native report')
        for path, digest in row['dependency_sha256'].items():
            bound.file(path, digest)
        capture = row['stack_usage']
        capture_path = bound.file(capture['path'], capture['sha256'])
        unit = stack.load_capture(capture)
        require(capture_path == obj.with_suffix('.stack.json') and
                Path(unit['source']) == source and Path(unit['object']) == obj and
                unit['command'] == command and unit['cwd'] == str(cwd) and
                unit.get('native_apple_compiler') is True,
                'Actual source/object/command/native stack-capture bindings differ')
        if unit['usage_file']:
            bound.file(unit['usage_file'], unit['usage_sha256'])
        units.append({'capture': capture_path, 'unit': unit, 'object': obj,
            'image': macho.Object(obj, allow_empty_code_without_symbols=True)})
    require({p.resolve() for p in objects_dir.glob('*.o')} == seen,
            'Missing or extra object in the complete measured object directory')
    return units


def select_final_graphs(graphs, final_path, bound):
    """Select retained named atoms conservatively; local-name collisions stay.

    The complete native graph is decoded first. A source atom is removed only
    when none of its aliases appears in the actual final text nlist. Ambiguous
    local aliases retain every candidate; they never erase a possible edge.
    Final functions not represented by a source capture remain explicit unknown
    auxiliary/framework contributions, rather than being assigned a zero frame.
    """
    final_path = bound.file(final_path)
    image = linker.Image(final_path, 11)
    names = {s['name'] for s in image.symbols if s['section'] and
        s['kind'] & 0x0e == 0x0e and image.sections[s['section'] - 1]['name'] == '__text'}
    require(names, 'Final native kernel image has no named executable atoms')
    selected, mapped = [], set()
    for graph in graphs:
        kept = [deepcopy(n) for n in graph['nodes'] if set(n['symbols']) & names]
        if kept:
            mapped.update(s for n in kept for s in n['symbols'] if s in names)
            selected.append(dict(graph, nodes=kept))
    return selected, {'path': str(final_path), 'sha256': sha(final_path),
        'actual_named_final_text_symbols': len(names), 'mapped_final_text_symbols': len(mapped),
        'unmeasured_auxiliary_final_text_symbols': sorted(names - mapped),
        'local_name_collisions_retained_conservatively': True,
        'final_symbol_filter_is_formal_reachability_proof': False}


def selected_actual_roots(graphs, roots, local_roots):
    """Resolve selected actual local entries without claiming external linkage."""
    candidates = {name for g in graphs for n in g['nodes'] for name in n['symbols']}
    analysis_graphs = deepcopy(graphs)
    query_roots = dict(roots)
    for label, (identity, name) in local_roots.items():
        key = '__s540_diagnostic_local_root_' + hashlib.sha256(identity.encode()).hexdigest()
        require(key not in candidates, 'Diagnostic local-root lookup key collides with actual code')
        matches = [n for g in analysis_graphs for n in g['nodes'] if n['id'] == identity]
        require(len(matches) == 1 and name in matches[0]['symbols'] and
            name not in matches[0]['external_symbols'],
            'Actual object-scoped local callback owner is absent/ambiguous or is not local')
        matches[0]['external_symbols'].append(key)
        query_roots[label] = key
    result = closure.selected_roots(analysis_graphs, query_roots)
    for label, (identity, name) in local_roots.items():
        result['roots'][label].update(symbol=name, root_lookup='source-scoped-local-node-id',
            source_scoped_local_node_id=identity, actual_machine_linkage_changed=False)
    return result


def measure_verified_plan(args, value, verify_callback, original_report_path,
                          project_report_path, *, profile_contract=None,
                          context_review_callback=None):
    """Verify, decode and recheck every current measured source/object binding."""
    verify_source_plan(value, verify_callback)
    native = composer.load('s540_current_graph_native_authenticator',
        HERE.parent / 'prospective-native-target-preparation/compile_native.py')
    native.verify_native_reports(args, value, verify_callback)
    output = Path(getattr(args, 'stack_output', Path(args.output) / 'stack-measurement')).resolve()
    require(not output.exists(), 'Fresh graph measurement output is required')
    output.mkdir(parents=True)
    bound = Bindings()
    for p in (Path(__file__), ROOT / 'builders/nvidia_stack_root_closure.py',
              ROOT / 'builders/nvidia_stack_usage.py', ROOT / 'builders/nvidia_metaclass_initializers.py',
              ROOT / 'builders/nvidia_nvoc_definitions.py', Path(native.__file__)):
        bound.file(p)
    bound.file(Path(args.composition) / 'composition.json')
    decoder = bound.file(Path(args.llvm_objdump))
    original = checked_rows(args, value, original_report_path, False, bound)
    project = checked_rows(args, value, project_report_path, True, bound)
    units = original + project
    require(len({u['object'] for u in units}) == len(units), 'Original/project object inventories overlap')
    argv = [str(decoder), '--macho', '--disassemble', '--no-show-raw-insn', '--no-symbolic-operands']
    with ThreadPoolExecutor(max_workers=4) as pool:
        graphs = list(pool.map(lambda u: closure.fresh_graph(u, argv), units))
    context = context_review_callback(args, value, graphs) if context_review_callback else {
        'status': 'no-context-pruning-applied', 'refinements': [],
        'unknown_callback_receivers_remain_barriers': True}
    require(not context.get('refinements'),
            'This current checker admits no unreviewed graph-rewriting context refinement')
    final = None
    if getattr(args, 'final_image', None):
        graphs, final = select_final_graphs(graphs, Path(args.final_image), bound)
    roots = dict(ROOT_SYMBOLS)
    # These are separately measured actual caller roots, not evidence that an
    # old closed Owner::initialize has become reachable.
    candidates = {name for g in graphs for n in g['nodes'] for name in n['symbols']}
    for label, part in (('experimental_owner', 'experimentalInitialize'),
                        ('privileged_target_request', 'externalMethod'),
                        ('owner_worker_dispatch', 'runWorker')):
        matches = sorted(n for n in candidates if part in n and 'S540' in n)
        for index, name in enumerate(matches):
            roots[label + '_' + str(index)] = name
    composition = Path(args.composition).resolve(strict=True)
    local_roots = {}
    for relative, label, fragment in CALLBACK_ROOTS:
        matches = {node['id']: (node, min(name for name in node['symbols'] if fragment in name))
            for g in graphs if g['source'] == str(composition / 'project' / relative)
            for node in g['nodes'] if any(fragment in name for name in node['symbols'])}
        require(matches, 'The actual registered callback entry is absent: ' + relative + ': ' + label)
        for index, (identity, (node, name)) in enumerate(sorted(matches.items())):
            key = label + '_' + str(index)
            if name in node['external_symbols']:
                roots[key] = name
            else:
                local_roots[key] = (identity, name)
    require(any(k.startswith('experimental_owner_') for k in roots),
            'Actual experimental Owner entry is absent from measured code')
    require(any(k.startswith('privileged_target_request_') for k in roots),
            'Actual privileged user-client entry is absent from measured code')
    # The unchanged resolver accepts external-symbol root names. Its direct
    # local edges already use exact object-scoped node IDs. Expose each chosen
    # actual local callback to the ROOT LOOKUP ONLY under a collision-free
    # diagnostic key in a private analysis copy. Do not alter persisted graphs,
    # linkage facts, machine symbols, edges or barriers.
    result = selected_actual_roots(graphs, roots, local_roots)
    require(all(row['definition_count'] == 1 for row in result['roots'].values()),
            'A selected actual execution root is missing or ambiguous')
    graph_path = output / 'current-object-graphs.json'
    write(graph_path, graphs)
    bound.file(graph_path)
    bound.unchanged()
    verify_source_plan(value, verify_callback)
    result.update(format=1, status='complete-current-native-stack-graph-measured',
        original_translation_units=len(original), project_translation_units=len(project),
        dynamic_function_count=sum(not f['static_frame_known'] for u in units for f in u['unit']['functions']),
        complete_native_object_inventory=True, current_native_object_count=len(units),
        graph_path=str(graph_path), graph_sha256=sha(graph_path),
        composition_sha256=sha(Path(args.composition) / 'composition.json'),
        input_sha256=bound.files, decoder_command=argv, profile_contract=profile_contract,
        context_review=context, final_image_selection=final,
        actual_target_stack_bytes=None, irq_stack_capacity_observed=False,
        kernel_stack_bound_proven=False, aggregate_stack_proven=False,
        production_candidate_allowed=False, kernel_execution='not_tested')
    write(output / 'results.json', result)
    return result
