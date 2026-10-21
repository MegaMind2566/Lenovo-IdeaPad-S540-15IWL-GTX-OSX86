static NV_STATUS _osRunAll1HzCallbacks(OBJGPU *pGpu)
{
    OBJTMR *pTmr = GPU_GET_TIMER(pGpu);
    OS1HZTIMERENTRY **ppEntryPtr = &pTmr->pOs1HzCallbackList;
    NvU32 visited = 0;
    NvU64 seen = 0;
    NV_STATUS status = s540RcCheck(pGpu);
    if (status != NV_OK) return status;
    if (!gpuIsGpuFullPower(pGpu)) return NV_ERR_NOT_READY;

    while (*ppEntryPtr != NULL)
    {
        OS1HZTIMERENTRY *entry = *ppEntryPtr;
        NvU64 serial, bit;
        if (visited++ == TMR_NUM_CALLBACKS_OS || !s540RcEntry(pTmr, entry))
            return s540RcRefuse(NV_ERR_INVALID_STATE);
        bit = 1ULL << (entry - pTmr->os1HzCallbackTable);
        if (seen & bit) return s540RcRefuse(NV_ERR_INVALID_STATE);
        seen |= bit;
        status = s540RcCheck(pGpu);
        if (status != NV_OK) return status;
        serial = __atomic_load_n(&s540RcMutationSerial, __ATOMIC_ACQUIRE);
        if (entry->callback != NULL)
            entry->callback(pGpu, entry->data);

        /* The arbitrary original void callback has genuinely returned. It may
         * have removed itself, freed its data, or reused this table slot for a
         * different registration. Never walk its now-free next pointer or
         * pretend the replacement callback has already completed. */
        if (__atomic_load_n(&s540RcMutationSerial, __ATOMIC_ACQUIRE) != serial)
            return s540RcRefuse(NV_ERR_BUSY_RETRY);
        if (!(entry->flags & NV_OS_1HZ_REPEAT))
        {
            status = s540RcMutating();
            if (status != NV_OK) return status;
            *ppEntryPtr = entry->next;
            entry->next = pTmr->pOs1HzCallbackFreeList;
            pTmr->pOs1HzCallbackFreeList = entry;
        }
        else
            ppEntryPtr = &entry->next;
        /* Retire an already returned oneshot exactly once before consuming a
         * later revocation. Unvisited entries remain on the actual live list. */
        status = s540RcCheck(pGpu);
        if (status != NV_OK) return status;
    }
    pGpu->lastCallbackTime = osGetMonotonicTimeNs();
    return NV_OK;
}

NV_STATUS s540Global_s540OsRunQueued1HzCallbacksUnderLockStatus(OBJGPU *pGpu)
{
    NV_STATUS status;
    if (!rmDeviceGpuLockIsOwner(pGpu->gpuInstance)) return NV_ERR_INVALID_LOCK_STATE;
    if (portUtilIsInterruptContext()) return NV_ERR_INVALID_STATE;
    status = s540RcCheck(pGpu);
    if (status != NV_OK) return status;
    if (!pGpu->bCallbackQueued) return NV_OK;
    status = _osRunAll1HzCallbacks(pGpu);
    /* No software-drain completion after low power, mutation, cancellation,
     * corrupt list or callback failure. A void legacy caller may ignore only
     * the C return value; it cannot erase this real pending bit/refusal. */
    if (status == NV_OK)
        portAtomicSetU32(&pGpu->bCallbackQueued, NV_FALSE);
    else
        portAtomicSetU32(&pGpu->bCallbackQueued, NV_TRUE);
    return status;
}
