// SPDX-License-Identifier: MIT
// Exact original nv.h ABI with explicit PCI/console facts fixtures. No GPU.
#include "nv.h"
#include "os-interface.h"
#include "../src/S540NvidiaGspContext.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
static NvU32 checks;
static void require(NvBool condition, const char *reason) {
    ++checks;
    if (!condition) { fprintf(stderr, "GSP metadata check failed: %s\n", reason); exit(1); }
}
// Functional memory helpers, not RM callback success fixtures.
void *NV_API_CALL os_mem_set(void *out, NvU8 value, NvU32 bytes) {
    volatile NvU8 *target = out;
    while (bytes--) *target++ = value;
    return out;
}
void *NV_API_CALL os_mem_copy(void *out, const void *in, NvU32 bytes) {
    volatile NvU8 *target = out;
    const volatile NvU8 *source = in;
    while (bytes--) *target++ = *source++;
    return out;
}
// No original RM body is supposed to run in this host-context test. Fail
// immediately if a fixture accidentally queues RM work or enters teardown.
void NV_API_CALL rm_execute_work_item(nvidia_stack_t *stack, void *item) {
    (void)stack; (void)item; abort();
}
void NV_API_CALL rm_free_private_state(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
void NV_API_CALL rm_destroy_event_locks(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *stack,
                                               nv_state_t *nv, void *event) {
    (void)stack; (void)nv; (void)event; abort();
}
static S540NvidiaGlobalRmPlatformFacts host_facts(void) {
    S540NvidiaGlobalRmPlatformFacts f = {0};
    f.format = 1; f.known = S540_GLOBAL_FACT_ALL;
    f.cpuCount = 1; f.cpuFrequencyHz = 2000000000ULL;
    f.osMajor = 25; f.osVersion = "native-unit-fixture"; f.osDate = "native-unit-fixture";
    return f;
}
static S540GspDeviceFacts device_facts(void) {
    S540GspDeviceFacts f = {0};
    NvU32 i;
    f.format = 1; f.vendor = 0x10de; f.device = 0x1f91;
    f.subsystemVendor = 0x17aa; f.subsystemDevice = 0x3806;
    f.configuration[0] = 0x1f9110de; f.configuration[11] = 0x380617aa;
    f.segmentKnown = f.pciConfigurationRead = f.barsVerified = f.poweredD0 = NV_TRUE;
    f.intelConsoleVerified = f.noCoherentGpuMemoryProfile = f.nvidiaConsoleExcluded = NV_TRUE;
    f.pciHandle = &checks;
    for (i = 0; i != 3; ++i) {
        f.bars[i].physical = 0x1000000ULL * (i + 1);
        f.bars[i].bytes = 0x100000; f.bars[i].offset = 0x10 + i * 8;
    }
    return f;
}
static NvBool refused_case(NvU32 mode) {
    pid_t child = fork();
    int status = 0;
    if (child < 0) return NV_FALSE;
    if (!child) {
        S540NvidiaGlobalRmPlatformFacts host = host_facts();
        S540GspDeviceFacts facts = device_facts();
        S540GspContext *context = NULL;
        S540NvidiaGlobalRmHostSnapshot snapshot;
        NvU64 address = 91, bytes = 92;
        NvU32 width = 93, height = 94, depth = 95, pitch = 96;
        NvU32 iso = 97, niso = 98;
        nv_state_t *state;
        NvBool preserved;
        if (s540GlobalRmHostInitialize(&host) != NV_OK || s540GspContextCreate(&facts, &context) != NV_OK) _Exit(2);
        state = s540GspContextState(context);
        if (mode == 0) nv_get_screen_info((nv_state_t *)(NvUPtr)1, &address, &width, &height, &depth, &pitch, &bytes);
        if (mode == 1) nv_get_screen_info(state, &address, &width, NULL, &depth, &pitch, &bytes);
        if (mode == 2) nv_get_disp_smmu_stream_ids((nv_state_t *)(NvUPtr)1, &iso, &niso);
        if (mode == 3) nv_get_disp_smmu_stream_ids(state, &iso, NULL);
        preserved = address == 91 && bytes == 92 && width == 93 && height == 94 && depth == 95 && pitch == 96 && iso == 97 && niso == 98;
        s540GlobalRmHostSnapshot(&snapshot);
        preserved = preserved && snapshot.unavailableCalls == 1 && snapshot.liveAllocations == 1;
        preserved = preserved && s540GspContextDestroy(context, NV_TRUE, NULL) == NV_ERR_INVALID_STATE;
        // Failed metadata admission deliberately invalidates this session and
        // retains its owner; it is not reported as successful cleanup.
        _Exit(preserved ? 0 : 3);
    }
    return waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
int main(void) {
    S540NvidiaGlobalRmPlatformFacts host = host_facts();
    S540GspDeviceFacts facts = device_facts(), incomplete;
    S540GspContext *context = NULL, *unchanged = (S540GspContext *)(NvUPtr)1;
    S540GspContextSnapshot final;
    S540NvidiaGlobalRmHostSnapshot snapshot;
    nv_state_t *state;
    NvU64 address = 1, bytes = 2;
    NvU32 width = 3, height = 4, depth = 5, pitch = 6, iso = 7, niso = 8;
    NvU32 i;
    for (i = 0; i != 4; ++i) require(refused_case(i), "unknown owner or missing output preserves values and refuses admission");
    require(s540GlobalRmHostInitialize(&host) == NV_OK, "real tracked host initialized");
    incomplete = facts; incomplete.nvidiaConsoleExcluded = NV_FALSE;
    require(s540GspContextCreate(&incomplete, &unchanged) == NV_ERR_NOT_SUPPORTED && unchanged == (S540GspContext *)(NvUPtr)1, "Intel-only proof cannot exclude a NVIDIA console");
    incomplete = facts; incomplete.intelConsoleVerified = NV_FALSE;
    require(s540GspContextCreate(&incomplete, &unchanged) == NV_ERR_NOT_SUPPORTED, "missing positive Intel console proof refuses");
    require(s540GspContextCreate(&facts, &context) == NV_OK && context, "actual host context binds explicit ownership facts");
    state = s540GspContextState(context);
    require(state && ((NvUPtr)state % 16) == 0, "original state is aligned within its owned allocation");
    nv_get_screen_info(state, &address, &width, &height, &depth, &pitch, &bytes);
    require(!address && !width && !height && !depth && !pitch && !bytes, "bound non-console initializes every original output");
    nv_get_disp_smmu_stream_ids(state, &iso, &niso);
    require(iso == state->iommus.dispIsoStreamId && niso == state->iommus.dispNisoStreamId, "initial stream IDs copy initialized original state");
    state->iommus.dispIsoStreamId = 0x12345678;
    state->iommus.dispNisoStreamId = 0xffffffff;
    nv_get_disp_smmu_stream_ids(state, &iso, &niso);
    require(iso == 0x12345678 && niso == 0xffffffff, "stream callback copies original fields instead of constants");
    s540GlobalRmHostSnapshot(&snapshot);
    require(!snapshot.unavailableCalls && !snapshot.invalidFrees && snapshot.liveAllocations == 1, "valid callbacks preserve clean real host state");
    require(s540GspContextDestroy(context, NV_TRUE, &final) == NV_OK && final.quiescent && !final.quarantined, "normal context fully drains and releases ownership");
    s540GlobalRmHostSnapshot(&snapshot);
    require(!snapshot.liveAllocations && snapshot.allocations == snapshot.frees && !s540DarwinLiveObjects(), "all host, lock and queue resources released");
    require(s540GlobalRmHostShutdown(), "real host clean shutdown");
    printf("{\"format\":1,\"component\":\"nvidia-gsp-context-metadata\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"refusal_cases\":4,\"provider_facts_fixture\":true,\"original_rm_executed\":false,\"ownership_refusals_verified\":true,\"cleanup\":true,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
}
