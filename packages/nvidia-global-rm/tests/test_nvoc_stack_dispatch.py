"""Finite NVOC targets require actual member typing, never name similarity."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
