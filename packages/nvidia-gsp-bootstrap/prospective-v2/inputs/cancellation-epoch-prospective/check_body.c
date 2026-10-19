/* SPDX-License-Identifier: MIT */
/* One complete actual original body; every hardware/firmware endpoint is an
 * explicit stage fixture. Actual generated original types/casts are used. */
#include "nv.h"
#include "gpu/gpu.h"
#include "gpu/gsp/kernel_gsp.h"
#include "gpu/rpc/objrpc.h"
#include "published/turing/tu102/dev_falcon_v4.h"
static OBJGPU gpu;
static KernelGsp gsp;
static OBJRPC rpc;
static RM_RISCV_UCODE_DESC descriptor;
static NvU32 failStage, stages, oldStopSeen, lastStage, frees;
// Typed diagnostic endpoints preserve the original assertion/return macros.
void nvAssertFailedNoLog(NV_ASSERT_FAILED_FUNC_TYPE) {}
void nvAssertOkFailedNoLog(NvU32 status NV_ASSERT_FAILED_FUNC_COMMA_TYPE) {}
static NvBool visit(NvU32 stage) {
    ++stages; lastStage = stage;
    if (gsp.bGspRmUnloaded) ++oldStopSeen;
    return failStage == stage;
}
static NV_STATUS stageStatus(NvU32 stage) { return visit(stage) ? NV_ERR_GENERIC : NV_OK; }
static void fixtureFree(void *data) { (void)data; ++frees; }
static void fixtureLog(int level, const char *format, ...) { (void)level; (void)format; }
static void fixtureWrite(OBJGPU *pGpu, KernelFalcon *flcn, NvU32 offset, NvU32 value) {
    (void)pGpu; (void)flcn; (void)offset; (void)value; visit(7);
}
#undef kgspExecuteScrubberIfNeeded_HAL
#define kgspExecuteScrubberIfNeeded_HAL(...) stageStatus(1)
#undef kgspGetFrtsSize_HAL
#define kgspGetFrtsSize_HAL(...) 1
#undef kflcnReset_HAL
#define kflcnReset_HAL(...) stageStatus(2)
#undef kgspExecuteFwsec_HAL
#define kgspExecuteFwsec_HAL(...) stageStatus(3)
#undef kflcnResetIntoRiscv_HAL
#define kflcnResetIntoRiscv_HAL(...) stageStatus(4)
#undef kgspProgramLibosBootArgsAddr_HAL
#define kgspProgramLibosBootArgsAddr_HAL(...) ((void)visit(5))
#undef kgspExecuteBooterLoad_HAL
#define kgspExecuteBooterLoad_HAL(...) stageStatus(6)
#undef kflcnRegWrite_HAL
#define kflcnRegWrite_HAL fixtureWrite
#undef kflcnIsRiscvActive_HAL
#define kflcnIsRiscvActive_HAL(...) (!visit(8))
#define _kgspIsProcessorSuspended(...) NV_FALSE
#undef GspStatusQueueInit
#define GspStatusQueueInit(...) stageStatus(9)
#undef kgspSendInitRpcs
#define kgspSendInitRpcs(...) stageStatus(10)
#undef kgspWaitForRmResumeDone
#define kgspWaitForRmResumeDone(...) stageStatus(11)
#undef portMemFree
#define portMemFree fixtureFree
#undef NV_PRINTF
#define NV_PRINTF(...) fixtureLog(__VA_ARGS__)
#undef DBG_BREAKPOINT
#define DBG_BREAKPOINT() ((void)0)

#if S540_EPOCH_BASELINE
#include "baseline-body.inc"
#else
#include "proposed-body.inc"
#endif

NV_STATUS s540EpochRun(NvU32 bootMode, NvU32 failedStage) {
    stages = oldStopSeen = lastStage = frees = 0; failStage = failedStage;
    gsp.bGspRmUnloaded = NV_TRUE; // Explicit previous-completion fixture.
    gsp.__nvoc_pbase_KernelFalcon = &gsp.__nvoc_base_KernelFalcon;
    gsp.pScrubberUcode = (void *)&gsp;
    gsp.pPreparedFwsecCmd = (void *)&gsp;
    gsp.pGspRmBootUcodeDesc = &descriptor; gsp.pRpc = &rpc;
    return kgspBootstrap_TU102(&gpu, &gsp, (KernelGspBootMode)bootMode);
}
NvU32 s540EpochStages(void) { return stages; }
NvU32 s540EpochOldStopSeen(void) { return oldStopSeen; }
NvU32 s540EpochLastStage(void) { return lastStage; }
NvU32 s540EpochFrees(void) { return frees; }
NvBool s540EpochStopped(void) { return gsp.bGspRmUnloaded; }
