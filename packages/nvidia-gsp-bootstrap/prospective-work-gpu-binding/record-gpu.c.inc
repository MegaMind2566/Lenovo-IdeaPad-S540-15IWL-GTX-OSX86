/* SPDX-License-Identifier: MIT
 * Append to record C556f1771; the builder adds gpuInstance to actual metadata,
 * declares gpuBindingCheckMetadata above its two admission/entry call sites,
 * and leaves the existing policy and RM-semaphore refusal gate unchanged.
 */
enum { GPU_BINDING_EMPTY = 0, GPU_BINDING_RESERVING = 1,
       GPU_BINDING_PUBLISHED = 2 };
static struct {
    NvU32 state, instance;
    NvU64 generation;
    const void *nv, *gpu;
} gpuBinding;

static NV_STATUS gpuBindingPublished(void)
{
    if (first() != NV_OK) return first();
    if (LD(&gpuBinding.state) != GPU_BINDING_PUBLISHED ||
        LD(&gpuBinding.generation) != LD(&record.generation) ||
        !exact(LD(&gpuBinding.nv)) || !LD(&gpuBinding.gpu))
        return refuse(NV_ERR_NOT_READY, SITE_BIND);
    return NV_OK;
}

NV_STATUS s540FirstTxnGpuAttachReserve(const void *nv,
    const void *gpu, NvU32 instance)
{
    NvU32 empty = GPU_BINDING_EMPTY;
    NV_STATUS status;
    if (checkedMaster(nv) != NV_OK || !gpu ||
        instance >= sizeof(NvU32) * 8U ||
        !LD(&record.originalInFlight) ||
        LD(&record.phase) != S540_FIRST_OP)
        return refuse(NV_ERR_INVALID_STATE, SITE_BIND);
    status = checkExecution();
    if (status != NV_OK) return refuse(status, SITE_BIND);
    if (!__atomic_compare_exchange_n(&gpuBinding.state, &empty,
            (NvU32)GPU_BINDING_RESERVING, NV_FALSE,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return refuse(NV_ERR_IN_USE, SITE_BIND);
    /* RESERVING is never executable. Even an interrupted/refused publication
     * retains this planned identity; there is no replacement or reset path. */
    ST(&gpuBinding.nv, nv);
    ST(&gpuBinding.gpu, gpu);
    ST(&gpuBinding.instance, instance);
    ST(&gpuBinding.generation, LD(&record.generation));
    return first();
}

NV_STATUS s540FirstTxnGpuAttachPublish(const void *nv,
    const void *gpu, NvU32 instance)
{
    NvU32 expected = GPU_BINDING_RESERVING;
    NV_STATUS status;
    if (checkedMaster(nv) != NV_OK || !LD(&record.originalInFlight) ||
        LD(&record.phase) != S540_FIRST_OP ||
        LD(&gpuBinding.state) != GPU_BINDING_RESERVING ||
        LD(&gpuBinding.nv) != nv || LD(&gpuBinding.gpu) != gpu ||
        LD(&gpuBinding.instance) != instance ||
        LD(&gpuBinding.generation) != LD(&record.generation))
        return refuse(NV_ERR_INVALID_STATE, SITE_BIND);
    status = checkExecution();
    if (status != NV_OK) return refuse(status, SITE_BIND);
    /* Only the typed original commit, after BOTH actual reciprocal stores,
     * calls this publication. No service/queue guard reads private RM state. */
    if (!__atomic_compare_exchange_n(&gpuBinding.state, &expected,
            (NvU32)GPU_BINDING_PUBLISHED, NV_FALSE,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return refuse(NV_ERR_IN_USE, SITE_BIND);
    return first();
}

static NV_STATUS gpuBindingCheckMetadata(const S540FirstTxnOriginalWork *metadata)
{
    NV_STATUS status;
    if (!metadata) return refuse(NV_ERR_INVALID_ARGUMENT, SITE_WORK);
    if (!(metadata->flags & S540_FIRST_GPU_REQUIRES_GPU)) return NV_OK;
    status = gpuBindingPublished();
    if (status != NV_OK) return status;
    if (metadata->gpuInstance != LD(&gpuBinding.instance))
        return refuse(NV_ERR_INVALID_DEVICE, SITE_WORK);
    return NV_OK;
}

NV_STATUS s540FirstTxnGpuCheckResolvedWork(const void *nv,
    const void *originalWork, const void *gpu, NvU32 instance)
{
    S540FirstTxnOriginalWork metadata = {0};
    NvS32 i = active(work, currentThread()), event;
    NV_STATUS status;
    if (!exact(nv) || !originalWork || !gpu || i < 0 ||
        work[i].data != originalWork ||
        !s540GspCancellationCurrentScopeActive())
        return refuse(NV_ERR_INVALID_STATE, SITE_WORK);
    status = gpuBindingPublished();
    if (status != NV_OK) return status;
    if (LD(&gpuBinding.nv) != nv || LD(&gpuBinding.gpu) != gpu ||
        LD(&gpuBinding.instance) != instance)
        return refuse(NV_ERR_INVALID_DEVICE, SITE_WORK);
    status = s540FirstTxnInspectOriginalWork(originalWork, &metadata);
    if (status != NV_OK) return refuse(status, SITE_WORK);
    if (!(metadata.flags & S540_FIRST_GPU_REQUIRES_GPU) ||
        metadata.gpuInstance != instance ||
        descriptor(S540_FIRST_DESC_WORK, metadata.callback, 0, metadata.flags) !=
            (NvS32)work[i].descriptor)
        return refuse(NV_ERR_INVALID_DEVICE, SITE_WORK);
    status = gpuBindingCheckMetadata(&metadata);
    if (status != NV_OK) return status;
    if (work[i].eventId) {
        event = eventIndex(metadata.parameter, work[i].eventId);
        status = authenticateEvent(event);
        if (status != NV_OK) return refuse(status, SITE_WORK);
    }
    return first();
}

NV_STATUS s540FirstTxnGpuRejectWork(const void *originalWork, NV_STATUS failure)
{
    NvS32 i = active(work, currentThread());
    if (!bound() || !originalWork || i < 0 ||
        work[i].data != originalWork ||
        !s540GspCancellationCurrentScopeActive())
        return refuse(NV_ERR_INVALID_STATE, SITE_WORK);
    /* Denial only: do not manufacture original/action return or release an
     * event borrower. The actual original done and later wrapper/action return
     * keep their existing separate ownership boundaries. */
    return refuse(failure, SITE_WORK);
}

NV_STATUS s540FirstTxnGpuPrivateStateMayChange(const void *nv)
{
    if (!bound()) {
        if (LD(&record.phase) == S540_FIRST_UNBOUND) return NV_OK;
        return refuse(NV_ERR_IN_USE, SITE_BIND);
    }
    if (first() != NV_OK) return first();
    /* Initial private construction precedes exact-nv Bind. Only its actual
     * retained master may perform it. Once attached, even an empty/recovery
     * private pointer is not permission to replace this generation. */
    if (!LD(&record.nv) && nv && master() &&
        s540Darwin_os_semaphore_may_sleep() &&
        LD(&record.phase) == S540_FIRST_OP)
        return NV_OK;
    return refuse(NV_ERR_IN_USE, SITE_BIND);
}
