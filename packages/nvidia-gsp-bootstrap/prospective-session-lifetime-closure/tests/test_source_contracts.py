#!/usr/bin/env python3
"""Admission and actual lifecycle ordering contracts for the isolated successor."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import prepare


class Contracts(unittest.TestCase):
    def setUp(self):
        self.values = {name: (ROOT/name).read_text() for name in prepare.INPUTS}
        self.changed = prepare.transforms(self.values)

    def test_gates_and_original_refusal_preserved(self):
        boot = self.changed[prepare.BOOT]
        self.assertIn('constexpr NvU32 kBlockedGates = OriginalAbiClosure | PowerLifetime |', boot)
        start = boot.index('    NV_STATUS initialize() {')
        end = boot.index('    NV_STATUS stop() {', start)
        self.assertEqual(boot[start:end], self.values[prepare.BOOT][
            self.values[prepare.BOOT].index('    NV_STATUS initialize() {'):
            self.values[prepare.BOOT].index('    NV_STATUS stop() {')])

    def test_real_session_acquisition_and_permanent_stop_guards(self):
        method = (HERE/'owner-lifetime.cpp.inc').read_text()
        self.assertLess(method.index('s540ReserveDiagnosticModulePin()'),
            method.index('beginRmHardwareDma(&transport)'))
        self.assertLess(method.index('beginRmHardwareDma(&transport)'),
            method.index('diagnosticLifetimeHeld = true'))
        self.assertNotIn('s540FirstTxnBeginOwner', method)
        boot = self.changed[prepare.BOOT]
        stop = boot[boot.index('    NV_STATUS stop() {'):]
        self.assertLess(stop.index('diagnosticLifetimeHeld || transport.hardwareDmaLifetimeHeld()'),
            stop.index('s540GspContextDisableAdapter(context)'))
        detach = boot[boot.index('    static NV_STATUS detach('):boot.index('    NV_STATUS failed(')]
        self.assertLess(detach.index('self->diagnosticLifetimeHeld'), detach.index('s540GspTimersUnbind'))

    def test_pm_producer_preserves_real_event_before_worker_post(self):
        boot = self.changed[prepare.BOOT]
        callback = boot[boot.index('    static NV_STATUS postRevocation('):boot.index('    static NV_STATUS action(')]
        self.assertNotIn('power.snapshot()', callback)
        self.assertLess(callback.index('power.revocationEventNs()'), callback.index('s540GspCancellationRevokeAt'))
        self.assertLess(callback.index('s540GspCancellationRevokeAt'), callback.index('dispatcher.post(PowerRevoked)'))
        event = (HERE/'power-event.cpp.inc').read_text()
        self.assertNotIn('exactDomain', event)
        self.assertNotIn('PMstop', event)
        self.assertNotIn('acknowledge', event)
        self.assertNotIn('IOLockLock', event)
        self.assertNotIn('lock_guard', event)

    def test_actual_loader_guards_before_destructive_transitions(self):
        loader = prepare.loader_transform((ROOT/prepare.LOADER).read_text())
        module = loader[loader.index('kern_return_t s540ProspectiveModuleStopBackend(void)'):]
        self.assertLess(module.index('s540GspDiagnosticLifetimePinCount()'), module.index('s540ProspectiveBeginStop'))
        stop = loader[loader.index('void S540ProspectiveLoaderControl::stop(IOService *provider)'):]
        self.assertLess(stop.index('s540GspDiagnosticLifetimePinCount()'), stop.index('s540ProspectiveServiceGone'))

    def test_transforms_reject_drift_and_replay(self):
        changed = dict(self.values)
        changed[prepare.BOOT] = changed[prepare.BOOT].replace('    NV_STATUS initialize() {', '    NV_STATUS otherInitialize() {')
        with self.assertRaises(ValueError):
            prepare.transforms(changed)
        with self.assertRaises(ValueError):
            prepare.transforms(self.changed)


if __name__ == '__main__':
    unittest.main()
