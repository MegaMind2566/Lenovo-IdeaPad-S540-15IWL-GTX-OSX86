/* A separate, immutable-identity cleanup observer. No first-error or phase
 * bit is cleared. In particular, this is not an original-entry authorizer. */
NV_STATUS s540FirstTxnCleanupMaskReadMaster(const void *nv,
    S540FirstTxnGlobalSnapshot *out)
{
    S540GspCancellationSnapshot cancellation = {0};
    S540GspCancellationCommitSnapshot commit = {0};
    S540FirstTxnGlobalSnapshot view = {0};
    NV_STATUS status;
    NvU32 phase;
    if (!out || !nv) return NV_ERR_INVALID_ARGUMENT;
    if (checkedMaster(nv) != NV_OK || !exactGlobalMaster())
        return NV_ERR_INVALID_STATE;
    /* This path exists only for a genuine sticky failure. The ordinary clean
     * operation authorizer keeps its original rules and separate call sites. */
    if (first() == NV_OK || !LD(&record.originalReturned) ||
        !LD(&record.originalExitReady) || LD(&record.originalInFlight) ||
        !LD(&globalEpoch.originalReturned) || !LD(&globalEpoch.validated) ||
        LD(&globalEpoch.state) != S540_FIRST_GLOBAL_READY)
        return NV_ERR_INVALID_STATE;
    phase = LD(&record.phase);
    if (phase != S540_FIRST_RETAINED) return NV_ERR_INVALID_STATE;
    status = s540GspCancellationGetSnapshot(LD(&record.cancelToken), &cancellation);
    if (status != NV_OK) return status;
    if (!cancellation.bound || cancellation.generation != LD(&record.cancelToken) ||
        cancellation.ownerThread != LD(&record.masterThread) ||
        cancellation.phase != S540_GSP_CANCEL_CLEANUP || !cancellation.revoked ||
        cancellation.publicationInFlight || !cancellation.deadlineNs)
        return NV_ERR_INVALID_STATE;
    status = s540GspCancellationCommitReadState(nv, &commit);
    if (status != NV_OK) return status;
    if (commit.generation != cancellation.generation || !commit.revoked ||
        commit.publicationInFlight || commit.inFlight)
        return NV_ERR_IN_USE;
    /* Reject every ticket, including queued/claimed/retained tickets: it must
     * have completed its real cancellation/return, not just stopped running.
     * A sticky first error prevents new admit/enter commits after this point. */
    if (LD(&record.gate) || LD(&record.freeGate) ||
        (LD(&record.control) >> 48) || LD(&backendScopes) ||
        liveEntries(work) || liveEntries(direct) || borrowers())
        return NV_ERR_IN_USE;
    status = s540FirstTxnIrqValidateSoftwareDrained();
    if (status != NV_OK) return status;
    status = s540GspCancellationCheckState(nv);
    if (status != NV_OK) return status;
    status = s540FirstTxnGlobalGetSnapshot(&view);
    if (status != NV_OK) return status;
    if (view.owner != LD(&record.owner) || view.generation != LD(&record.generation) ||
        view.masterThread != LD(&record.masterThread) || view.nv != nv ||
        view.firstStatus != (NvU32)first() || view.firstStatus == NV_OK ||
        view.state != S540_FIRST_GLOBAL_READY || !view.validated)
        return NV_ERR_INVALID_STATE;
    *out = view;
    return NV_OK;
}
