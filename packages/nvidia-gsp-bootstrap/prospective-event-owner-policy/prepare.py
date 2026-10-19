#!/usr/bin/env python3
"""Isolated RC participation successor; does not grant arbitrary event owners.

The immutable RC descriptor names the real original wrapper. Its callback data
is the transaction's exact nv, not a fabricated TMR_EVENT or NVOC object. The
actual timer service supplies every stage/arm observation.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / 'builders/check_nvidia_execution.py').is_file())
PARENT = HERE.parent / 'prospective-first-transaction'
PARENT_FREEZE = '7084ff0cf9c795a3f1dc5f4cc24fb53652b46462c336978e33d072bc4fcb2366'

def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Changed source boundary: ' + old[:100])
    return source.replace(old, new, 1)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def record_overlay(source):
    source = once(source, 'static Entry work[CAPACITY], direct[CAPACITY];',
        'static Entry work[CAPACITY], direct[CAPACITY];\nstatic NvU64 rcLastArm;')
    source = once(source, 'NvBool isDirect,NvU64 *out) {',
        'NvBool isDirect,NvBool isRc,NvU64 *out) {')
    source = once(source, '''    if(isDirect){
        e=eventIndex(data,eventId);''', '''    if(isRc){
        NvUPtr callback=0;
        if(!isDirect || data!=nv || eventId || !arm)return refuse(NV_ERR_INVALID_STATE,SITE_DIRECT);
        status=s540FirstTxnInspectOriginalRc(nv,&callback);
        if(status!=NV_OK)return refuse(status,SITE_DIRECT);
        d=descriptor(S540_FIRST_DESC_RC,callback,0,0);
        if(d<0)return refuse(NV_ERR_NOT_SUPPORTED,SITE_DIRECT);
    }else if(isDirect){
        e=eventIndex(data,eventId);''')
    source = once(source,
        '    if(isDirect && arm<=LD(&events[e].lastArm)){unlockGate();return refuse(NV_ERR_INVALID_STATE,SITE_DIRECT);}',
        '    if(isDirect && arm<=(isRc?LD(&rcLastArm):LD(&events[e].lastArm))){unlockGate();return refuse(NV_ERR_INVALID_STATE,SITE_DIRECT);}')
    source = once(source, '    if(isDirect)ST(&events[e].lastArm,arm);',
        '    if(isRc)ST(&rcLastArm,arm);else if(isDirect)ST(&events[e].lastArm,arm);')
    source = once(source, 'return admit(nv,q,data,0,0,NV_FALSE,out);',
        'return admit(nv,q,data,0,0,NV_FALSE,NV_FALSE,out);')
    source = once(source, 'return admit(nv,t,event,eventId,arm,NV_TRUE,out);',
        'return admit(nv,t,event,eventId,arm,NV_TRUE,NV_FALSE,out);')
    source = once(source, 'NV_STATUS s540FirstTxnWorkRejected(',
        'NV_STATUS s540FirstTxnRcAdmit(const void *nv,const void *t,NvU64 arm,NvU64 *out){return admit(nv,t,nv,0,arm,NV_TRUE,NV_TRUE,out);}\nNV_STATUS s540FirstTxnWorkRejected(')
    source = once(source, '''    if(timer){
        e=eventIndex(data,entries[i].eventId);status=authenticateEvent(e);''', '''    if(timer && s540FirstTxnOriginalDescriptors[entries[i].descriptor].role==S540_FIRST_DESC_RC){
        NvUPtr callback=0;
        status=data==nv&&!entries[i].eventId?s540FirstTxnInspectOriginalRc(nv,&callback):NV_ERR_INVALID_STATE;
        if(status==NV_OK && descriptor(S540_FIRST_DESC_RC,callback,0,0)!=(NvS32)entries[i].descriptor)status=NV_ERR_INVALID_STATE;
    }else if(timer){
        e=eventIndex(data,entries[i].eventId);status=authenticateEvent(e);''')
    return source

def header_overlay(source):
    source = once(source, 'S540_FIRST_DESC_OWNER=3 };', 'S540_FIRST_DESC_OWNER=3, S540_FIRST_DESC_RC=4 };')
    return once(source, 'NV_STATUS s540FirstTxnInspectOriginalWork(',
        'NV_STATUS s540FirstTxnRcAdmit(const void *, const void *, NvU64 arm, NvU64 *);\n'
        'NV_STATUS s540FirstTxnInspectOriginalRc(const void *, NvUPtr *);\nNV_STATUS s540FirstTxnInspectOriginalWork(')

def original_policy_overlay(source):
    """Apply only to the frozen parent's actual osapi.c, never to upstream."""
    return once(source, 'const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[] = {',
        'const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[] = {\n'
        '    { S540_FIRST_DESC_RC, S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,\n'
        '      0, 0, (NvUPtr)&rm_run_rc_callback, 0, NV_FALSE },')

RC_ORIGINAL = '''/* SPDX-License-Identifier: MIT */
/* The record authenticates the exact nv and actual service stage. This typed
 * probe supplies the original wrapper address, not caller-selected policy. */
#include "nv.h"
#include "S540NvidiaGspFirstTransaction.h"
NV_STATUS s540FirstTxnInspectOriginalRc(const void *nv, NvUPtr *out)
{
    if (!nv || !out) return NV_ERR_INVALID_ARGUMENT;
    *out = (NvUPtr)&rm_run_rc_callback;
    return NV_OK;
}
'''

def timers_overlay(source):
    source = once(source, 'NvU64 transactionGeneration, rcArmGeneration, rcArmLease, rcRunningLease;',
        'NvU64 transactionGeneration, rcArmGeneration, rcRunningArmGeneration, rcArmLease, rcRunningLease;')
    source = once(source, 'static void rc_callback(void *context) {', '''static NV_STATUS rc_arm_locked(S540GspDeviceTimers *device) {
    NV_STATUS status;
    if (!device->transactionGeneration) return s540DarwinTimerArm(device->rc, 1000000000ULL);
    if (device->rcArmLease || device->rcArmGeneration == ~(NvU64)0) return NV_ERR_IN_USE;
    ++device->rcArmGeneration;
    (void)timerContextStage(device->rc, S540_FIRST_SERVICE_ADMIT, device->nv, device->rcArmGeneration);
    status = s540FirstTxnRcAdmit(device->nv, device->rc, device->rcArmGeneration, &device->rcArmLease);
    if (status == NV_OK) status = s540DarwinTimerArm(device->rc, 1000000000ULL);
    if (status != NV_OK) {
        device->quarantined = NV_TRUE;
        if (device->rcArmLease) (void)s540FirstTxnDirectRetain(device->nv, device->rc, device->rcArmLease, status);
    }
    (void)timerContextStage(device->rc, 0, NULL, 0);
    return status;
}
/* Only a successful synchronous backend cancel can retire a pending RC arm.
 * The fixed caller holds the actual service guard and is the transaction owner. */
static NV_STATUS rc_cancelled_locked(S540GspDeviceTimers *device) {
    NV_STATUS status = NV_OK;
    if (!device->transactionGeneration) return NV_OK;
    (void)timerContextStage(device->rc, S540_FIRST_SERVICE_CANCELLED, device->nv, device->rcArmGeneration);
    if (device->rcArmLease) {
        status = s540FirstTxnDirectCancelled(device->nv, device->rc, device->rcArmLease);
        if (status == NV_OK) device->rcArmLease = 0;
    }
    if (status == NV_OK && device->rcRunningLease) status = NV_ERR_IN_USE;
    (void)timerContextStage(device->rc, 0, NULL, 0);
    if (status != NV_OK) device->quarantined = NV_TRUE;
    return status;
}
static void rc_callback(void *context) {''')
    source = once(source, '''    NvBool enabled = !device->stopping && !device->rcStopping && __atomic_load_n(&device->nv->rc_timer_enabled, __ATOMIC_ACQUIRE);
    s540Darwin_os_release_spinlock(device->guard, token);
    if (!enabled) return;''', '''    NvBool enabled = !device->stopping && !device->rcStopping && __atomic_load_n(&device->nv->rc_timer_enabled, __ATOMIC_ACQUIRE);
    status = NV_OK;
    if (enabled && device->transactionGeneration) {
        if (!device->rcArmLease || device->rcRunningLease) status = NV_ERR_INVALID_STATE;
        else {
            device->rcRunningLease = device->rcArmLease; device->rcArmLease = 0;
            device->rcRunningArmGeneration = device->rcArmGeneration;
            (void)timerContextStage(device->rc, S540_FIRST_SERVICE_ENTER, device->nv, device->rcRunningArmGeneration);
            status = s540FirstTxnDirectEnter(device->nv, device->rc, device->rcRunningLease);
            if (status != NV_OK) (void)s540FirstTxnDirectRetain(device->nv, device->rc, device->rcRunningLease, status);
            (void)timerContextStage(device->rc, 0, NULL, 0);
        }
        if (status != NV_OK) device->quarantined = NV_TRUE;
    }
    s540Darwin_os_release_spinlock(device->guard, token);
    if (!enabled || status != NV_OK) return;''')
    source = once(source, '''    status = rm_run_rc_callback(lease.stack, device->nv);
    s540GlobalRmHostFree(lease.allocation);''', '''    status = rm_run_rc_callback(lease.stack, device->nv);
    if (device->transactionGeneration) {
        NV_STATUS returned = s540FirstTxnDirectOriginalReturned(device->nv, status);
        if (status == NV_OK) status = returned;
    }
    s540GlobalRmHostFree(lease.allocation);''')
    # The callback's stack allocation can fail AFTER real participant entry.
    # Retain that participant; an uncalled original wrapper has not returned.
    old='    if (!allocate_stack(&lease)) { __atomic_fetch_add(&device->callbackFailures, 1U, __ATOMIC_RELAXED); reject(device); return; }'
    if source.count(old) != 2: raise ValueError('Unexpected callback allocation boundary')
    source = source.replace(old, '''    if (!allocate_stack(&lease)) {
        if (device->transactionGeneration) {
            token = s540Darwin_os_acquire_spinlock(device->guard);
            (void)timerContextStage(device->rc, S540_FIRST_SERVICE_ENTER, device->nv, device->rcRunningArmGeneration);
            (void)s540FirstTxnDirectRetain(device->nv, device->rc, device->rcRunningLease, NV_ERR_NO_MEMORY);
            (void)timerContextStage(device->rc, 0, NULL, 0);
            device->quarantined = NV_TRUE;
            s540Darwin_os_release_spinlock(device->guard, token);
        }
        __atomic_fetch_add(&device->callbackFailures, 1U, __ATOMIC_RELAXED); reject(device); return;
    }''', 1)
    source = once(source, 'if (s540DarwinTimerArm(device->rc, 1000000000ULL) != NV_OK)',
        'if (rc_arm_locked(device) != NV_OK)')
    source = once(source, '''    if (device->transactionGeneration) {
        device->quarantined = NV_TRUE;
        s540Darwin_os_release_spinlock(device->guard, token); reject(device); return -1;
    }
    if (device->stopping || device->rcStopping''',
        '    if (device->stopping || device->rcStopping')
    source = once(source, '    status = s540DarwinTimerArm(device->rc, 1000000000ULL);',
        '    status = rc_arm_locked(device);')
    source = once(source, '''    if (status == NV_OK) {
        // The unmodified RM callback reads''', '''    if (status == NV_OK) status = rc_cancelled_locked(device);
    if (status == NV_OK) {
        // The unmodified RM callback reads''')
    source = once(source, '''        if (result == NV_OK) __atomic_store_n(&nv->rc_timer_enabled, 0U, __ATOMIC_RELEASE);''', '''        if (result == NV_OK) {
            token = s540Darwin_os_acquire_spinlock(device->guard);
            result = rc_cancelled_locked(device);
            if (result == NV_OK) __atomic_store_n(&nv->rc_timer_enabled, 0U, __ATOMIC_RELEASE);
            s540Darwin_os_release_spinlock(device->guard, token);
        }''')
    source = once(source, '''    device->transactionGeneration = generation;
    s540Darwin_os_release_spinlock(device->guard, token); return NV_OK;''', '''    if (!timerStageSlot(device->rc, NV_TRUE, generation)) {
        device->quarantined = NV_TRUE;
        s540Darwin_os_release_spinlock(device->guard, token); return NV_ERR_INSUFFICIENT_RESOURCES;
    }
    device->transactionGeneration = generation;
    s540Darwin_os_release_spinlock(device->guard, token); return NV_OK;''')
    source = once(source, '''    for (item = device->nano; item && item->timer != timer; item = item->next) {}
    if (item && item->runningLease) {''', '''    if (timer == device->rc && device->rcRunningLease) {
        (void)timerContextStage(timer, S540_FIRST_SERVICE_RETURNED, device->nv, device->rcRunningArmGeneration);
        status = s540FirstTxnDirectReturned(device->nv, timer, device->rcRunningLease);
        if (status == NV_OK) device->rcRunningLease = 0;
        else device->quarantined = NV_TRUE;
        (void)timerContextStage(timer, 0, NULL, 0);
    }
    for (item = device->nano; item && item->timer != timer; item = item->next) {}
    if (item && item->runningLease) {''')
    return source

def prepare(output):
    output = Path(output).resolve()
    if output.is_relative_to(REPO) and not output.is_relative_to(REPO / 'build'):
        raise ValueError('Repository output must be under build/')
    if output.exists() and any(output.iterdir()): raise ValueError('Fresh output required')
    freeze=PARENT/'FROZEN-SHA256.json'
    if hashlib.sha256(freeze.read_bytes()).hexdigest()!=PARENT_FREEZE:
        raise ValueError('Frozen parent inventory changed')
    manifest=json.loads(freeze.read_text())
    observed={p.relative_to(PARENT).as_posix() for p in PARENT.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.name!='FROZEN-SHA256.json'}
    if observed!=set(manifest['files']):raise ValueError('Frozen parent file set changed')
    for name,expected in manifest['files'].items():
        path=PARENT/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Frozen parent input changed before import: '+name)
    for name,expected in manifest['project_dependencies'].items():
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Frozen parent dependency changed: '+name)
    top = load('rc_parent_check', PARENT / 'check_first_transaction.py')
    top.verify_freeze(PARENT, 'FROZEN-SHA256.json')
    top.verify_freeze(PARENT.parent/'prospective-host-retention', 'FROZEN-SHA256.json')
    sys.path.insert(0, str(PARENT / 'services'))
    import prepare_timers
    output.mkdir(parents=True, exist_ok=True)
    prepare_timers.prepare(output)
    files = {
        'S540NvidiaGspFirstTransaction.c': record_overlay((PARENT/'record/S540NvidiaGspFirstTransaction.c').read_text()),
        'S540NvidiaGspFirstTransaction.h': header_overlay((PARENT/'record/S540NvidiaGspFirstTransaction.h').read_text()),
        'S540NvidiaGspTimersOriginal.c': timers_overlay((output/'S540NvidiaGspTimersOriginal.c').read_text()),
        'S540NvidiaFirstTxnRcOriginal.c': RC_ORIGINAL,
    }
    for name, value in files.items(): (output/name).write_text(value)
    report = {'production_modified': False, 'hardware_admission': False,
        'event_owner_rows_added': 0,
        'original_descriptor_required': 'S540_FIRST_DESC_RC + actual &rm_run_rc_callback',
        'source_sha256': {name:hashlib.sha256(value.encode()).hexdigest() for name,value in files.items()}}
    (output/'RC-SOURCE-REPORT.json').write_text(json.dumps(report, indent=2)+'\n')
    return report

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(prepare(parser.parse_args().output),indent=2))
