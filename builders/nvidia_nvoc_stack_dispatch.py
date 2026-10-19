"""Typed, source-bound evidence for a narrowly resolvable NVOC indirect call.

This does not assign arbitrary address-taken functions to a call site. It admits
only a unique machine/IR indirect call, a compiler-confirmed struct member, and
the exact constant assignments to that member in the reviewed generated source.
It emits evidence; it does not change the stack collector or admission gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import nvidia_metaclass_initializers as macho
import nvidia_stack_usage as stack

IDENTIFIER = r'[A-Za-z_][A-Za-z_0-9]*'
SSA = r'%[-A-Za-z$._0-9]+'
METADATA = r'(?:,\s*![A-Za-z_0-9.]+\s+!\d+)*'


def _strip_comments(text: str) -> str:
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m[0].count('\n'),
                  text, flags=re.S)


def catalog(source_root: Path, header: Path, generated: Path, field: str) -> dict:
    """Refuse any occurrence outside the four reviewed generated patterns.

    Hash the entire searched C/C++ source inventory, not just files that already
    contain the field. A newly introduced store/escape therefore changes the
    identity and is examined, rather than silently retaining an old target set.
    """
    if not re.fullmatch(IDENTIFIER, field):
        raise ValueError('Invalid NVOC field identifier.')
    source_root = source_root.resolve(strict=True)
    header, generated = header.resolve(strict=True), generated.resolve(strict=True)
    inventory, references, targets = [], [], set()
    for path in sorted(source_root.rglob('*')):
        if not path.is_file() or path.suffix not in ('.c', '.h', '.cpp', '.hpp'):
            continue
        relative = str(path.relative_to(source_root))
        inventory.append([relative, stack.sha(path)])
        text = _strip_comments(path.read_text(errors='strict'))
        for number, line in enumerate(text.splitlines(), 1):
            if not re.search(r'\b' + re.escape(field) + r'\b', line):
                continue
            assignment = re.fullmatch(r'\s*pThis->' + re.escape(field) +
                                      r'\s*=\s*&(' + IDENTIFIER + r');\s*', line)
            if path == generated and assignment:
                kind = 'constant-generated-assignment'
                targets.add(assignment[1])
            elif path == header and re.fullmatch(
                    r'\s*.+\(\s*\*\s*' + re.escape(field) + r'\s*\)\s*\(.*;\s*', line):
                kind = 'member-declaration'
            elif path == header and re.fullmatch(
                    r'\s*#define\s+' + IDENTIFIER + r'\([^)]*\)\s+' +
                    IDENTIFIER + r'->' + re.escape(field) + r'\s*', line):
                kind = 'generated-load-macro'
            elif path == header and re.fullmatch(
                    r'\s*return\s+' + IDENTIFIER + r'->' + re.escape(field) + r'\([^;]*\);\s*', line):
                kind = 'generated-dispatch-call'
            else:
                raise ValueError('Unreviewed NVOC member use/store/escape at ' + relative + ':' + str(number))
            references.append({'source': relative, 'line': number, 'kind': kind,
                               'text': line.strip()})
    if not targets or sum(value['kind'] == 'member-declaration' for value in references) != 1:
        raise ValueError('NVOC member requires one declaration and constant generated targets.')
    return {'field': field, 'targets': sorted(targets), 'references': references,
            'source_root': str(source_root), 'header': str(header), 'generated': str(generated),
            'header_sha256': stack.sha(header), 'generated_sha256': stack.sha(generated),
            'source_inventory_sha256': hashlib.sha256(json.dumps(inventory).encode()).hexdigest(),
            'source_inventory_file_count': len(inventory)}


def function_ir(text: str, function: str) -> str:
    starts = list(re.finditer(r'^define\b[^\n]*@' + re.escape(function) + r'\(', text, re.M))
    if len(starts) != 1:
        raise ValueError('Expected one actual LLVM function: ' + function)
    start = starts[0].start()
    end = text.find('\n}', start)
    if end < 0:
        raise ValueError('Truncated LLVM function.')
    body = text[start:end + 2]
    if re.search(r'\b(?:asm|callbr|invoke)\b', body):
        raise ValueError('Inline assembly or alternate call control requires separate review.')
    return body


def indirect_gep(text: str, function: str) -> dict:
    """Require one actual indirect IR call loaded from one constant struct GEP.

    SSA spelling is not interpreted as a member name. The independent probe
    below maps the actual C member to this type/index with the same compiler.
    """
    body = function_ir(text, function)
    calls = re.findall(r'\bcall\b[^\n]*?\s(' + SSA + r')\(', body)
    if len(calls) != 1:
        raise ValueError('Expected exactly one actual indirect LLVM call.')
    load = re.findall(r'^\s*' + re.escape(calls[0]) + r'\s*=\s*load ptr, ptr\s+(' + SSA + r'),', body, re.M)
    if len(load) != 1:
        raise ValueError('Indirect LLVM callee is not one direct member load.')
    return gep_definition(body, load[0])


def gep_definition(body: str, value: str) -> dict:
    matches = list(re.finditer(r'^\s*' + re.escape(value) +
        r'\s*=\s*getelementptr(?: inbounds)?\s+%struct\.(' + IDENTIFIER + r'),\s*ptr\s+(' + SSA +
        r'),\s*i64 0,\s*i32 (\d+)' + METADATA + r'\s*$', body, re.M))
    if len(matches) != 1:
        raise ValueError('Callee does not use one constant typed struct member GEP.')
    match = matches[0]
    return {'llvm_struct': match[1], 'llvm_member_index': int(match[3]), 'receiver': match[2]}


def probe_gep(text: str) -> dict:
    body = function_ir(text, 's540StackLoadTarget')
    returned = re.findall(r'^\s*ret ptr (' + SSA + r')' + METADATA + r'\s*$', body, re.M)
    if len(returned) != 1:
        raise ValueError('Typed load probe has no unique pointer return.')
    load = re.findall(r'^\s*' + re.escape(returned[0]) +
                      r'\s*=\s*load ptr, ptr (' + SSA + r'),', body, re.M)
    if len(load) != 1:
        raise ValueError('Typed load probe has no unique member load.')
    return gep_definition(body, load[0])


def probe_source(include: str, owner: str, field: str, targets: list[str]) -> str:
    if not re.fullmatch(r'[A-Za-z_0-9/.-]+', include) or not all(
            re.fullmatch(IDENTIFIER, value) for value in [owner, field, *targets]):
        raise ValueError('Invalid typed NVOC probe input.')
    assertions = '\n'.join('_Static_assert(__builtin_types_compatible_p(S540StackType, '
        '__typeof__(&' + name + ')), "NVOC candidate type");' for name in targets)
    return ('/* Compile-only evidence, never linked into the driver. */\n#include "' + include + '"\n'
        'typedef __typeof__(((struct ' + owner + ' *)0)->' + field + ') S540StackType;\n' + assertions + '\n'
        '__attribute__((used)) const unsigned long long s540StackFieldOffset = '
        '__builtin_offsetof(struct ' + owner + ', ' + field + ');\n'
        '__attribute__((used)) S540StackType const s540StackTargets[] = { ' +
        ', '.join('&' + value for value in targets) + ' };\n'
        '__attribute__((used,noinline)) S540StackType s540StackLoadTarget(struct ' + owner +
        ' *p) { return p->' + field + '; }\n')


def probe_object(obj: Path, targets: list[str], *, namespace: str = '') -> dict:
    image = macho.Object(obj)
    def named(name, size):
        found = [value for value in image.symbols if value.name == '_' + name and value.section]
        if len(found) != 1:
            raise ValueError('Typed NVOC probe requires unique data symbol: ' + name)
        value = found[0]
        section = image.sections[value.section - 1]
        relative = value.value - section.address
        if relative < 0 or relative + size > section.size:
            raise ValueError('Typed NVOC data symbol is out of range.')
        following = [symbol.value - section.address for symbol in image._defined(value.section)
                     if symbol.value > value.value]
        atom_end = min(following, default=section.size)
        if atom_end - relative != size:
            raise ValueError('Typed NVOC data atom has extra or missing bytes.')
        return section, relative
    offset_section, offset = named('s540StackFieldOffset', 8)
    if any(value.offset < offset + 8 and value.offset + value.width > offset
           for value in image.relocations(offset_section)):
        raise ValueError('Typed member offset must be an actual absolute compiler constant.')
    field_offset = int.from_bytes(image.data[offset_section.offset + offset:
                                             offset_section.offset + offset + 8], 'little')
    section, relative = named('s540StackTargets', 8 * len(targets))
    relocations = [value for value in image.relocations(section)
                   if relative <= value.offset < relative + 8 * len(targets)]
    if [value.offset - relative for value in relocations] != list(range(0, 8 * len(targets), 8)):
        raise ValueError('Every typed candidate pointer requires one exact relocation.')
    actual = []
    for index, relocation in enumerate(relocations):
        if relocation.pc_relative or relocation.width != 8 or relocation.kind != 0:
            raise ValueError('Unexpected typed candidate pointer relocation encoding.')
        target, _ = image.target(section, relocation)
        if 'function' in target:
            name = target['function']
            allowed = {'_' + targets[index], '_' + namespace + targets[index]}
        elif 'external' in target and target['addend'] == 0:
            name = target['external']
            allowed = {'_' + namespace + targets[index]}
        else:
            raise ValueError('Typed candidate does not identify one exact function.')
        # Header-local stubs may remain local/unrenamed. An actual undefined
        # symbol must obey the real global namespace overlay exactly.
        if name not in allowed:
            raise ValueError('Compiler typed candidate targets differ from generated assignments.')
        actual.append(name)
    return {'field_offset_bytes': field_offset, 'compiled_target_symbols': actual,
            'object_sha256': stack.sha(obj)}


def _command(unit: dict, source: Path, output: Path, *, ir: bool = False,
             named: bool = False) -> list[str]:
    command, result, index = unit['command'], [], 0
    source_spelling = str(source)
    while index < len(command):
        value = command[index]
        if value == '-o':
            index += 2
            continue
        if value in ('-c', '-emit-llvm', '-S'):
            index += 1
            continue
        candidate = Path(value)
        candidate = candidate if candidate.is_absolute() else Path(unit['cwd'] or '.') / candidate
        if not value.startswith('-') and candidate.resolve() == Path(unit['source']):
            # __FILE__ is part of original assertion strings. Preserve the
            # actual compile spelling, not merely its resolved path identity.
            if source.resolve() == Path(unit['source']):
                source_spelling = value
            index += 1
            continue
        result.append(value)
        index += 1
    if named:
        result.append('-fno-discard-value-names')
    if ir:
        result.extend(['-emit-llvm', '-S'])
    else:
        result.append('-c')
    return [*result, source_spelling, '-o', str(output)]


def prove(reference: dict, source_root: Path, *, owner: str, field: str,
          header: Path, generated: Path, include: str, function: str,
          output: Path, decoder: list[str] | None = None, namespace: str = '') -> dict:
    unit = stack.load_capture(reference)
    catalog_record = catalog(source_root, header, generated, field)
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'typed-nvoc-probe.c'
    source.write_text(probe_source(include, owner, field, catalog_record['targets']))
    named, original_ir = output / 'original-with-names.o', output / 'original.ll'
    obj, probe_ir = output / 'typed-nvoc-probe.o', output / 'typed-nvoc-probe.ll'
    commands = []
    for input_file, destination, ir, names in [
            (Path(unit['source']), named, False, True),
            (Path(unit['source']), original_ir, True, True),
            (source, obj, False, False), (source, probe_ir, True, True)]:
        command = _command(unit, input_file, destination, ir=ir, named=names)
        run = subprocess.run(command, cwd=unit['cwd'], text=True, capture_output=True, timeout=180)
        destination.with_suffix(destination.suffix + '.log').write_text(run.stdout + run.stderr)
        if run.returncode:
            raise ValueError('Actual typed NVOC compile failed: ' + run.stderr[-4000:])
        commands.append(command)
    if named.read_bytes() != Path(unit['object']).read_bytes():
        raise ValueError('LLVM value-name reporting changed the measured object bytes.')
    actual_gep = indirect_gep(original_ir.read_text(), namespace + function)
    expected_gep = probe_gep(probe_ir.read_text())
    if any(actual_gep[key] != expected_gep[key] for key in ('llvm_struct', 'llvm_member_index')):
        raise ValueError('Actual indirect callee does not load the compiled C member.')
    abi = probe_object(obj, catalog_record['targets'], namespace=namespace)
    graph = stack.extract_graph(reference, decoder=decoder)
    nodes = [value for value in graph['nodes'] if '_' + namespace + function in value['symbols']]
    if len(nodes) != 1:
        raise ValueError('Expected one actual machine function.')
    node = nodes[0]
    sites = [value for value in node['unknown_sites'] if value['reason'] == 'indirect-control-transfer']
    if len(sites) != 1:
        raise ValueError('Unique IR evidence requires exactly one machine indirect call.')
    site = sites[0]
    machine = re.fullmatch(r'callq?\s+\*((?:0x[0-9a-f]+|\d+))\(%r(?:[a-z]+|[0-9]+)\)', site['instruction'])
    if not machine or int(machine[1], 0) != abi['field_offset_bytes']:
        raise ValueError('Actual machine call does not use the compiled member byte offset.')
    if catalog(source_root, header, generated, field) != catalog_record:
        raise ValueError('NVOC source inventory changed while compiling the typed proof.')
    result = {'format': 1, 'status': 'one-typed-nvoc-dispatch-target-set-established',
              'stack_capture': reference, 'source_catalog': catalog_record,
              'native_apple_compiler': unit['native_apple_compiler'],
              'function': function, 'machine_site': site,
              'machine_offset_in_function': site['address'] - node['start'],
              'compiler_gep': actual_gep, 'typed_probe_gep': expected_gep, 'typed_probe_abi': abi,
              'object_identity_with_value_names': True, 'commands': commands,
              'evidence_sha256': {str(path): stack.sha(path)
                  for path in (source, obj, probe_ir, original_ir, named)},
              'target_definition_binding': 'pending; local targets require their actual defining object',
              'callee_stack_bounds': 'not_established', 'aggregate_stack_proven': False,
              'kernel_execution': 'not_tested', 'production_candidate_allowed': False}
    path = output / 'typed-nvoc-dispatch.json'
    stack.write(path, result)
    return {'path': str(path), 'sha256': stack.sha(path), 'aggregate_stack_proven': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True,
        help='Actual compiled kernel_gsp.stack.json from the checked namespace build.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path,
        help='Pinned/checked NVIDIA tree; defaults to the actual capture cwd ancestor.')
    parser.add_argument('--namespace', default='s540Global_',
        help='Exact symbol namespace in the captured compiler command; empty for original control.')
    parser.add_argument('--llvm-objdump', type=Path,
        help='Explicit local cross decoder; native default is xcrun otool -tv.')
    args = parser.parse_args()
    if args.namespace and not re.fullmatch(IDENTIFIER, args.namespace):
        parser.error('Namespace must be one identifier prefix or empty.')
    reference = {'path': str(args.capture.resolve(strict=True)), 'sha256': stack.sha(args.capture)}
    unit = stack.load_capture(reference)
    root = args.source_root or Path(unit['cwd']).parents[1]
    root = root.resolve(strict=True)
    expected_source = root / 'src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c'
    if Path(unit['source']) != expected_source:
        raise ValueError('The dispatch proof requires the actual pinned kernel_gsp.c capture.')
    decoder = ([str(args.llvm_objdump), '--macho', '--disassemble', '--no-show-raw-insn',
                '--no-symbolic-operands'] if args.llvm_objdump else None)
    result = prove(reference, root, owner='OBJGPU', field='__gpuMarkDeviceForReset__',
        header=root / 'src/nvidia/generated/g_gpu_nvoc.h',
        generated=root / 'src/nvidia/generated/g_gpu_nvoc.c', include='gpu/gpu.h',
        function='kgspRecvPoll_IMPL', output=args.output, namespace=args.namespace,
        decoder=decoder)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
