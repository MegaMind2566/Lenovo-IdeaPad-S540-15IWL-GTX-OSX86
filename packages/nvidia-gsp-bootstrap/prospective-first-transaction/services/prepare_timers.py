#!/usr/bin/env python3
"""Exact isolated overlay of checked timer port + actual Darwin timer backend.

The return hook is deliberately in the real backend AFTER action(context)
returns. A status from within the original wrapper cannot forge that boundary.
"""
from pathlib import Path
import hashlib, json, difflib
from prepare_services import HERE, REPO, SERVICE, replace

import sys
sys.path.insert(0,str(REPO/'builders'))
import compile_nvidia_global_rm as original

def timer_overlay(source):
    source = replace(source, '#include "S540NvidiaGspTimers.h"',
        '#include "S540NvidiaGspTimers.h"\n#include "S540NvidiaGspFirstTransaction.h"\n'
        '#include "S540NvidiaFirstTxnServices.h"')
    source = replace(source, '    NvBool cancelling;\n};',
        '    NvBool cancelling, backendDestroyed;\n    NvU64 eventGeneration, armGeneration, runningArmGeneration, armLease, runningLease;\n};')
    source = replace(source, '    NvBool quarantined;\n};',
        '    NvBool quarantined;\n    NvBool stopCompleted;\n'
        '    NvU64 transactionGeneration, rcArmGeneration, rcArmLease, rcRunningLease;\n};')
    source = replace(source, 'static S540GspDeviceTimers *binding;', '''static S540GspDeviceTimers *binding;
typedef struct TimerStage {
    const void *identity;
    NvU64 sequence, thread, generation;
    NvU32 stage;
    const void *data;
} TimerStage;
/* Never recycle a slot in this one-transaction candidate. Old identity probes
 * read metadata only, never dereference a freed service timer or event. */
static TimerStage timerStages[257];
static TimerStage *timerStageSlot(const void *identity, NvBool create, NvU64 generation) {
    NvU32 index;
    for (index = 0; index != 257; ++index)
        if (__atomic_load_n(&timerStages[index].identity, __ATOMIC_ACQUIRE) == identity)
            return &timerStages[index];
    if (!create) return NULL;
    for (index = 0; index != 257; ++index) {
        if (!__atomic_load_n(&timerStages[index].identity, __ATOMIC_ACQUIRE)) {
            timerStages[index].generation = generation;
            __atomic_store_n(&timerStages[index].identity, identity, __ATOMIC_RELEASE);
            return &timerStages[index];
        }
    }
    return NULL;
}
static NV_STATUS timerContextStage(const void *identity, NvU32 stage, const void *data, NvU64 generation) {
    TimerStage *slot = timerStageSlot(identity, NV_FALSE, 0);
    NvU64 thread = 0;
    if (!slot || (stage && s540Darwin_os_get_current_thread(&thread) != NV_OK))
        return NV_ERR_INVALID_STATE;
    __atomic_fetch_add(&slot->sequence, 1ULL, __ATOMIC_ACQ_REL);
    __atomic_store_n(&slot->thread, thread, __ATOMIC_RELAXED);
    __atomic_store_n(&slot->data, data, __ATOMIC_RELAXED);
    __atomic_store_n(&slot->stage, stage, __ATOMIC_RELAXED);
    __atomic_store_n(&slot->generation, generation, __ATOMIC_RELAXED);
    __atomic_fetch_add(&slot->sequence, 1ULL, __ATOMIC_RELEASE);
    return NV_OK;
}
NV_STATUS s540FirstTxnServicesReadTimerContext(const void *identity, S540FirstTxnServiceContext *out) {
    TimerStage *slot;
    NvU64 sequence;
    S540FirstTxnServiceContext result = {0};
    if (!identity || !out) return NV_ERR_INVALID_ARGUMENT;
    slot = timerStageSlot(identity, NV_FALSE, 0);
    if (!slot) return NV_ERR_INVALID_STATE;
    sequence = __atomic_load_n(&slot->sequence, __ATOMIC_ACQUIRE);
    if (sequence & 1) return NV_ERR_IN_USE;
    result.stage = __atomic_load_n(&slot->stage, __ATOMIC_RELAXED);
    result.thread = __atomic_load_n(&slot->thread, __ATOMIC_RELAXED);
    result.data = __atomic_load_n(&slot->data, __ATOMIC_RELAXED);
    result.generation = __atomic_load_n(&slot->generation, __ATOMIC_RELAXED);
    if (!result.stage || !result.thread ||
        __atomic_load_n(&slot->sequence, __ATOMIC_ACQUIRE) != sequence)
        return NV_ERR_INVALID_STATE;
    *out = result; return NV_OK;
}''')
    # Direct admission before the real backend publication, under its actual
    # timer registry guard. Pending-arm replacement is deliberately refused.
    source = replace(source, '''    status = s540DarwinTimerArm(item->timer, delay);''', '''    status = NV_OK;
    if (device->transactionGeneration) {
        if (item->armLease || item->armGeneration == ~(NvU64)0) status = NV_ERR_IN_USE;
        else ++item->armGeneration;
        (void)timerContextStage(item->timer, S540_FIRST_SERVICE_ADMIT, item->event, item->armGeneration);
        if (status == NV_OK) status = s540FirstTxnDirectAdmit(nv, item->timer, item->event,
            item->eventGeneration, item->armGeneration, &item->armLease);
        if (status == NV_OK) status = s540DarwinTimerArm(item->timer, delay);
        if (status != NV_OK) {
            device->quarantined = NV_TRUE;
            (void)s540FirstTxnDirectRetain(nv, item->timer, item->armLease, status);
        }
        (void)timerContextStage(item->timer, 0, NULL, 0);
    } else status = s540DarwinTimerArm(item->timer, delay);''')
    # nano event construction publishes a durable identity even on refusal;
    # the output stays NULL, and the failed service is retained/quarantined.
    source = replace(source, '''    item->next = device->nano; device->nano = item; ++device->liveNano;
    *output = item;''', '''    status = NV_OK;
    if (device->transactionGeneration) {
        if (!timerStageSlot(item->timer, NV_TRUE, device->transactionGeneration)) status = NV_ERR_NO_MEMORY;
        else {
            (void)timerContextStage(item->timer, S540_FIRST_SERVICE_ADMIT, event, device->transactionGeneration);
            status = s540FirstTxnEventConstruct(nv, event, item->timer, &item->eventGeneration);
            (void)timerContextStage(item->timer, 0, NULL, 0);
        }
        if (status != NV_OK) device->quarantined = NV_TRUE;
    }
    item->next = device->nano; device->nano = item; ++device->liveNano;
    if (status == NV_OK) *output = item;''')
    # Genuine foreign callback enters only after its direct lease was admitted.
    source = replace(source, '''    NvBool allowed = !device->stopping && !item->deleting && !item->cancelling;
    s540Darwin_os_release_spinlock(device->guard, token);
    if (!allowed) return;''', '''    NvBool allowed = !device->stopping && !item->deleting && !item->cancelling;
    status = NV_OK;
    if (allowed && device->transactionGeneration) {
        item->runningLease = item->armLease; item->armLease = 0;
        item->runningArmGeneration = item->armGeneration;
        (void)timerContextStage(item->timer, S540_FIRST_SERVICE_ENTER, item->event, item->runningArmGeneration);
        status = s540FirstTxnDirectEnter(device->nv, item->timer, item->runningLease);
        if (status != NV_OK) {
            device->quarantined = NV_TRUE;
            (void)s540FirstTxnDirectRetain(device->nv, item->timer, item->runningLease, status);
        }
        (void)timerContextStage(item->timer, 0, NULL, 0);
    }
    s540Darwin_os_release_spinlock(device->guard, token);
    if (!allowed || status != NV_OK) return;''')
    source = replace(source, '''    status = rm_run_nano_timer_callback(lease.stack, device->nv, item->event);
    s540GlobalRmHostFree(lease.allocation);''', '''    status = rm_run_nano_timer_callback(lease.stack, device->nv, item->event);
    if (device->transactionGeneration) {
        NV_STATUS returned = s540FirstTxnDirectOriginalReturned(device->nv, status);
        if (status == NV_OK) status = returned;
    }
    s540GlobalRmHostFree(lease.allocation);''')
    # Direct cancellation is genuine synchronous callback-return evidence. It
    # does not retire accepted work borrowing the original event.
    source = replace(source, '''    item->cancelling = NV_FALSE;
    if (deleting) {''', '''    if (device->transactionGeneration) {
        (void)timerContextStage(item->timer, S540_FIRST_SERVICE_CANCELLED, item->event, item->armGeneration);
        if (item->armLease) {
            status = s540FirstTxnDirectCancelled(device->nv, item->timer, item->armLease);
            if (status == NV_OK) item->armLease = 0;
        }
        if (status == NV_OK && deleting)
            status = s540FirstTxnEventCanDestroy(device->nv, item->event, item->timer, item->eventGeneration);
        (void)timerContextStage(item->timer, 0, NULL, 0);
        if (status != NV_OK || item->runningLease) {
            device->quarantined = NV_TRUE;
            s540Darwin_os_release_spinlock(device->guard, token);
            return status != NV_OK ? status : NV_ERR_IN_USE;
        }
    }
    item->cancelling = NV_FALSE;
    if (deleting) {''')
    source = replace(source, '''    if (deleting) { s540DarwinTimerDestroy(item->timer); s540GlobalRmHostFree(item); }''', '''    if (deleting) {
        s540DarwinTimerDestroy(item->timer);
        if (device->transactionGeneration) {
            token = s540Darwin_os_acquire_spinlock(device->guard);
            item->backendDestroyed = NV_TRUE;
            (void)timerContextStage(item->timer, S540_FIRST_SERVICE_DESTROYED, item->event, item->eventGeneration);
            status = s540FirstTxnEventDestroyed(device->nv, item->event, item->timer, item->eventGeneration);
            (void)timerContextStage(item->timer, 0, NULL, 0);
            if (status != NV_OK) device->quarantined = NV_TRUE;
            else {
                struct nv_nano_timer **link = &device->nano;
                while (*link != item) link = &(*link)->next;
                *link = item->next; --device->liveNano;
            }
            s540Darwin_os_release_spinlock(device->guard, token);
            if (status != NV_OK) return status;
        }
        s540GlobalRmHostFree(item);
    }''')
    source = replace(source, '''    if (deleting) {
        struct nv_nano_timer **link''', '''    if (deleting && !device->transactionGeneration) {
        struct nv_nano_timer **link''')
    source = replace(source, '''            NV_STATUS status = s540DarwinTimerCancel(item->timer);
            if (status != NV_OK) result = status;''', '''            NV_STATUS status = s540DarwinTimerCancel(item->timer);
            if (status == NV_OK && device->transactionGeneration) {
                token = s540Darwin_os_acquire_spinlock(device->guard);
                (void)timerContextStage(item->timer, S540_FIRST_SERVICE_CANCELLED, item->event, item->armGeneration);
                if (item->armLease) {
                    status = s540FirstTxnDirectCancelled(device->nv, item->timer, item->armLease);
                    if (status == NV_OK) item->armLease = 0;
                }
                if (status == NV_OK && item->runningLease) status = NV_ERR_IN_USE;
                (void)timerContextStage(item->timer, 0, NULL, 0);
                s540Darwin_os_release_spinlock(device->guard, token);
            }
            if (status != NV_OK && result == NV_OK) result = status;''')
    source = replace(source, '    device->draining = NV_FALSE;',
        '    device->draining = NV_FALSE;\n    device->stopCompleted = result == NV_OK;')
    source = replace(source, '''    if (!device) return NV_ERR_INVALID_ARGUMENT;
    status = s540GspTimersStop(nv);''', '''    if (!device) return NV_ERR_INVALID_ARGUMENT;
    // No original/GSP final receipt exists; never release callback text owners.
    if (device->transactionGeneration) return NV_ERR_IN_USE;
    status = s540GspTimersStop(nv);''')
    source += '''
NV_STATUS s540FirstTxnTimersBind(const void *nv, NvU64 generation) {
    S540GspDeviceTimers *device = find_device((nv_state_t *)nv);
    NvU64 token;
    if (!device || !generation || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->transactionGeneration || device->nano || device->callbacks ||
        device->stopping || device->quarantined || device->nv->rc_timer_enabled) {
        s540Darwin_os_release_spinlock(device->guard, token); return NV_ERR_IN_USE;
    }
    device->transactionGeneration = generation;
    s540Darwin_os_release_spinlock(device->guard, token); return NV_OK;
}
NV_STATUS s540FirstTxnTimersValidateStopped(const void *nv, NvU64 generation) {
    S540GspDeviceTimers *device = find_device((nv_state_t *)nv);
    struct nv_nano_timer *item;
    NV_STATUS status = NV_OK;
    NvU64 token;
    if (!device || !generation || !ordinary()) return NV_ERR_INVALID_ARGUMENT;
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->transactionGeneration != generation || !device->stopping ||
        !device->stopCompleted || device->draining || device->quarantined ||
        device->nv->rc_timer_enabled || device->rcArmLease || device->rcRunningLease)
        status = NV_ERR_INVALID_STATE;
    for (item = device->nano; item; item = item->next)
        if (item->armLease || item->runningLease || item->cancelling || item->deleting)
            status = NV_ERR_IN_USE;
    s540Darwin_os_release_spinlock(device->guard, token); return status;
}
/* Called by the actual Darwin backend only AFTER nano_callback returns. */
NV_STATUS s540FirstTxnTimerActionReturned(S540DarwinTimer *timer) {
    S540GspDeviceTimers *device = __atomic_load_n(&binding, __ATOMIC_ACQUIRE);
    struct nv_nano_timer *item;
    NV_STATUS status = NV_OK;
    NvU64 token;
    if (!device || !device->transactionGeneration) return NV_OK;
    token = s540Darwin_os_acquire_spinlock(device->guard);
    for (item = device->nano; item && item->timer != timer; item = item->next) {}
    if (item && item->runningLease) {
        (void)timerContextStage(timer, S540_FIRST_SERVICE_RETURNED, item->event, item->runningArmGeneration);
        status = s540FirstTxnDirectReturned(device->nv, timer, item->runningLease);
        if (status == NV_OK) item->runningLease = 0;
        else device->quarantined = NV_TRUE;
        (void)timerContextStage(timer, 0, NULL, 0);
    }
    s540Darwin_os_release_spinlock(device->guard, token); return status;
}
'''
    # RC remains a deliberately explicit blocked producer: no invented owner
    # descriptor for rm_run_rc_callback. Stop still drains any earlier real RC.
    source = replace(source, '''    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->stopping || device->rcStopping''', '''    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->transactionGeneration) {
        device->quarantined = NV_TRUE;
        s540Darwin_os_release_spinlock(device->guard, token); reject(device); return -1;
    }
    if (device->stopping || device->rcStopping''')
    return source

def prepare(output):
    output = Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    relative='packages/nvidia-gsp-bootstrap/timers/'
    inputs={relative+name:(REPO/relative/name).read_bytes() for name in ['S540NvidiaGspTimersOriginal.c','S540NvidiaGspTimers.h']}
    checked=original._strict_patch(inputs,(REPO/'packages/nvidia-gsp-bootstrap/prospective-timer-checked/patches/timer-checked-port-prospective.patch').read_bytes())
    source=checked[relative+'S540NvidiaGspTimersOriginal.c'].decode()
    (output/'S540NvidiaGspTimers.h').write_bytes(checked[relative+'S540NvidiaGspTimers.h'])
    if hashlib.sha256(source.encode()).hexdigest() != 'c03ad97a6437d331403d765b1d5b2e5b20c4c13197c9cd4c19883766d6275d3a':
        raise ValueError('Frozen checked timer input mismatch')
    result = timer_overlay(source)
    (output/'S540NvidiaGspTimersOriginal.c').write_text(result)
    backend = (SERVICE/'S540NvidiaDarwinTimer.cpp').read_text()
    if hashlib.sha256(backend.encode()).hexdigest() != '3c3960367042379f94cf53b2edd9eb24f09aea3b97391e51264fa394e65de19a':
        raise ValueError('Real timer backend input differs from pinned checkpoint')
    changed = replace(backend, 'using namespace S540DarwinInternal;',
        'using namespace S540DarwinInternal;\n'
        'extern "C" NV_STATUS s540FirstTxnTimerActionReturned(S540DarwinTimer *);')
    changed = replace(changed, '''    timer->action(timer->context);
    token = timer->guard.lock();''', '''    timer->action(timer->context);
    // Actual action return, before clearing the backend's callback identity.
    (void)s540FirstTxnTimerActionReturned(timer);
    token = timer->guard.lock();''')
    (output/'S540NvidiaDarwinTimer.cpp').write_text(changed)
    report = {}
    for name, before, after in [('S540NvidiaGspTimersOriginal.c',source,result),
            ('S540NvidiaDarwinTimer.cpp',backend,changed)]:
        report[name] = {'input_sha256':hashlib.sha256(before.encode()).hexdigest(),
            'output_sha256':hashlib.sha256(after.encode()).hexdigest()}
        (output/(name+'.patch')).write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='a/'+name,tofile='b/'+name)))
    report.update({'production_modified':False,'hardware_admission':False,
        'rc_producer_disposition':'refuse-retain-until-exact-original-policy-reviewed',
        'pending_timer_rearm':'refuse-retain-until-replacement-lease-proof'})
    (output/'timer-source-hashes.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output)
