/* SPDX-License-Identifier: MIT */
/* Exact original layout and entry declarations precede this private bridge. */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGspContext.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

// The original OS layer owns this opaque type. The Darwin implementation uses
// its address only as a bound identity; no Linux dma_device layout is imported.
struct nv_dma_device { NvU64 identity; };
enum { MAIN, ISR, LOCKED_BH, UNLOCKED_BH, DEVICE_WORK, GLOBAL_WORK, STACKS };
struct S540GspContext {
    nv_state_t nv;
    struct nv_dma_device dma;
    nvidia_stack_t stacks[STACKS];
    struct os_work_queue *deviceQueue, *globalQueue;
    void *isrGuard;
    NvU64 ownerThread;
    void *allocationBase;
    NvBool globalQueueBound;
    NvBool metadataBound;
    NvBool intelConsoleVerified, nvidiaConsoleExcluded;
    S540GspContextSnapshot state;
};
// One S540 adapter belongs to the externally serialized operational session.
// Keep this binding through original private-state destruction; every producer
// must have quiesced before ContextDestroy releases it.
static S540GspContext *metadataContext;
static NvBool owner(S540GspContext *context)
{
    NvU64 thread = 0;
    return context && s540Darwin_os_semaphore_may_sleep() &&
        s540Darwin_os_get_current_thread(&thread) == NV_OK &&
        thread == context->ownerThread;
}
static void deviceWork(void *opaque, void *item)
{
    S540GspContext *context = opaque;
    rm_execute_work_item(&context->stacks[DEVICE_WORK], item);
}
static void globalWork(void *opaque, void *item)
{
    S540GspContext *context = opaque;
    rm_execute_work_item(&context->stacks[GLOBAL_WORK], item);
}
static NvBool cleanHost(void)
{
    S540NvidiaGlobalRmHostSnapshot host;
    s540GlobalRmHostSnapshot(&host);
    return host.initialized && !host.unavailableCalls && !host.invalidFrees;
}
NV_STATUS s540GspContextCreate(const S540GspDeviceFacts *facts, S540GspContext **out)
{
    S540GspContext *context;
    void *allocationBase;
    NvU64 thread = 0;
    NvU32 i;
    NV_STATUS status;
    if (!out || !facts || facts->format != 1 ||
        facts->vendor != 0x10de || facts->device != 0x1f91 ||
        facts->subsystemVendor != 0x17aa || facts->subsystemDevice != 0x3806 ||
        !facts->segmentKnown || !facts->pciConfigurationRead ||
        !facts->barsVerified || !facts->poweredD0 ||
        !facts->intelConsoleVerified || !facts->nvidiaConsoleExcluded ||
        !facts->noCoherentGpuMemoryProfile ||
        !s540Darwin_os_semaphore_may_sleep() ||
        s540Darwin_os_get_current_thread(&thread) != NV_OK || !thread || !cleanHost())
        return NV_ERR_NOT_SUPPORTED;
    for (i = 0; i != NV_GPU_NUM_BARS; ++i) {
        const S540GspBar *bar = &facts->bars[i];
        if (!bar->physical || !bar->bytes || bar->physical > ~(NvU64)0 - bar->bytes ||
            bar->offset < 0x10 || bar->offset > 0x24 || (bar->offset & 3))
            return NV_ERR_INVALID_ARGUMENT;
    }
    if ((facts->configuration[0] & 0xffff) != facts->vendor ||
        (facts->configuration[0] >> 16) != facts->device ||
        (facts->configuration[11] & 0xffff) != facts->subsystemVendor ||
        (facts->configuration[11] >> 16) != facts->subsystemDevice)
        return NV_ERR_INVALID_DATA;
    allocationBase = s540GlobalRmHostAllocate(sizeof(*context) + 15);
    if (!allocationBase) return NV_ERR_NO_MEMORY;
    context = (S540GspContext *)(((NvUPtr)allocationBase + 15) & ~(NvUPtr)15);
    os_mem_set(context, 0, sizeof(*context));
    context->allocationBase = allocationBase;
    context->ownerThread = thread;
    context->intelConsoleVerified = facts->intelConsoleVerified;
    context->nvidiaConsoleExcluded = facts->nvidiaConsoleExcluded;
    context->state.created = NV_TRUE;
    for (i = 0; i != STACKS; ++i) {
        context->stacks[i].size = sizeof(context->stacks[i].stack);
        context->stacks[i].top = context->stacks[i].stack + context->stacks[i].size;
    }
    context->nv.os_state = context;
    context->nv.handle = facts->pciHandle;
    context->nv.pci_info.domain = facts->segment;
    context->nv.pci_info.bus = facts->bus;
    context->nv.pci_info.slot = facts->slot;
    context->nv.pci_info.function = facts->function;
    context->nv.pci_info.vendor_id = facts->vendor;
    context->nv.pci_info.device_id = facts->device;
    context->nv.subsystem_vendor = facts->subsystemVendor;
    context->nv.subsystem_id = facts->subsystemDevice;
    for (i = 0; i != 16; ++i) context->nv.pci_cfg_space[i] = facts->configuration[i];
    for (i = 0; i != NV_GPU_NUM_BARS; ++i) {
        context->nv.bars[i].cpu_address = facts->bars[i].physical;
        context->nv.bars[i].size = facts->bars[i].bytes;
        context->nv.bars[i].offset = facts->bars[i].offset;
    }
    context->nv.regs = &context->nv.bars[NV_GPU_BAR_INDEX_REGS];
    context->nv.fb = &context->nv.bars[NV_GPU_BAR_INDEX_FB];
    // nv.ud is a distinct aperture populated by the original adapter init;
    // it is not a pointer to BAR2 and must remain zero before that operation.
    context->nv.dma_dev = &context->dma;
    context->nv.dma_mask = 0xffffffffULL; // Original initial PCI DMA profile.
    context->nv.cpu_numa_node_id = -1; // Explicit Darwin no-NUMA backend.
    context->nv.request_firmware = NV_TRUE;
    context->nv.allow_fallback_to_monolithic_rm = NV_FALSE;
    context->nv.enable_firmware_logs = NV_FALSE;
    // These are explicit unsupported Darwin feature profiles, not device
    // discovery results: DMA-BUF, Tegra, CXL and coherent GPU memory are absent.
    context->nv.dma_buf_supported = NV_FALSE;
    context->nv.coherent_gpu_mem_mode = NV_COHERENT_GPU_MEM_MODE_NONE;
    os_mem_copy(context->nv.cached_gpu_info.vbios_version, "??.??.??.??.??", 15);
    status = s540Darwin_os_alloc_spinlock(&context->isrGuard);
    if (status != NV_OK) goto fail;
    status = s540DarwinWorkQueueCreate(deviceWork, context, &context->deviceQueue);
    if (status != NV_OK) goto fail;
    context->nv.queue = context->deviceQueue;
    status = s540DarwinWorkQueueCreate(globalWork, context, &context->globalQueue);
    if (status != NV_OK) goto fail;
    status = s540DarwinBindGlobalWorkQueue(context->globalQueue);
    if (status != NV_OK) goto fail;
    context->globalQueueBound = NV_TRUE;
    {
        S540GspContext *expected = NULL;
        if (!__atomic_compare_exchange_n(&metadataContext, &expected, context,
                NV_FALSE, __ATOMIC_RELEASE, __ATOMIC_RELAXED)) {
            status = NV_ERR_STATE_IN_USE;
            goto fail;
        }
        context->metadataBound = NV_TRUE;
    }
    *out = context;
    return NV_OK;
fail:
    if (s540GspContextDestroy(context, NV_TRUE, NULL) != NV_OK) {
        *out = context;
        return NV_ERR_INVALID_STATE;
    }
    return status;
}
void *s540GspContextState(S540GspContext *context) { return context ? &context->nv : NULL; }
void *s540GspContextDmaDevice(S540GspContext *context) { return context ? &context->dma : NULL; }
void *s540GspContextMainStack(S540GspContext *context) { return context ? &context->stacks[MAIN] : NULL; }
NV_STATUS s540GspContextSetPciHandle(S540GspContext *context, void *handle)
{
    if (!owner(context) || !handle || context->nv.handle ||
        context->state.eventLocks || context->state.privateState)
        return NV_ERR_INVALID_STATE;
    context->nv.handle = handle;
    return NV_OK;
}
NV_STATUS s540GspContextPrepare(S540GspContext *context)
{
    NV_STATUS status;
    if (!owner(context) || !context->nv.handle || !s540GlobalRmIsInitialized() || !cleanHost() ||
        context->state.eventLocks || context->state.privateState) return NV_ERR_INVALID_STATE;
    if (!rm_init_event_locks(&context->stacks[MAIN], &context->nv)) return NV_ERR_NO_MEMORY;
    context->state.eventLocks = NV_TRUE;
    status = rm_is_supported_device(&context->stacks[MAIN], &context->nv);
    if (status != NV_OK) return status;
    if (!rm_init_private_state(&context->stacks[MAIN], &context->nv)) return NV_ERR_NOT_SUPPORTED;
    context->state.privateState = NV_TRUE;
    return cleanHost() ? NV_OK : NV_ERR_INVALID_STATE;
}
NV_STATUS s540GspContextInitializeAdapter(S540GspContext *context)
{
    if (!owner(context) || !context->state.privateState || context->state.adapterAttempted ||
        !cleanHost()) return NV_ERR_INVALID_STATE;
    context->state.adapterAttempted = NV_TRUE;
    context->state.adapterInitialized = rm_init_adapter(&context->stacks[MAIN], &context->nv);
    if (!context->state.adapterInitialized) return NV_ERR_NOT_READY;
    context->nv.flags |= NV_FLAG_INITIALIZED;
    return cleanHost() ? NV_OK : NV_ERR_INVALID_STATE;
}
NV_STATUS s540GspContextDisableAdapter(S540GspContext *context)
{
    if (!owner(context) || !context->state.adapterInitialized || context->state.adapterDisabled)
        return NV_ERR_INVALID_STATE;
    rm_disable_adapter(&context->stacks[MAIN], &context->nv);
    if (!cleanHost()) { context->state.quarantined = NV_TRUE; return NV_ERR_INVALID_STATE; }
    context->state.adapterDisabled = NV_TRUE;
    return NV_OK;
}
NV_STATUS s540GspContextShutdownAdapter(S540GspContext *context, NvBool irqQuiescent)
{
    if (!owner(context) || !irqQuiescent || !context->state.adapterDisabled ||
        context->state.adapterShutdown) return NV_ERR_INVALID_STATE;
    rm_shutdown_adapter(&context->stacks[MAIN], &context->nv);
    if (!cleanHost()) { context->state.quarantined = NV_TRUE; return NV_ERR_INVALID_STATE; }
    context->nv.flags &= ~NV_FLAG_INITIALIZED;
    context->state.adapterShutdown = NV_TRUE;
    return NV_OK;
}
NV_STATUS s540GspContextDestroy(S540GspContext *context, NvBool irqQuiescent,
                               S540GspContextSnapshot *finalSnapshot)
{
    NV_STATUS status;
    if (!owner(context) || !irqQuiescent || context->state.quarantined ||
        (context->state.adapterInitialized && !context->state.adapterShutdown)) return NV_ERR_INVALID_STATE;
    // A failed original init performs its internal GPU unwind. No Linux
    // initialized-device teardown is fabricated for a never initialized GPU.
    if (context->deviceQueue) {
        status = s540DarwinWorkQueueStop(context->deviceQueue);
        if (status != NV_OK) goto quarantine;
    }
    if (context->globalQueueBound) {
        status = s540DarwinUnbindGlobalWorkQueue(context->globalQueue);
        if (status != NV_OK) goto quarantine;
        context->globalQueueBound = NV_FALSE;
    }
    if (context->globalQueue) {
        status = s540DarwinWorkQueueStop(context->globalQueue);
        if (status != NV_OK) goto quarantine;
    }
    context->state.workStopped = NV_TRUE;
    if (context->state.privateState) {
        rm_free_private_state(&context->stacks[MAIN], &context->nv);
        context->state.privateState = NV_FALSE;
    }
    if (context->state.eventLocks) {
        rm_destroy_event_locks(&context->stacks[MAIN], &context->nv);
        context->nv.event_spinlock = NULL;
        context->state.eventLocks = NV_FALSE;
    }
    if (!cleanHost()) { status = NV_ERR_INVALID_STATE; goto quarantine; }
    if (context->metadataBound) {
        S540GspContext *expected = context;
        if (!__atomic_compare_exchange_n(&metadataContext, &expected, NULL,
                NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) {
            status = NV_ERR_INVALID_STATE;
            goto quarantine;
        }
        context->metadataBound = NV_FALSE;
    }
    if (context->deviceQueue) s540DarwinWorkQueueDestroy(context->deviceQueue);
    if (context->globalQueue) s540DarwinWorkQueueDestroy(context->globalQueue);
    if (context->isrGuard) s540Darwin_os_free_spinlock(context->isrGuard);
    context->state.quiescent = NV_TRUE;
    if (finalSnapshot) s540GspContextSnapshot(context, finalSnapshot);
    s540GlobalRmHostFree(context->allocationBase);
    return NV_OK;
quarantine:
    context->state.quarantined = NV_TRUE;
    if (finalSnapshot) s540GspContextSnapshot(context, finalSnapshot);
    return status;
}
void s540GspContextSnapshot(S540GspContext *context, S540GspContextSnapshot *out)
{
    if (!context || !out) return;
    out->created = context->state.created;
    out->eventLocks = context->state.eventLocks;
    out->privateState = context->state.privateState;
    out->adapterAttempted = context->state.adapterAttempted;
    out->adapterInitialized = context->state.adapterInitialized;
    out->adapterDisabled = context->state.adapterDisabled;
    out->adapterShutdown = context->state.adapterShutdown;
    out->workStopped = context->state.workStopped;
    out->quiescent = context->state.quiescent;
    out->quarantined = context->state.quarantined;
    out->interruptsHandled = __atomic_load_n(&context->state.interruptsHandled, __ATOMIC_RELAXED);
    out->lockedBottomHalves = __atomic_load_n(&context->state.lockedBottomHalves, __ATOMIC_RELAXED);
    out->unlockedBottomHalves = __atomic_load_n(&context->state.unlockedBottomHalves, __ATOMIC_RELAXED);
}
NvBool s540GspContextInterruptTop(S540GspContext *context, NvBool *locked, NvBool *unlocked)
{
    NvU32 faults = 0, needLocked = 0;
    NvBool handled;
    NvU64 level;
    if (!context || !locked || !unlocked || !context->state.privateState) return NV_FALSE;
    level = s540Darwin_os_acquire_spinlock(context->isrGuard);
    rm_gpu_handle_mmu_faults(&context->stacks[ISR], &context->nv, &faults);
    handled = rm_isr(&context->stacks[ISR], &context->nv, &needLocked);
    *locked = needLocked != 0;
    *unlocked = needLocked == 0 && faults != 0;
    if (handled || faults) __atomic_add_fetch(&context->state.interruptsHandled, 1, __ATOMIC_RELAXED);
    s540Darwin_os_release_spinlock(context->isrGuard, level);
    return handled || faults;
}
void s540GspContextLockedBottomHalf(S540GspContext *context)
{
    rm_isr_bh(&context->stacks[LOCKED_BH], &context->nv);
    __atomic_add_fetch(&context->state.lockedBottomHalves, 1, __ATOMIC_RELAXED);
}
void s540GspContextUnlockedBottomHalf(S540GspContext *context)
{
    rm_isr_bh_unlocked(&context->stacks[UNLOCKED_BH], &context->nv);
    __atomic_add_fetch(&context->state.unlockedBottomHalves, 1, __ATOMIC_RELAXED);
}

static S540GspContext *metadataOwner(nv_state_t *nv)
{
    S540GspContext *context = __atomic_load_n(&metadataContext, __ATOMIC_ACQUIRE);
    return context && &context->nv == nv ? context : NULL;
}

void NV_API_CALL nv_get_screen_info(nv_state_t *nv, NvU64 *physical,
    NvU32 *width, NvU32 *height, NvU32 *depth, NvU32 *pitch, NvU64 *bytes)
{
    S540GspContext *context = metadataOwner(nv);
    s540GlobalRmRecordServiceName(__func__);
    if (!context || !context->intelConsoleVerified || !context->nvidiaConsoleExcluded ||
        !physical || !width || !height || !depth || !pitch || !bytes) {
        // A void callback cannot report unsupported data through a status.
        // Preserve outputs and invalidate admission instead of guessing facts.
        s540GlobalRmRecordUnavailable(25);
        return;
    }
    // The exhaustive provider query excluded this endpoint from every active
    // console. These are the original Linux non-console output values, not
    // fabricated framebuffer geometry or another GPU's framebuffer address.
    *physical = 0;
    *width = *height = *depth = *pitch = 0;
    *bytes = 0;
}

void NV_API_CALL nv_get_disp_smmu_stream_ids(nv_state_t *nv,
    NvU32 *iso, NvU32 *niso)
{
    S540GspContext *context = metadataOwner(nv);
    s540GlobalRmRecordServiceName(__func__);
    if (!context || !iso || !niso) {
        s540GlobalRmRecordUnavailable(26);
        return;
    }
    // Exact pinned nv.c contract: copy the initialized original state. No
    // stream IDs or Tegra/SMMU presence are inferred from this PCIe endpoint.
    *iso = context->nv.iommus.dispIsoStreamId;
    *niso = context->nv.iommus.dispNisoStreamId;
}
