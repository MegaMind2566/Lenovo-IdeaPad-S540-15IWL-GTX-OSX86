// SPDX-License-Identifier: MIT
// Full pinned NVIDIA ABI with explicit RM callback fixtures, never a GPU test.
#include "nv.h"
#include "os-interface.h"
#include "../S540NvidiaGspTimers.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
static unsigned checks;
static NvU32 hostObjects, unavailable, callbackErrors, rcCalls, nanoCalls;
static NvU32 failHost, blockNano, nanoEntered, releaseNano;
static NvU32 selfCancel;
static nv_nano_timer_t *selfHandle;
static nv_state_t *expectedNv;
static void *expectedEvent;
static void require(NvBool value, const char *reason) {
    ++checks;
    if (!value) { fprintf(stderr, "GSP timer check failed: %s\n", reason); exit(1); }
}
void *s540GlobalRmHostAllocate(NvU64 bytes) {
    void *result;
    if (__atomic_exchange_n(&failHost, 0U, __ATOMIC_RELAXED)) return NULL;
    result = calloc(1, (size_t)bytes);
    if (result) __atomic_fetch_add(&hostObjects, 1U, __ATOMIC_RELAXED);
    return result;
}
void s540GlobalRmHostFree(void *pointer) {
    if (pointer) { free(pointer); __atomic_fetch_sub(&hostObjects, 1U, __ATOMIC_RELAXED); }
}
void s540GlobalRmRecordUnavailable(NvU32 service) {
    (void)service; __atomic_fetch_add(&unavailable, 1U, __ATOMIC_RELAXED);
}
void *NV_API_CALL os_mem_set(void *output, NvU8 byte, NvU32 count) {
    volatile NvU8 *target = output;
    while (count--) *target++ = byte;
    return output;
}
static NvBool valid_stack(nvidia_stack_t *stack, nv_state_t *nv) {
    return stack && ((NvUPtr)stack % 16) == 0 && nv == expectedNv && stack->size == sizeof(stack->stack) && stack->top == stack->stack + stack->size;
}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *stack, nv_state_t *nv) {
    if (!valid_stack(stack, nv) || !nv->rc_timer_enabled) __atomic_fetch_add(&callbackErrors, 1U, __ATOMIC_RELAXED);
    __atomic_fetch_add(&rcCalls, 1U, __ATOMIC_RELAXED);
    return NV_OK;
}
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *stack, nv_state_t *nv, void *event) {
    if (!valid_stack(stack, nv) || event != expectedEvent) __atomic_fetch_add(&callbackErrors, 1U, __ATOMIC_RELAXED);
    __atomic_fetch_add(&nanoEntered, 1U, __ATOMIC_RELAXED);
    if (selfCancel) nv_cancel_nano_timer(nv, selfHandle);
    while (__atomic_load_n(&blockNano, __ATOMIC_RELAXED) && !__atomic_load_n(&releaseNano, __ATOMIC_RELAXED)) usleep(1000);
    __atomic_fetch_add(&nanoCalls, 1U, __ATOMIC_RELAXED);
    return NV_OK;
}
static NvBool wait_for(NvU32 *value, NvU32 count) {
    unsigned i;
    for (i = 0; i < 3000 && __atomic_load_n(value, __ATOMIC_RELAXED) < count; ++i) usleep(1000);
    return __atomic_load_n(value, __ATOMIC_RELAXED) == count;
}
static NvBool quarantine_child(void) {
    pid_t child = fork();
    int status = 0;
    if (child < 0) return NV_FALSE;
    if (child == 0) {
        nv_state_t *nv = calloc(1, sizeof(*nv));
        S540GspTimersSnapshot snapshot;
        NvBool valid;
        expectedNv = nv; expectedEvent = &checks; selfCancel = 1;
        if (!nv || s540GspTimersBind(nv) != NV_OK) _Exit(2);
        nv_create_nano_timer(nv, expectedEvent, &selfHandle);
        if (!selfHandle) _Exit(3);
        nv_start_nano_timer(nv, selfHandle, 0);
        if (!wait_for(&nanoCalls, 1)) _Exit(4);
        s540GspTimersGetSnapshot(&snapshot);
        valid = snapshot.quarantined && snapshot.cancellationFailures == 1 && snapshot.liveNanoTimers == 1;
        valid = valid && s540GspTimersUnbind(nv) != NV_OK;
        s540GspTimersGetSnapshot(&snapshot);
        valid = valid && snapshot.bound && snapshot.quarantined && __atomic_load_n(&hostObjects, __ATOMIC_RELAXED) >= 2 && s540DarwinLiveObjects() >= 3;
        // This failure profile deliberately retains an unsafe-to-release
        // binding. Process exit disposes the isolated fixture; it is not
        // presented as a successful cleanup or leak-free kernel path.
        _Exit(valid ? 0 : 5);
    }
    return waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
int main(void) {
    nv_state_t *nv = calloc(1, sizeof(*nv));
    nv_state_t *other = calloc(1, sizeof(*other));
    nv_nano_timer_t *nano = NULL;
    S540GspTimersSnapshot snapshot;
    require(quarantine_child(), "failed real self-cancellation retains callback data and quarantines session");
    require(nv && other, "native device-state fixtures allocated");
    expectedNv = nv; expectedEvent = &checks;
    require(s540GspTimersBind(NULL) == NV_ERR_INVALID_ARGUMENT, "null binding refused");
    __atomic_store_n(&failHost, 1U, __ATOMIC_RELAXED);
    require(s540GspTimersBind(nv) == NV_ERR_NO_MEMORY && !hostObjects, "bind host allocation failure");
    require(s540GspTimersBind(nv) == NV_OK, "real timer binding created");
    require(s540GspTimersBind(nv) == NV_ERR_IN_USE, "duplicate bind refused");
    require(nv->rc_timer_enabled == 0, "RC flag initially disabled");
    require(nv_start_rc_timer(other) == -1, "foreign RC device refused");
    require(nv_stop_rc_timer(nv) == -1, "disabled RC timer stop reports original refusal");
    require(nv_start_rc_timer(nv) == 0 && nv->rc_timer_enabled == 1, "original RC enable flag set");
    require(nv_start_rc_timer(nv) == -1, "duplicate RC start refused");
    require(wait_for(&rcCalls, 1), "actual ordinary worker invoked typed RC callback fixture");
    require(nv_stop_rc_timer(nv) == 0 && !nv->rc_timer_enabled, "RC stop drains and clears flag");
    require(rcCalls == 1 && callbackErrors == 0, "RC callback received separate initialized heap stack");
    __atomic_store_n(&failHost, 1U, __ATOMIC_RELAXED);
    nv_create_nano_timer(nv, expectedEvent, &nano);
    require(nano == NULL, "nano host allocation failure preserves null output");
    nv_create_nano_timer(other, expectedEvent, &nano);
    require(nano == NULL, "foreign nano device refused");
    nv_create_nano_timer(nv, expectedEvent, &nano);
    require(nano != NULL, "nano timer created");
    s540GspTimersGetSnapshot(&snapshot);
    require(snapshot.bound && snapshot.liveNanoTimers == 1 && !snapshot.quarantined, "private nano ownership tracked");
    nv_start_nano_timer(nv, nano, 1000000ULL);
    require(wait_for(&nanoCalls, 1), "typed nano callback invoked");
    require(callbackErrors == 0, "nano callback received independent initialized heap stack");
    __atomic_store_n(&failHost, 1U, __ATOMIC_RELAXED);
    nv_start_nano_timer(nv, nano, 1000000ULL);
    {
        unsigned i;
        for (i = 0; i < 3000; ++i) {
            s540GspTimersGetSnapshot(&snapshot);
            if (snapshot.callbackFailures) break;
            usleep(1000);
        }
    }
    require(snapshot.callbackFailures == 1 && nanoCalls == 1, "callback stack allocation failure never calls RM with a null or shared stack");
    require(!snapshot.quarantined, "failed callback allocation leaves cancellable owned timer");
    nv_start_nano_timer(nv, nano, 60000000000ULL);
    nv_cancel_nano_timer(nv, nano);
    require(nanoCalls == 1, "pending nano callback cancelled synchronously");
    nv_start_nano_timer(nv, nano, 1000000ULL);
    require(wait_for(&nanoCalls, 2), "nano timer rearms after cancellation");
    nv_destroy_nano_timer(nv, nano); nano = NULL;
    s540GspTimersGetSnapshot(&snapshot);
    require(snapshot.liveNanoTimers == 0, "destroy releases nano ownership");
    nv_create_nano_timer(nv, expectedEvent, &nano);
    require(nano != NULL, "leftover original timer created for session drain");
    nv_start_nano_timer(nv, nano, 60000000000ULL);
    require(s540GspTimersStop(nv) == NV_OK, "session stop synchronously cancels every timer");
    s540GspTimersGetSnapshot(&snapshot);
    require(snapshot.stopped && snapshot.liveNanoTimers == 1 && !snapshot.quarantined, "stopped session retains original timer handle until release");
    require(nv_start_rc_timer(nv) == -1, "stopped session rejects RC rearm");
    nv_start_nano_timer(nv, nano, 0);
    require(nanoCalls == 2, "stopped session never dispatches rejected nano work");
    nv_destroy_nano_timer(nv, nano);
    require(s540GspTimersUnbind(nv) == NV_OK, "unbind after original RM relinquishes handles");
    s540GspTimersGetSnapshot(&snapshot);
    require(!snapshot.bound && !hostObjects && !s540DarwinLiveObjects(), "complete timer and host cleanup");
    require(s540GspTimersBind(nv) == NV_OK && s540GspTimersUnbind(nv) == NV_OK, "session can be rebound after clean teardown");
    require(!hostObjects && !s540DarwinLiveObjects() && callbackErrors == 0, "no callback or allocation resources leaked");
    free(other); free(nv);
    printf("{\"component\":\"nvidia-gsp-timers\",\"format\":1,\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"rc_callbacks\":%u,\"nano_callbacks\":%u,\"callback_fixture\":true,\"stack_abi_verified\":true,\"quarantine_retention_verified\":true,\"cleanup\":true,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks, rcCalls, nanoCalls);
    return 0;
}
