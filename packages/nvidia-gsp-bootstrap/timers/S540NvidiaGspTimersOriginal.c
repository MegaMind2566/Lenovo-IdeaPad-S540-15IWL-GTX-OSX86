// SPDX-License-Identifier: MIT
// Compile against the full pinned nv.h and forced full-RM namespace header.
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGspTimers.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"

typedef struct S540GspDeviceTimers S540GspDeviceTimers;
struct nv_nano_timer {
    struct nv_nano_timer *next;
    S540GspDeviceTimers *owner;
    S540DarwinTimer *timer;
    void *event;
    NvBool deleting;
    NvBool cancelling;
};
struct S540GspDeviceTimers {
    nv_state_t *nv;
    void *guard;
    S540DarwinTimer *rc;
    struct nv_nano_timer *nano;
    NvU32 liveNano;
    NvU32 callbacks;
    NvU32 callbackFailures;
    NvU32 cancellationFailures;
    NvU32 rejected;
    NvBool stopping;
    NvBool rcStopping;
    NvBool draining;
    NvBool quarantined;
};
static S540GspDeviceTimers *binding;
enum { TIMER_UNAVAILABLE = 24 };

static NvBool ordinary(void) { return s540Darwin_os_semaphore_may_sleep(); }
static void reject(S540GspDeviceTimers *device) {
    if (device) __atomic_fetch_add(&device->rejected, 1U, __ATOMIC_RELAXED);
    s540GlobalRmRecordUnavailable(TIMER_UNAVAILABLE);
}
static S540GspDeviceTimers *find_device(nv_state_t *nv) {
    S540GspDeviceTimers *device = __atomic_load_n(&binding, __ATOMIC_ACQUIRE);
    return device && device->nv == nv ? device : NULL;
}
static struct nv_nano_timer *find_timer(S540GspDeviceTimers *device, nv_nano_timer_t *handle) {
    struct nv_nano_timer *item;
    for (item = device->nano; item; item = item->next) if (item == handle) return item;
    return NULL;
}
typedef struct S540TimerStackLease { void *allocation; nvidia_stack_t *stack; } S540TimerStackLease;
static NvBool allocate_stack(S540TimerStackLease *lease) {
    NvUPtr aligned;
    lease->allocation = s540GlobalRmHostAllocate(sizeof(nvidia_stack_t) + 15U);
    lease->stack = NULL;
    if (!lease->allocation) return NV_FALSE;
    // IOMalloc's general allocation contract must not be assumed to satisfy
    // NVIDIA's explicit 16-byte alternate-stack alignment on every SDK.
    aligned = ((NvUPtr)lease->allocation + 15U) & ~(NvUPtr)15U;
    lease->stack = (nvidia_stack_t *)aligned;
    lease->stack->size = sizeof(lease->stack->stack);
    lease->stack->top = lease->stack->stack + lease->stack->size;
    return NV_TRUE;
}
static void rc_callback(void *context) {
    S540GspDeviceTimers *device = context;
    S540TimerStackLease lease;
    NV_STATUS status;
    NvBool armFailed = NV_FALSE;
    NvU64 token = s540Darwin_os_acquire_spinlock(device->guard);
    NvBool enabled = !device->stopping && !device->rcStopping && __atomic_load_n(&device->nv->rc_timer_enabled, __ATOMIC_ACQUIRE);
    s540Darwin_os_release_spinlock(device->guard, token);
    if (!enabled) return;
    if (!allocate_stack(&lease)) { __atomic_fetch_add(&device->callbackFailures, 1U, __ATOMIC_RELAXED); reject(device); return; }
    status = rm_run_rc_callback(lease.stack, device->nv);
    s540GlobalRmHostFree(lease.allocation);
    __atomic_fetch_add(&device->callbacks, 1U, __ATOMIC_RELAXED);
    if (status != NV_OK) __atomic_fetch_add(&device->callbackFailures, 1U, __ATOMIC_RELAXED);
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (status == NV_OK && !device->stopping && !device->rcStopping && __atomic_load_n(&device->nv->rc_timer_enabled, __ATOMIC_ACQUIRE)) {
        if (s540DarwinTimerArm(device->rc, 1000000000ULL) != NV_OK) {
            device->quarantined = NV_TRUE;
            armFailed = NV_TRUE;
        }
    }
    s540Darwin_os_release_spinlock(device->guard, token);
    if (armFailed) reject(device);
}
static void nano_callback(void *context) {
    struct nv_nano_timer *item = context;
    S540GspDeviceTimers *device = item->owner;
    S540TimerStackLease lease;
    NV_STATUS status;
    NvU64 token = s540Darwin_os_acquire_spinlock(device->guard);
    NvBool allowed = !device->stopping && !item->deleting && !item->cancelling;
    s540Darwin_os_release_spinlock(device->guard, token);
    if (!allowed) return;
    if (!allocate_stack(&lease)) { __atomic_fetch_add(&device->callbackFailures, 1U, __ATOMIC_RELAXED); reject(device); return; }
    status = rm_run_nano_timer_callback(lease.stack, device->nv, item->event);
    s540GlobalRmHostFree(lease.allocation);
    __atomic_fetch_add(&device->callbacks, 1U, __ATOMIC_RELAXED);
    if (status != NV_OK) __atomic_fetch_add(&device->callbackFailures, 1U, __ATOMIC_RELAXED);
}
NV_STATUS s540GspTimersBind(nv_state_t *nv) {
    S540GspDeviceTimers *device;
    S540GspDeviceTimers *expected = NULL;
    NV_STATUS status;
    if (!nv) return NV_ERR_INVALID_ARGUMENT;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    if (__atomic_load_n(&binding, __ATOMIC_ACQUIRE)) return NV_ERR_IN_USE;
    device = s540GlobalRmHostAllocate(sizeof(*device));
    if (!device) return NV_ERR_NO_MEMORY;
    os_mem_set(device, 0, sizeof(*device));
    device->nv = nv;
    status = s540Darwin_os_alloc_spinlock(&device->guard);
    if (status != NV_OK) { s540GlobalRmHostFree(device); return status; }
    status = s540DarwinTimerCreate(rc_callback, device, &device->rc);
    if (status != NV_OK) {
        s540Darwin_os_free_spinlock(device->guard);
        s540GlobalRmHostFree(device);
        return status;
    }
    if (!__atomic_compare_exchange_n(&binding, &expected, device, NV_FALSE, __ATOMIC_RELEASE, __ATOMIC_RELAXED)) {
        s540DarwinTimerDestroy(device->rc);
        s540Darwin_os_free_spinlock(device->guard);
        s540GlobalRmHostFree(device);
        return NV_ERR_IN_USE;
    }
    __atomic_store_n(&nv->rc_timer_enabled, 0U, __ATOMIC_RELEASE);
    return NV_OK;
}
NvS32 NV_API_CALL nv_start_rc_timer(nv_state_t *nv) {
    S540GspDeviceTimers *device = find_device(nv);
    NV_STATUS status;
    NvU64 token;
    if (!device) { reject(NULL); return -1; }
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->stopping || device->rcStopping || device->quarantined || __atomic_load_n(&nv->rc_timer_enabled, __ATOMIC_ACQUIRE)) {
        s540Darwin_os_release_spinlock(device->guard, token);
        return -1;
    }
    __atomic_store_n(&nv->rc_timer_enabled, 1U, __ATOMIC_RELEASE);
    status = s540DarwinTimerArm(device->rc, 1000000000ULL);
    if (status != NV_OK) __atomic_store_n(&nv->rc_timer_enabled, 0U, __ATOMIC_RELEASE);
    s540Darwin_os_release_spinlock(device->guard, token);
    if (status != NV_OK) reject(device);
    return status == NV_OK ? 0 : -1;
}
NvS32 NV_API_CALL nv_stop_rc_timer(nv_state_t *nv) {
    S540GspDeviceTimers *device = find_device(nv);
    NV_STATUS status;
    NvU64 token;
    if (!device || !ordinary()) { reject(device); return -1; }
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->rcStopping || !__atomic_load_n(&nv->rc_timer_enabled, __ATOMIC_ACQUIRE)) {
        s540Darwin_os_release_spinlock(device->guard, token); return -1;
    }
    device->rcStopping = NV_TRUE;
    s540Darwin_os_release_spinlock(device->guard, token);
    status = s540DarwinTimerCancel(device->rc);
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (status == NV_OK) {
        // The unmodified RM callback reads this field without an atomic API.
        // Publish its disabled value only after the callback is fully drained;
        // rcStopping already prevented admission and rearm during cancellation.
        __atomic_store_n(&nv->rc_timer_enabled, 0U, __ATOMIC_RELEASE);
        device->rcStopping = NV_FALSE;
    }
    s540Darwin_os_release_spinlock(device->guard, token);
    if (status != NV_OK) {
        token = s540Darwin_os_acquire_spinlock(device->guard);
        device->quarantined = NV_TRUE;
        ++device->cancellationFailures;
        s540Darwin_os_release_spinlock(device->guard, token);
        reject(device);
    }
    return status == NV_OK ? 0 : -1;
}
void NV_API_CALL nv_create_nano_timer(nv_state_t *nv, void *event, nv_nano_timer_t **output) {
    S540GspDeviceTimers *device = find_device(nv);
    struct nv_nano_timer *item;
    NvU64 token;
    NV_STATUS status;
    if (!output) { reject(device); return; }
    *output = NULL;
    if (!device || !ordinary()) { reject(device); return; }
    item = s540GlobalRmHostAllocate(sizeof(*item));
    if (!item) { reject(device); return; }
    os_mem_set(item, 0, sizeof(*item));
    item->owner = device; item->event = event;
    status = s540DarwinTimerCreate(nano_callback, item, &item->timer);
    if (status != NV_OK) { s540GlobalRmHostFree(item); reject(device); return; }
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->stopping || device->quarantined) {
        s540Darwin_os_release_spinlock(device->guard, token);
        s540DarwinTimerDestroy(item->timer); s540GlobalRmHostFree(item); reject(device); return;
    }
    item->next = device->nano; device->nano = item; ++device->liveNano;
    *output = item;
    s540Darwin_os_release_spinlock(device->guard, token);
}
void NV_API_CALL nv_start_nano_timer(nv_state_t *nv, nv_nano_timer_t *handle, NvU64 delay) {
    S540GspDeviceTimers *device = find_device(nv);
    struct nv_nano_timer *item;
    NvU64 token;
    NV_STATUS status;
    if (!device) { reject(NULL); return; }
    token = s540Darwin_os_acquire_spinlock(device->guard);
    item = find_timer(device, handle);
    if (!item || item->deleting || item->cancelling || device->stopping || device->quarantined) {
        s540Darwin_os_release_spinlock(device->guard, token); reject(device); return;
    }
    // TimerArm is explicitly allocation-free and interrupt-safe. Holding the
    // registry guard closes the arm-versus-cancel admission race.
    status = s540DarwinTimerArm(item->timer, delay);
    s540Darwin_os_release_spinlock(device->guard, token);
    if (status != NV_OK) reject(device);
}
static NV_STATUS cancel_nano(S540GspDeviceTimers *device, nv_nano_timer_t *handle, NvBool deleting) {
    struct nv_nano_timer *item;
    NV_STATUS status;
    NvU64 token;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    token = s540Darwin_os_acquire_spinlock(device->guard);
    item = find_timer(device, handle);
    if (!item || item->deleting || item->cancelling || device->draining) {
        s540Darwin_os_release_spinlock(device->guard, token); return NV_ERR_IN_USE;
    }
    item->cancelling = NV_TRUE;
    if (deleting) item->deleting = NV_TRUE;
    s540Darwin_os_release_spinlock(device->guard, token);
    status = s540DarwinTimerCancel(item->timer);
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (status != NV_OK) {
        device->quarantined = NV_TRUE; ++device->cancellationFailures;
        // Never release callback data after a failed synchronous cancellation.
        s540Darwin_os_release_spinlock(device->guard, token); return status;
    }
    item->cancelling = NV_FALSE;
    if (deleting) {
        struct nv_nano_timer **link = &device->nano;
        while (*link != item) link = &(*link)->next;
        *link = item->next; --device->liveNano;
    }
    s540Darwin_os_release_spinlock(device->guard, token);
    if (deleting) { s540DarwinTimerDestroy(item->timer); s540GlobalRmHostFree(item); }
    return NV_OK;
}
void NV_API_CALL nv_cancel_nano_timer(nv_state_t *nv, nv_nano_timer_t *timer) {
    S540GspDeviceTimers *device = find_device(nv);
    if (!device || cancel_nano(device, timer, NV_FALSE) != NV_OK) reject(device);
}
void NV_API_CALL nv_destroy_nano_timer(nv_state_t *nv, nv_nano_timer_t *timer) {
    S540GspDeviceTimers *device = find_device(nv);
    if (!device || cancel_nano(device, timer, NV_TRUE) != NV_OK) reject(device);
}
NV_STATUS s540GspTimersStop(nv_state_t *nv) {
    S540GspDeviceTimers *device = find_device(nv);
    struct nv_nano_timer *item;
    NvU64 token;
    NV_STATUS result = NV_OK;
    if (!device) return NV_ERR_INVALID_ARGUMENT;
    if (!ordinary()) return NV_ERR_INVALID_REQUEST;
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->draining) { s540Darwin_os_release_spinlock(device->guard, token); return NV_ERR_IN_USE; }
    device->stopping = NV_TRUE; device->draining = NV_TRUE;
    device->rcStopping = NV_TRUE;
    for (item = device->nano; item; item = item->next) {
        if (item->cancelling || item->deleting) result = NV_ERR_IN_USE;
    }
    s540Darwin_os_release_spinlock(device->guard, token);
    if (result == NV_OK) {
        result = s540DarwinTimerCancel(device->rc);
        if (result == NV_OK) __atomic_store_n(&nv->rc_timer_enabled, 0U, __ATOMIC_RELEASE);
    }
    if (result == NV_OK) {
        for (item = device->nano; item; item = item->next) {
            NV_STATUS status = s540DarwinTimerCancel(item->timer);
            if (status != NV_OK) result = status;
        }
    }
    token = s540Darwin_os_acquire_spinlock(device->guard);
    device->draining = NV_FALSE;
    if (result != NV_OK) { device->quarantined = NV_TRUE; ++device->cancellationFailures; }
    s540Darwin_os_release_spinlock(device->guard, token);
    return result;
}
NV_STATUS s540GspTimersUnbind(nv_state_t *nv) {
    S540GspDeviceTimers *device = find_device(nv);
    struct nv_nano_timer *item;
    NvU64 token;
    NV_STATUS status;
    if (!device) return NV_ERR_INVALID_ARGUMENT;
    status = s540GspTimersStop(nv);
    if (status != NV_OK) return status;
    token = s540Darwin_os_acquire_spinlock(device->guard);
    if (device->quarantined) { s540Darwin_os_release_spinlock(device->guard, token); return NV_ERR_INVALID_STATE; }
    s540Darwin_os_release_spinlock(device->guard, token);
    // External RM timer callers have relinquished all references. All software
    // callbacks are synchronously stopped before either device or RM teardown.
    __atomic_store_n(&binding, (S540GspDeviceTimers *)NULL, __ATOMIC_RELEASE);
    while ((item = device->nano) != NULL) {
        device->nano = item->next;
        s540DarwinTimerDestroy(item->timer);
        s540GlobalRmHostFree(item);
    }
    s540DarwinTimerDestroy(device->rc);
    s540Darwin_os_free_spinlock(device->guard);
    s540GlobalRmHostFree(device);
    return NV_OK;
}
void s540GspTimersGetSnapshot(S540GspTimersSnapshot *out) {
    S540GspDeviceTimers *device;
    NvU64 token;
    if (!out) return;
    os_mem_set(out, 0, sizeof(*out));
    device = __atomic_load_n(&binding, __ATOMIC_ACQUIRE);
    if (!device) return;
    token = s540Darwin_os_acquire_spinlock(device->guard);
    out->liveNanoTimers = device->liveNano;
    out->callbacks = __atomic_load_n(&device->callbacks, __ATOMIC_RELAXED);
    out->callbackFailures = __atomic_load_n(&device->callbackFailures, __ATOMIC_RELAXED);
    out->cancellationFailures = device->cancellationFailures;
    out->rejectedCalls = __atomic_load_n(&device->rejected, __ATOMIC_RELAXED);
    out->bound = NV_TRUE; out->stopped = device->stopping; out->quarantined = device->quarantined;
    s540Darwin_os_release_spinlock(device->guard, token);
}
