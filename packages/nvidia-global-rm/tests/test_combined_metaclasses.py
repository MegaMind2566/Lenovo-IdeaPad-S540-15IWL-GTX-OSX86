"""Actual Mach-O loader-table controls; SDK composition is checked in native CI."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'builders'))
import nvidia_combined_metaclasses as combined


class LoaderEntries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = os.environ.get('S540_STACK_TEST_CLANG') or shutil.which('clang') or shutil.which('clang-18')
        if not cls.cc:
            raise unittest.SkipTest('Actual Clang required.')

    def object(self, directory, name, assembly):
        source = directory/(name+'.s')
        obj = directory/(name+'.o')
        source.write_text(assembly)
        subprocess.run([self.cc, '-target', 'x86_64-apple-macos15', '-c', str(source),
                        '-o', str(obj)], check=True, capture_output=True)
        return obj

    def assembly(self):
        return '''.text
__GLOBAL__sub_I_power:
 callq _power_meta
 retq
__GLOBAL__sub_I_control:
 callq _control_meta
 retq
_power_meta:
 retq
_control_meta:
 retq
_power_term:
 retq
_control_term:
 retq
.section __DATA,__mod_init_func,mod_init_funcs
.p2align 3
.quad __GLOBAL__sub_I_power
.quad __GLOBAL__sub_I_control
.section __DATA,__mod_term_func,mod_term_funcs
.p2align 3
.quad _power_term
.quad _control_term
'''

    def test_distinct_real_tu_wrappers_and_complete_local_closures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.object(Path(tmp), 'combined', self.assembly())
            image = combined.metaclass.Object(path)
            with self.assertRaisesRegex(ValueError, 'collapse'):
                image.loader_graph()
            graphs = combined.entry_graphs(image)
            self.assertEqual(len(graphs), 4)
            self.assertEqual(set(graphs[0]['functions']), {'<translation-unit-initializer>', '_power_meta'})
            self.assertEqual(set(graphs[1]['functions']), {'<translation-unit-initializer>', '_control_meta'})
            self.assertTrue(all(g['entries'][0]['offset'] == 0 for g in graphs))

    def test_added_or_changed_actual_entry_cannot_disappear_in_multiset(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            base = self.object(directory, 'base', self.assembly())
            extra = self.object(directory, 'extra', self.assembly()+'.quad _power_term\n')
            changed = self.object(directory, 'changed', self.assembly().replace('callq _control_meta', 'callq _power_meta'))
            self.assertEqual(sum(combined.entry_inventory(base).values()), 4)
            self.assertEqual(sum(combined.entry_inventory(extra).values()), 5)
            self.assertNotEqual(combined.entry_inventory(base), combined.entry_inventory(extra))
            self.assertNotEqual(combined.entry_inventory(base), combined.entry_inventory(changed))

    def test_missing_pointer_relocation_and_unnamed_interior_are_refused(self):
        variants = [('.quad _power_term', '.quad 0'),
                    ('.quad _power_term', '.quad _power_term+1')]
        for index, (old, new) in enumerate(variants):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                path = self.object(Path(tmp), 'invalid', self.assembly().replace(old, new))
                with self.assertRaises(ValueError):
                    combined.entry_inventory(path)

    def test_alternate_loader_table_refused_even_when_other_entries_are_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.object(Path(tmp), 'alternate', self.assembly()+
                               '.section __DATA,__init_offsets,regular\n.long 0\n')
            with self.assertRaisesRegex(ValueError, 'alternate'):
                combined.entry_inventory(path)


if __name__ == '__main__':
    unittest.main()
