/* SPDX-License-Identifier: MIT */
/* Exact production helper plus complete original intrSet/Get and osDisable/
 * osEnable bodies. NVIDIA layouts come from the full original headers. Strong
 * record admission, real-lock adapters and hardware HALs are explicit fixtures. */
#define NVOC_GPU_H_PRIVATE_ACCESS_ALLOWED
#define NVOC_INTR_H_PRIVATE_ACCESS_ALLOWED
#include "nv.h"
#include "nv-priv.h"
#include "osapi.h"
#include "gpu/gpu.h"
#include "gpu/intr/intr.h"
#include "core/system.h"
#include "core/thread_state.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540ProspectiveRmLockOwnership.h"
#include "S540NvidiaIrqOriginal.h"
#include <stdio.h>
#include <stdlib.h>

static nv_state_t state, foreignState;
static nvidia_stack_t stack;
static OBJGPU gpu;
static Intr intr;
static OBJSYS systemFixture;
static S540FirstTxnGlobalSnapshot epoch;
static S540ProspectiveRmLockOwnership observedLocks;
static NvU32 checks,failures,masterReads,apiAcquires,gpuAcquires,apiReleases,gpuReleases;
static NvU32 irqDrainChecks,lockReads;
static NvU32 hardwareTop,hardwareStall,hardwareNonstall,hardwareWrites,pendingDrains;
static NvU32 runtimeDepth,threadStateDepth;
static NvBool globalFailure,foreignMaster,failApi,failGpu,foreignGpu,mutateEpoch;
static NvBool tegra,missingIntr,keepPending,irqNotDrained;
static void require(NvBool value) { if(!value)abort(); }
static void clear(void *object,size_t bytes) {
    volatile NvU8 *value=object;while(bytes--)*value++=0;
}
static void expect(NvBool value,const char *message) {
    ++checks;if(!value){++failures;fprintf(stderr,"IRQ original: %s\n",message);}
}
static OBJGPU *privateGpu(nv_state_t *nv) { require(nv==&state);return foreignGpu?NULL:&gpu; }
static nv_state_t *gpuState(OBJGPU *object) { require(object==&gpu);return &state; }
static Intr *gpuIntr(OBJGPU *object) { require(object==&gpu);return missingIntr?NULL:&intr; }
#undef NV_GET_NV_PRIV_PGPU
#define NV_GET_NV_PRIV_PGPU privateGpu
#undef NV_GET_NV_STATE
#define NV_GET_NV_STATE gpuState
#undef GPU_GET_INTR
#define GPU_GET_INTR gpuIntr
#undef SYS_GET_INSTANCE
#define SYS_GET_INSTANCE() (&systemFixture)
#undef NV_ENTER_RM_RUNTIME
#define NV_ENTER_RM_RUNTIME(sp,fp) do { require((sp)==&stack && !runtimeDepth);runtimeDepth=1;(fp)=NULL; } while(0)
#undef NV_EXIT_RM_RUNTIME
#define NV_EXIT_RM_RUNTIME(sp,fp) do { (void)(sp);(void)(fp);require(runtimeDepth==1 && !threadStateDepth);runtimeDepth=0; } while(0)
#undef NV_ASSERT
#define NV_ASSERT(value) require(value)
#undef NV_PRINTF
#define NV_PRINTF(...) ((void)0)

NV_STATUS s540FirstTxnGlobalReadMaster(S540FirstTxnGlobalSnapshot *out) {
    ++masterReads;
    if(globalFailure)return NV_ERR_NOT_READY;
    if(foreignMaster)return NV_ERR_INVALID_STATE;
    require(out!=NULL);*out=epoch;return NV_OK;
}
NV_STATUS s540FirstTxnIrqValidateSoftwareDrained(void) {
    ++irqDrainChecks;return irqNotDrained?NV_ERR_IN_USE:NV_OK;
}
NV_STATUS s540ProspectiveReadOriginalLockOwnership(const OBJSYS *sys,S540ProspectiveRmLockOwnership *out) {
    require(sys==&systemFixture && out && irqDrainChecks && !irqNotDrained);
    ++lockReads;*out=observedLocks;return NV_OK;
}
NV_STATUS s540ProspectiveOriginalCurrentThreadLocksReleased(const OBJSYS *sys) {
    require(sys==&systemFixture);return observedLocks.apiOwned||observedLocks.perGpuMask||observedLocks.allocationOwned?
        NV_ERR_INVALID_LOCK_STATE:NV_OK;
}
NV_STATUS NV_API_CALL rm_acquire_api_lock(nvidia_stack_t *sp) {
    require(sp==&stack && !observedLocks.apiOwned);++apiAcquires;
    if(failApi)return NV_ERR_BUSY_RETRY;
    observedLocks.apiOwned=NV_TRUE;return NV_OK;
}
NV_STATUS NV_API_CALL rm_acquire_gpu_lock(nvidia_stack_t *sp,nv_state_t *nv) {
    require(sp==&stack && nv==&state && observedLocks.apiOwned && !observedLocks.perGpuMask);++gpuAcquires;
    if(failGpu)return NV_ERR_BUSY_RETRY;
    observedLocks.perGpuMask=1U<<gpu.gpuInstance;if(mutateEpoch)++epoch.generation;return NV_OK;
}
NvBool rmDeviceGpuLockIsOwner(NvU32 instance) {
    return instance==gpu.gpuInstance && observedLocks.perGpuMask==(1U<<instance);
}
void threadStateInit(THREAD_STATE_NODE *node,NvU32 flags) {
    require(node && !flags && runtimeDepth==1 && !threadStateDepth);threadStateDepth=1;
}
void threadStateFree(THREAD_STATE_NODE *node,NvU32 flags) {
    require(node && !flags && runtimeDepth==1 && threadStateDepth==1);threadStateDepth=0;
}
static void hardwareEnable(OBJGPU *object,Intr *i,NvU32 value,THREAD_STATE_NODE *node) {
    require(object==&gpu && i==&intr && !node && observedLocks.apiOwned && observedLocks.perGpuMask);
    hardwareTop=value;++hardwareWrites;
}
static void hardwareStallEnable(OBJGPU *object,Intr *i,NvU32 value,THREAD_STATE_NODE *node) {
    require(object==&gpu && i==&intr && !node);hardwareStall=value;++hardwareWrites;
}
static void hardwareRestoreNonstall(OBJGPU *object,Intr *i,NvU32 value,THREAD_STATE_NODE *node) {
    require(object==&gpu && i==&intr && !node);hardwareNonstall=value;++hardwareWrites;
}
static NvU32 hardwareRead(OBJGPU *object,Intr *i,THREAD_STATE_NODE *node) {
    require(object==&gpu && i==&intr && !node);return hardwareTop;
}
#undef intrSetIntrEnInHw_HAL
#define intrSetIntrEnInHw_HAL hardwareEnable
#undef intrSetStall_HAL
#define intrSetStall_HAL hardwareStallEnable
#undef intrRestoreNonStall_HAL
#define intrRestoreNonStall_HAL hardwareRestoreNonstall
#undef intrGetIntrEnFromHw_HAL
#define intrGetIntrEnFromHw_HAL hardwareRead
void nv_control_soc_irqs(nv_state_t *nv,NvBool enable) {(void)nv;(void)enable;abort();}

#include "actual-mask-bodies.inc"

NV_STATUS NV_API_CALL rm_release_gpu_lock(nvidia_stack_t *sp,nv_state_t *nv) {
    require(sp==&stack && nv==&state && observedLocks.apiOwned && observedLocks.perGpuMask);++gpuReleases;
    /* The fixture release uses the exact original re-enable body. A mask that
     * only touched hardware would restore the old intrEn0 value here. */
    if(!missingIntr && !tegra)osEnableInterrupts(&gpu);
    observedLocks.perGpuMask=0;return NV_OK;
}
NV_STATUS NV_API_CALL rm_release_api_lock(nvidia_stack_t *sp) {
    require(sp==&stack && observedLocks.apiOwned && !observedLocks.perGpuMask);++apiReleases;
    observedLocks.apiOwned=NV_FALSE;return NV_OK;
}
void osRunQueued1HzCallbacksUnderLock(OBJGPU *object) {
    require(object==&gpu && observedLocks.apiOwned && observedLocks.perGpuMask &&
        runtimeDepth==1 && threadStateDepth==1);++pendingDrains;
    if(!keepPending)gpu.bCallbackQueued=NV_FALSE;
}

#include "S540NvidiaIrqOriginal.c"

static void reset(void) {
    clear(&gpu,sizeof(gpu));clear(&intr,sizeof(intr));
    clear(&epoch,sizeof(epoch));clear(&observedLocks,sizeof(observedLocks));
    gpu.gpuInstance=0;
    intr.halIntrEnabled=NV_TRUE;intr.intrEn0=INTERRUPT_TYPE_HARDWARE;
    epoch.owner=&systemFixture;epoch.nv=&state;epoch.generation=7;epoch.masterThread=31;
    epoch.state=S540_FIRST_GLOBAL_READY;epoch.validated=NV_TRUE;observedLocks.thread=31;
    hardwareTop=hardwareStall=hardwareNonstall=INTERRUPT_TYPE_DISABLED;
    masterReads=apiAcquires=gpuAcquires=apiReleases=gpuReleases=hardwareWrites=pendingDrains=0;
    irqDrainChecks=lockReads=0;
    runtimeDepth=threadStateDepth=0;globalFailure=foreignMaster=failApi=failGpu=foreignGpu=mutateEpoch=NV_FALSE;
    tegra=missingIntr=keepPending=irqNotDrained=NV_FALSE;
}
static void checkRefusal(const char *message) {
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)!=NV_OK && !hardwareWrites && !pendingDrains,message);
}
int main(void) {
    reset();expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_OK &&
        intr.intrEn0==INTERRUPT_TYPE_DISABLED && hardwareTop==INTERRUPT_TYPE_DISABLED &&
        hardwareStall==INTERRUPT_TYPE_DISABLED && hardwareNonstall==INTERRUPT_TYPE_DISABLED && hardwareWrites==6,
        "persistent logical disable survives exact original hardware-mask and re-enable bodies");
    expect(apiAcquires==1 && gpuAcquires==1 && apiReleases==1 && gpuReleases==1 && masterReads==2 &&
        irqDrainChecks==1 && lockReads==2 &&
        !runtimeDepth && !threadStateDepth && !observedLocks.apiOwned && !observedLocks.perGpuMask,
        "successful mask uses authentic master observations and releases both original-lock fixtures");
    reset();gpu.bCallbackQueued=NV_TRUE;
    expect(s540FirstTxnDrainQueued1Hz(&stack,&state)==NV_OK && pendingDrains==1 && !gpu.bCallbackQueued &&
        apiAcquires==1 && gpuAcquires==1 && gpuReleases==1 && apiReleases==1,
        "pending drain executes only under actual production helper lock and runtime scopes");
    reset();keepPending=NV_TRUE;gpu.bCallbackQueued=NV_TRUE;
    expect(s540FirstTxnDrainQueued1Hz(&stack,&state)==NV_ERR_BUSY_RETRY && gpu.bCallbackQueued && pendingDrains==1,
        "remaining original pending state is refused without fabricating its completion");
    reset();globalFailure=NV_TRUE;checkRefusal("strong-record refusal precedes original entry");
    reset();irqNotDrained=NV_TRUE;
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_ERR_IN_USE && irqDrainChecks==1 &&
        !lockReads && !apiAcquires && !gpuAcquires && !hardwareWrites,
        "genuine ISR/DPC exclusion is required before complete original lock ownership is read");
    reset();irqNotDrained=NV_TRUE;
    expect(s540FirstTxnDrainQueued1Hz(&stack,&state)==NV_ERR_IN_USE && irqDrainChecks==1 &&
        !lockReads && !apiAcquires && !gpuAcquires && !pendingDrains,
        "master pending drain cannot query transferred lock ownership before IRQ/BH quiescence");
    reset();foreignMaster=NV_TRUE;checkRefusal("foreign master cannot request a hardware mask");
    reset();epoch.nv=&foreignState;checkRefusal("foreign nv cannot borrow the genuine master epoch");
    reset();epoch.validated=NV_FALSE;checkRefusal("unvalidated global epoch cannot enter original mask");
    reset();observedLocks.thread=9;checkRefusal("complete lock reader must observe the exact master thread");
    reset();observedLocks.apiOwned=NV_TRUE;checkRefusal("held API token is rejected before recursive acquisition");
    reset();observedLocks.perGpuMask=1;checkRefusal("held GPU token is rejected before acquisition");
    reset();observedLocks.allocationOwned=NV_TRUE;checkRefusal("held allocation token cannot enter mask");
    reset();failApi=NV_TRUE;checkRefusal("actual API acquisition failure performs no hardware operation");
    expect(apiAcquires==1 && !apiReleases && !gpuAcquires,"failed API acquisition grants no release token");
    reset();failGpu=NV_TRUE;
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_ERR_BUSY_RETRY && !hardwareWrites &&
        apiAcquires==1 && gpuAcquires==1 && apiReleases==1 && !gpuReleases,
        "failed GPU acquisition releases only its acquired API owner");
    reset();foreignGpu=NV_TRUE;
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_ERR_INVALID_STATE && !hardwareWrites &&
        apiReleases==1 && !gpuAcquires,"unavailable original GPU retains owners and never acquires foreign state");
    reset();missingIntr=NV_TRUE;
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_ERR_NOT_SUPPORTED && !hardwareWrites &&
        apiReleases==1 && gpuReleases==1,"missing interrupt object refuses direct mask and releases locks");
    reset();intr.halIntrEnabled=NV_FALSE;
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_ERR_NOT_SUPPORTED &&
        intr.intrEn0==INTERRUPT_TYPE_HARDWARE,"frozen HAL cannot masquerade as a persisted intrEn0 disable");
    reset();tegra=NV_TRUE;gpu.PDB_PROP_GPU_TEGRA_SOC_NVDISPLAY=NV_TRUE;
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_ERR_NOT_SUPPORTED && !hardwareWrites,
        "unsupported Tegra IRQ route cannot reach hardware callbacks");
    reset();mutateEpoch=NV_TRUE;
    expect(s540FirstTxnIrqMaskHardware(&stack,&state)==NV_ERR_INVALID_STATE && apiReleases==1 && gpuReleases==1,
        "changed epoch after lock acquisition refuses masking");
    reset();expect(s540FirstTxnIrqMaskHardware(NULL,&state)==NV_ERR_INVALID_ARGUMENT && !masterReads &&
        s540FirstTxnIrqMaskHardware(&stack,NULL)==NV_ERR_INVALID_ARGUMENT,
        "missing real stack or nv is rejected before original entry");
    printf("{\"checks\":%u,\"failures\":%u,\"production_helper_body\":true,\"full_original_headers\":true,\"original_mask_enable_bodies\":4,\"hardware_execution\":false}\n",checks,failures);
    return failures?1:0;
}
