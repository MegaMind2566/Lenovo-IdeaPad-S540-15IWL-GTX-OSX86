/* SPDX-License-Identifier: MIT */
/* Actual original osCancel/osDestroy bodies, real TimerOriginal and native
 * Darwin timer backend. RM callbacks and host allocator are explicit fixtures. */
#include "nv.h"
#include "os-interface.h"
#include "os/os.h"
#include "S540NvidiaGspTimers.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
static unsigned checks, failures;
static NvU32 hostObjects, unavailable, callbackErrors, nanoCalls, entered, released;
static NvU32 block, callbackReturned, cancelStarted, cancelReturned, selfMode;
static NV_STATUS observed, directCancelResult;
static nv_state_t *expectedNv;
static nv_nano_timer_t *handle;
static void *expectedEvent;
static void expect(NvBool value, const char *why) {
    ++checks; if (!value) { ++failures; fprintf(stderr, "Checked timer: %s\n", why); }
}
void *s540GlobalRmHostAllocate(NvU64 bytes) {
    void *p = calloc(1, (size_t)bytes);
    if (p) __atomic_fetch_add(&hostObjects, 1U, __ATOMIC_RELAXED);
    return p;
}
void s540GlobalRmHostFree(void *p) {
    if (p) { free(p); __atomic_fetch_sub(&hostObjects, 1U, __ATOMIC_RELAXED); }
}
void s540GlobalRmRecordUnavailable(NvU32 service) {
    (void)service; __atomic_fetch_add(&unavailable, 1U, __ATOMIC_RELAXED);
}
void *NV_API_CALL os_mem_set(void *out, NvU8 byte, NvU32 bytes) {
    volatile NvU8 *d = out;
    while (bytes--) *d++ = byte;
    return out;
}
static NvBool stackValid(nvidia_stack_t *s, nv_state_t *nv) {
    return s && ((NvUPtr)s % 16) == 0 && nv == expectedNv && s->size == sizeof(s->stack) &&
        s->top == s->stack + s->size;
}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *s, nv_state_t *nv) {
    if (!stackValid(s, nv)) ++callbackErrors;
    return NV_OK;
}
#if S540_TIMER_OS_BASELINE
#include "baseline-os-bodies.inc"
#else
#include "proposed-os-bodies.inc"
#endif
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *s, nv_state_t *nv, void *event) {
    if (!stackValid(s, nv) || event != expectedEvent) ++callbackErrors;
    __atomic_store_n(&entered, 1U, __ATOMIC_RELEASE);
    if (selfMode == 1) observed = osCancelNanoTimer(nv, handle);
    if (selfMode == 2) observed = osDestroyNanoTimer(nv, handle);
    while (__atomic_load_n(&block, __ATOMIC_ACQUIRE) &&
           !__atomic_load_n(&released, __ATOMIC_ACQUIRE)) usleep(1000);
    __atomic_fetch_add(&nanoCalls, 1U, __ATOMIC_RELAXED);
    __atomic_store_n(&callbackReturned, 1U, __ATOMIC_RELEASE);
    return NV_OK;
}
static NvBool waitFor(NvU32 *value) {
    for (unsigned i = 0; i < 3000 && !__atomic_load_n(value, __ATOMIC_ACQUIRE); ++i) usleep(1000);
    return __atomic_load_n(value, __ATOMIC_ACQUIRE) != 0;
}
static void *cancelThread(void *unused) {
    (void)unused;
    __atomic_store_n(&cancelStarted, 1U, __ATOMIC_RELEASE);
    directCancelResult = osCancelNanoTimer(expectedNv, handle);
    if (!__atomic_load_n(&callbackReturned, __ATOMIC_ACQUIRE)) ++callbackErrors;
    __atomic_store_n(&cancelReturned, 1U, __ATOMIC_RELEASE);
    return NULL;
}
static NvBool failedSelfCancelChild(NvU32 mode) {
    const pid_t child = fork(); int exitStatus;
    if (child < 0) return NV_FALSE;
    if (!child) {
        nv_state_t *nv = calloc(1, sizeof(*nv)); S540GspTimersSnapshot snapshot;
        expectedNv = nv; expectedEvent = &checks; selfMode = mode;
        observed = NV_OK; entered = callbackReturned = 0;
        if (!nv || s540GspTimersBind(nv) != NV_OK) _Exit(2);
        nv_create_nano_timer(nv, expectedEvent, &handle);
        if (!handle) _Exit(3);
        nv_start_nano_timer(nv, handle, 0);
        if (!waitFor(&callbackReturned)) _Exit(4);
        s540GspTimersGetSnapshot(&snapshot);
        NvBool valid = observed == NV_ERR_ILLEGAL_ACTION && snapshot.quarantined &&
            snapshot.cancellationFailures == 1 && snapshot.liveNanoTimers == 1 &&
            snapshot.rejectedCalls == 1 && unavailable == 1 && !callbackErrors;
        valid = valid && s540GspTimersUnbind(nv) != NV_OK;
        s540GspTimersGetSnapshot(&snapshot);
        valid = valid && snapshot.bound && snapshot.quarantined &&
            hostObjects >= 2 && s540DarwinLiveObjects() >= 3;
        // Deliberately retained failed profile ends in its child process.
        _Exit(valid ? 0 : 5);
    }
    return waitpid(child, &exitStatus, 0) == child && WIFEXITED(exitStatus) && WEXITSTATUS(exitStatus) == 0;
}
int main(void) {
    expect(failedSelfCancelChild(1), "actual self-cancel error reaches original status caller and retains all owners");
    expect(failedSelfCancelChild(2), "actual self-destroy error reaches original status caller and retains all owners");
    nv_state_t *nv = calloc(1, sizeof(*nv)), *foreign = calloc(1, sizeof(*foreign));
    S540GspTimersSnapshot snapshot; pthread_t thread;
    expectedNv = nv; expectedEvent = &checks;
    expect(nv && foreign && s540GspTimersBind(nv) == NV_OK, "real timer binding exists");
    nv_create_nano_timer(nv, expectedEvent, &handle);
    expect(handle != NULL, "real original timer handle is allocated");
    nv_start_nano_timer(nv, handle, 60000000000ULL);
    expect(osCancelNanoTimer(nv, handle) == NV_OK && !nanoCalls,
        "original checked cancel reaches actual pending timer cancellation");
    expect(osCancelNanoTimer(nv, handle) == NV_OK,
        "already completed/inactive timer still invokes actual idempotent cancellation");
    block = 1; entered = released = callbackReturned = cancelStarted = cancelReturned = 0;
    nv_start_nano_timer(nv, handle, 0);
    expect(waitFor(&entered), "real timer callback is inside actual callback endpoint");
    expect(pthread_create(&thread, NULL, cancelThread, NULL) == 0 && waitFor(&cancelStarted),
        "independent real thread requests original checked cancellation");
    usleep(10000);
    expect(!__atomic_load_n(&cancelReturned, __ATOMIC_ACQUIRE),
        "checked status cannot return while direct timer callback remains active");
    __atomic_store_n(&released, 1U, __ATOMIC_RELEASE);
    expect(pthread_join(thread, NULL) == 0 && directCancelResult == NV_OK &&
        callbackReturned && !callbackErrors, "actual cancellation returns after direct callback return");
    block = 0;
    expect(osDestroyNanoTimer(nv, handle) == NV_OK, "original checked destroy removes actual timer and worker");
    handle = NULL;
    s540GspTimersGetSnapshot(&snapshot);
    expect(snapshot.liveNanoTimers == 0 && !snapshot.quarantined,
        "successful checked deletion relinquishes its exact handle ownership");
    expect(osCancelNanoTimer(foreign, NULL) == NV_ERR_INVALID_STATE && unavailable == 1,
        "foreign exact-state binding failure is returned rather than hidden");
    expect(osDestroyNanoTimer(foreign, NULL) == NV_ERR_INVALID_STATE && unavailable == 2,
        "foreign destroy failure remains visible through original status ABI");
    expect(s540GspTimersStop(nv) == NV_OK && s540GspTimersUnbind(nv) == NV_OK,
        "normal profile actually drains and unbinds timer service");
    expect(!hostObjects && !s540DarwinLiveObjects() && !callbackErrors,
        "normal profile releases all actual callback, timer and allocator owners");
    free(foreign); free(nv);
    printf("{\"format\":1,\"component\":\"nvidia-gsp-checked-timer-bridge\","
        "\"checks\":%u,\"failures\":%u,\"status\":\"%s\",\"actual_original_bodies\":2,"
        "\"real_timer_backend\":true,\"direct_callback_return_verified\":true,"
        "\"accepted_event_borrowers_drained\":false,\"execution\":\"native-user-space\","
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
        "\"original_entry_admission\":false}\n", checks, failures, failures ? "failed" : "passed");
    return 0;
}
