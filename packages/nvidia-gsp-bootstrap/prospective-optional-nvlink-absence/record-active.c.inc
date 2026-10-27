/* Pure read of actual strong-record fields and a small stable snapshot of its
 * real cancellation producer. No caller readiness flag, cached FirstTxn or
 * service counters, counter mutation or cleanup/release permit exists. */
NV_STATUS s540FirstTxnOptionalNvlinkActive(const void *nv, NvU64 *generation)
{
    S540GspCancellationSnapshot cancellation;
    NV_STATUS status;
    if (!generation) return NV_ERR_INVALID_ARGUMENT;
    *generation = 0;
    if (checkedMaster(nv) != NV_OK || !exactGlobalMaster() ||
        LD(&record.phase) != S540_FIRST_OP ||
        !LD(&record.originalInFlight) || LD(&record.originalExitReady) ||
        LD(&record.originalReturned) ||
        LD(&globalEpoch.state) != S540_FIRST_GLOBAL_READY ||
        !LD(&globalEpoch.validated) || !LD(&globalEpoch.originalReturned) ||
        LD(&globalEpoch.originalStatus) != NV_OK ||
        LD(&globalEpoch.validationStatus) != NV_OK)
        return NV_ERR_INVALID_STATE;
    status = s540GspCancellationGetSnapshot(LD(&record.cancelToken), &cancellation);
    if (status != NV_OK) return status;
    if (cancellation.format != 1U || !cancellation.bound ||
        cancellation.generation != LD(&record.cancelToken) ||
        cancellation.ownerThread != LD(&record.masterThread) ||
        cancellation.phase != S540_GSP_CANCEL_OPERATION)
        return NV_ERR_INVALID_STATE;
    if (cancellation.publicationInFlight) return NV_ERR_NOT_READY;
    if (cancellation.revoked) return NV_ERR_OPERATION_ABORTED;
    if (first() != NV_OK) return first();
    *generation = LD(&record.generation);
    return NV_OK;
}

/* Diagnostic access is distinct from active-call authority: it requires the
 * real wrapper-return fields, accepts a sticky retained failure and can only
 * read the same immutable owner/generation from its actual ordinary master. */
NV_STATUS s540FirstTxnOptionalNvlinkReturned(const void *nv, NvU64 generation)
{
    if (!generation || checkedMaster(nv) != NV_OK || !exactGlobalMaster() ||
        generation != LD(&record.generation) ||
        LD(&record.originalInFlight) || !LD(&record.originalExitReady) ||
        !LD(&record.originalReturned) ||
        LD(&globalEpoch.state) != S540_FIRST_GLOBAL_READY ||
        !LD(&globalEpoch.validated) || !LD(&globalEpoch.originalReturned) ||
        LD(&globalEpoch.originalStatus) != NV_OK ||
        LD(&globalEpoch.validationStatus) != NV_OK)
        return NV_ERR_INVALID_STATE;
    return NV_OK;
}
