/* SPDX-License-Identifier: MIT */
/* Unmodified original ISR/fault and Context wrapper bodies with complete
 * original layouts. Runtime, allocator, HAL and spinlock endpoints below are
 * explicit fixtures. No GPU, hardware IRQ or CPU stack switch is executed. */
#define NVOC_GPU_H_PRIVATE_ACCESS_ALLOWED
#define NVOC_INTR_H_PRIVATE_ACCESS_ALLOWED
#include "nv.h"
#include "nv-priv.h"
#include "osapi.h"
#include "gpu/gpu.h"
#include "gpu/intr/intr.h"
#include "gpu/mmu/kern_gmmu.h"
#include "nv_sriov_defines.h"
#include "core/thread_state.h"
#include "libraries/tls/tls.h"
#include "S540NvidiaGspContext.h"
#include "S540NvidiaDarwinServices.h"
#include <stdio.h>
#include <stdlib.h>

#include "actual-context-layout.inc"

static S540GspContext context;
static nv_priv_t privateState;
static OBJGPU gpu;
static NvU32 checks, failures, runtimeDepth, runtimeEntries;
static NvU32 isrCalls, faultCalls, allocatorCalls, threadStateCalls;
static NvU32 guardAcquires, guardReleases, lockedCalls, unlockedCalls;
static NV_STATUS isrStatus=NV_ERR_NO_INTR_PENDING;
static NvU32 copiedFaults;
static NvBool gspClient=NV_TRUE;
static nvidia_stack_t *expectedStack;
static int lockIdentity, allocatorIdentity;

static void require(NvBool value) { if(!value)abort(); }
static void expect(NvBool value,const char *message) {
    ++checks;
    if(!value){++failures;fprintf(stderr,"preinit original: %s\n",message);}
}
static void runtimeEnter(nvidia_stack_t *sp,void **saved) {
    require(sp==expectedStack && !runtimeDepth);
    require(sp->size==sizeof(sp->stack) && sp->top==sp->stack+sp->size);
    *saved=NULL;runtimeDepth=1;++runtimeEntries;
}
static void runtimeExit(nvidia_stack_t *sp,void *saved) {
    (void)saved;require(sp==expectedStack && runtimeDepth==1);runtimeDepth=0;
}
#undef NV_ENTER_RM_RUNTIME
#define NV_ENTER_RM_RUNTIME(sp,fp) runtimeEnter((sp),&(fp))
#undef NV_EXIT_RM_RUNTIME
#define NV_EXIT_RM_RUNTIME(sp,fp) runtimeExit((sp),(fp))

static NV_STATUS fixtureIsr(NvBool test,OBJGPU *object) {
    require(object==&gpu && !test && runtimeDepth==1);++isrCalls;return isrStatus;
}
#undef isrWrapper
#define isrWrapper fixtureIsr
static KernelGmmu *fixtureGmmu(OBJGPU *object) { require(object==&gpu);return NULL; }
#undef GPU_GET_KERNEL_GMMU
#define GPU_GET_KERNEL_GMMU fixtureGmmu
#undef IS_VGPU_GSP_PLUGIN_OFFLOAD_ENABLED
#define IS_VGPU_GSP_PLUGIN_OFFLOAD_ENABLED(gpu) NV_FALSE
#undef IS_VIRTUAL
#define IS_VIRTUAL(gpu) NV_FALSE
#undef IS_VIRTUAL_WITH_SRIOV
#define IS_VIRTUAL_WITH_SRIOV(gpu) NV_FALSE
#undef IS_GSP_CLIENT
#define IS_GSP_CLIENT(gpu) gspClient

static PORT_MEM_ALLOCATOR *fixtureAllocator(void *storage,NvLength bytes) {
    require(storage && bytes==TLS_ISR_ALLOCATOR_SIZE && runtimeDepth==1);
    ++allocatorCalls;return (PORT_MEM_ALLOCATOR *)&allocatorIdentity;
}
#undef portMemAllocatorCreateOnExistingBlock
#define portMemAllocatorCreateOnExistingBlock fixtureAllocator
static void fixtureAllocatorRelease(PORT_MEM_ALLOCATOR *allocator) {
    require(allocator==(PORT_MEM_ALLOCATOR *)&allocatorIdentity && runtimeDepth==1);
}
#undef portMemAllocatorRelease
#define portMemAllocatorRelease fixtureAllocatorRelease
static void fixtureTls(PORT_MEM_ALLOCATOR *allocator) {
    require(allocator==(PORT_MEM_ALLOCATOR *)&allocatorIdentity && runtimeDepth==1);
}
#undef tlsIsrInit
#define tlsIsrInit fixtureTls
#undef tlsIsrDestroy
#define tlsIsrDestroy fixtureTls
static void fixtureThreadState(THREAD_STATE_NODE *node,OBJGPU *object,NvU32 flags) {
    require(node && object==&gpu && flags==THREAD_STATE_FLAGS_IS_ISR_LOCKLESS && runtimeDepth==1);
    ++threadStateCalls;
}
#undef threadStateInitISRLockless
#define threadStateInitISRLockless fixtureThreadState
#undef threadStateFreeISRLockless
#define threadStateFreeISRLockless fixtureThreadState
static NvBool fixturePending(OBJGPU *object,KernelGmmu *gmmu,THREAD_STATE_NODE *node) {
    (void)object;(void)gmmu;(void)node;abort();
}
#undef kgmmuIsNonReplayableFaultPending_HAL
#define kgmmuIsNonReplayableFaultPending_HAL fixturePending
static void fixtureClear(OBJGPU *object,KernelGmmu *gmmu,THREAD_STATE_NODE *node) {
    (void)object;(void)gmmu;(void)node;abort();
}
#undef kgmmuClearNonReplayableFaultIntr_HAL
#define kgmmuClearNonReplayableFaultIntr_HAL fixtureClear
static NV_STATUS fixtureDoorbell(OBJGPU *object,Intr *intr,NvU32 value) {
    (void)object;(void)intr;(void)value;abort();
}
#undef intrTriggerPrivDoorbell_HAL
#define intrTriggerPrivDoorbell_HAL fixtureDoorbell
static NV_STATUS _rm_gpu_copy_mmu_faults_unlocked(OBJGPU *object,NvU32 *faults,
    THREAD_STATE_NODE *node) {
    require(object==&gpu && faults && node && runtimeDepth==1);
    ++faultCalls;*faults=copiedFaults;return NV_OK;
}
static void RmIsrBottomHalf(nv_state_t *nv) {
    require(nv==&context.nv && expectedStack==&context.stacks[LOCKED_BH]);++lockedCalls;
}
static void RmIsrBottomHalfUnlocked(nv_state_t *nv) {
    require(nv==&context.nv && expectedStack==&context.stacks[UNLOCKED_BH]);++unlockedCalls;
}
NvU64 NV_API_CALL s540Darwin_os_acquire_spinlock(void *handle) {
    require(handle==&lockIdentity);++guardAcquires;return 31;
}
void NV_API_CALL s540Darwin_os_release_spinlock(void *handle,NvU64 saved) {
    require(handle==&lockIdentity && saved==31);++guardReleases;
}

#include "actual-preinit-bodies.inc"

static void reset(void) {
    NvU32 i;
    context.nv.priv=&privateState;
    privateState.flags=0;privateState.pGpu=NULL;
    context.state.privateState=NV_TRUE;context.state.interruptsHandled=0;
    context.state.lockedBottomHalves=context.state.unlockedBottomHalves=0;
    context.isrGuard=&lockIdentity;
    for(i=0;i<STACKS;++i){context.stacks[i].size=sizeof(context.stacks[i].stack);
        context.stacks[i].top=context.stacks[i].stack+context.stacks[i].size;}
    expectedStack=&context.stacks[ISR];
    runtimeDepth=runtimeEntries=isrCalls=faultCalls=allocatorCalls=threadStateCalls=0;
    guardAcquires=guardReleases=lockedCalls=unlockedCalls=0;
    isrStatus=NV_ERR_NO_INTR_PENDING;copiedFaults=0;gspClient=NV_TRUE;
}
int main(void) {
    NvU32 need,faults;NvBool locked,unlocked;
    reset();need=0xabcdefU;
    expect(!rm_isr(expectedStack,&context.nv,&need) && need==0xabcdefU,
        "private-only original ISR refuses before touching outputs/runtime");
    expect(!runtimeEntries&&!isrCalls,"private-only original ISR never dispatches GPU");
    faults=0xabcdefU;
    expect(rm_gpu_handle_mmu_faults(expectedStack,&context.nv,&faults)==NV_ERR_OBJECT_NOT_FOUND&&faults==0,
        "original NULL-GPU fault path zeros count and reports missing object");
    expect(runtimeEntries==1&&!runtimeDepth&&!allocatorCalls&&!threadStateCalls,
        "original NULL-GPU fault path balances runtime and never initializes GPU TLS");
    locked=unlocked=NV_TRUE;
    expect(!s540GspContextInterruptTop(&context,&locked,&unlocked)&&!locked&&!unlocked,
        "actual Context wrapper initializes both pending outputs before early originals");
    expect(guardAcquires==1&&guardReleases==1&&!context.state.interruptsHandled,
        "actual Context wrapper releases ISR serialization without a fabricated handled count");
    privateState.flags=NV_INIT_FLAG_GPU_STATE_LOAD;need=0xabcdefU;
    expect(!rm_isr(expectedStack,&context.nv,&need)&&need==0xabcdefU,
        "loaded flag with NULL GPU still refuses and preserves pending output");
    locked=unlocked=NV_TRUE;
    expect(!s540GspContextInterruptTop(&context,&locked,&unlocked)&&!locked&&!unlocked,
        "Context handles original NULL-GPU result even with stale loaded flag");
    reset();privateState.pGpu=&gpu;
    expect(!s540GspContextInterruptTop(&context,&locked,&unlocked)&&!locked&&!unlocked,
        "constructed pre-load GPU uses genuine GSP fault branch but does not dispatch ISR");
    expect(!isrCalls&&allocatorCalls==1&&threadStateCalls==2&&!runtimeDepth,
        "constructed pre-load path uses balanced original fault-wrapper runtime/TLS calls");
    privateState.flags=NV_INIT_FLAG_GPU_STATE_LOAD;
    isrStatus=NV_OK;
    expect(s540GspContextInterruptTop(&context,&locked,&unlocked)&&!locked&&!unlocked,
        "loaded genuine ISR success preserves no-bottom-half semantics");
    isrStatus=NV_WARN_MORE_PROCESSING_REQUIRED;
    expect(s540GspContextInterruptTop(&context,&locked,&unlocked)&&locked&&!unlocked,
        "loaded genuine ISR more-processing requests locked bottom half");
    isrStatus=NV_ERR_NO_INTR_PENDING;
    expect(!s540GspContextInterruptTop(&context,&locked,&unlocked)&&!locked&&!unlocked,
        "genuine no-pending result does not fabricate handling");
    isrStatus=NV_ERR_INVALID_STATE;
    expect(!s540GspContextInterruptTop(&context,&locked,&unlocked)&&!locked&&!unlocked,
        "genuine unexpected ISR status follows original refusal branch");
    gspClient=NV_FALSE;copiedFaults=3;
    expect(s540GspContextInterruptTop(&context,&locked,&unlocked)&&!locked&&unlocked,
        "original copied-fault path selects unlocked bottom half when ISR needs none");
    isrStatus=NV_WARN_MORE_PROCESSING_REQUIRED;
    expect(s540GspContextInterruptTop(&context,&locked,&unlocked)&&locked&&!unlocked,
        "original locked request takes precedence over unlocked copied-fault scheduling");
    expectedStack=&context.stacks[LOCKED_BH];s540GspContextLockedBottomHalf(&context);
    expectedStack=&context.stacks[UNLOCKED_BH];s540GspContextUnlockedBottomHalf(&context);
    expect(lockedCalls==1&&unlockedCalls==1&&context.state.lockedBottomHalves==1&&
        context.state.unlockedBottomHalves==1&&!runtimeDepth,
        "actual Context and original bottom wrappers preserve distinct owned stacks");
    expect(guardAcquires==guardReleases,"every actual top-half spinlock acquisition returns its token");
    printf("{\"checks\":%u,\"failures\":%u,\"original_layout_headers_used\":true,\"complete_original_bodies\":4,\"complete_context_bodies\":3,\"hardware_execution\":false}\n",checks,failures);
    return failures?1:0;
}
