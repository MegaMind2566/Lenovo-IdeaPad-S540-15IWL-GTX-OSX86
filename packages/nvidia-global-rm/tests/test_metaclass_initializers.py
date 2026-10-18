#!/usr/bin/env python3
"""Loader-graph parser regressions. Mach-O fixtures are never executed."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import nvidia_metaclass_initializers as metaclass


def fixture(path: Path, *, prefix=False, extra_entry=False, instruction=0x55,
            external=None, class_name=None, omit_pointer=False, interior=False,
            bad_flags=False, vtable_addend=16, padding=0, omit_finalizer=False,
            imports=(), definitions=(), external_string=False, string_addend=0,
            unterminated_string=False):
    """Small named-section/nlist/relocation records, not executable images."""
    base = 16 if prefix else 0
    text = bytearray(b'\x90' * (base + 80))
    text[base] = instruction
    text[base + 47] = text[base + 63] = text[-1] = 0xc3
    # Alignment after the last reachable function precedes the runtime atom.
    text[base + 64:base + 64] = b'\x90' * padding
    meta_address, vtable_address = len(text), len(text) + 40
    cstring_address = len(text) + 88
    cstring = (class_name or metaclass.CLASS_NAME).encode() + (b'X' if unterminated_string else b'\0')
    loader_address = (cstring_address + len(cstring) + 7) & ~7
    symbol_rows = [
        ('__GLOBAL__sub_I_' + ('actual.cpp' if prefix else 'reference.cpp'), 0x0e, 1, base),
        (metaclass.META_OBJECT, 0x0f, 2, meta_address),
        (metaclass.META_VTABLE, 0x0f, 2, vtable_address),
        (external or '__ZN11OSMetaClassC2EPKcPKS_j', 1, 0, 0),
        ('__ZN11OSMetaClassD2Ev', 1, 0, 0),
        ('_runtime_body', 0x0e, 1, base + 64 + padding),
        ('__GLOBAL__D_a', 0x0e, 1, base + 48),
        ('__ZN9IOService10gMetaClassE', 1, 0, 0),
    ]
    if prefix:
        symbol_rows.append(('_runtime_prefix', 0x0e, 1, 0))
    symbol_rows.extend((name, 1, 0, 0) for name in imports)
    symbol_rows.extend((name, 0x0f, 1, base + 64 + padding) for name in definitions)
    string_symbol = len(symbol_rows)
    if external_string:
        symbol_rows.append(('L_class_name', 0x0e, 3, cstring_address))
    text_relocations = []
    for offset, symbol, addend in ((4, 3, 0), (12, 1, 0), (20, 2, vtable_addend),
                                   (52, 1, 0), (58, 4, 0)):
        struct.pack_into('<i', text, base + offset, addend)
        kind = 2 if symbol in (3, 4) else 1
        text_relocations.append((base + offset, symbol | (1 << 24) | (2 << 25) | (1 << 27) | (kind << 28)))
    string_offset = base + 28
    struct.pack_into('<i', text, string_offset,
                     string_addend if external_string else
                     cstring_address - (string_offset + 4) + string_addend)
    target = (string_symbol | (1 << 27)) if external_string else 3
    text_relocations.append((string_offset, target | (1 << 24) | (2 << 25) | (1 << 28)))
    pointers = 2 if extra_entry else 1
    loader = bytearray(pointers * 8)
    loader_relocations = [] if omit_pointer else [(0, (3 << 25) | (1 << 27))]
    if interior:
        struct.pack_into('<Q', loader, 0, 1)
    if extra_entry:
        loader_relocations.append((8, 5 | (3 << 25) | (1 << 27)))
    finalizer = b'' if omit_finalizer else bytes(8)
    finalizer_relocations = [] if omit_finalizer else [(0, 6 | (3 << 25) | (1 << 27))]
    commands_size = 72 + 5 * 80 + 24
    text_file_offset = 32 + commands_size
    cstring_file_offset = text_file_offset + len(text)
    loader_file_offset = (cstring_file_offset + len(cstring) + 7) & ~7
    finalizer_file_offset = loader_file_offset + len(loader)
    relocation_offset = finalizer_file_offset + len(finalizer)
    text_relocation_bytes = b''.join(struct.pack('<II', *record) for record in text_relocations)
    loader_relocation_offset = relocation_offset + len(text_relocation_bytes)
    loader_relocation_bytes = b''.join(struct.pack('<II', *record) for record in loader_relocations)
    finalizer_relocation_offset = loader_relocation_offset + len(loader_relocation_bytes)
    finalizer_relocation_bytes = b''.join(struct.pack('<II', *record) for record in finalizer_relocations)
    symbol_offset = finalizer_relocation_offset + len(finalizer_relocation_bytes)
    strings, symbols = bytearray(b'\0'), bytearray()
    for name, kind, section, value in symbol_rows:
        symbols += struct.pack('<IBBHQ', len(strings), kind, section, 0, value)
        strings += name.encode() + b'\0'
    string_table_offset = symbol_offset + len(symbols)
    def section(name, address, size, offset, reloff, nreloc, flags):
        return struct.pack('<16s16sQQIIIIIIII', name.encode(), b'__DATA' if name != '__text' else b'__TEXT',
                           address, size, offset, 3, reloff, nreloc, flags, 0, 0, 0)
    sections = section('__text', 0, len(text), text_file_offset, relocation_offset, len(text_relocations), 0x80000400)
    sections += section('__common', meta_address, 88, 0, 0, 0, 1)
    sections += section('__cstring', cstring_address, len(cstring), cstring_file_offset, 0, 0, 2)
    sections += section('__mod_init_func', loader_address, len(loader), loader_file_offset,
                        loader_relocation_offset, len(loader_relocations), 0 if bad_flags else 9)
    sections += section('__mod_term_func', loader_address + len(loader), len(finalizer), finalizer_file_offset,
                        finalizer_relocation_offset, len(finalizer_relocations), 10)
    segment = struct.pack('<II16sQQQQIIII', 0x19, 72 + len(sections), b'', 0,
                          loader_address + len(loader) + len(finalizer), text_file_offset,
                          relocation_offset - text_file_offset, 7, 7, 5, 0) + sections
    symtab = struct.pack('<6I', 2, 24, symbol_offset, len(symbol_rows), string_table_offset, len(strings))
    header = struct.pack('<8I', 0xfeedfacf, 0x01000007, 3, 1, 2, commands_size, 0, 0)
    data = bytearray(header + segment + symtab + text + cstring)
    data += b'\0' * (loader_file_offset - len(data)) + loader + finalizer
    data += text_relocation_bytes + loader_relocation_bytes + finalizer_relocation_bytes + symbols + strings
    path.write_bytes(data)


class MetaclassInitializers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.reference = self.directory / 'reference.o'
        self.actual = self.directory / 'actual.o'
        fixture(self.reference)
        fixture(self.actual, prefix=True)

    def verify(self):
        return metaclass.verify_metaclass_initializers(self.actual, self.reference)

    def test_rebased_code_and_class_string_match(self):
        record = self.verify()
        self.assertEqual(record['status'], 'matched-exact-metaclass-codegen')
        self.assertEqual(record['initializer_entries'], 1)
        self.assertEqual(record['finalizer_entries'], 1)
        self.assertFalse(record['production_candidate_allowed'])

    def test_extra_initializer_rejected(self):
        fixture(self.actual, prefix=True, extra_entry=True)
        with self.assertRaisesRegex(ValueError, 'differs from the exact SDK'):
            self.verify()

    def test_linker_alignment_nops_do_not_change_loader_operation(self):
        fixture(self.actual, prefix=True, padding=7)
        self.assertEqual(self.verify()['status'], 'matched-exact-metaclass-codegen')

    def test_defined_symbol_and_section_string_relocations_match(self):
        fixture(self.actual, prefix=True, external_string=True)
        self.assertEqual(self.verify()['status'], 'matched-exact-metaclass-codegen')

    def test_defined_string_symbol_addend_changes_the_target(self):
        fixture(self.actual, prefix=True, external_string=True, string_addend=1)
        with self.assertRaisesRegex(ValueError, 'differs from the exact SDK'):
            self.verify()

    def test_defined_string_symbol_cannot_escape_its_section(self):
        for addend in (-1, len(metaclass.CLASS_NAME) + 1):
            with self.subTest(addend=addend):
                fixture(self.actual, prefix=True, external_string=True, string_addend=addend)
                with self.assertRaisesRegex(ValueError, 'outside its cstring section'):
                    self.verify()

    def test_defined_string_symbol_requires_terminator_inside_section(self):
        fixture(self.actual, prefix=True, external_string=True, unterminated_string=True)
        with self.assertRaisesRegex(ValueError, 'Unterminated loader class-name string'):
            self.verify()

    def test_changed_instruction_rejected(self):
        fixture(self.actual, prefix=True, instruction=0x56)
        with self.assertRaisesRegex(ValueError, 'differs from the exact SDK'):
            self.verify()

    def test_changed_external_target_rejected(self):
        fixture(self.actual, prefix=True, external='_unreviewed_operation')
        with self.assertRaisesRegex(ValueError, 'differs from the exact SDK'):
            self.verify()

    def test_false_reference_cannot_approve_other_code(self):
        fixture(self.reference, external='_unreviewed_operation')
        with self.assertRaisesRegex(ValueError, 'unreviewed external'):
            self.verify()

    def test_atexit_runtime_cannot_be_approved_by_reference(self):
        for symbol in ('___cxa_atexit', '___dso_handle'):
            with self.subTest(symbol=symbol):
                fixture(self.reference, external=symbol)
                with self.assertRaisesRegex(ValueError, 'unreviewed external'):
                    self.verify()

    def test_missing_sdk_finalizer_rejected(self):
        fixture(self.reference, omit_finalizer=True)
        with self.assertRaisesRegex(ValueError, 'exactly one metaclass initializer and finalizer'):
            self.verify()

    def test_different_class_rejected(self):
        fixture(self.actual, prefix=True, class_name='AnotherIOService')
        with self.assertRaisesRegex(ValueError, 'differs from the exact SDK'):
            self.verify()

    def test_unrelocated_loader_pointer_rejected(self):
        fixture(self.actual, prefix=True, omit_pointer=True)
        with self.assertRaisesRegex(ValueError, 'Every loader pointer'):
            self.verify()

    def test_interior_entry_rejected(self):
        fixture(self.actual, prefix=True, interior=True)
        with self.assertRaisesRegex(ValueError, 'interior code addend'):
            self.verify()

    def test_mislabelled_loader_section_rejected(self):
        fixture(self.actual, prefix=True, bad_flags=True)
        with self.assertRaisesRegex(ValueError, 'table name/type'):
            self.verify()

    def test_data_addend_change_rejected(self):
        fixture(self.actual, prefix=True, vtable_addend=24)
        with self.assertRaisesRegex(ValueError, 'differs from the exact SDK'):
            self.verify()

    def test_unapproved_object_must_have_no_initializers(self):
        with self.assertRaisesRegex(ValueError, 'unapproved project object'):
            metaclass.verify_no_initializers(self.actual)

    def test_alternate_loader_table_cannot_hide_beside_reviewed_table(self):
        # The same bytes/entry relocations cannot be relabelled as a legacy
        # loader section and thereby disappear from the inspected entry set.
        for name in ('__constructor', '__destructor', '__init_offsets'):
            with self.subTest(name=name):
                fixture(self.actual, prefix=True)
                data = self.actual.read_bytes().replace(b'__mod_init_func\0', name.encode().ljust(16, b'\0'), 1)
                self.actual.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'alternate loader table'):
                    self.verify()

    def test_truncated_object_rejected(self):
        self.actual.write_bytes(self.actual.read_bytes()[:39])
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            self.verify()

    def test_framework_imports_derive_inherited_sdk_slots(self):
        sdk_method = '__ZN9IOService5startEPS_'
        sdk_const_method = '__ZNK8OSObject12getMetaClassEv'
        fixture(self.reference, imports=(sdk_method, sdk_const_method))
        fixture(self.actual, prefix=True, imports=(sdk_method, sdk_const_method))
        inherited, dependencies = metaclass.framework_imports(self.actual, self.reference)
        self.assertEqual(inherited, metaclass.EXTERNALS | {sdk_method, sdk_const_method})
        self.assertEqual(dependencies, set())

    def test_implemented_project_override_is_not_a_framework_import(self):
        override = metaclass.CLASS_PREFIX + '4freeEv'
        fixture(self.reference, imports=(override,))
        fixture(self.actual, prefix=True, definitions=(override,))
        inherited, dependencies = metaclass.framework_imports(self.actual, self.reference)
        self.assertEqual(dependencies, {override})
        self.assertNotIn(override, inherited)

    def test_unimplemented_project_virtual_cannot_become_framework(self):
        override = metaclass.CLASS_PREFIX + '4freeEv'
        fixture(self.reference, imports=(override,))
        fixture(self.actual, prefix=True, imports=(override,))
        with self.assertRaisesRegex(ValueError, 'unimplemented project dependency'):
            metaclass.framework_imports(self.actual, self.reference)

    def test_const_protocol_dependency_requires_actual_definition(self):
        dependency = '__ZNK18S540NvidiaGspPower6Detail8Protocol5readyEv'
        fixture(self.reference, imports=(dependency,))
        fixture(self.actual, prefix=True, imports=(dependency,))
        with self.assertRaisesRegex(ValueError, 'unimplemented project dependency'):
            metaclass.framework_imports(self.actual, self.reference)
        fixture(self.actual, prefix=True, definitions=(dependency,))
        inherited, dependencies = metaclass.framework_imports(self.actual, self.reference)
        self.assertIn(dependency, dependencies)
        self.assertNotIn(dependency, inherited)

    def test_non_sdk_reference_dependencies_cannot_become_framework(self):
        for dependency in ('_s540UnimplementedCBridge',
                           '__ZN16S540PrivateOther4workEv',
                           '__ZN20UnreviewedSdkService5startEv'):
            with self.subTest(dependency=dependency):
                fixture(self.reference, imports=(dependency,))
                fixture(self.actual, prefix=True, imports=(dependency,))
                with self.assertRaises(ValueError):
                    metaclass.framework_imports(self.actual, self.reference)

    def test_project_definition_cannot_replace_sdk_method(self):
        sdk_method = '__ZN9IOService5startEPS_'
        fixture(self.reference, imports=(sdk_method,))
        fixture(self.actual, prefix=True, definitions=(sdk_method,))
        with self.assertRaisesRegex(ValueError, 'replace an inherited framework operation'):
            metaclass.framework_imports(self.actual, self.reference)

    def test_extra_actual_import_is_never_added_to_sdk_approval(self):
        extra = '_s540UnexpectedKernelCall'
        fixture(self.actual, prefix=True, imports=(extra,))
        inherited, dependencies = metaclass.framework_imports(self.actual, self.reference)
        self.assertNotIn(extra, inherited | dependencies)

    def test_framework_import_derivation_still_requires_exact_loader_code(self):
        fixture(self.actual, prefix=True, instruction=0x56)
        with self.assertRaisesRegex(ValueError, 'differs from the exact SDK'):
            metaclass.framework_imports(self.actual, self.reference)


if __name__ == '__main__':
    unittest.main()
