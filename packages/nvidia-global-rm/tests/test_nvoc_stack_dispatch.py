"""Finite NVOC targets require actual member typing, never name similarity."""
from pathlib import Path
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'builders'))
import nvidia_nvoc_stack_dispatch as nvoc


HEADER = '''struct Device;
typedef int (*Handler)(struct Device *, int);
struct Device { void *base; int (*__dispatch__)(struct Device *, int); };
extern int target(struct Device *, int);
static inline int stub(struct Device *p, int n) { return n; }
#define dispatch_FNPTR(p) p->__dispatch__
static inline int dispatch(struct Device *p, int n) {
    return p->__dispatch__(p, n);
}
'''
GENERATED = '''#include "device.h"
void init(struct Device *pThis, int choose) {
 if (choose) {
  pThis->__dispatch__ = &stub;
 } else {
  pThis->__dispatch__ = &target;
 }
}
'''


def ir_body(extra='', field_index=1, receiver='%object'):
    # Deliberately unrelated SSA names. A plausible member-name SSA spelling
    # must not be accepted in place of tracing the actual load and typed GEP.
    return ('define i32 @entry(ptr %object) {\n'
            '  %slot = getelementptr inbounds %struct.Device, ptr ' + receiver +
            ', i64 0, i32 ' + str(field_index) + ', !dbg !12\n'
            '  %actual = load ptr, ptr %slot, align 8\n'
            '  %result = call i32 %actual(ptr %object, i32 4)\n' + extra +
            '  ret i32 %result\n}\n')


class NvocStackDispatch(unittest.TestCase):
    def source_tree(self, directory):
        root = Path(directory)
        header, generated = root / 'device.h', root / 'g_device_nvoc.c'
        header.write_text(HEADER)
        generated.write_text(GENERATED)
        return root, header, generated

    def test_only_exact_generated_member_assignments_form_the_target_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root, header, generated = self.source_tree(directory)
            record = nvoc.catalog(root, header, generated, '__dispatch__')
            self.assertEqual(record['targets'], ['stub', 'target'])
            self.assertEqual(record['source_inventory_file_count'], 2)
            self.assertEqual(len(record['references']), 5)

    def test_any_external_write_or_pointer_escape_is_rejected(self):
        for line in ('p->__dispatch__ = &target;', 'save(&p->__dispatch__);',
                     'p->__dispatch__ = unknown();', 'memcpy(&p->__dispatch__, q, 8);'):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as directory:
                root, header, generated = self.source_tree(directory)
                (root / 'other.c').write_text('void other(void) { ' + line + ' }\n')
                with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                    nvoc.catalog(root, header, generated, '__dispatch__')

    def test_nonconstant_generated_assignment_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, header, generated = self.source_tree(directory)
            generated.write_text(GENERATED.replace('&target;', 'get_target();'))
            with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                nvoc.catalog(root, header, generated, '__dispatch__')

    def test_new_source_changes_inventory_even_without_current_field_uses(self):
        with tempfile.TemporaryDirectory() as directory:
            root, header, generated = self.source_tree(directory)
            before = nvoc.catalog(root, header, generated, '__dispatch__')
            (root / 'another.c').write_text('void unrelated(void) {}\n')
            after = nvoc.catalog(root, header, generated, '__dispatch__')
            self.assertNotEqual(before['source_inventory_sha256'], after['source_inventory_sha256'])

    def test_callee_is_traced_to_constant_typed_gep(self):
        record = nvoc.indirect_gep(ir_body(), 'entry')
        self.assertEqual(record, {'llvm_struct': 'Device', 'llvm_member_index': 1,
                                  'receiver': '%object'})

    def test_misleading_member_ssa_name_does_not_override_actual_gep(self):
        text = ir_body(field_index=7).replace('%actual', '%__dispatch__')
        self.assertEqual(nvoc.indirect_gep(text, 'entry')['llvm_member_index'], 7)

    def test_typed_member_gep_accepts_canonical_llvm_no_wrap_flags(self):
        for flags in ('', 'inbounds', 'nuw', 'nusw', 'inbounds nuw', 'nusw nuw'):
            with self.subTest(flags=flags):
                text = ir_body().replace('getelementptr inbounds ',
                    'getelementptr ' + (flags + ' ' if flags else ''))
                self.assertEqual(nvoc.indirect_gep(text, 'entry')['llvm_member_index'], 1)

    def test_no_wrap_flags_cannot_justify_byte_offsets_or_dynamic_members(self):
        for replacement in ('getelementptr inbounds nuw i8, ptr %object, i64 8',
                            'getelementptr inbounds nuw %struct.Device, ptr %object, i64 0, i32 %index',
                            'getelementptr unknown %struct.Device, ptr %object, i64 0, i32 1'):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                nvoc.indirect_gep(ir_body().replace(
                    'getelementptr inbounds %struct.Device, ptr %object, i64 0, i32 1',
                    replacement), 'entry')

    def test_byte_address_description_does_not_assign_a_struct_type(self):
        body = ir_body().replace('getelementptr inbounds %struct.Device, ptr %object, i64 0, i32 1',
                                 'getelementptr inbounds i8, ptr %object, i64 8')
        value = nvoc.member_address(body, '%slot')
        self.assertEqual(value['byte_offset'], 8)
        self.assertNotIn('llvm_struct', value)
        self.assertEqual(value['c_member_identity'], 'requires-independent-typed-source-proof')

    def test_multiple_indirect_calls_cannot_be_matched_by_machine_order(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            nvoc.indirect_gep(ir_body('  %other = call i32 %actual(ptr %object, i32 8)\n'), 'entry')

    def test_phi_and_dynamic_index_do_not_get_a_guessed_member(self):
        for old, new in (('load ptr, ptr %slot', 'load ptr, ptr %phi'),
                         ('i32 1, !dbg', 'i32 %index, !dbg')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                nvoc.indirect_gep(ir_body().replace(old, new), 'entry')

    def test_inline_assembly_requires_separate_control_flow_review(self):
        with self.assertRaisesRegex(ValueError, 'assembly'):
            nvoc.indirect_gep(ir_body('  call void asm sideeffect "", ""()\n'), 'entry')

    def test_original_source_spelling_is_preserved_for_file_assertions(self):
        unit = {'command': ['clang', '-O2', '-c', 'src/input.c', '-o', '/tmp/input.o', '-fstack-usage'],
                'source': '/tree/src/input.c', 'cwd': '/tree'}
        command = nvoc._command(unit, Path(unit['source']), Path('/tmp/named.o'), named=True)
        self.assertIn('src/input.c', command)
        self.assertNotIn('/tree/src/input.c', command)
        self.assertNotIn('/tmp/input.o', command)

    def test_probe_has_exact_compatible_type_assertion_for_every_candidate(self):
        source = nvoc.probe_source('gpu/device.h', 'Device', '__dispatch__', ['stub', 'target'])
        self.assertEqual(source.count('_Static_assert('), 2)
        self.assertIn('__builtin_offsetof(struct Device, __dispatch__)', source)
        with self.assertRaises(ValueError):
            nvoc.probe_source('bad".h', 'Device', '__dispatch__', ['target'])


class ActualMachOProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = os.environ.get('S540_STACK_TEST_CLANG') or shutil.which('clang')
        if not cls.compiler:
            raise unittest.SkipTest('Actual Clang required for typed Mach-O probe controls.')

    def compile(self, root, targets, *, wrong_signature=False):
        (root / 'device.h').write_text(HEADER.replace('extern int target(struct Device *, int);',
            'extern void target(struct Device *);') if wrong_signature else HEADER)
        source, obj = root / 'probe.c', root / 'probe.o'
        source.write_text(nvoc.probe_source('device.h', 'Device', '__dispatch__', targets))
        command = [self.compiler, '-target', 'x86_64-apple-macos15', '-O2',
                   '-ffreestanding', '-fno-pic', '-fno-stack-protector', '-std=gnu11',
                   '-Werror=incompatible-function-pointer-types', '-c', str(source), '-o', str(obj)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=60)
        return result, obj

    def test_actual_compiler_abi_and_exact_local_external_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, obj = self.compile(root, ['stub', 'target'])
            self.assertEqual(result.returncode, 0, result.stderr)
            record = nvoc.probe_object(obj, ['stub', 'target'])
            self.assertEqual(record['field_offset_bytes'], 8)
            self.assertEqual(record['compiled_target_symbols'], ['_stub', '_target'])
            with self.assertRaisesRegex(ValueError, 'targets differ'):
                nvoc.probe_object(obj, ['stub', 'some_same_signature_function'])
            with self.assertRaisesRegex(ValueError, 'targets differ'):
                nvoc.probe_object(obj, ['stub', 'target'], namespace='ns_')

    def test_extra_pointer_cannot_hide_after_expected_target_array(self):
        with tempfile.TemporaryDirectory() as directory:
            result, obj = self.compile(Path(directory), ['stub', 'target', 'stub'])
            self.assertEqual(result.returncode, 0, result.stderr)
            with self.assertRaisesRegex(ValueError, 'extra or missing'):
                nvoc.probe_object(obj, ['stub', 'target'])

    def test_signature_mismatch_is_an_actual_compiler_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _ = self.compile(Path(directory), ['stub', 'target'], wrong_signature=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('NVOC candidate type', result.stderr)

    def test_relative_output_survives_actual_compilation_from_source_cwd(self):
        evidence = os.environ.get('S540_NVOC_TEST_EVIDENCE_DIR')
        evidence = Path(evidence).resolve() if evidence else None
        decoder = None
        if sys.platform != 'darwin':
            objdump = (os.environ.get('S540_STACK_TEST_OBJDUMP') or
                       shutil.which('llvm-objdump') or shutil.which('llvm-objdump-18'))
            if not objdump:
                self.skipTest('Actual Mach-O disassembler required for the complete path control.')
            decoder = [objdump, '--macho', '--disassemble', '--no-show-raw-insn',
                       '--no-symbolic-operands']
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'source'
            root.mkdir()
            _, header, generated = NvocStackDispatch().source_tree(root)
            source, obj = root / 'entry.c', base / 'entry.o'
            source.write_text('#include "device.h"\n'
                              'int entry(struct Device *p, int n) { return dispatch(p, n) + 1; }\n')
            command = [self.compiler, '-target', 'x86_64-apple-macos15', '-O2',
                       '-ffreestanding', '-fno-pic', '-fno-stack-protector', '-std=gnu11',
                       '-I', str(root), '-fstack-usage', '-c', 'entry.c', '-o', str(obj)]
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            capture = nvoc.stack.capture_usage(source, obj, command, cwd=root)
            previous = Path.cwd()
            try:
                os.chdir(base)
                result = nvoc.prove(capture, root, owner='Device', field='__dispatch__',
                    header=header, generated=generated, include='device.h', function='entry',
                    output=Path('proof'), decoder=decoder)
            finally:
                os.chdir(previous)
                if evidence:
                    evidence.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(root, evidence / 'source', dirs_exist_ok=True)
                    if (base / 'proof').is_dir():
                        shutil.copytree(base / 'proof', evidence / 'proof', dirs_exist_ok=True)
                    for measured in base.glob('entry.*'):
                        shutil.copy2(measured, evidence / measured.name)
            self.assertEqual(Path(result['path']).parent, base / 'proof')
            self.assertTrue((base / 'proof/original-with-names.o').is_file())
            self.assertFalse((root / 'proof').exists())

    def test_lowered_byte_gep_requires_actual_ast_and_matching_compiler_provenance(self):
        """Exercise the Apple lowering with real source AST/IR/object evidence.

        Clang 18 on this control host retains struct GEPs. Only LLVM text is
        synthetically lowered below; object bytes, frontend AST and debug
        locations come from the actual compiler. Native Apple runs also cover
        the unmodified byte form in the relative-output control above.
        """
        decoder = None
        if sys.platform != 'darwin':
            objdump = (os.environ.get('S540_STACK_TEST_OBJDUMP') or
                       shutil.which('llvm-objdump') or shutil.which('llvm-objdump-18'))
            if not objdump:
                self.skipTest('Actual Mach-O disassembler required.')
            decoder = [objdump, '--macho', '--disassemble', '--no-show-raw-insn', '--no-symbolic-operands']
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            root = base / 'source'
            root.mkdir()
            _, header, generated = NvocStackDispatch().source_tree(root)
            source, obj = root / 'entry.c', root / 'entry.o'
            source.write_text('#include "device.h"\n'
                              'int entry(struct Device *p, int n) { return dispatch(p, n) + 1; }\n')
            command = [self.compiler, '-target', 'x86_64-apple-macos15', '-O2',
                       '-ffreestanding', '-fno-pic', '-fno-stack-protector', '-std=gnu11',
                       '-I', str(root), '-fstack-usage', '-c', 'entry.c', '-o', str(obj)]
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            capture = nvoc.stack.capture_usage(source, obj, command, cwd=root)
            actual_run = subprocess.run

            def lowered_run(argv, **kwargs):
                result = actual_run(argv, **kwargs)
                if not result.returncode and '-emit-llvm' in argv:
                    destination = Path(argv[argv.index('-o') + 1])
                    text = destination.read_text()
                    text = re.sub(r'getelementptr inbounds %struct.Device, ptr (%[-A-Za-z$._0-9]+), i64 0, i32 1',
                                  r'getelementptr inbounds i8, ptr \1, i64 8', text)
                    destination.write_text(text)
                return result

            with mock.patch.object(nvoc.subprocess, 'run', side_effect=lowered_run):
                result = nvoc.prove(capture, root, owner='Device', field='__dispatch__',
                    header=header, generated=generated, include='device.h', function='entry',
                    output=base / 'proof', decoder=decoder)
            record = json.loads(Path(result['path']).read_text())
            self.assertEqual(record['compiler_gep']['address_form'], 'untyped-byte-gep')
            self.assertTrue(record['lowered_member_typed_source']['ast']['same_translation_unit_field_identity'])
            self.assertFalse(record['aggregate_stack_proven'])
            original = (base / 'proof/original.ll').read_text()
            body, slot, load, call = nvoc._indirect_load(original, 'entry')
            document = json.loads((base / 'proof/original.ast.json').read_text())
            binding = record['lowered_member_typed_source']['ast']

            def bind(doc):
                return nvoc.typed_ast.member_binding(doc, owner='Device', field='__dispatch__',
                    wrapper='dispatch', header=header, dispatch_line=8)

            bad = copy.deepcopy(document)
            owner = next(node for node in bad['inner'] if node.get('name') == 'Device' and node.get('completeDefinition'))
            member = next(node for node in owner['inner'] if node.get('name') == '__dispatch__')
            member['id'] += '-different-declaration'
            with self.assertRaisesRegex(ValueError, 'FieldDecl'):
                bind(bad)
            bad = copy.deepcopy(document)
            bad['inner'].append(copy.deepcopy(owner))
            with self.assertRaisesRegex(ValueError, 'unambiguous owner'):
                bind(bad)
            bad = copy.deepcopy(document)
            wrapper = next(node for node in bad['inner'] if node.get('name') == 'dispatch')
            wrapper['storageClass'] = 'extern'
            with self.assertRaisesRegex(ValueError, 'static inline'):
                bind(bad)

            def debug(text=original, load_text=load, call_text=call, source_path=source):
                return nvoc.typed_ast.debug_member_binding(text, function='entry', load=load_text,
                    call=call_text, header=header, source=source_path, cwd=root, binding=binding)

            self.assertEqual(debug()['ast']['field_type'], binding['field_type'])
            with self.assertRaisesRegex(ValueError, 'debug location'):
                debug(load_text=re.sub(r', !dbg !\d+', '', load))
            with self.assertRaisesRegex(ValueError, 'actual AST'):
                debug(original.replace('line: 8, column: 15', 'line: 8, column: 14'))
            with self.assertRaisesRegex(ValueError, 'measured root'):
                debug(source_path=root / 'different.c')
            with self.assertRaisesRegex(ValueError, 'actual AST'):
                debug(call_text=load)
            # A matching numeric byte offset never substitutes for missing
            # compiler provenance, even with genuine typed candidate pointers.
            with mock.patch.object(nvoc.subprocess, 'run', side_effect=lowered_run), \
                    mock.patch.object(nvoc.typed_ast, 'member_binding', side_effect=ValueError('unproved source type')):
                with self.assertRaisesRegex(ValueError, 'unproved source type'):
                    nvoc.prove(capture, root, owner='Device', field='__dispatch__',
                        header=header, generated=generated, include='device.h', function='entry',
                        output=base / 'refused-proof', decoder=decoder)


if __name__ == '__main__':
    unittest.main()
