s540FirstTxnOriginalLocksReleased(const void *exactNv)
{
    S540FirstTxnGlobalSnapshot before = {0}, after = {0};
    S540FirstTxnSnapshot recordBefore = {0}, recordAfter = {0};
    OBJSYS *sys;
    NvU64 thread = 0, afterThread = 0;
    NV_STATUS status;
    if (!exactNv || !s540Darwin_os_semaphore_may_sleep())
        return NV_ERR_INVALID_REQUEST;
    status = s540Darwin_os_get_current_thread(&thread);
    if (status != NV_OK) return status;
    if (!thread || thread == ~(NvU64)0) return NV_ERR_INVALID_STATE;
    status = s540FirstTxnGlobalGetSnapshot(&before);
    if (status != NV_OK) return status;
    status = s540FirstTxnGetSnapshot(exactNv, &recordBefore);
    if (status != NV_OK) return status;
    /* Global/record owner, generation and ordinary thread become immutable at
     * BeginOwner. READY comes only from completed, validated global startup.
     * The retained experiment excludes global teardown for this lifetime.
     * Sticky firstStatus is observed and preserved; it is not an RM lock. */
    if (!before.owner || before.nv != exactNv || !before.generation ||
        before.masterThread != thread || before.state != S540_FIRST_GLOBAL_READY ||
        !before.originalReturned || !before.validated ||
        recordBefore.generation != before.generation ||
        recordBefore.masterThread != thread ||
        recordBefore.firstStatus != before.firstStatus)
        return NV_ERR_INVALID_STATE;
    sys = SYS_GET_INSTANCE();
    if (!sys) return NV_ERR_NOT_READY;
    /* This strong query reads the actual API TLS and GPU/allocation ownership
     * and requires the selected basic lock model with SYS.pSema == NULL.
     * No generic literal osIsRmSemaOwner() is treated as evidence. */
    status = s540ProspectiveOriginalCurrentThreadLocksReleased(sys);
    if (status != NV_OK) return status;
    if (SYS_GET_INSTANCE() != sys) return NV_ERR_INVALID_STATE;
    status = s540Darwin_os_get_current_thread(&afterThread);
    if (status != NV_OK) return status;
    status = s540FirstTxnGlobalGetSnapshot(&after);
    if (status != NV_OK) return status;
    status = s540FirstTxnGetSnapshot(exactNv, &recordAfter);
    if (status != NV_OK) return status;
    if (afterThread != thread || SYS_GET_INSTANCE() != sys ||
        after.owner != before.owner || after.nv != before.nv ||
        after.generation != before.generation || after.masterThread != thread ||
        after.state != before.state || after.originalReturned != before.originalReturned ||
        after.validated != before.validated || after.firstStatus != before.firstStatus ||
        recordAfter.generation != recordBefore.generation ||
        recordAfter.masterThread != thread ||
        recordAfter.firstStatus != recordBefore.firstStatus)
        return NV_ERR_INVALID_STATE;
    return NV_OK;
}
