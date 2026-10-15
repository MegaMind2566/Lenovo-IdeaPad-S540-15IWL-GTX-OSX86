# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Provenance(unittest.TestCase):
    def test_reference_bytes(self):
        record = json.loads((ROOT / 'PROVENANCE.json').read_text())
        self.assertEqual(record['commit'], '1a82fbfda8f321b056eb3568850f9316c5e465c5')
        self.assertEqual(len(record['reference_files']), 4)
        for item in record['reference_files']:
            self.assertEqual(hashlib.sha256((ROOT / item['local']).read_bytes()).hexdigest(), item['sha256'])

    def test_full_original_abi_and_callbacks(self):
        source = (ROOT / 'S540NvidiaGspTimersOriginal.c').read_text()
        self.assertIn('#include "nv.h"', source)
        self.assertIn('rm_run_rc_callback(lease.stack, device->nv)', source)
        self.assertIn('rm_run_nano_timer_callback(lease.stack, device->nv, item->event)', source)
        self.assertNotIn('typedef struct nvidia_stack_s', source)
        self.assertNotIn('typedef struct nv_state_t', source)

    def test_real_heap_alternate_stack(self):
        source = (ROOT / 'S540NvidiaGspTimersOriginal.c').read_text()
        self.assertIn('s540GlobalRmHostAllocate(sizeof(nvidia_stack_t) + 15U)', source)
        self.assertIn('lease->stack->size = sizeof(lease->stack->stack)', source)
        self.assertIn('lease->stack->top = lease->stack->stack + lease->stack->size', source)
        self.assertIn('s540GlobalRmHostFree(lease.allocation)', source)

    def test_failed_cancellation_retains_ownership(self):
        source = (ROOT / 'S540NvidiaGspTimersOriginal.c').read_text()
        self.assertIn('device->quarantined = NV_TRUE', source)
        self.assertIn('if (device->quarantined)', source)
        self.assertIn('return NV_ERR_INVALID_STATE', source)
        self.assertIn('s540DarwinTimerCancel(item->timer)', source)

    def test_native_callback_fixtures_are_explicit(self):
        source = (ROOT / 'tests/check_gsp_timers_native.c').read_text()
        self.assertIn('callback_fixture', source)
        self.assertIn('never a GPU test', source)
        self.assertIn('((NvUPtr)stack % 16) == 0', source)


if __name__ == '__main__':
    unittest.main()
