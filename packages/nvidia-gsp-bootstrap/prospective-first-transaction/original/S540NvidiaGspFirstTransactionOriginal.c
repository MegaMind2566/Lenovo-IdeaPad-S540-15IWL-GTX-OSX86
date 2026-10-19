/* SPDX-License-Identifier: MIT */
/* Strong source probes, actual pinned NVIDIA types. No caller readiness flag. */
#include "nv.h"
#include "nv-priv.h"
#include "gpu/gpu.h"
#include "core/locks.h"
#include "rmapi/rmapi.h"
#include "gpu/timer/objtmr.h"
#include "nvoc/rtti.h"
#include "S540NvidiaGspFirstTransactionOriginal.h"
#include "../../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../../nvidia-device-transport/src/nv_unsupported_memory.h"
#include "../../../nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.h"
#include "../../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

NV_STATUS s540FirstTxnOriginalApiGpuLocksReleased(const void *exactNv)
{
    if (exactNv == NULL || !s540Darwin_os_semaphore_may_sleep())
        return NV_ERR_INVALID_REQUEST;
    if (rmapiLockIsOwner() || rmGpuLocksGetOwnedMask() != 0)
        return NV_ERR_INVALID_LOCK_STATE;
    return NV_OK;
}
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *exactNv)
{
    NV_STATUS status = s540FirstTxnOriginalApiGpuLocksReleased(exactNv);
    if (status != NV_OK) return status;
    /* The exact v2 osAcquireRmSema/CondAcquire/Release are no-op functions.
     * No real RM-semaphore receipt exists. The generated osIsRmSemaOwner
     * literal true is deliberately not used as evidence. Admission remains
     * blocked on that selected-service gap; API/GPU tokens are actually read. */
    return NV_ERR_NOT_SUPPORTED;
}

NV_STATUS s540FirstTxnOriginalReadServiceCounters(const void *exactNv,
    S540FirstTxnServiceCounters *out)
{
    S540NvidiaGlobalRmHostSnapshot host;
    S540DeviceMemoryStatistics memory;
    S540NvidiaGlobalCryptoSnapshot crypto;
    if (exactNv == NULL || out == NULL) return NV_ERR_INVALID_ARGUMENT;
    s540GlobalRmHostSnapshot(&host);
    memory = s540DeviceMemoryStatistics();
    s540Global_crypto_snapshot(&crypto);
    out->hostInitialized = host.initialized;
    out->hostUnavailable = host.unavailableCalls;
    out->hostInvalidFrees = host.invalidFrees;
    out->memoryUnavailableEver = memory.unavailableOperationsEver;
    out->memoryViolationsEver = memory.lifetimeViolationsEver;
    out->cryptoUnavailable = crypto.unavailable_calls;
    out->cryptoMaskLow = crypto.unavailable_symbol_mask;
    out->cryptoMaskHigh = crypto.unavailable_symbol_mask_high;
    out->cryptoOverflow = crypto.counter_overflow != 0;
    return NV_OK;
}

NV_STATUS s540FirstTxnCheckBeforeDestroyGpu(OBJGPU *gpu)
{
    if (gpu == NULL) return NV_ERR_INVALID_ARGUMENT;
    return s540FirstTxnCheckBeforeDestroy(NV_GET_NV_STATE(gpu));
}
NV_STATUS s540FirstTxnRequestDeferredCleanupGpu(OBJGPU *gpu, NV_STATUS status)
{
    if (gpu == NULL) return NV_ERR_INVALID_ARGUMENT;
    return s540FirstTxnRequestDeferredCleanup(NV_GET_NV_STATE(gpu), status);
}
NV_STATUS s540FirstTxnRetainOriginalAllocationGpu(OBJGPU *gpu,
    const void *allocation, const void *mapping, const void *mappingPriv)
{
    if (gpu == NULL) return NV_ERR_INVALID_ARGUMENT;
    return s540FirstTxnRetainOriginalAllocation(NV_GET_NV_STATE(gpu), allocation, mapping, mappingPriv);
}

NV_STATUS s540FirstTxnInspectOriginalWork(const void *originalWork,
    S540FirstTxnOriginalWork *out)
{
    const nv_work_item_t *work = originalWork;
    NvU32 flags = 0;
    if (work == NULL || out == NULL) return NV_ERR_INVALID_ARGUMENT;
    if (work->flags.bDontFreeParams) flags |= S540_FIRST_WORK_DONT_FREE;
    if (work->flags.bFallbackToDpc) flags |= S540_FIRST_WORK_FALLBACK;
    if (work->flags.bRequiresGpu) flags |= S540_FIRST_WORK_REQUIRES_GPU;
    if (work->flags.bLockSema) flags |= S540_FIRST_WORK_SEMA;
    if (work->flags.apiLock == WORKITEM_FLAGS_API_LOCK_READ_WRITE) flags |= S540_FIRST_WORK_API_WRITE;
    else if (work->flags.apiLock == WORKITEM_FLAGS_API_LOCK_READ_ONLY) flags |= S540_FIRST_WORK_API_READ;
    else if (work->flags.apiLock != WORKITEM_FLAGS_API_LOCK_NOT_ACQUIRED) return NV_ERR_INVALID_ARGUMENT;
    if (work->flags.bLockGpus) flags |= S540_FIRST_WORK_ALL_GPUS;
    if (work->flags.bLockGpuGroupDevice) flags |= S540_FIRST_WORK_GROUP_DEVICE;
    if (work->flags.bLockGpuGroupSubdevice) flags |= S540_FIRST_WORK_GROUP_SUBDEVICE;
    if (work->flags.bFullGpuSanity) flags |= S540_FIRST_WORK_FULL_SANITY;
    if (work->flags.bDropOnUnloadQueueFlush) flags |= S540_FIRST_WORK_DROP_FLUSH;
    if (work->flags.bSetExpandedGpuVisibility) flags |= S540_FIRST_WORK_EXPANDED;
    out->callback = work->flags.bRequiresGpu ? (NvUPtr)work->func.pGpuFunction : (NvUPtr)work->func.pSystemFunction;
    out->parameter = work->pData;
    out->flags = flags;
    return NV_OK;
}

NV_STATUS s540FirstTxnInspectOriginalEvent(const void *originalEvent,
    S540FirstTxnOriginalEvent *out)
{
    const TMR_EVENT *event = originalEvent;
    if (event == NULL || out == NULL) return NV_ERR_INVALID_ARGUMENT;
    /* pUserData is copied as the original callback's owner identity only.
     * It is NOT assumed to be an NVOC object. A reviewed callback descriptor
     * and registered owner generation must authenticate it before use. */
    out->callback = (NvUPtr)event->pTimeProc;
    out->owner = event->pUserData;
    return NV_OK;
}

NV_STATUS s540FirstTxnInspectOriginalOwner(const void *originalObject,
    NvUPtr *classIdentity)
{
    const Dynamic *object = originalObject;
    if (object == NULL || classIdentity == NULL) return NV_ERR_INVALID_ARGUMENT;
    /* Only actual typed NVOC registration sites may supply this object.
     * Arbitrary event pUserData has not acquired that authority. */
    if (object->__nvoc_rtti == NULL || object->__nvoc_rtti->pClassDef == NULL)
        return NV_ERR_INVALID_STATE;
    *classIdentity = (NvUPtr)object->__nvoc_rtti->pClassDef;
    return NV_OK;
}
