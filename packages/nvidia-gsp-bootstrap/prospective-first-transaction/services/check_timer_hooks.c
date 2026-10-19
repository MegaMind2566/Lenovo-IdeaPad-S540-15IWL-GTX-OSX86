/* SPDX-License-Identifier: MIT */
/* Actual full-header checked port + real timer backend. The strong record is
 * replaced by explicit controls ONLY in this plumbing/fault-boundary test. */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGspTimers.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaFirstTxnServices.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
static unsigned checks, failures;
static NvU32 hostObjects, unavailable, entered, released, originalReturned, actionReturned;
static NvU32 blocked, borrowers, cancellations, destroyed, eventFailed;
static NvU32 locksHeld, queuedReturned;
static NvU32 failDestroyed;
static NvU64 admittedArm, admittedLease, masterThread, callbackThread;
static nv_state_t *exactNv;
static int event;
static const void *timerIdentity;
static struct os_work_queue *deviceQueue, *globalQueue;
enum { TRANSACTION_GEN = 19, EVENT_GEN = 47 };
static void require(NvBool v) { if (!v) abort(); }
static void expect(NvBool v, const char *why) {
    ++checks; if (!v) { ++failures; fprintf(stderr, "timer hooks: %s\n", why); }
}
static NvBool waitFor(NvU32 *value) {
    for (unsigned n = 0; n != 3000 && !__atomic_load_n(value, __ATOMIC_ACQUIRE); ++n) usleep(1000);
    return __atomic_load_n(value, __ATOMIC_ACQUIRE) != 0;
}
void *s540GlobalRmHostAllocate(NvU64 bytes) {
    void *p = calloc(1, (size_t)bytes); if (p) ++hostObjects; return p;
}
void s540GlobalRmHostFree(void *p) { if (p) { free(p); --hostObjects; } }
void s540GlobalRmRecordUnavailable(NvU32 service) { (void)service; ++unavailable; }
void *NV_API_CALL os_mem_set(void *out, NvU8 byte, NvU32 bytes) {
    NvU8 *p = out; while (bytes--) *p++ = byte; return out;
}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *stack, nv_state_t *nv, void *data) {
    require(stack && ((NvUPtr)stack & 15) == 0 && nv == exactNv && data == &event);
    __atomic_store_n(&entered, 1U, __ATOMIC_RELEASE);
    if (blocked) require(waitFor(&released));
    // Explicit dependency control represents a queued event borrower. This
    // test does not pretend to execute an NVIDIA work item or admit its policy.
    return NV_OK;
}
static NvBool probe(const void *timer, NvU32 stage, NvU64 generation, const void *data) {
    S540FirstTxnServiceContext c = {0}; NvU64 thread = 0;
    return s540Darwin_os_get_current_thread(&thread) == NV_OK &&
        s540FirstTxnServicesReadTimerContext(timer, &c) == NV_OK &&
        c.stage == stage && c.generation == generation && c.thread == thread && c.data == data;
}
NV_STATUS s540FirstTxnEventConstruct(const void *nv, const void *data, const void *timer, NvU64 *out) {
    require(nv == exactNv && data == &event && probe(timer, S540_FIRST_SERVICE_ADMIT, TRANSACTION_GEN, data));
    timerIdentity = timer;
    if (eventFailed) return NV_ERR_NOT_SUPPORTED;
    *out = EVENT_GEN; return NV_OK;
}
NV_STATUS s540FirstTxnDirectAdmit(const void *nv, const void *timer, const void *data,
    NvU64 eventGen, NvU64 arm, NvU64 *out) {
    require(nv == exactNv && timer == timerIdentity && eventGen == EVENT_GEN && arm &&
        probe(timer, S540_FIRST_SERVICE_ADMIT, arm, data));
    admittedArm = arm; admittedLease += 10; *out = admittedLease; return NV_OK;
}
NV_STATUS s540FirstTxnDirectEnter(const void *nv, const void *timer, NvU64 lease) {
    require(nv == exactNv && lease == admittedLease &&
        probe(timer, S540_FIRST_SERVICE_ENTER, admittedArm, &event));
    require(s540Darwin_os_get_current_thread(&callbackThread) == NV_OK);
    return NV_OK;
}
NV_STATUS s540FirstTxnDirectOriginalReturned(const void *nv, NV_STATUS status) {
    require(nv == exactNv && status == NV_OK && __atomic_load_n(&entered, __ATOMIC_ACQUIRE));
    __atomic_store_n(&originalReturned, 1U, __ATOMIC_RELEASE); return NV_OK;
}
NV_STATUS s540FirstTxnDirectReturned(const void *nv, const void *timer, NvU64 lease) {
    require(nv == exactNv && lease == admittedLease && originalReturned &&
        probe(timer, S540_FIRST_SERVICE_RETURNED, admittedArm, &event));
    __atomic_store_n(&actionReturned, 1U, __ATOMIC_RELEASE); return NV_OK;
}
NV_STATUS s540FirstTxnDirectCancelled(const void *nv, const void *timer, NvU64 lease) {
    require(nv == exactNv && lease == admittedLease &&
        probe(timer, S540_FIRST_SERVICE_CANCELLED, admittedArm, &event));
    ++cancellations; return NV_OK;
}
NV_STATUS s540FirstTxnDirectRetain(const void *nv, const void *timer, NvU64 lease, NV_STATUS status) {
    (void)lease; require(nv == exactNv && timer == timerIdentity && status != NV_OK); return status;
}
NV_STATUS s540FirstTxnEventCanDestroy(const void *nv, const void *data, const void *timer, NvU64 eventGen) {
    require(nv == exactNv && data == &event && eventGen == EVENT_GEN &&
        probe(timer, S540_FIRST_SERVICE_CANCELLED, admittedArm, data));
    return borrowers ? NV_ERR_IN_USE : NV_OK;
}
NV_STATUS s540FirstTxnEventDestroyed(const void *nv, const void *data, const void *timer, NvU64 eventGen) {
    require(nv == exactNv && eventGen == EVENT_GEN &&
        probe(timer, S540_FIRST_SERVICE_DESTROYED, EVENT_GEN, data));
    ++destroyed; return failDestroyed ? NV_ERR_INVALID_STATE : NV_OK;
}
/* Explicit original-lock probe control for endpoint ordering only. The actual
 * original helper is compiled/tested in the separate original-source report. */
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *nv) {
    NvU64 thread = 0;
    require(nv == exactNv && s540Darwin_os_get_current_thread(&thread) == NV_OK);
    return thread == masterThread && !locksHeld ? NV_OK : NV_ERR_IN_USE;
}
NV_STATUS s540FirstTxnWorkAdmit(const void *nv, const void *q, const void *data, NvU64 *out) {
    S540FirstTxnServiceContext c = {0};
    require(nv == exactNv && s540FirstTxnServicesReadQueueContext(q, &c) == NV_OK &&
        c.stage == S540_FIRST_SERVICE_ADMIT && c.data == data && c.generation == TRANSACTION_GEN);
    *out = 1; return NV_OK;
}
NV_STATUS s540FirstTxnWorkEnter(const void *nv, const void *q, const void *data, NvU64 lease) {
    (void)q; require(nv == exactNv && data == &event && lease == 1); return NV_OK;
}
NV_STATUS s540FirstTxnWorkReturned(const void *nv, const void *q, NvU64 lease) {
    (void)q; require(nv == exactNv && lease == 1 && queuedReturned); return NV_OK;
}
NV_STATUS s540FirstTxnWorkRejected(const void *nv, const void *q, const void *data, NV_STATUS status) {
    (void)q; (void)data; require(nv == exactNv && status != NV_OK); return status;
}
NV_STATUS s540FirstTxnWorkRetain(const void *nv, const void *q, NvU64 lease, NV_STATUS status) {
    (void)nv; (void)q; (void)lease; (void)status; abort();
}
static void queuedAction(void *context, void *data) {
    require(context == exactNv && data == &event);
    __atomic_store_n(&queuedReturned, 1U, __ATOMIC_RELEASE);
}
static void setup(nv_nano_timer_t **handle) {
    exactNv = calloc(1, sizeof(*exactNv)); require(exactNv != NULL);
    require(s540Darwin_os_get_current_thread(&masterThread) == NV_OK);
    require(s540GspTimersBind(exactNv) == NV_OK);
    require(s540DarwinWorkQueueCreate(queuedAction, exactNv, &deviceQueue) == NV_OK);
    require(s540DarwinWorkQueueCreate(queuedAction, exactNv, &globalQueue) == NV_OK);
    require(s540DarwinBindGlobalWorkQueue(globalQueue) == NV_OK);
    require(s540FirstTxnServicesBind(exactNv, TRANSACTION_GEN, deviceQueue, globalQueue) == NV_OK);
    nv_create_nano_timer(exactNv, &event, handle);
}
static void healthy(void) {
    nv_nano_timer_t *handle = NULL; S540GspTimersSnapshot snapshot;
    setup(&handle); expect(handle != NULL, "actual event timer is bound to immutable generation");
    S540FirstTxnServiceContext c = {0};
    expect(s540FirstTxnServicesReadTimerContext(timerIdentity, &c) != NV_OK,
        "ordinary caller cannot invent a guarded service stage");
    nv_start_nano_timer(exactNv, handle, 60000000000ULL);
    expect(s540GspTimersCancelNano(exactNv, handle) == NV_OK && cancellations == 1 && !entered,
        "pending arm lease retires only after actual backend cancellation");
    expect(s540GspTimersCancelNano(exactNv, handle) == NV_OK && cancellations == 1,
        "idempotent cancel cannot retire the same arm lease twice");
    blocked = 1;
    nv_start_nano_timer(exactNv, handle, 0); require(waitFor(&entered));
    expect(callbackThread && callbackThread != masterThread && !originalReturned && !actionReturned,
        "genuine foreign timer thread has entered but no return is forged");
    __atomic_store_n(&released, 1U, __ATOMIC_RELEASE); require(waitFor(&actionReturned));
    expect(originalReturned && actionReturned && admittedArm == 2,
        "actual original wrapper and later actual callback action have distinct boundaries");
    expect(s540GspTimersDestroyNano(exactNv, handle) == NV_OK && destroyed == 1,
        "event zero-borrower control allows checked real deletion");
    expect(s540FirstTxnServicesReadTimerContext(timerIdentity, &c) != NV_OK,
        "post-destroy identity query uses safe metadata tombstone, never freed timer storage");
    s540GspTimersGetSnapshot(&snapshot);
    expect(snapshot.liveNanoTimers == 0 && !snapshot.quarantined,
        "successful actual deletion relinquishes only its own event timer");
    locksHeld = 1;
    expect(s540FirstTxnServicesSealAndDrain(exactNv, TRANSACTION_GEN) == NV_ERR_IN_USE,
        "actual endpoint checks original lock probe before blocking any real service");
    s540GspTimersGetSnapshot(&snapshot);
    expect(!snapshot.stopped, "refused lock context cannot falsely publish timer stop");
    locksHeld = 0;
    expect(s540Darwin_os_queue_work_item(deviceQueue, &event) == NV_OK,
        "fixed endpoint owns a real accepted queue action before its drain");
    expect(s540FirstTxnServicesSealAndDrain(exactNv, TRANSACTION_GEN) == NV_OK &&
        s540FirstTxnTimersValidateStopped(exactNv, TRANSACTION_GEN) == NV_OK,
        "fixed endpoint performs real timer stop, both queue seals and actual callback drains");
    expect(queuedReturned && s540FirstTxnServicesValidateRetired(exactNv, TRANSACTION_GEN) == NV_OK,
        "actual queue/timer guarded states attest retired software participants");
    expect(s540FirstTxnServicesSealAndDrain(exactNv, TRANSACTION_GEN + 1) != NV_OK,
        "stale endpoint generation cannot reuse another transaction's drains");
    expect(s540FirstTxnTimersValidateStopped(exactNv, TRANSACTION_GEN + 1) != NV_OK &&
        s540GspTimersUnbind(exactNv) == NV_ERR_IN_USE && hostObjects >= 1,
        "no final hardware/text receipt exists so service owner remains retained");
}
static void borrowed(void) {
    nv_nano_timer_t *handle = NULL; S540GspTimersSnapshot snapshot;
    setup(&handle); require(handle != NULL); borrowers = 1;
    nv_start_nano_timer(exactNv, handle, 0); require(waitFor(&actionReturned));
    expect(s540GspTimersDestroyNano(exactNv, handle) == NV_ERR_IN_USE && !destroyed,
        "completed direct callback cannot authorize deletion of an accepted event borrower");
    s540GspTimersGetSnapshot(&snapshot);
    expect(snapshot.liveNanoTimers == 1 && snapshot.quarantined && hostObjects >= 2,
        "checked deletion refusal retains real event, timer, registry and callback owners");
    expect(s540FirstTxnTimersValidateStopped(exactNv, TRANSACTION_GEN) != NV_OK,
        "software-retired evidence cannot be forged after borrower refusal");
}
static void refusedEvent(void) {
    nv_nano_timer_t *handle = NULL; S540GspTimersSnapshot snapshot;
    eventFailed = 1; setup(&handle);
    s540GspTimersGetSnapshot(&snapshot);
    expect(!handle && snapshot.liveNanoTimers == 1 && snapshot.quarantined,
        "unknown event callback refusal retains unpublished service storage");
    expect(s540GspTimersUnbind(exactNv) == NV_ERR_IN_USE && hostObjects >= 2,
        "unknown event cannot become successful teardown or free callback text owners");
}
static void failedDestroyedNote(void) {
    nv_nano_timer_t *handle = NULL; S540GspTimersSnapshot snapshot;
    setup(&handle); require(handle != NULL); failDestroyed = 1;
    expect(s540GspTimersDestroyNano(exactNv, handle) == NV_ERR_INVALID_STATE && destroyed == 1,
        "post-physical-destroy note refusal remains visible");
    s540GspTimersGetSnapshot(&snapshot);
    expect(snapshot.liveNanoTimers == 1 && snapshot.quarantined && hostObjects >= 2,
        "post-destroy refusal retains item owner as dead-backend tombstone in the actual registry");
    expect(s540GspTimersStop(exactNv) == NV_ERR_IN_USE &&
        s540GspTimersDestroyNano(exactNv, handle) == NV_ERR_IN_USE,
        "retry never passes the freed backend pointer to a cancel/destroy operation");
}
int main(void) {
    unsigned total = 0;
    for (unsigned test = 0; test != 4; ++test) {
        int pipefd[2]; require(pipe(pipefd) == 0);
        pid_t child = fork(); require(child >= 0);
        if (!child) {
            close(pipefd[0]);
            if (!test) healthy(); else if (test == 1) borrowed(); else if (test == 2) refusedEvent(); else failedDestroyedNote();
            unsigned result[2] = {checks, failures};
            require(write(pipefd[1], result, sizeof(result)) == sizeof(result));
            close(pipefd[1]); _Exit(failures ? 1 : 0);
        }
        close(pipefd[1]); unsigned result[2] = {0};
        require(read(pipefd[0], result, sizeof(result)) == sizeof(result)); close(pipefd[0]);
        int status = 0; require(waitpid(child, &status, 0) == child);
        total += result[0]; failures += result[1];
        if (!WIFEXITED(status) || WEXITSTATUS(status)) ++failures;
    }
    printf("{\"checks\":%u,\"failures\":%u,\"component\":\"real-timer-first-transaction-hook-controls\","
        "\"record_hooks\":\"explicit-controls\",\"original_callback_policy_admitted\":false,"
        "\"hardware_admission\":false}\n", total, failures);
    return failures ? 1 : 0;
}
