"""Exact loader-code audit for the one reviewed IOKit power-service metaclass.

The SDK reference instantiates only OSDefineMetaClassAndStructors with the same
class declaration and compiler flags. Every initializer/finalizer entry, local
instruction byte and relocation reachable from those entries must match. Other
project objects still require an empty loader table. This is codegen evidence,
not authorization to execute the GPU or bypass the kernel startup gates.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'packages/nvidia-gsp-bootstrap/tests/sdk_power_metaclass_reference.cpp'
CLASS_HEADER = ROOT / 'packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPowerService.hpp'
CLASS_NAME = 'S540NvidiaGspPowerService'
CLASS_PREFIX = '__ZN18S540GspPowerKernel25' + CLASS_NAME
META_OBJECT = CLASS_PREFIX + '10gMetaClassE'
META_VTABLE = '__ZTVN18S540GspPowerKernel25' + CLASS_NAME + '9MetaClassE'
EXTERNALS = {
    '__ZN11OSMetaClassC2EPKcPKS_j', '__ZN11OSMetaClassD2Ev',
    '__ZN9IOService10gMetaClassE',
}
LOADER_TYPES = {'__mod_init_func': 9, '__mod_term_func': 10}
OTHER_LOADER_NAMES = {'__constructor', '__destructor', '__init_offsets',
                      '__init_array', '__fini_array', '.ctors', '.dtors'}


@dataclass(frozen=True)
class Section:
    name: str
    segment: str
    address: int
    size: int
    offset: int
    relocation_offset: int
    relocation_count: int
    flags: int


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: int
    section: int
    value: int


@dataclass(frozen=True)
class Relocation:
    offset: int
    symbol: int
    pc_relative: bool
    width: int
    external: bool
    kind: int


def _name(data: bytes) -> str:
    return data.split(b'\0', 1)[0].decode('ascii')


def _function_name(name: str) -> str:
    # Clang includes the TU basename in its single registration wrapper. The
    # reference has a different filename; no other symbol spelling is relaxed.
    return '<translation-unit-initializer>' if name.startswith('__GLOBAL__sub_I_') else name


def _without_alignment_nops(code: bytearray, relocation_end: int) -> bytearray:
    # MH_OBJECT has symbol starts, not function sizes. ld -r may append the
    # next input atom's alignment NOPs to the final function's inferred range.
    # Strip only x86 NOP encodings within one 16-byte alignment boundary, and
    # never an instruction operand covered by a relocation.
    bases = ('90', '6690', '0f1f00', '0f1f4000', '0f1f440000',
             '660f1f440000', '0f1f8000000000', '0f1f840000000000')
    patterns = {bytes.fromhex(value) for value in bases}
    for prefixes in range(1, 8):
        for segment in ('', '2e'):
            pattern = bytes.fromhex('66' * prefixes + segment + '0f1f840000000000')
            if len(pattern) <= 15:
                patterns.add(pattern)
    removed = 0
    for _ in range(15):
        matched = next((pattern for pattern in sorted(patterns, key=len, reverse=True)
                        if removed + len(pattern) <= 15 and len(code) - len(pattern) >= relocation_end and
                        code.endswith(pattern)), None)
        if matched is None:
            break
        del code[-len(matched):]
        removed += len(matched)
    return code


class Object:
    def __init__(self, path: Path, *, allow_empty_code_without_symbols: bool = False):
        self.path, self.data = path, path.read_bytes()
        data = self.data
        if len(data) < 32:
            raise ValueError('Truncated metaclass Mach-O header.')
        magic, cpu, _, kind, count, command_bytes, _, _ = struct.unpack_from('<8I', data)
        if (magic, cpu, kind) != (0xfeedfacf, 0x01000007, 1):
            raise ValueError('Metaclass audit requires an x86-64 MH_OBJECT.')
        if command_bytes > len(data) - 32:
            raise ValueError('Truncated Mach-O load commands.')
        self.sections: list[Section] = []
        table = None
        position = 32
        for _ in range(count):
            if position + 8 > 32 + command_bytes:
                raise ValueError('Truncated Mach-O load command.')
            command, size = struct.unpack_from('<II', data, position)
            if size < 8 or position + size > 32 + command_bytes:
                raise ValueError('Invalid Mach-O load command.')
            if command == 0x19:
                if size < 72:
                    raise ValueError('Truncated segment command.')
                sections = struct.unpack_from('<I', data, position + 64)[0]
                if 72 + sections * 80 > size:
                    raise ValueError('Truncated section table.')
                for index in range(sections):
                    values = struct.unpack_from('<16s16sQQIIIIIIII', data, position + 72 + index * 80)
                    section = Section(_name(values[0]), _name(values[1]), values[2], values[3],
                                      values[4], values[6], values[7], values[8])
                    if section.flags & 0xff not in (1, 0xc, 0x12) and section.offset + section.size > len(data):
                        raise ValueError('Truncated section contents.')
                    if section.relocation_offset + section.relocation_count * 8 > len(data):
                        raise ValueError('Truncated section relocations.')
                    self.sections.append(section)
            elif command == 2:
                if size < 24 or table is not None:
                    raise ValueError('Invalid symbol-table command.')
                table = struct.unpack_from('<4I', data, position + 8)
            position += size
        if position != 32 + command_bytes:
            raise ValueError('Incomplete Mach-O command/symbol tables.')
        if table is None:
            if (not allow_empty_code_without_symbols or
                    any(section.size and (section.name == '__text' or section.flags & 0x80000400)
                        for section in self.sections)):
                raise ValueError('Incomplete Mach-O command/symbol tables.')
            self.symbols = []
            return
        symbol_offset, symbol_count, string_offset, string_bytes = table
        if symbol_offset + symbol_count * 16 > len(data) or string_offset + string_bytes > len(data):
            raise ValueError('Truncated Mach-O symbol table.')
        self.symbols: list[Symbol] = []
        for index in range(symbol_count):
            string, kind, section, _, value = struct.unpack_from('<IBBHQ', data, symbol_offset + index * 16)
            if string >= string_bytes or section > len(self.sections):
                raise ValueError('Invalid Mach-O symbol reference.')
            name_end = data.find(b'\0', string_offset + string, string_offset + string_bytes)
            if name_end < 0:
                raise ValueError('Unterminated Mach-O symbol name.')
            self.symbols.append(Symbol(data[string_offset + string:name_end].decode('ascii'), kind, section, value))

    def relocations(self, section: Section) -> list[Relocation]:
        result = []
        occupied: set[int] = set()
        for index in range(section.relocation_count):
            address, info = struct.unpack_from('<II', self.data, section.relocation_offset + index * 8)
            width = 1 << ((info >> 25) & 3)
            if address & 0x80000000 or address + width > section.size:
                raise ValueError('Unsupported or out-of-range Mach-O relocation.')
            byte_range = set(range(address, address + width))
            if occupied & byte_range:
                raise ValueError('Overlapping relocation fields are not admitted.')
            occupied.update(byte_range)
            external = bool(info & (1 << 27))
            symbol = info & 0xffffff
            if (external and symbol >= len(self.symbols)) or (not external and not 1 <= symbol <= len(self.sections)):
                raise ValueError('Invalid relocation target.')
            kind = info >> 28
            if kind not in (0, 1, 2, 3, 4, 6, 7, 8):
                raise ValueError('Unsupported metaclass relocation kind.')
            result.append(Relocation(address, symbol, bool(info & (1 << 24)), width, external, kind))
        return sorted(result, key=lambda value: value.offset)

    def _defined(self, section: int) -> list[Symbol]:
        return [symbol for symbol in self.symbols if symbol.section == section and
                symbol.kind & 0xe0 == 0 and symbol.kind & 0x0e == 0x0e]

    def _code_symbol(self, section: int, address: int) -> Symbol:
        matches = [symbol for symbol in self._defined(section) if symbol.value == address]
        if not matches:
            raise ValueError('Loader code targets an unnamed interior instruction.')
        # Constructor aliases share an address. Keep the same deterministic
        # canonical name in separately compiled/reference/relocatable objects.
        return sorted(matches, key=lambda value: value.name)[0]

    def _cstring_target(self, section: Section, address: int) -> dict:
        if not section.address <= address < section.address + section.size:
            raise ValueError('Loader class-name target points outside its cstring section.')
        offset = section.offset + address - section.address
        end = self.data.find(b'\0', offset, section.offset + section.size)
        if end < 0:
            raise ValueError('Unterminated loader class-name string.')
        return {'cstring': self.data[offset:end].decode('ascii')}

    def target(self, section: Section, relocation: Relocation) -> tuple[dict, Symbol | None]:
        start = section.offset + relocation.offset
        raw = int.from_bytes(self.data[start:start + relocation.width], 'little', signed=relocation.pc_relative)
        if relocation.external:
            symbol = self.symbols[relocation.symbol]
            if not symbol.section:
                if symbol.kind & 0x0e != 0:
                    raise ValueError('Unexpected absolute/common external in loader code.')
                return {'external': symbol.name, 'addend': raw}, None
            target_section = self.sections[symbol.section - 1]
            if target_section.name == '__text':
                if raw:
                    raise ValueError('Loader calls an interior code addend.')
                function = self._code_symbol(symbol.section, symbol.value)
                return {'function': _function_name(function.name)}, function
            if target_section.name == '__cstring':
                # A relocatable link may name a defined string symbol where
                # the compiler used a section-relative relocation. Resolve
                # the actual symbol+addend address; retain the exact string,
                # relocation encoding and caller instruction comparison.
                return self._cstring_target(target_section, symbol.value + raw), None
            return {'data': symbol.name, 'addend': raw}, None
        target_section = self.sections[relocation.symbol - 1]
        address = raw
        if relocation.pc_relative:
            address += section.address + relocation.offset + relocation.width
            address += {6: 1, 7: 2, 8: 4}.get(relocation.kind, 0)
        if not target_section.address <= address < target_section.address + target_section.size:
            raise ValueError('Local relocation points outside its target section.')
        if target_section.name == '__text':
            function = self._code_symbol(relocation.symbol, address)
            return {'function': _function_name(function.name)}, function
        if target_section.name == '__cstring':
            return self._cstring_target(target_section, address), None
        symbols = [symbol for symbol in self._defined(relocation.symbol) if symbol.value <= address]
        if not symbols:
            raise ValueError('Loader data relocation has no named owner.')
        symbol = max(symbols, key=lambda value: value.value)
        return {'data': symbol.name, 'addend': address - symbol.value}, None

    def loader_graph(self) -> dict:
        entries, pending = [], []
        for section in self.sections:
            section_type = section.flags & 0xff
            if section.name in OTHER_LOADER_NAMES or section_type == 0x16:
                raise ValueError('An unreviewed alternate loader table is not admitted.')
            if section.name not in LOADER_TYPES and section_type not in LOADER_TYPES.values():
                continue
            if LOADER_TYPES.get(section.name) != section_type or section.size % 8:
                raise ValueError('Unexpected loader table name/type/alignment.')
            relocations = self.relocations(section)
            if [value.offset for value in relocations] != list(range(0, section.size, 8)):
                raise ValueError('Every loader pointer requires one exact relocation.')
            for relocation in relocations:
                if relocation.pc_relative or relocation.kind != 0 or relocation.width != 8:
                    raise ValueError('Unexpected loader-pointer relocation encoding.')
                target, function = self.target(section, relocation)
                if function is None:
                    raise ValueError('Loader table does not target local named code.')
                entries.append({'section': section.name, 'offset': relocation.offset, 'target': target})
                pending.append(function)
        functions = {}
        while pending:
            function = pending.pop()
            name = _function_name(function.name)
            if name in functions:
                if functions[name]['symbol'] != function:
                    raise ValueError('Multiple loader functions collapse to the same canonical identity.')
                continue
            section = self.sections[function.section - 1]
            if (section.name != '__text' or section.segment != '__TEXT' or
                    section.flags & 0x80000400 != 0x80000400):
                raise ValueError('Loader code is not in the executable __TEXT,__text section.')
            following = [symbol.value for symbol in self._defined(function.section) if symbol.value > function.value]
            end = min(following, default=section.address + section.size)
            start = function.value - section.address
            code = bytearray(self.data[section.offset + start:section.offset + end - section.address])
            relocations = []
            functions[name] = {'symbol': function}
            for relocation in self.relocations(section):
                if not start <= relocation.offset < end - section.address:
                    continue
                if relocation.offset + relocation.width > end - section.address:
                    raise ValueError('Relocation crosses a loader function boundary.')
                target, called = self.target(section, relocation)
                relative = relocation.offset - start
                code[relative:relative + relocation.width] = b'\0' * relocation.width
                relocations.append({'offset': relative, 'kind': relocation.kind,
                                    'pc_relative': relocation.pc_relative,
                                    'width': relocation.width, 'target': target})
                if called is not None:
                    pending.append(called)
            relocation_end = max((value['offset'] + value['width'] for value in relocations), default=0)
            code = _without_alignment_nops(code, relocation_end)
            functions[name].update(code=code.hex(), relocations=relocations)
        return {'entries': entries, 'functions': {
            name: {key: value for key, value in record.items() if key != 'symbol'}
            for name, record in sorted(functions.items())}}


def _review_reference(graph: dict) -> None:
    entries = graph['entries']
    initializers = [entry for entry in entries if entry['section'] == '__mod_init_func']
    finalizers = [entry for entry in entries if entry['section'] == '__mod_term_func']
    if len(initializers) != 1 or len(finalizers) != 1:
        raise ValueError('The SDK reference requires exactly one metaclass initializer and finalizer.')
    external, data, strings = set(), set(), set()
    for name, function in graph['functions'].items():
        if (name != '<translation-unit-initializer>' and not name.startswith('__GLOBAL__D_') and
                not name.startswith(CLASS_PREFIX + '9MetaClass')):
            raise ValueError('Reference loader reaches non-metaclass local code: ' + name)
        for relocation in function['relocations']:
            target = relocation['target']
            if 'external' in target:
                if target['external'] not in EXTERNALS or target['addend']:
                    raise ValueError('Reference loader reaches an unreviewed external/addend.')
                external.add(target['external'])
            elif 'data' in target:
                # Itanium C++ vptrs skip the two 8-byte vtable header words.
                expected_addend = {META_OBJECT: 0, META_VTABLE: 16}.get(target['data'])
                if expected_addend is None or target['addend'] != expected_addend:
                    raise ValueError('Reference loader touches non-metaclass data.')
                data.add(target['data'])
            elif 'cstring' in target:
                if target['cstring'] != CLASS_NAME:
                    raise ValueError('Reference loader registers an unexpected class name.')
                strings.add(target['cstring'])
    if not {'__ZN11OSMetaClassC2EPKcPKS_j', '__ZN11OSMetaClassD2Ev'} <= external:
        raise ValueError('Reference loader does not construct and destroy the actual OSMetaClass.')
    if data != {META_OBJECT, META_VTABLE} or strings != {CLASS_NAME}:
        raise ValueError('Reference loader does not register the exact reviewed class metadata.')


def verify_no_initializers(path: Path) -> None:
    if Object(path).loader_graph()['entries']:
        raise ValueError('An unapproved project object gained loader initialization: ' + path.name)


def verify_metaclass_initializers(actual: Path, reference: Path) -> dict:
    import json
    reference_graph = Object(reference).loader_graph()
    _review_reference(reference_graph)
    actual_graph = Object(actual).loader_graph()
    if actual_graph != reference_graph:
        raise ValueError('Actual loader initialization differs from the exact SDK metaclass reference: ' +
                         json.dumps({'actual': actual_graph, 'reference': reference_graph}, sort_keys=True))
    canonical = json.dumps(reference_graph, sort_keys=True, separators=(',', ':')).encode()
    return {'format': 1, 'status': 'matched-exact-metaclass-codegen',
            'class': CLASS_NAME, 'initializer_entries': sum(
                entry['section'] == '__mod_init_func' for entry in reference_graph['entries']),
            'finalizer_entries': sum(entry['section'] == '__mod_term_func' for entry in reference_graph['entries']),
            'loader_function_count': len(reference_graph['functions']),
            'loader_graph_sha256': hashlib.sha256(canonical).hexdigest(),
            'loader_external_symbols': sorted({relocation['target']['external']
                for function in reference_graph['functions'].values()
                for relocation in function['relocations'] if 'external' in relocation['target']}),
            'object_sha256': hashlib.sha256(actual.read_bytes()).hexdigest(),
            'reference_object_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
            'reference_source_sha256': hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
            'class_declaration_sha256': hashlib.sha256(CLASS_HEADER.read_bytes()).hexdigest(),
            'kernel_execution': 'not_tested', 'production_candidate_allowed': False}


def framework_imports(actual: Path, reference: Path) -> tuple[set[str], set[str]]:
    """Derive inherited SDK-vtable imports without approving project methods.

    The reference's compiler-generated IOService/OSMetaClass vtables refer to
    the inherited framework methods as well as our declared virtual overrides.
    Only overrides actually provided by the project can be subtracted. Their
    private namespace is checked, so another unimplemented project method
    cannot become a supposedly available framework operation.
    """
    verify_metaclass_initializers(actual, reference)
    project = Object(actual)
    defined = {symbol.name for symbol in project.symbols if symbol.section and
               symbol.kind & 0xe0 == 0 and symbol.kind & 1 and symbol.kind & 0x0e == 0x0e}
    undefined = {symbol.name for symbol in Object(reference).symbols if
                 symbol.kind == 1 and not symbol.section and not symbol.value}
    private_prefixes = tuple(prefix + owner for prefix in ('__ZN', '__ZNK')
                             for owner in ('18S540GspPowerKernel',
                                           '18S540NvidiaGspPower6Detail8Protocol'))
    dependencies = {name for name in undefined if name.startswith(private_prefixes)}
    if dependencies - defined:
        raise ValueError('The metaclass reference has an unimplemented project dependency: ' +
                         str(sorted(dependencies - defined)))
    if (undefined & defined) - dependencies:
        raise ValueError('Project definitions replace an inherited framework operation.')
    # Only these actual SDK ancestors supply the reference's inherited slots.
    # A private default member initializer can add other unresolved symbols
    # without changing the loader graph; it must never approve those as SDK.
    sdk_ancestors = ('OSMetaClass', 'OSMetaClassBase', 'OSObject',
                     'IORegistryEntry', 'IOService')
    framework_prefixes = tuple(prefix + str(len(owner)) + owner
                               for prefix in ('__ZN', '__ZNK') for owner in sdk_ancestors)
    framework = undefined - dependencies
    if unreviewed := {name for name in framework if not name.startswith(framework_prefixes)}:
        raise ValueError('The metaclass reference imports outside its SDK ancestry: ' +
                         str(sorted(unreviewed)))
    return framework, dependencies


def compile_reference(output: Path, kernel_flags: list[str], cpp_flags: list[str],
                      *, compiler: list[str] | None = None) -> Path:
    import nvidia_execution_commands as commands
    # Reject another authored/global operation in the independent reference.
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', REFERENCE.read_text(), flags=re.S)
    if re.findall(r'^\s*#include\s+"([^"\n]+)"\s*$', source, flags=re.M) != [
            '../platform/S540NvidiaGspPowerService.hpp']:
        raise ValueError('The metaclass reference must use the reviewed shared class declaration.')
    source = re.sub(r'^\s*#include[^\n]*$', '', source, flags=re.M)
    expected = 'namespace S540GspPowerKernel { OSDefineMetaClassAndStructors(S540NvidiaGspPowerService, IOService); }'
    if re.sub(r'\s+', '', source) != re.sub(r'\s+', '', expected):
        raise ValueError('The independent metaclass reference must contain only the reviewed macro.')
    output.mkdir(parents=True, exist_ok=True)
    obj = output / 'sdk-power-metaclass-reference.o'
    # LLVM18 TargetPassConfig::addISelPrepare lowers Mach-O llvm.global_dtors
    # back into __cxa_atexit even with -fno-use-cxa-atexit. The kernel compiler
    # caller must disable that backend pass as well. The actual graph review,
    # rather than a flag spelling, proves one real init and term and no cxa.
    # XNU f6217f... libkern/c++/OSRuntime.cpp consumes both SECT_MOD* tables in
    # OSRuntimeInitializeCPP/OSRuntimeFinalizeCPP (including failed load unwind).
    commands.run(*(compiler or ['/usr/bin/xcrun', 'clang++']), *kernel_flags, *cpp_flags,
                 '-c', str(REFERENCE), '-o', str(obj))
    _review_reference(Object(obj).loader_graph())
    return obj
