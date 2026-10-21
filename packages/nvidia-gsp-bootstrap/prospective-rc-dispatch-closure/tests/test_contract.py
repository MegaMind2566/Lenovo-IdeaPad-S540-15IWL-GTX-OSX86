#!/usr/bin/env python3
"""Source provenance, ABI, overlap and refusal-boundary contracts."""
from pathlib import Path
import hashlib
import sys
import unittest
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE));import prepare
BASE=ROOT/'build/integrated-successor-5'
class Contract(unittest.TestCase):
    def setUp(self):
        self.original={name:(BASE/'source'/name).read_text() for name in prepare.ORIGINAL_INPUTS}
        self.project={name:(BASE/'project'/name).read_text() for name in prepare.INPUTS}
    def test_exact_complete_source_pins(self):
        for name,text in self.original.items():
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),prepare.PINNED_INPUTS[name])
        altered=dict(self.original);altered[prepare.TIMER]+='\n/* tamper */\n'
        with self.assertRaises(ValueError):prepare.original_transforms(altered)
        with self.assertRaises(ValueError):prepare.original_transforms({prepare.TIMER:self.original[prepare.TIMER]})
    def test_existing_generated_abi_is_preserved(self):
        self.assertNotIn('src/nvidia/generated/g_os_nvoc.h',prepare.ORIGINAL_INPUTS)
        generated=(BASE/'source/src/nvidia/generated/g_os_nvoc.h').read_text()
        self.assertTrue('NvBool    osRun1HzCallbacksNow(OBJGPU *pGpu);' in generated)
        self.assertTrue('void      osRunQueued1HzCallbacksUnderLock(OBJGPU *pGpu);' in generated)
        out=prepare.original_transforms(self.original)[prepare.TIMER]
        self.assertIn('NvBool osRun1HzCallbacksNow(OBJGPU *pGpu)',out)
        self.assertIn('void osRunQueued1HzCallbacksUnderLock(OBJGPU *pGpu)',out)
        self.assertEqual(set(prepare.EXPORTS),{prepare.TIMER})
    def test_ordered_bridge_overlap_is_exact(self):
        incoming=dict(self.project)
        incoming[prepare.IRQ]='/* earlier reviewed IRQ installation successor */\n'+incoming[prepare.IRQ]
        out=prepare.transforms(incoming)[prepare.IRQ]
        self.assertTrue(out.startswith('/* earlier reviewed IRQ installation successor */'))
        self.assertIn('status = s540Global_s540OsRunQueued1HzCallbacksUnderLockStatus(gpu);',out)
        altered=dict(self.project);altered[prepare.IRQ]+=altered[prepare.IRQ]
        with self.assertRaises(ValueError):prepare.transforms(altered)
        with self.assertRaises(ValueError):prepare.transforms({})
    def test_complete_parent_not_mutated(self):
        before={name:hashlib.sha256(text.encode()).hexdigest() for name,text in self.original.items()}
        prepare.original_transforms(self.original);prepare.transforms(self.project)
        for name,digest in before.items():
            self.assertEqual(hashlib.sha256((BASE/'source'/name).read_bytes()).hexdigest(),digest)
        self.assertEqual(prepare.PROJECT_UNITS,())
        self.assertEqual(prepare.COMPILE_DEFINITIONS,{})
    def test_real_wrapper_propagates_failure_after_runtime_exit(self):
        out=prepare.original_transforms(self.original)[prepare.OSAPI]
        section=out[out.index('NV_STATUS NV_API_CALL rm_run_rc_callback('):out.index('static void _tmrEventServiceTimerWorkItem')]
        self.assertLess(section.index('NV_ENTER_RM_RUNTIME'),section.index('status = s540Global_s540OsRun1HzCallbacksNowStatus'))
        self.assertLess(section.index('NV_EXIT_RM_RUNTIME'),section.index('return status;'))
        self.assertNotIn('return NV_OK;',section)
if __name__=='__main__':unittest.main()
