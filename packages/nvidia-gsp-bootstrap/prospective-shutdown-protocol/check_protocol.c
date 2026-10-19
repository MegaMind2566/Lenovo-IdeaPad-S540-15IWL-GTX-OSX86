/* SPDX-License-Identifier: MIT */
/* CPU controls with actual NVIDIA layouts. All hardware, record, thread,
 * runtime and lock endpoints below are explicit fixtures, not native evidence. */
#include "nv.h"
#include "nv-priv.h"
#include "osapi.h"
#include "gpu/gpu.h"
#include "gpu/gsp/kernel_gsp.h"
#include "core/locks.h"
#include "core/thread_state.h"
#include "rmapi/rmapi.h"
#include "S540NvidiaShutdownProtocol.h"
#include "../prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static nv_state_t state;
static nv_priv_t privateState;
static OBJGPU gpu, replacementGpu;
static KernelGsp gsp;
static nvidia_stack_t controlStack;
static unsigned scenario, checks, failures, snapshots, captures, errors;
static unsigned runtimeDepth, threadDepth, apiDepth, gpuDepth;
static unsigned apiAcquired, apiReleased, gpuAcquired, gpuReleased, unloaded, suspended;
static NvU64 generation = 71;
static NV_STATUS sticky;
static int actualOwner, replacementOwner;
void *memset(void *address, int value, size_t bytes)
{ NvU8 *p = address; while (bytes--) *p++ = (NvU8)value; return address; }

static void expect(NvBool value, const char *why)
{
    ++checks;
    if (!value) { ++failures; fprintf(stderr, "shutdown protocol: %s\n", why); }
}
NvBool s540Darwin_os_semaphore_may_sleep(void) { return NV_TRUE; }
NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out)
{ *out = scenario == 6 ? 82 : 81; return NV_OK; }
NV_STATUS s540FirstTxnGetSnapshot(const void *nv, S540FirstTxnSnapshot *out)
{
    if (nv != &state) return NV_ERR_INVALID_ARGUMENT;
    memset(out, 0, sizeof(*out));
    ++snapshots;
    out->generation = generation;
    out->masterThread = 81;
    out->phase = S540_FIRST_OP;
    out->originalReturned = scenario != 4;
    out->originalExitReady = NV_TRUE;
    out->firstStatus = sticky;
    return NV_OK;
}
NV_STATUS s540FirstTxnHostCaptureAllocation(S540FirstTxnHostIdentity *out)
{
    ++captures;
    if (scenario == 18) return NV_ERR_NO_MEMORY;
    out->generation = generation + (scenario == 5 ? 1 : 0);
    out->owner = scenario == 15 && gpuDepth ? &replacementOwner : &actualOwner;
    return NV_OK;
}
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *nv)
{
    if (nv != &state) return NV_ERR_INVALID_ARGUMENT;
    if (scenario == 1) return NV_ERR_NOT_SUPPORTED;
    return apiDepth || gpuDepth ? NV_ERR_INVALID_LOCK_STATE : NV_OK;
}
void s540FirstTxnObserveServiceRefusal(NvU32 domain, NvU32 symbol, NV_STATUS status)
{
    if (domain != 0x534450U || !symbol || status == NV_OK) ++errors;
    if (sticky == NV_OK) sticky = status;
}
NV_STATUS s540GspCancellationBeginCleanupState(const void *nv)
{
    if (nv != &state || runtimeDepth != 1 || threadDepth != 1 || apiDepth || gpuDepth) ++errors;
    return scenario == 21 ? NV_ERR_INVALID_STATE : NV_OK;
}
NV_STATUS s540GspCancellationCheckState(const void *nv)
{ if (nv != &state) ++errors; return scenario == 22 ? NV_ERR_TIMEOUT : NV_OK; }
NV_STATUS rmapiLockAcquire(NvU32 flags, NvU32 module)
{
    if (flags != API_LOCK_FLAGS_NONE || module != RM_LOCK_MODULES_DESTROY ||
        runtimeDepth != 1 || threadDepth != 1 || apiDepth || gpuDepth) ++errors;
    if (scenario == 7) return NV_ERR_TIMEOUT;
    ++apiDepth; ++apiAcquired;
    if (scenario == 9) privateState.pGpu = &replacementGpu;
    return NV_OK;
}
void rmapiLockRelease(void)
{
    if (apiDepth != 1 || gpuDepth) ++errors;
    if (scenario == 13 && sticky != NV_ERR_INVALID_LOCK_STATE) ++errors;
    --apiDepth; ++apiReleased;
}
NV_STATUS rmGpuLocksAcquire(NvU32 flags, NvU32 module)
{
    if (flags != GPUS_LOCK_FLAGS_NONE || module != RM_LOCK_MODULES_DESTROY ||
        apiDepth != 1 || gpuDepth) ++errors;
    if (scenario == 8) return NV_ERR_TIMEOUT;
    ++gpuDepth; ++gpuAcquired;
    if (scenario == 10) ++generation;
    return NV_OK;
}
NV_STATUS rmGpuLocksRelease(NvU32 flags, OBJGPU *unused)
{
    if (flags != GPUS_LOCK_FLAGS_NONE || unused || gpuDepth != 1 || apiDepth != 1) ++errors;
    if ((scenario == 11 || scenario == 12) && sticky == NV_OK) ++errors;
    --gpuDepth; ++gpuReleased;
    if (scenario == 14) sticky = NV_ERR_NOT_SUPPORTED;
    return scenario == 13 ? NV_ERR_INVALID_LOCK_STATE : NV_OK;
}
static void fixtureThreadInit(THREAD_STATE_NODE *node, NvU32 flags)
{ (void)node; if (flags != THREAD_STATE_FLAGS_NONE || runtimeDepth != 1) ++errors; ++threadDepth; }
static void fixtureThreadFree(THREAD_STATE_NODE *node, NvU32 flags)
{ (void)node; if (flags != THREAD_STATE_FLAGS_NONE || threadDepth != 1 || apiDepth || gpuDepth) ++errors; --threadDepth; }
static NV_STATUS fixtureUnload(OBJGPU *exactGpu, NvU32 flags)
{
    ++unloaded;
    if (exactGpu != &gpu || flags != GPU_STATE_FLAGS_FAST_UNLOAD ||
        apiDepth != 1 || gpuDepth != 1) ++errors;
    return scenario == 11 ? NV_ERR_GENERIC : NV_OK;
}
static NV_STATUS fixtureSuspend(OBJGPU *exactGpu, KernelGsp *exactGsp,
    KernelGspUnloadMode mode, NvU32 flags)
{
    ++suspended;
    if (exactGpu != &gpu || exactGsp != &gsp || mode != KGSP_UNLOAD_MODE_NORMAL ||
        flags != GPU_STATE_FLAGS_FAST_UNLOAD || !unloaded || apiDepth != 1 || gpuDepth != 1) ++errors;
    if (scenario == 19) privateState.pGpu = &replacementGpu;
    return scenario == 12 ? NV_ERR_TIMEOUT : NV_OK;
}
static NvBool fixtureIsGspClient(OBJGPU *p) { return p == &gpu && scenario != 23; }
static KernelGsp *fixtureGetGsp(OBJGPU *p) { return p == &gpu ? &gsp : NULL; }
#undef NV_PRINTF
#define NV_PRINTF(...) ((void)0)
#undef gpuStateUnload
#define gpuStateUnload fixtureUnload
#undef kgspUnloadRm
#define kgspUnloadRm fixtureSuspend
#undef IS_GSP_CLIENT
#define IS_GSP_CLIENT fixtureIsGspClient
#undef GPU_GET_KERNEL_GSP
#define GPU_GET_KERNEL_GSP fixtureGetGsp
/* Byte-exact complete gpuEnterShutdown_IMPL body from the frozen source. */
#include "actual-gpu-enter-shutdown.inc"

#undef NV_ENTER_RM_RUNTIME
#define NV_ENTER_RM_RUNTIME(s, f) do { if ((s) != &controlStack || runtimeDepth) ++errors; (f) = NULL; ++runtimeDepth; } while (0)
#undef NV_EXIT_RM_RUNTIME
#define NV_EXIT_RM_RUNTIME(s, f) do { if ((s) != &controlStack || (f) || runtimeDepth != 1 || threadDepth) ++errors; --runtimeDepth; } while (0)
#undef threadStateInit
#define threadStateInit fixtureThreadInit
#undef threadStateFree
#define threadStateFree fixtureThreadFree
/* The actual successor bridge, unmodified, in this fixture translation unit. */
#include "S540NvidiaShutdownProtocol.c"

int main(int argc, char **argv)
{
    S540ShutdownProtocolEvidence evidence;
    NV_STATUS status, expectedStatus;
    nv_state_t *input = &state;
    if (argc != 2) return 2;
    scenario = (unsigned)strtoul(argv[1], NULL, 10);
    if (scenario > 23) return 2;
    state.priv = &privateState;
    privateState.pGpu = &gpu;
    gpu.pOsGpuInfo = &state;
    privateState.flags = NV_INIT_FLAG_GPU_STATE | NV_INIT_FLAG_GPU_STATE_LOAD;
    if (scenario == 2) sticky = NV_ERR_NO_MEMORY;
    if (scenario == 3) input = (nv_state_t *)(NvUPtr)0x1000;
    if (scenario == 16) privateState.flags = NV_INIT_FLAG_GPU_STATE;
    if (scenario == 17) gpu.pOsGpuInfo = NULL;
    memset(&evidence, 0, sizeof(evidence));
    status = s540ShutdownProtocolRun(&controlStack, input, scenario == 20 ? NULL : &evidence);
    expectedStatus = scenario == 0 ? NV_OK :
        scenario == 1 || scenario == 14 ? NV_ERR_NOT_SUPPORTED :
        scenario == 2 || scenario == 18 ? NV_ERR_NO_MEMORY :
        scenario == 3 || scenario == 20 ? NV_ERR_INVALID_ARGUMENT :
        scenario == 4 ? NV_ERR_NOT_READY :
        scenario == 7 || scenario == 8 || scenario == 12 || scenario == 22 ? NV_ERR_TIMEOUT :
        scenario == 11 ? NV_ERR_GENERIC :
        scenario == 13 ? NV_ERR_INVALID_LOCK_STATE : NV_ERR_INVALID_STATE;
    expect(status == expectedStatus, "real status or exact refusal reaches caller");
    expect(!errors && !runtimeDepth && !threadDepth && !apiDepth && !gpuDepth,
        "runtime/thread/API/GPU boundaries balance and preserve exact order");
    expect(apiAcquired == apiReleased && gpuAcquired == gpuReleased,
        "every acquired lock token is released once");
    if (scenario != 20) {
        const NvBool claimed = (scenario >= 7 && scenario <= 15) || scenario == 19 || scenario == 0 || (scenario >= 21 && scenario <= 22);
        const NvBool entered = scenario == 0 || (scenario >= 11 && scenario <= 14) || scenario == 19;
        expect(evidence.format == 1 && evidence.operationStatus == status &&
            evidence.sourceProfileSha256 && strlen(evidence.sourceProfileSha256) == 64,
            "evidence preserves real result and immutable source-profile digest");
        expect(evidence.claimed == claimed && evidence.originalEntered == entered &&
            evidence.originalReturned == entered, "no preflight failure claims original execution");
        expect(unloaded == (NvU32)entered && suspended == (NvU32)(entered && scenario != 11),
            "actual original body stops before GSP on engine-unload failure");
        if (claimed) {
            expect(evidence.owner == &actualOwner && evidence.generation == 71 &&
                evidence.masterThread == 81 && evidence.nv == &state &&
                evidence.privateState == &privateState && evidence.gpu == &gpu,
                "claimed identity cannot be retagged by later pointer/generation/owner mutation");
            expect(protocolClaim == 1, "attempt has no reset or retry endpoint");
        }
        if (entered) {
            const NV_STATUS original = scenario == 11 ? NV_ERR_GENERIC :
                scenario == 12 ? NV_ERR_TIMEOUT : NV_OK;
            expect(evidence.originalReturnStatus == original &&
                evidence.protocolCompleted == (original == NV_OK),
                "original return remains separate from later lock/service/identity failure");
            expect(privateState.flags == (NV_INIT_FLAG_GPU_STATE | NV_INIT_FLAG_GPU_STATE_LOAD),
                "protocol does not clear adapter ownership flags or perform GPU destruction");
        }
        if (scenario == 0 || scenario == 7 || scenario == 8 || scenario == 11 || scenario == 12 || scenario == 13) {
            const unsigned oldUnload = unloaded, oldSuspend = suspended;
            expect(s540ShutdownProtocolRun(&controlStack, &state, &evidence) == NV_ERR_STATE_IN_USE,
                "a successful or partial original attempt cannot be repeated");
            expect(unloaded == oldUnload && suspended == oldSuspend,
                "replay executes no additional original stage");
        }
    }
    printf("{\"scenario\":%u,\"checks\":%u,\"failures\":%u,\"hardware_endpoints_fixture\":true,\"record_lock_runtime_endpoints_fixture\":true,\"original_entry_admission\":false}\n",
        scenario, checks, failures);
    return failures ? 1 : 0;
}
