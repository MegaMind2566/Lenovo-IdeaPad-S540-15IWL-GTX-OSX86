#!/usr/bin/env python3
"""Prove the exact native Owner action jump table is intra-function control.

No arbitrary indirect call is assigned zero cost. The reviewed site is a
bounds-checked compiler switch JMP, with actual LC_DATA_IN_CODE table entries.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

OBJECT_SHA256 = '183e8929486c0bb1c0b9a922d032f8701f9c205a42d7bbc8903f1ab95761800f'
FUNCTION = '__ZN22S540NvidiaGspBootstrap5Owner4Impl6actionEPvj'
SOURCE_SHA256 = '1c4cd89bc61665fbeb56d8efdacd356414c1c7c5de0134363f8859bf624365f5'


def require(value, message):
    if not value:
        raise ValueError(message)


def guarded_table(text, start, end, indirect, instructions, relocations, data_entries):
    """A deliberately narrow Apple-Clang x86-64 switch pattern."""
    beginning = indirect - 27
    require(start <= beginning and indirect + 2 <= end, 'Switch guard is outside its function.')
    code = text[beginning:beginning + 29]
    require(len(code) == 29 and code[:6] == bytes.fromhex('41ffce4183fe') and
        code[7:9] == bytes.fromhex('0f87') and code[13:16] == bytes.fromhex('488d05') and
        code[20:] == bytes.fromhex('4a630cb04801c1ffe1'), 'Not the exact reviewed guarded switch encoding.')
    count = code[6] + 1
    require(count == 5, 'The reviewed switch has exactly five entries.')
    table = beginning + 20 + int.from_bytes(code[16:20], 'little', signed=True)
    out_of_range = beginning + 13 + int.from_bytes(code[9:13], 'little', signed=True)
    require(start <= table and table + count * 4 <= end, 'Switch table escapes its function range.')
    require((table, count * 4, 4) in data_entries,
            'Actual MH_OBJECT LC_DATA_IN_CODE must identify the exact JUMP_TABLE32 range.')
    require(not any(beginning <= r.offset < beginning + 29 or table <= r.offset < table + count * 4
                    for r in relocations), 'Switch proof cannot interpret relocated guard/table bytes.')
    targets = [table + int.from_bytes(text[table + 4*i:table + 4*i + 4], 'little', signed=True)
               for i in range(count)]
    by_address = {i['address']: i for i in instructions}
    require(all(start <= target < end and not table <= target < table + count * 4 and
                target in by_address and by_address[target]['mnemonic'] != '<undecoded>'
                for target in [out_of_range, *targets]),
            'Every bounded switch destination must be a decoded instruction in the same function.')
    for instruction in instructions:
        address, mnemonic, operands = (instruction[k] for k in ('address', 'mnemonic', 'operands'))
        if not start <= address < end:
            continue
        if mnemonic.startswith(('call', 'jmp', 'j')):
            if '*' in operands or operands.lstrip().startswith('%'):
                require(address == indirect and mnemonic == 'jmpq' and operands == '*%rcx',
                        'Another indirect transfer prevents a closed switch CFG proof.')
                continue
            match = re.fullmatch(r'0x([0-9a-f]+)', operands)
            require(match is not None, 'Unexpected direct branch spelling.')
            destination = int(match[1], 16)
            require(not beginning + 13 <= destination <= indirect,
                    'A direct branch bypasses the unsigned index guard.')
            require(not table <= destination < table + count * 4,
                    'A direct branch can execute the data table.')
    preceding = [i for i in instructions if start <= i['address'] < table and
                 not i['mnemonic'].startswith('nop')]
    require(preceding and preceding[-1]['mnemonic'] == 'jmp' and
            '*' not in preceding[-1]['operands'], 'Control can fall through into table bytes.')
    require(all(by_address.get(table + i * 4, {}).get('mnemonic') == '<undecoded>'
                for i in range(count)), 'Expected the five frozen collector data barriers.')
    return {'guard_address': beginning, 'indirect_jump_address': indirect,
        'table_address': table, 'table_bytes': text[table:table + count * 4].hex(),
        'unsigned_index_range': [0, count - 1], 'table_destinations': targets,
        'out_of_range_destination': out_of_range,
        'resolved_barriers': [{'address': indirect, 'reason': 'indirect-control-transfer'}] +
            [{'address': table + i*4, 'reason': 'undecoded-instruction'} for i in range(count)],
        'new_inter_function_call_edges': 0,
        'reason': 'Every guarded JMP target remains inside this measured function; table bytes are compiler-identified data.'}


def run(args):
    sys.path.insert(0, str(args.repository.resolve(strict=True) / 'builders'))
    import nvidia_metaclass_initializers as macho
    import nvidia_stack_usage as stack
    require(stack.sha(args.object) == OBJECT_SHA256, 'The exact reviewed native object is required.')
    require(stack.sha(args.source) == SOURCE_SHA256, 'The exact reviewed Owner source is required.')
    image = macho.Object(args.object)
    section = next(s for s in image.sections if s.name == '__text')
    symbols = image._defined(image.sections.index(section) + 1)
    selected = [s for s in symbols if s.name == FUNCTION]
    require(len(selected) == 1, 'One actual Owner action machine definition is required.')
    start = selected[0].value
    end = min((s.value for s in symbols if s.value > start), default=section.address + section.size)
    run = subprocess.run([str(args.llvm_objdump), '--macho', '--disassemble',
        '--no-show-raw-insn', '--no-symbolic-operands', str(args.object)],
        text=True, capture_output=True, timeout=120)
    require(run.returncode == 0, 'Actual decoder failed.')
    instructions = stack.parse_disassembly(run.stdout)
    data_entries, position = [], 32
    for _ in range(struct.unpack_from('<I', image.data, 16)[0]):
        command, size = struct.unpack_from('<II', image.data, position)
        if command == 0x29:
            offset, length = struct.unpack_from('<II', image.data, position + 8)
            require(length % 8 == 0 and offset + length <= len(image.data), 'Invalid data-in-code table.')
            data_entries.extend(struct.unpack_from('<IHH', image.data, i)
                                for i in range(offset, offset + length, 8))
        position += size
    proof = guarded_table(image.data[section.offset:section.offset + section.size], start, end,
        0x4d6, instructions, image.relocations(section), data_entries)
    result = {'format': 1, 'status': 'exact-native-intra-function-switch-proven',
        'object_sha256': OBJECT_SHA256, 'source_sha256': SOURCE_SHA256,
        'function': FUNCTION, 'function_range': [start, end], 'proof': proof,
        'scope': 'This exact native object only; no function-pointer target, callback lifetime or external stack bound inferred.',
        'aggregate_stack_proven': False, 'original_entry_admission': False,
        'kernel_execution': False, 'gpu_access': False}
    require(not args.output.exists(), 'Fresh switch evidence file required.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository', 'object', 'source', 'llvm-objdump', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    print(json.dumps(run(parser.parse_args())))
