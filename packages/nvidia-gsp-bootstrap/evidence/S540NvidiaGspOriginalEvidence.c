/* SPDX-License-Identifier: MIT */
#define NVOC_GPU_H_PRIVATE_ACCESS_ALLOWED
#define NVOC_KERNEL_GSP_H_PRIVATE_ACCESS_ALLOWED
#include "nv.h"
#include "S540NvidiaGspOriginalEvidence.h"
#include "nv-priv.h"
#include "gpu/gpu.h"
#include "kernel/gpu/gsp/kernel_gsp.h"

static NvBool record(S540GspOriginalEvidence *out, NvBool condition)
{
    ++out->checks;
    if (!condition)
        ++out->failures;
    return condition;
}

NV_STATUS s540GspObserveOriginal(nvidia_stack_t *sp, nv_state_t *nv,
                               S540GspOriginalEvidence *out)
{
    nv_priv_t *priv;
    OBJGPU *gpu;
    KernelGsp *gsp;
    NV_STATUS status, releaseStatus;
    NvBool gpuReleased = NV_TRUE;
    const NvU32 requiredFlags = NV_INIT_FLAG_HAL | NV_INIT_FLAG_HAL_COMPONENTS |
        NV_INIT_FLAG_GPU_STATE | NV_INIT_FLAG_GPU_STATE_LOAD |
        NV_INIT_FLAG_CORE_LOGIC | NV_INIT_FLAG_GPUMGR_ATTACH | NV_INIT_FLAG_DMA;

    if (out == NULL)
        return NV_ERR_INVALID_ARGUMENT;
    *out = (S540GspOriginalEvidence){0};
    if (!record(out, sp != NULL && nv != NULL))
        return NV_ERR_INVALID_ARGUMENT;

    status = rm_acquire_api_lock(sp);
    out->apiLockAcquired = record(out, status == NV_OK);
    if (status != NV_OK)
        return status;

    priv = NV_GET_NV_PRIV(nv);
    gpu = NV_GET_NV_PRIV_PGPU(nv);
    out->gpuObjectPresent = record(out, priv != NULL && gpu != NULL);
    if (!out->gpuObjectPresent) {
        status = NV_ERR_NOT_READY;
        goto releaseApi;
    }

    status = rm_acquire_gpu_lock(sp, nv);
    out->gpuLockAcquired = record(out, status == NV_OK);
    if (status != NV_OK)
        goto releaseApi;
    gpuReleased = NV_FALSE;

    out->targetDevice = record(out, nv->pci_info.vendor_id == 0x10de &&
                                   nv->pci_info.device_id == 0x1f91);
    out->ownerMatches = record(out, NV_GET_NV_STATE(gpu) == nv);
    out->gspClient = record(out, IS_GSP_CLIENT(gpu));
    gsp = GPU_GET_KERNEL_GSP(gpu);
    out->gspObjectPresent = record(out, gsp != NULL);

    /* Sole true assignment follows both successful GSP_INIT and decode. */
    out->gspInitResponseDecoded = record(out, gpu->gspRmInitialized);
    out->gpuFullyConstructed = record(out, gpu->bFullyConstructed);
    out->gpuStateLoaded = record(out, gpu->bStateLoaded);
    out->gpuStateStable = record(out, !gpu->bStateLoading && !gpu->bStateUnloading);
    out->originalInitFlagsComplete = record(out,
        (priv->flags & requiredFlags) == requiredFlags);
    out->gpuConnected = record(out, gpu->getProperty(gpu, PDB_PROP_GPU_IS_CONNECTED));
    out->gpuNotLost = record(out, !gpu->getProperty(gpu, PDB_PROP_GPU_IS_LOST));
    if (gsp != NULL) {
        out->bootAttempts = gsp->bootAttempts;
        out->gspHealthy = record(out, !gsp->bInInit && !gsp->bInLockdown &&
            !gsp->bFatalError && !gsp->bGspRmForceUnloaded && !gsp->bGspRmUnloaded);
    } else {
        record(out, NV_FALSE);
    }
    status = out->failures == 0 ? NV_OK : NV_ERR_NOT_READY;
    releaseStatus = rm_release_gpu_lock(sp, nv);
    gpuReleased = record(out, releaseStatus == NV_OK);
    if (!gpuReleased)
        status = releaseStatus;

releaseApi:
    releaseStatus = rm_release_api_lock(sp);
    if (!record(out, releaseStatus == NV_OK))
        status = releaseStatus;
    out->locksReleased = releaseStatus == NV_OK && gpuReleased;
    out->adapterReady = status == NV_OK && out->failures == 0 &&
        out->apiLockAcquired && out->gpuLockAcquired && out->locksReleased;
    return status;
}
