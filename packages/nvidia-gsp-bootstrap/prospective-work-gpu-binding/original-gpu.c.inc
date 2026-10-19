/* SPDX-License-Identifier: MIT
 * Append to the actual-header first-transaction original bridge. No private
 * pointer lookup occurs under a queue guard or in the GPU work check.
 */
_Static_assert((NvU32)S540_FIRST_WORK_REQUIRES_GPU == (NvU32)S540_FIRST_GPU_REQUIRES_GPU,
               "The record must use the actual canonical requires-GPU bit");
_Static_assert(sizeof(rmGpuLocksGetOwnedMask()) == sizeof(NvU32),
               "GPU ownership mask width changed");

NV_STATUS s540FirstTxnOriginalGpuAttachFailed(void *osInfo, NV_STATUS failure)
{
    /* This source hook must run before every attach rollback mutation and
     * before the outer caller loses its pending-device/argument ownership. */
    return s540FirstTxnRequestDeferredCleanup((nv_state_t *)osInfo,
        failure == NV_OK ? NV_ERR_INVALID_STATE : failure);
}

NV_STATUS s540FirstTxnOriginalGpuAttachBegin(OBJGPU *gpu, void *osInfo)
{
    nv_state_t *nv = (nv_state_t *)osInfo;
    nv_priv_t *priv;
    if (!gpu || !nv)
        return s540FirstTxnOriginalGpuAttachFailed(osInfo, NV_ERR_INVALID_ARGUMENT);
    if (!rmapiLockIsOwner())
        return s540FirstTxnOriginalGpuAttachFailed(osInfo, NV_ERR_INVALID_LOCK_STATE);
    /* The API token protects this original private-pointer read. The hook is
     * BEFORE either source store, so refused reattach cannot overwrite them. */
    priv = NV_GET_NV_PRIV(nv);
    if (!priv || priv->pGpu != NULL || gpu->pOsGpuInfo != NULL ||
        gpu->gpuInstance >= sizeof(NvU32) * 8U)
        return s540FirstTxnOriginalGpuAttachFailed(osInfo, NV_ERR_INVALID_STATE);
    return s540FirstTxnGpuAttachReserve(nv, gpu, gpu->gpuInstance);
}

NV_STATUS s540FirstTxnOriginalGpuAttachCommit(OBJGPU *gpu, void *osInfo)
{
    nv_state_t *nv = (nv_state_t *)osInfo;
    nv_priv_t *priv;
    if (!gpu || !nv)
        return s540FirstTxnOriginalGpuAttachFailed(osInfo, NV_ERR_INVALID_ARGUMENT);
    if (!rmapiLockIsOwner())
        return s540FirstTxnOriginalGpuAttachFailed(osInfo, NV_ERR_INVALID_LOCK_STATE);
    priv = NV_GET_NV_PRIV(nv);
    if (!priv || priv->pGpu != gpu || NV_GET_NV_STATE(gpu) != nv)
        return s540FirstTxnOriginalGpuAttachFailed(osInfo, NV_ERR_INVALID_STATE);
    return s540FirstTxnGpuAttachPublish(nv, gpu, gpu->gpuInstance);
}

NV_STATUS s540FirstTxnOriginalRejectWorkGpu(const void *originalWork,
    NV_STATUS failure)
{
    return s540FirstTxnGpuRejectWork(originalWork, failure);
}

NV_STATUS s540FirstTxnOriginalCheckWorkGpu(const void *originalWork, OBJGPU *gpu)
{
    const nv_work_item_t *item = (const nv_work_item_t *)originalWork;
    NvU32 instance;
    NV_STATUS status;
    if (!item || !gpu || !item->flags.bRequiresGpu)
        return s540FirstTxnOriginalRejectWorkGpu(originalWork, NV_ERR_INVALID_ARGUMENT);
    instance = item->gpuInstance;
    if (instance >= sizeof(NvU32) * 8U || gpu->gpuInstance != instance ||
        !(rmGpuLocksGetOwnedMask() & NVBIT(instance)))
        return s540FirstTxnOriginalRejectWorkGpu(originalWork, NV_ERR_INVALID_LOCK_STATE);
    /* Work holds the actual selected GPU token. Its reciprocal nv identity is
     * compared with the published cache; NV_GET_NV_PRIV_PGPU requires an API
     * token and is deliberately not used here. No new OWNER policy is granted. */
    status = s540FirstTxnGpuCheckResolvedWork(NV_GET_NV_STATE(gpu), originalWork,
        gpu, instance);
    return status == NV_OK ? NV_OK :
        s540FirstTxnOriginalRejectWorkGpu(originalWork, status);
}

NV_STATUS s540FirstTxnOriginalGpuDetach(OBJGPU *gpu)
{
    if (!gpu || !rmapiLockIsOwner()) {
        s540FirstTxnObserveServiceRefusal(4U, 1U, NV_ERR_INVALID_LOCK_STATE);
        return NV_ERR_INVALID_LOCK_STATE;
    }
    /* Must run before client-pending masks, DPC detach, caps mutation or the
     * void-delete/unlink path. Existing unknown-OWNER policy refuses OBJGPU;
     * the source caller must propagate refusal without any of those changes. */
    return s540FirstTxnCheckBeforeDeleteObject(gpu);
}
