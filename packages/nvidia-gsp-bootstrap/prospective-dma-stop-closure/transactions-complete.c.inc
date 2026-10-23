kbifWaitForTransactionsComplete_TU102
(
    OBJGPU    *pGpu,
    KernelBif *pKernelBif
)
{
    const void *state;
    void *handle;
    NvU16 vendorId = 0, deviceId = 0;
    NvU32 value;
    RMTIMEOUT timeout;
    S540GspCancellationCommitSnapshot observed = {0};
    S540GspCancellationCommitLease lease = 0;
    NV_STATUS status, completed;
    if (pGpu == NULL) return NV_ERR_INVALID_ARGUMENT;
    state = NV_GET_NV_STATE(pGpu);
    /* CheckState alone returns OK for unrelated/unbound identities. Require
     * the exact real bound state and this thread's enrolled scope first. */
    if (!state || !s540GspCancellationCurrentScopeActive()) return NV_ERR_INVALID_STATE;
    status = s540GspCancellationCommitReadState(state, &observed);
    if (status != NV_OK) return status;
    if (!observed.generation || observed.publicationInFlight || observed.inFlight)
        return NV_ERR_IN_USE;
    status = s540GspCancellationCheckState(state);
    if (status != NV_OK) return status;
    /* A real accepted endpoint can finish after revocation. Its reservation
     * persists until its actual return; no new read starts after OP closes. */
    status = s540GspCancellationSubmitEnterState(state, &lease);
    if (status != NV_OK) return status;
    handle = osPciInitHandle(gpuGetDomain(pGpu), gpuGetBus(pGpu),
        gpuGetDevice(pGpu), 0, &vendorId, &deviceId);
    completed = s540GspCancellationCommitLeaveState(state, lease);
    if (completed != NV_OK) return completed;
    if (!handle) return NV_ERR_INVALID_STATE;
    if (vendorId == 0xffffU || deviceId == 0xffffU) return NV_ERR_GPU_IS_LOST;
    status = s540GspCancellationCheckState(state);
    if (status != NV_OK) return status;
    gpuSetTimeout(pGpu, GPU_TIMEOUT_DEFAULT, &timeout, 0);
    for (;;)
    {
        status = s540GspCancellationCheckState(state);
        if (status != NV_OK) return status;
        status = s540GspCancellationSubmitEnterState(state, &lease);
        if (status != NV_OK) return status;
        value = osPciReadDword(handle, NV_XVE_DEVICE_CONTROL_STATUS);
        completed = s540GspCancellationCommitLeaveState(state, lease);
        if (completed != NV_OK) return completed;
        status = s540GspCancellationCheckState(state);
        if (status != NV_OK) return status;
        if (value == ~(NvU32)0) return NV_ERR_GPU_IS_LOST;
        /* TP is outstanding non-posted requests awaiting completion. Zero
         * does not certify posted writes, whole DMA stop or safe reclamation. */
        if (DRF_VAL(_XVE, _DEVICE_CONTROL_STATUS, _TRANSACTIONS_PENDING, value) == 0)
            return NV_OK;
        status = gpuCheckTimeout(pGpu, &timeout);
        if (status != NV_OK) return status;
    }
}
