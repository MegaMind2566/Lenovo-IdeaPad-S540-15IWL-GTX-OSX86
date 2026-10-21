import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('allocator_prepare', HERE / 'prepare.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class SourceRefusalControls(unittest.TestCase):
    def test_new_alias_writer_does_not_reuse_reviewed_source_identity(self):
        values = {name: '' for name in module.ORIGINAL_INPUTS}
        values[module.MEMORY] = '/* new opaque writer */\nvoid mutate(void *p) { *(void **)p=0; }\n'
        with self.assertRaisesRegex(ValueError, 'writer inventory changed'):
            module.original_transforms(values)

    def test_wrong_input_set_and_existing_project_replacements_are_refused(self):
        with self.assertRaises(ValueError):
            module.original_transforms({module.CORE: ''})
        with self.assertRaises(ValueError):
            module.transforms({'unreviewed-project.c': ''})

    def test_planner_declares_only_real_changed_originals_and_one_guard_unit(self):
        self.assertEqual(module.INPUTS, ())
        self.assertEqual(module.transforms({}), {})
        self.assertEqual(len(module.PROJECT_UNITS), 1)
        self.assertEqual(len(module.EXPORTS[module.UNIT]), 10)
        self.assertEqual(set(module.COMPANIONS), {module.UNIT, module.DIRECTORY + '/S540NvidiaAllocatorEpoch.h'})


if __name__ == '__main__':
    unittest.main()
