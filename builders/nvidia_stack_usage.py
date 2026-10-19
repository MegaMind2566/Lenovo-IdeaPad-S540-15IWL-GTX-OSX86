#!/usr/bin/env python3
"""Compiler stack measurements and conservative x86-64 Mach-O call graphs.

Reports are diagnostic inputs to admission review. Unknown indirect calls,
recursion, external code, dynamic frames and framework/interrupt headroom never
receive a guessed bound. A successful build does not enable original entry.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from bisect import bisect_left
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess

import nvidia_metaclass_initializers as macho

FORMAT = 1
ROOT = Path(__file__).resolve().parents[1]
SOURCE_DEFAULT_STACK_BYTES = 16384
RETURN_ADDRESS_BYTES = 8
ROOTS = {
    'global_initialize': '_s540Global_coreInitializeRm',
    'global_shutdown': '_s540Global_coreShutdownRm',
    'adapter_initialize': '_s540Global_rm_init_adapter',
    'adapter_disable': '_s540Global_rm_disable_adapter',
    'adapter_shutdown': '_s540Global_rm_shutdown_adapter',
    'recovery_timer': '_s540Global_rm_run_rc_callback',
    'nano_timer': '_s540Global_rm_run_nano_timer_callback',
    'interrupt_top': '_s540Global_rm_isr',
    'interrupt_locked_bottom': '_s540Global_rm_isr_bh',
    'interrupt_unlocked_bottom': '_s540Global_rm_isr_bh_unlocked',
    'context_initialize_wrapper': '_s540GspContextInitializeAdapter',
    'context_disable_wrapper': '_s540GspContextDisableAdapter',
    'context_shutdown_wrapper': '_s540GspContextShutdownAdapter',
    'context_interrupt_wrapper': '_s540GspContextInterruptTop',
}
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def parse_usage(text: str) -> list[dict]:
    records = []
    names = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.rsplit('\t', 2)
        if len(fields) != 3:
            raise ValueError('Malformed compiler stack-usage record at line ' + str(line_number))
        location, size, kind = fields
        match = re.fullmatch(r'(.+?):(\d+):(?:(\d+):)?(.+)', location)
        if not match or not re.fullmatch(r'\d+', size) or kind not in (
                'static', 'dynamic', 'dynamic,bounded'):
            raise ValueError('Unsupported compiler stack-usage record: ' + line)
        function = match[4]
        if function in names:
            raise ValueError('Repeated stack-usage function identity: ' + function)
        names.add(function)
        records.append({'compiler_function': function, 'symbol': '_' + function,
                        'source_location': location, 'reported_bytes': int(size),
                        'kind': kind, 'static_frame_known': kind == 'static'})
    return records

def verify_codegen(compiler: list[str], flags: list[str], output: Path, *,
                   cwd: Path | None = None, cpp: bool = False,
                   native_apple: bool = False) -> dict:
    """Prove actual compiler capability and byte-identical control objects."""
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / ('packages/nvidia-global-rm/tests/fixtures/stack_usage_probe.' +
                     ('cpp' if cpp else 'c'))
    baseline = output / 'without-usage.o'
    measured = output / 'with-usage.o'
    flags = [flag for flag in flags if flag != '-fstack-usage']
    for obj, extra in [(baseline, []), (measured, ['-fstack-usage'])]:
        run = subprocess.run([*compiler, *flags, *extra, '-c', str(source), '-o', str(obj)],
                             cwd=cwd, text=True, capture_output=True, timeout=180)
        obj.with_suffix('.log').write_text(run.stdout + run.stderr)
        if run.returncode:
            raise ValueError('Actual compiler stack-usage capability control failed: ' + run.stderr[-4000:])
    if baseline.read_bytes() != measured.read_bytes():
        raise ValueError('-fstack-usage changed the actual compiler control object bytes.')
    capture = capture_usage(source, measured,
        [*compiler, *flags, '-fstack-usage', '-c', str(source), '-o', str(measured)],
        cwd=cwd, native_apple=native_apple)
    if capture['function_count'] < 2:
        raise ValueError('Stack-usage capability control lost its caller and callee.')
    record = {'format': FORMAT, 'status': 'actual-compiler-stack-usage-control-passed',
              'native_apple_compiler': native_apple, 'source_sha256': sha(source),
              'identical_object_bytes': True, 'object_sha256': sha(measured),
              'stack_capture': capture, 'kernel_execution': 'not_tested',
              'production_candidate_allowed': False}
    path = output / 'stack-usage-capability.json'
    write(path, record)
    return {'path': str(path), 'sha256': sha(path), 'identical_object_bytes': True,
            'native_apple_compiler': native_apple}

def capture_usage(source: Path, obj: Path, command: list[str], *,
                  cwd: Path | None = None, native_apple: bool = False) -> dict:
    """Bind an actual .su to the source, complete command and emitted object."""
    if '-fstack-usage' not in command:
        raise ValueError('Stack capture requires the actual -fstack-usage compilation.')
    source, obj = source.resolve(strict=True), obj.resolve(strict=True)
    usage = obj.with_suffix('.su')
    # Parse the real object, independently of compiler-reported symbol names.
    image = macho.Object(obj, allow_empty_code_without_symbols=True)
    executable = any(section.size and
        (section.name == '__text' or section.flags & 0x80000400)
        for section in image.sections)
    if usage.is_file():
        functions = parse_usage(usage.read_text())
        usage_emission = 'compiler-file'
    elif not executable:
        # Clang does not open a .su output for a completely compiled-out
        # translation unit. Bind that absence to the actual empty machine
        # object instead of manufacturing a compiler output or losing a TU.
        functions = []
        usage_emission = 'not-emitted-for-object-without-executable-code'
    else:
        raise ValueError('The actual compiler did not emit stack usage: ' + str(usage))
    definitions = {symbol.name for symbol in image.symbols if symbol.section and
                   image.sections[symbol.section - 1].name == '__text' and
                   symbol.kind & 0xe0 == 0 and symbol.kind & 0x0e == 0x0e}
    absent = [record['symbol'] for record in functions if record['symbol'] not in definitions]
    if absent:
        raise ValueError('Compiler stack records lack actual text definitions: ' + str(absent[:10]))
    record = {'format': FORMAT, 'status': 'compiler-stack-usage-captured',
              'native_apple_compiler': native_apple,
              'source': str(source), 'source_sha256': sha(source),
              'object': str(obj), 'object_sha256': sha(obj),
              'usage_file': str(usage) if usage.is_file() else None,
              'usage_sha256': sha(usage) if usage.is_file() else None,
              'usage_emission': usage_emission,
              'command': command, 'cwd': str(cwd.resolve()) if cwd else None,
              'command_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest(),
              'functions': functions, 'kernel_execution': 'not_tested',
              'production_candidate_allowed': False}
    path = obj.with_suffix('.stack.json')
    write(path, record)
    return {'path': str(path), 'sha256': sha(path),
            'function_count': len(functions),
            'dynamic_function_count': sum(not value['static_frame_known'] for value in functions),
            'native_apple_compiler': native_apple}

def load_capture(reference: dict) -> dict:
    path = Path(reference['path'])
    if sha(path) != reference['sha256']:
        raise ValueError('Stack capture identity changed.')
    record = json.loads(path.read_text())
    if record.get('format') != FORMAT or record.get('status') != 'compiler-stack-usage-captured':
        raise ValueError('Unsupported stack capture.')
    for field in ('source', 'object'):
        if sha(Path(record[field])) != record[field.replace('_file', '') + '_sha256']:
            raise ValueError('Stack capture input changed: ' + field)
    if record['usage_file'] is not None:
        if sha(Path(record['usage_file'])) != record['usage_sha256']:
            raise ValueError('Stack capture input changed: usage_file')
        if record['functions'] != parse_usage(Path(record['usage_file']).read_text()):
            raise ValueError('Parsed compiler stack records changed.')
    else:
        image = macho.Object(Path(record['object']), allow_empty_code_without_symbols=True)
        if (record.get('usage_emission') != 'not-emitted-for-object-without-executable-code'
                or record['usage_sha256'] is not None or record['functions']
                or any(section.size and (section.name == '__text' or section.flags & 0x80000400)
                       for section in image.sections)
                or Path(record['object']).with_suffix('.su').exists()):
            raise ValueError('Absent compiler stack output lacks an unchanged empty-object proof.')
    return record

def usage_manifest(references: list[dict], output: Path) -> dict:
    units = [load_capture(reference) for reference in references]
    largest = sorted((dict(function, object=unit['object']) for unit in units
                      for function in unit['functions'] if function['static_frame_known']),
                     key=lambda value: value['reported_bytes'], reverse=True)[:50]
    record = {'format': FORMAT, 'status': 'compiler-stack-usage-collected',
              'unit_count': len(units), 'units': references,
              'function_count': sum(len(unit['functions']) for unit in units),
              'dynamic_function_count': sum(not function['static_frame_known']
                  for unit in units for function in unit['functions']),
              'largest_static_frames': largest,
              'aggregate_stack_proven': False, 'production_candidate_allowed': False}
    write(output, record)
    return {'path': str(output), 'sha256': sha(output), 'unit_count': len(units),
            'function_count': record['function_count'],
            'dynamic_function_count': record['dynamic_function_count'],
            'aggregate_stack_proven': False}

def load_manifest(reference: dict | None) -> list[dict]:
    if not reference:
        return []
    path = Path(reference['path'])
    if sha(path) != reference['sha256']:
        raise ValueError('Stack-usage manifest changed.')
    value = json.loads(path.read_text())
    if value.get('status') != 'compiler-stack-usage-collected':
        raise ValueError('Unsupported stack-usage manifest.')
    for unit in value['units']:
        load_capture(unit)
    return value['units']

def parse_disassembly(text: str) -> list[dict]:
    """Accept native otool -tv and LLVM's numeric Mach-O disassembly control."""
    active, result, seen = False, [], set()
    for line in text.splitlines():
        if line.strip() == '(__TEXT,__text) section':
            active = True
            continue
        if line.lstrip().startswith('(') and ') section' in line:
            active = False
        if not active:
            continue
        match = re.match(r'^\s*([0-9a-fA-F]+):?\s+'
                         r'(?:(?:[0-9a-fA-F]{2}\s+)+)?'
                         r'([a-z][a-z0-9_.]*)\s*(.*)$', line)
        if not match:
            # Named labels are fine; undecodable address-bearing bytes are not.
            bad = re.match(r'^\s*([0-9a-fA-F]+):?\s+', line)
            if bad:
                address = int(bad[1], 16)
                result.append({'address': address, 'mnemonic': '<undecoded>', 'operands': line.strip()})
            continue
        address = int(match[1], 16)
        if address in seen:
            raise ValueError('Repeated decoder instruction address.')
        seen.add(address)
        result.append({'address': address, 'mnemonic': match[2], 'operands': match[3]})
    if not active and not result:
        raise ValueError('Decoder did not identify the actual __TEXT,__text section.')
    return sorted(result, key=lambda value: value['address'])

def extract_graph(reference: dict, *, decoder: list[str] | None = None) -> dict:
    unit = load_capture(reference)
    obj = Path(unit['object'])
    image = macho.Object(obj, allow_empty_code_without_symbols=True)
    texts = [(index, section) for index, section in enumerate(image.sections, 1)
             if section.name == '__text']
    if len(texts) > 1:
        raise ValueError('Ambiguous executable text sections in stack graph.')
    if not texts or not texts[0][1].size:
        return {'object': str(obj), 'object_sha256': unit['object_sha256'], 'nodes': []}
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
            # Preserve unnamed-by-compiler machine functions as unknown, rather
            # than dropping a potential direct/indirect target from the graph.
            frame, unknown = None, [{'reason': 'missing-compiler-stack-record'}]
        elif any(not value['static_frame_known'] for value in reported):
            frame, unknown = None, [{'reason': 'dynamic-compiler-stack-frame',
                                     'records': reported}]
        elif len({value['reported_bytes'] for value in reported}) != 1:
            frame, unknown = None, [{'reason': 'conflicting-stack-record-aliases'}]
        else:
            frame, unknown = reported[0]['reported_bytes'], []
        node = {'id': unit['object_sha256'] + ':' + aliases[0],
                'symbols': aliases, 'external_symbols': sorted(symbol.name for symbol in symbols if symbol.kind & 1),
                'object': str(obj), 'start': address,
                'end': positions[index + 1] if index + 1 < len(positions) else section.address + section.size,
                'static_frame_bytes': frame, 'compiler_records': reported,
                'calls': [], 'unknown_sites': unknown}
        nodes.append(node)
        at_address[address] = node
    if section.size and not nodes:
        raise ValueError('Actual executable text lacks named stack graph owners.')
    decoder = decoder or ['/usr/bin/xcrun', 'otool', '-tv']
    run = subprocess.run([*decoder, str(obj)], text=True, capture_output=True, timeout=180)
    if run.returncode:
        raise ValueError('Actual Mach-O disassembly failed: ' + run.stderr[-2000:])
    if sha(obj) != unit['object_sha256']:
        raise ValueError('Actual object changed during disassembly.')
    instructions = parse_disassembly(run.stdout) if section.size else []
    addresses = [value['address'] for value in instructions]
    relocations = image.relocations(section)
    by_offset = {value.offset: value for value in relocations}
    def destination(address: int, relative: int) -> dict:
        relocation = by_offset.get(address - section.address + relative)
        if relocation:
            if relocation.kind != 2 or not relocation.pc_relative or relocation.width != 4:
                return {'unresolved': 'unsupported-direct-branch-relocation'}
            try:
                target, function = image.target(section, relocation)
            except ValueError as error:
                return {'unresolved': str(error)}
            if function:
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
                    node['unknown_sites'].append({'reason': 'unsupported-direct-branch-encoding',
                                                   'address': address})
                    continue
                target = destination(address, relative)
                if 'local' in target and node['start'] <= target['local'] < node['end'] and not name.startswith('call'):
                    continue
                if 'local' in target:
                    owner = at_address.get(target['local'])
                    target = {'node': owner['id']} if owner else {'unresolved': 'interior-or-unnamed-code-target'}
                node['calls'].append({'address': address, 'kind': 'call' if name.startswith('call') else 'branch',
                                      'target': target})
            elif name in ('lcall', 'ljmp', 'ljmpq', 'lret', 'iret', 'iretq',
                          'syscall', 'sysenter', 'sysret', 'sysretq',
                          'int', 'int3', 'into', 'ud2') or (
                    name in ('rep', 'repe', 'repne', 'bnd', 'data16', 'notrack') and
                    re.search(r'\b(?:call|jmp|ret|iret)[qlw]?\b', operands)):
                node['unknown_sites'].append({'reason': 'unreviewed-special-control-transfer', 'address': address})
            if operands.endswith(', %rsp') and not (
                    re.fullmatch(r'\$-?(?:0x[0-9a-f]+|\d+), %rsp', operands) and name in ('addq', 'subq') or
                    name == 'movq' and operands == '%rbp, %rsp'):
                node['unknown_sites'].append({'reason': 'unreviewed-stack-pointer-write',
                                               'address': address, 'instruction': name + ' ' + operands})
    path = obj.with_suffix('.stack-graph.json')
    record = {'format': FORMAT, 'object': str(obj), 'object_sha256': unit['object_sha256'],
              'stack_capture': reference, 'decoder_command': decoder,
              'decoder_output_sha256': hashlib.sha256(run.stdout.encode()).hexdigest(),
              'nodes': nodes, 'kernel_execution': 'not_tested',
              'production_candidate_allowed': False}
    write(path, record)
    return record

def aggregate_graphs(graphs: list[dict], *, roots: dict[str, str] | None = None) -> dict:
    # Keep each hash-bound object graph immutable; global resolution is a
    # separate analysis, and repeated root queries must give the same result.
    nodes = {value['id']: deepcopy(value) for graph in graphs for value in graph['nodes']}
    definitions = defaultdict(set)
    for node in nodes.values():
        for name in node['external_symbols']:
            definitions[name].add(node['id'])
    for node in nodes.values():
        for edge in node['calls']:
            target = edge['target']
            if 'symbol' in target:
                edge['targets'] = sorted(definitions[target['symbol']])
                if not edge['targets']:
                    node['unknown_sites'].append({'reason': 'external-stack-bound-unavailable',
                                                   'address': edge['address'], 'target': target['symbol']})
            elif 'node' in target:
                edge['targets'] = [target['node']]
            else:
                edge['targets'] = []
                node['unknown_sites'].append({'reason': target['unresolved'], 'address': edge['address']})
    results = {}
    for label, symbol in (roots or ROOTS).items():
        memo, active, reached, reasons = {}, set(), set(), []
        def bound(identity: str) -> int | None:
            if identity in active:
                reasons.append({'function': identity, 'reason': 'recursion-cycle'})
                return None
            if identity in memo:
                return memo[identity]
            node = nodes[identity]
            reached.add(identity)
            reasons.extend(dict(value, function=identity) for value in node['unknown_sites'])
            active.add(identity)
            child_bounds = [bound(target) for edge in node['calls'] for target in edge['targets']]
            active.remove(identity)
            complete = node['static_frame_bytes'] is not None and not node['unknown_sites'] and all(
                value is not None for value in child_bounds)
            # Overcount tail branches deliberately: this is an upper bound of
            # a fully resolved compiled subgraph, never a measured peak or a
            # proof that a sum above the budget actually occurs at runtime.
            value = (node['static_frame_bytes'] + RETURN_ADDRESS_BYTES + max(child_bounds, default=0)
                     if complete else None)
            memo[identity] = value
            return value
        candidates = sorted(definitions[symbol])
        bounds = [bound(identity) for identity in candidates]
        if not candidates:
            reasons.append({'reason': 'missing-root-definition', 'target': symbol})
        known = bool(candidates) and all(value is not None for value in bounds)
        results[label] = {'symbol': symbol, 'compiled_graph_upper_bound_bytes': max(bounds) if known else None,
                          'compiled_graph_complete': known, 'reachable_function_count': len(reached),
                          'unknown_site_count': len(reasons), 'unknown_reason_counts': dict(Counter(
                              value['reason'] for value in reasons)), 'unknown_examples': reasons[:50]}
    return {'format': FORMAT, 'status': 'diagnostic-stack-audit; admission-not-proven',
            'function_count': len(nodes), 'object_count': len(graphs), 'roots': results,
            'largest_static_frames': sorted(({'function': node['id'], 'bytes': node['static_frame_bytes']}
                for node in nodes.values() if node['static_frame_bytes'] is not None),
                key=lambda value: value['bytes'], reverse=True)[:50],
            'source_default_thread_stack_bytes': SOURCE_DEFAULT_STACK_BYTES,
            'source_default_irq_stack_bytes': SOURCE_DEFAULT_STACK_BYTES,
            'actual_target_stack_bytes': None, 'framework_entry_headroom_bytes': None,
            'interrupt_nesting_budget_bytes': None,
            'inline_assembly_stack_contract': 'not_established',
            'return_address_bytes_added_per_function': RETURN_ADDRESS_BYTES,
            'limitations': ['Direct-call frame sums are conservative compiled-subgraph upper bounds, not runtime peaks.',
                'External SDK/memory helpers, indirect/NVOC calls, recursion and dynamic frames remain unknown.',
                'Inline-assembly stack behavior, scheduler/framework headroom, actual kernel configuration and interrupt nesting require separate review.',
                'A persistent thread or allocated NVIDIA stack buffer is not an enlarged XNU stack.'],
            'aggregate_stack_proven': False, 'kernel_execution': 'not_tested',
            'production_candidate_allowed': False}

def audit(manifests: list[dict | None], output: Path, *,
          decoder: list[str] | None = None,
          expected_objects: list[Path] | None = None) -> dict:
    references = [unit for manifest in manifests for unit in load_manifest(manifest)]
    missing = sum(manifest is None for manifest in manifests)
    with ThreadPoolExecutor(max_workers=6) as pool:
        graphs = list(pool.map(lambda value: extract_graph(value, decoder=decoder), references))
    result = aggregate_graphs(graphs)
    result['missing_usage_manifests'] = missing
    result['native_apple_compiler'] = bool(references) and all(
        load_capture(reference)['native_apple_compiler'] for reference in references)
    result['usage_manifests'] = manifests
    measured = {Path(load_capture(reference)['object']).resolve() for reference in references}
    expected = {path.resolve(strict=True) for path in expected_objects or []}
    if expected_objects is not None and measured - expected:
        raise ValueError('Stack capture contains objects outside the actual compilation.')
    result['expected_object_count'] = len(expected) if expected_objects is not None else None
    result['missing_object_measurements'] = sorted(str(path) for path in expected - measured)
    write(output, result)
    return {'path': str(output), 'sha256': sha(output), 'status': result['status'],
            'function_count': result['function_count'], 'missing_usage_manifests': missing,
            'aggregate_stack_proven': False, 'production_candidate_allowed': False}
