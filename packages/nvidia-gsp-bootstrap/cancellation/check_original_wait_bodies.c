/* SPDX-License-Identifier: MIT */
/* Actual source-extracted prospective function bodies, actual original types.
 * Register, timer and GSP event endpoints below are explicit CPU fixtures.
 * This does not construct an original adapter or claim hardware cleanup.
 */
#include "nv.h"
#include "gpu/gpu.h"
#include "gpu/falcon/kernel_falcon.h"
#include "gpu/gsp/kernel_gsp.h"
#include "vgpu/rpc_headers.h"
#define RPC_STRUCTURES
#define RPC_GENERIC_UNION
#include "g_rpc-structures.h"
#undef RPC_STRUCTURES
#undef RPC_GENERIC_UNION
#define RPC_MESSAGE_STRUCTURES
#define RPC_MESSAGE_GENERIC_UNION
#include "g_rpc-message-header.h"
#undef RPC_MESSAGE_STRUCTURES
#undef RPC_MESSAGE_GENERIC_UNION
#include "gpu/gsp/message_queue.h"
#include "gpu/gsp/message_queue_priv.h"
#include "msgq/msgq_priv.h"
#include "gpu/rpc/objrpc.h"
#include "published/turing/tu102/dev_falcon_v4.h"
#include "S540NvidiaGspCancellationOriginal.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

static OBJGPU gpu;
static KernelFalcon falcon;
static KernelGsp gsp;
static OBJRPC rpc;
static nv_state_t nv;
static MESSAGE_QUEUE_INFO queue;
static NvU32 reads, successAfter;
static NvU64 deadline;
static NvU32 observe(void) { return __atomic_add_fetch(&reads, 1U, __ATOMIC_RELAXED); }
static NvBool completed(void) {
    const NvU32 count = observe();
    return successAfter && count >= successAfter;
}
static NvU32 fixtureRead(OBJGPU *pGpu, KernelFalcon *flcn, NvU32 offset) {
    (void)pGpu; (void)flcn; (void)offset;
    return completed() ? DRF_DEF(_PFALCON, _FALCON, _CPUCTL_HALTED, _TRUE) : 0;
}
static NvBool fixtureCondition(OBJGPU *pGpu, void *data) {
    (void)pGpu; (void)data; return completed();
}
static void fixtureSet(TIMEOUT_DATA *data, RMTIMEOUT *timeout, NvU32 us, NvU32 flags) {
    (void)data; (void)timeout; (void)us; (void)flags;
    deadline = s540Darwin_os_get_monotonic_time_ns() + 2000000000ULL;
}
static NV_STATUS fixtureCheck(TIMEOUT_DATA *data, RMTIMEOUT *timeout, NvU32 line) {
    (void)data; (void)timeout; (void)line;
    return s540Darwin_os_get_monotonic_time_ns() >= deadline ? NV_ERR_TIMEOUT : NV_OK;
}
static void fixtureSpin(void) {}
static NV_STATUS fixtureDrainOne(OBJGPU *pGpu, OBJRPC *pRpc, NvU32 func, NvU32 sequence,
    KernelGspRpcEventHandlerContext context, GpuWaitConditionFunc *condition, void *data) {
    (void)pGpu; (void)pRpc; (void)func; (void)sequence; (void)context;
    (void)condition; (void)data;
    return completed() ? NV_WARN_NOTHING_TO_DO : NV_OK;
}
static NV_STATUS fixtureRegisters(OBJGPU *pGpu, NvU32 index, NvU32 *first, NvU32 *second,
    NvU32 *head, NvU32 *tail) {
    (void)pGpu; (void)index; (void)first; (void)second; *head = *tail = 0; return NV_OK;
}
static int fixtureLink(void) { return completed() ? 0 : 1; }
static void fixtureCleanup(MESSAGE_QUEUE_INFO *info) { (void)info; }
static void fixtureLog(int level, const char *format, ...) { (void)level; (void)format; }
static void fixtureLogs(KernelGsp *kgsp, NvBool force) { (void)kgsp; (void)force; }
static NvBool fixtureHealth(OBJGPU *pGpu, KernelGsp *kgsp) {
    (void)pGpu; (void)kgsp; return NV_TRUE;
}

#undef timeoutSet
#define timeoutSet fixtureSet
#undef timeoutCheck
#define timeoutCheck fixtureCheck
#undef osSpinLoop
#define osSpinLoop fixtureSpin
#undef kflcnRegRead_HAL
#define kflcnRegRead_HAL fixtureRead
#undef GPU_GET_RPC
#define GPU_GET_RPC(pGpu) (&rpc)
#undef GPU_GET_KERNEL_GSP
#define GPU_GET_KERNEL_GSP(pGpu) (&gsp)
#define _kgspRpcDrainOneEvent fixtureDrainOne
#undef kgspDumpGspLogs
#define kgspDumpGspLogs fixtureLogs
#undef kgspHealthCheck_HAL
#define kgspHealthCheck_HAL fixtureHealth
#undef IS_EMULATION
#define IS_EMULATION(...) NV_FALSE
#undef IS_SIMULATION
#define IS_SIMULATION(...) NV_FALSE
#undef gpuGetGspMsgQueueRegisters
#define gpuGetGspMsgQueueRegisters fixtureRegisters
#undef msgqRxLink
#define msgqRxLink(...) fixtureLink()
#define _gspMsgQueueCleanup fixtureCleanup
#undef NV_PRINTF
#define NV_PRINTF(...) fixtureLog(__VA_ARGS__)
#undef DBG_BREAKPOINT
#define DBG_BREAKPOINT() ((void)0)
#undef NV_ASSERT_OK_OR_RETURN
#define NV_ASSERT_OK_OR_RETURN(expr) do { NV_STATUS result_ = (expr); if (result_ != NV_OK) return result_; } while (0)
#undef threadStateResetTimeout
#define threadStateResetTimeout(...) NV_OK

#include "original_wait_bodies.inc"

void *s540CancellationWaitFixtureState(void) {
    NV_SET_NV_STATE(&gpu, &nv); gpu.timeoutData.pGpu = &gpu;
    return &nv;
}
void s540CancellationWaitFixtureReset(NvU32 completeAfter) {
    __atomic_store_n(&reads, 0U, __ATOMIC_RELAXED); successAfter = completeAfter;
}
NvU32 s540CancellationWaitFixtureReads(void) {
    return __atomic_load_n(&reads, __ATOMIC_RELAXED);
}
NV_STATUS s540CancellationWaitFixtureRun(NvU32 which) {
    MESSAGE_QUEUE_INFO *info = &queue;
    switch (which) {
    case 0: return timeoutCondWait(&gpu.timeoutData, NULL, fixtureCondition, NULL, __LINE__);
    case 1: return kflcnWaitForHalt_TU102(&gpu, &falcon, GPU_TIMEOUT_DEFAULT, 0);
    case 2: return _kgspRpcDrainEvents(&gpu, &gsp, 1, 1,
        KGSP_RPC_EVENT_HANDLER_CONTEXT_POLL, NULL, NULL);
    case 3: return GspStatusQueueInit(&gpu, &info);
    default: return NV_ERR_INVALID_ARGUMENT;
    }
}
