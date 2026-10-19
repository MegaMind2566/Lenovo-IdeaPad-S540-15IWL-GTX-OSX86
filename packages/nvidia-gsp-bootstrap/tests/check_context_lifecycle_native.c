// SPDX-License-Identifier: MIT
// Real context, host allocator, work queues and timers. Original RM lifecycle
// callbacks are explicit fixtures; no original adapter or GPU is executed.
#include "nv.h"
#include "os-interface.h"
#include "../src/S540NvidiaGspContext.h"
#include "../timers/S540NvidiaGspTimers.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.h"
#include "../../nvidia-device-transport/src/nv_unsupported_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>

static NvU32 checks, privateReleases, eventReleases, detachCalls, nanoCalls;
static NvU32 detachMode, metadataReleases, stackFailures;
static nv_state_t *expectedState;
static nv_nano_timer_t *originalTimer;
static NvBool cryptoRefusalOnInit;
static NvBool originalInitFailure;
static NvBool memoryRefusalOnInit;

static void require(NvBool condition, const char *reason)
{
    ++checks;
    if (!condition) { fprintf(stderr, "GSP context lifecycle failed: %s\n", reason); exit(1); }
}
static NvBool validStack(nvidia_stack_t *stack, nv_state_t *state)
{
    return stack && !((NvUPtr)stack & 15) && state == expectedState &&
        stack->size == sizeof(stack->stack) && stack->top == stack->stack + stack->size;
}
NvBool s540GlobalRmIsInitialized(void) { return NV_TRUE; }
NvBool NV_API_CALL rm_init_event_locks(nvidia_stack_t *stack, nv_state_t *state)
{
    return validStack(stack, state) &&
        s540Darwin_os_alloc_spinlock(&state->event_spinlock) == NV_OK;
}
NV_STATUS NV_API_CALL rm_is_supported_device(nvidia_stack_t *stack, nv_state_t *state)
{
    return validStack(stack, state) ? NV_OK : NV_ERR_INVALID_STATE;
}
NvBool NV_API_CALL rm_init_private_state(nvidia_stack_t *stack, nv_state_t *state)
{
    if (!validStack(stack, state)) return NV_FALSE;
    state->priv = s540GlobalRmHostAllocate(128);
    return state->priv != NULL;
}
NvBool NV_API_CALL rm_init_adapter(nvidia_stack_t *stack, nv_state_t *state)
{
    if (originalInitFailure && validStack(stack, state)) return NV_FALSE;
    if (memoryRefusalOnInit && validStack(stack, state)) {
        NvU64 address = 0x1000;
        void *output = (void *)(NvUPtr)0x1111;
        if (nv_register_phys_pages(state, &address, 1, 0, &output) != NV_ERR_NOT_SUPPORTED ||
            output != (void *)(NvUPtr)0x1111) abort();
        s540DeviceMemoryResetStatistics();
        return NV_TRUE;
    }
    if (!cryptoRefusalOnInit || !validStack(stack, state)) abort();
    // Explicit apparent-success fixture. The genuine unsupported crypto
    // boundary must invalidate admission even though this body returns true.
    if (s540Global_libspdm_x509_verify_cert_chain(NULL, 0, NULL, 0)) abort();
    return NV_TRUE;
}
void NV_API_CALL rm_execute_work_item(nvidia_stack_t *stack, void *item)
{
    (void)stack; (void)item; abort();
}
void NV_API_CALL rm_free_private_state(nvidia_stack_t *stack, nv_state_t *state)
{
    NvU64 physical = 1, bytes = 2;
    NvU32 width = 3, height = 4, depth = 5, pitch = 6;
    if (!validStack(stack, state) || !state->priv) abort();
    // Destruction still has its real timer binding and published metadata.
    nv_get_screen_info(state, &physical, &width, &height, &depth, &pitch, &bytes);
    if (physical || width || height || depth || pitch || bytes) abort();
    if (s540Darwin_os_is_queue_flush_ongoing(NULL)) abort();
    ++metadataReleases;
    nv_destroy_nano_timer(state, originalTimer); originalTimer = NULL;
    s540GlobalRmHostFree(state->priv); state->priv = NULL;
    ++privateReleases;
}
void NV_API_CALL rm_destroy_event_locks(nvidia_stack_t *stack, nv_state_t *state)
{
    if (!validStack(stack, state) || !state->event_spinlock || privateReleases != 1) abort();
    s540Darwin_os_free_spinlock(state->event_spinlock);
    state->event_spinlock = NULL;
    ++eventReleases;
}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *stack, nv_state_t *state)
{
    (void)stack; (void)state; abort();
}
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *stack,
                                                nv_state_t *state, void *event)
{
    if (!validStack(stack, state) || event != &checks)
        __atomic_add_fetch(&stackFailures, 1U, __ATOMIC_RELAXED);
    __atomic_add_fetch(&nanoCalls, 1U, __ATOMIC_RELAXED);
    return NV_OK;
}
static NV_STATUS detach(void *owner, void *opaque, void *dma)
{
    nv_state_t *state = opaque;
    NvU32 iso = 1, niso = 2;
    ++detachCalls;
    if (owner != &detachMode || state != expectedState || !dma || state->priv ||
        state->event_spinlock || privateReleases != 1 || eventReleases != 1)
        return NV_ERR_INVALID_STATE;
    // Metadata/global queue identity remain callable until successful detach.
    nv_get_disp_smmu_stream_ids(state, &iso, &niso);
    if (iso != state->iommus.dispIsoStreamId || niso != state->iommus.dispNisoStreamId ||
        s540Darwin_os_is_queue_flush_ongoing(NULL)) return NV_ERR_INVALID_STATE;
    if (detachMode == 1) return NV_ERR_IN_USE;
    if (detachMode == 2) return NV_OK; // Invalid positive claim must not free.
    return s540GspTimersUnbind(state);
}
static S540NvidiaGlobalRmPlatformFacts hostFacts(void)
{
    S540NvidiaGlobalRmPlatformFacts facts = {0};
    facts.format = 1; facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1; facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25; facts.osVersion = "native-lifecycle-fixture";
    facts.osDate = "native-lifecycle-fixture";
    return facts;
}
static S540GspDeviceFacts deviceFacts(void)
{
    S540GspDeviceFacts facts = {0};
    NvU32 i;
    facts.format = 1; facts.vendor = 0x10de; facts.device = 0x1f91;
    facts.subsystemVendor = 0x17aa; facts.subsystemDevice = 0x3806;
    facts.configuration[0] = 0x1f9110de; facts.configuration[11] = 0x380617aa;
    facts.configuration[2] = 0xa1;
    facts.segmentKnown = facts.pciConfigurationRead = facts.barsVerified = facts.poweredD0 = NV_TRUE;
    facts.intelConsoleVerified = facts.nvidiaConsoleExcluded = facts.noCoherentGpuMemoryProfile = NV_TRUE;
    facts.pciHandle = &checks;
    for (i = 0; i != 3; ++i) {
        facts.bars[i].physical = 0x1000000ULL * (i + 1);
        facts.bars[i].bytes = 0x100000; facts.bars[i].offset = 0x10 + i * 8;
    }
    return facts;
}
static NvBool cryptoRefusedCase(NvU32 mode)
{
    pid_t child = fork();
    int result = 0;
    if (child < 0) return NV_FALSE;
    if (!child) {
        S540NvidiaGlobalRmPlatformFacts host = hostFacts();
        S540GspDeviceFacts facts = deviceFacts();
        S540GspContext *context = NULL;
        S540GspContextSnapshot contextState;
        S540NvidiaGlobalRmHostSnapshot hostState;
        S540NvidiaGlobalCryptoSnapshot crypto;
        S540GspContextDetacher detacher = { &detachMode, detach };
        if (s540GlobalRmHostInitialize(&host) != NV_OK) _Exit(2);
        if (mode == 0) {
            (void)s540Global_libspdm_x509_verify_cert_chain(NULL, 0, NULL, 0);
            if (s540GspContextCreate(&facts, &context) != NV_ERR_NOT_SUPPORTED || context) _Exit(3);
        } else {
            if (s540GspContextCreate(&facts, &context) != NV_OK) _Exit(4);
            expectedState = s540GspContextState(context);
            if (s540GspContextSetDetacher(context, &detacher) != NV_OK ||
                s540GspContextPrepare(context) != NV_OK) _Exit(5);
            cryptoRefusalOnInit = mode == 1;
            originalInitFailure = mode == 2;
            if (s540GspContextInitializeAdapter(context) !=
                    (mode == 2 ? NV_ERR_NOT_READY : NV_ERR_INVALID_STATE)) _Exit(6);
            s540GspContextSnapshot(context, &contextState);
            if (!contextState.adapterAttempted ||
                contextState.adapterInitialized != (mode == 1) ||
                (mode == 2 && (!contextState.quarantined ||
                    s540GspContextReleaseOriginalState(context, NV_TRUE) != NV_ERR_INVALID_STATE)) ||
                s540GspContextDestroy(context, NV_TRUE, NULL) != NV_ERR_INVALID_STATE) _Exit(7);
        }
        s540GlobalRmHostSnapshot(&hostState);
        s540Global_crypto_snapshot(&crypto);
        if (mode == 2) {
            _Exit(hostState.liveAllocations && !hostState.unavailableCalls &&
                !hostState.invalidFrees && !crypto.unavailable_calls &&
                !privateReleases && !eventReleases && !detachCalls ? 0 : 9);
        }
        // The host itself stayed clean; a genuine high-mask crypto refusal is
        // the sole reason the apparent original success cannot be admitted.
        _Exit(!hostState.unavailableCalls && !hostState.invalidFrees &&
              crypto.unavailable_calls == 1 && crypto.unavailable_symbol_mask_high &&
              !crypto.counter_overflow ? 0 : 8);
    }
    return waitpid(child, &result, 0) == child && WIFEXITED(result) && WEXITSTATUS(result) == 0;
}
static NvBool memoryRefusedCase(NvU32 mode)
{
    pid_t child = fork();
    int result = 0;
    if (child < 0) return NV_FALSE;
    if (!child) {
        S540NvidiaGlobalRmPlatformFacts host = hostFacts();
        S540GspDeviceFacts facts = deviceFacts();
        S540GspContext *context = NULL;
        S540GspContextSnapshot captured;
        S540GspContextDetacher detacher = { &detachMode, detach };
        NvU64 address = 0x1000;
        void *output = (void *)(NvUPtr)0x1111;
        if (s540GlobalRmHostInitialize(&host) != NV_OK) _Exit(2);
        if (mode == 0) {
            (void)nv_register_phys_pages(NULL, &address, 1, 0, &output);
            s540DeviceMemoryResetStatistics();
            _Exit(s540DeviceMemoryStatistics().unavailableOperationsEver == 1 &&
                s540GspContextCreate(&facts, &context) == NV_ERR_NOT_SUPPORTED && !context ? 0 : 3);
        }
        if (s540GspContextCreate(&facts, &context) != NV_OK) _Exit(4);
        expectedState = s540GspContextState(context);
        if (s540GspContextSetDetacher(context, &detacher) != NV_OK ||
            s540GspContextPrepare(context) != NV_OK) _Exit(5);
        if (mode == 1) {
            (void)nv_register_phys_pages(expectedState, &address, 1, 0, &output);
            s540DeviceMemoryResetStatistics();
        } else if (mode == 2) memoryRefusalOnInit = NV_TRUE;
        else expectedState->pci_cfg_space[2] = 0xa2;
        if (s540GspContextInitializeAdapter(context) !=
            (mode == 3 ? NV_ERR_NOT_SUPPORTED : NV_ERR_INVALID_STATE)) _Exit(6);
        s540GspContextSnapshot(context, &captured);
        if (mode == 3) _Exit(!captured.adapterAttempted && !captured.adapterInitialized ? 0 : 7);
        if (s540DeviceMemoryStatistics().unavailableOperationsEver != 1 ||
            s540DeviceMemoryStatistics().unavailableOperations != 0) _Exit(8);
        if (mode == 1) _Exit(!captured.adapterAttempted && !captured.adapterInitialized &&
            s540GspContextDestroy(context, NV_TRUE, NULL) == NV_ERR_INVALID_STATE ? 0 : 9);
        _Exit(captured.adapterAttempted && captured.adapterInitialized && captured.quarantined &&
            s540GspContextDestroy(context, NV_TRUE, NULL) == NV_ERR_INVALID_STATE ? 0 : 10);
    }
    return waitpid(child, &result, 0) == child && WIFEXITED(result) && WEXITSTATUS(result) == 0;
}
int main(void)
{
    S540NvidiaGlobalRmPlatformFacts host = hostFacts();
    S540GspDeviceFacts facts = deviceFacts();
    S540GspContext *context = NULL;
    S540GspContextSnapshot snapshot;
    S540GspTimersSnapshot timers;
    S540NvidiaGlobalRmHostSnapshot allocation;
    S540GspContextDetacher detacher = { &detachMode, detach };
    unsigned i;
    require(cryptoRefusedCase(0), "earlier lifetime crypto refusal blocks a later context despite a clean host");
    require(cryptoRefusedCase(1), "crypto refusal during apparent adapter success invalidates admission and retains owner");
    require(cryptoRefusedCase(2), "failed original Boolean cannot authorize private state or backing destruction");
    require(memoryRefusedCase(0), "memory refusal survives native telemetry reset and blocks context creation");
    require(memoryRefusedCase(1), "memory refusal before adapter entry survives reset and retains context");
    require(memoryRefusedCase(2), "ignored memory refusal during apparent adapter success quarantines the context");
    require(memoryRefusedCase(3), "actual feature preflight rejects changed captured revision before original entry");
    require(s540GlobalRmHostInitialize(&host) == NV_OK, "tracked host starts");
    require(s540GspContextCreate(&facts, &context) == NV_OK, "real context starts");
    expectedState = s540GspContextState(context);
    require(expectedState != NULL, "retained original state is addressable");
    require(s540GspContextPrepare(context) == NV_ERR_INVALID_STATE, "original entry requires an operational detacher");
    require(s540GspContextSetDetacher(context, &detacher) == NV_OK, "owner registers real detach operations");
    require(s540GspContextSetDetacher(context, &detacher) == NV_ERR_INVALID_STATE, "detacher cannot be replaced");
    require(s540GspContextPrepare(context) == NV_OK, "typed original fixtures acquire real resources");
    require(s540GspContextValidateDmaStopReceipt(expectedState, context, 1, NULL) ==
            NV_ERR_INVALID_ARGUMENT, "DMA stop proof cannot be omitted");
    require(s540GspContextValidateDmaStopReceipt(expectedState, context, 1,
            (const S540GspDmaStopReceipt *)(NvUPtr)1) == NV_ERR_NOT_SUPPORTED,
            "unissued caller pointer cannot authorize hardware DMA retirement");
    require(s540GspTimersBind(expectedState) == NV_OK, "real timer binding owns original state");
    nv_create_nano_timer(expectedState, &checks, &originalTimer);
    require(originalTimer != NULL, "original timer handle acquired");
    nv_start_nano_timer(expectedState, originalTimer, 1000000ULL);
    for (i = 0; i < 3000 && !__atomic_load_n(&nanoCalls, __ATOMIC_RELAXED); ++i) usleep(1000);
    require(nanoCalls == 1 && !stackFailures, "actual worker invokes typed callback on independent stack");
    nv_start_nano_timer(expectedState, originalTimer, 60000000000ULL);
    require(nv_start_rc_timer(expectedState) == 0 && expectedState->rc_timer_enabled,
            "pending real timers exist before release");
    require(s540GspContextReleaseOriginalState(context, NV_FALSE) == NV_ERR_INVALID_STATE,
            "unconfirmed IRQ drain preserves original resources");
    require(!privateReleases && !eventReleases, "failed admission runs no destructor");
    require(s540GspContextReleaseOriginalState(context, NV_TRUE) == NV_OK,
            "release drains actual timers before original destructors");
    s540GspContextSnapshot(context, &snapshot);
    require(snapshot.originalReleased && snapshot.workStopped && !snapshot.finalDetach &&
            !snapshot.quiescent && !snapshot.quarantined, "released original state retains external ownership phase");
    s540GspTimersGetSnapshot(&timers);
    require(timers.bound && timers.stopped && !timers.liveNanoTimers &&
            !timers.quarantined && !expectedState->rc_timer_enabled,
            "stopped timer binding survives with live nv_state until actual unbind");
    require(privateReleases == 1 && eventReleases == 1 && metadataReleases == 1 &&
            !expectedState->priv && !expectedState->event_spinlock,
            "original resources are destroyed once while metadata is bound");
    require(s540GspContextReleaseOriginalState(context, NV_TRUE) == NV_OK &&
            privateReleases == 1 && eventReleases == 1, "release is idempotent");
    detachMode = 1;
    require(s540GspContextDestroy(context, NV_TRUE, &snapshot) == NV_ERR_IN_USE &&
            !snapshot.quarantined && !snapshot.finalDetach, "recoverable detach refusal retains owner for retry");
    detachMode = 2;
    require(s540GspContextDestroy(context, NV_TRUE, &snapshot) == NV_ERR_IN_USE &&
            !snapshot.quarantined && !snapshot.finalDetach,
            "positive detacher claim cannot bypass real bound timer service");
    s540GlobalRmHostSnapshot(&allocation);
    require(allocation.liveAllocations >= 2 && !allocation.invalidFrees &&
            !allocation.unavailableCalls, "refused finalization retains valid original and timer storage");
    detachMode = 3;
    require(s540GspContextDestroy(context, NV_TRUE, &snapshot) == NV_OK &&
            snapshot.originalReleased && snapshot.finalDetach && snapshot.quiescent,
            "real timer unbind completes before final original-state free");
    s540GspTimersGetSnapshot(&timers);
    s540GlobalRmHostSnapshot(&allocation);
    require(detachCalls == 3 && !timers.bound && !allocation.liveAllocations &&
            allocation.allocations == allocation.frees && !s540DarwinLiveObjects(),
            "all retries and successful teardown release real resources exactly once");
    require(s540GlobalRmHostShutdown(), "tracked host shuts down cleanly");
    printf("{\"format\":1,\"component\":\"nvidia-gsp-context-lifecycle\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"real_timer_binding\":true,\"recoverable_detach_refusals\":2,\"crypto_lifetime_refusals\":2,\"original_rm_executed\":false,\"callback_fixture\":true,\"cleanup\":true,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
}
