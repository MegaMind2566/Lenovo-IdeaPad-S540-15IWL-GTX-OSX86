kbifStopSysMemRequests_GM107
(
    OBJGPU    *pGpu,
    KernelBif *pKernelBif,
    NvBool     bStop
)
{
    const void *state;
    NvU32 regVal;
    NV_STATUS status, completed;
    S540GspCancellationCommitLease lease = 0;
    if (!pGpu) return NV_ERR_INVALID_ARGUMENT;
    state = NV_GET_NV_STATE(pGpu);
    status = s540GspCancellationSubmitEnterState(state, &lease);
    if (status != NV_OK) return status;
    status = GPU_BUS_CFG_RD32(pGpu, NV_XVE_DEV_CTRL, &regVal);
    completed = s540GspCancellationCommitLeaveState(state, lease);
    if (status != NV_OK) return status;
    if (completed != NV_OK) return completed;
    status = s540GspCancellationCheckState(state);
    if (status != NV_OK) return status;
    if (regVal == ~(NvU32)0) return NV_ERR_GPU_IS_LOST;
    regVal = bStop ? FLD_SET_DRF(_XVE, _DEV_CTRL, _CMD_BUS_MASTER, _DISABLED, regVal) :
        FLD_SET_DRF(_XVE, _DEV_CTRL, _CMD_BUS_MASTER, _ENABLED, regVal);
    if (bStop)
    {
        status = s540GspCancellationSubmitEnterState(state, &lease);
        if (status != NV_OK) return status;
        status = GPU_BUS_CFG_WR32(pGpu, NV_XVE_DEV_CTRL, regVal);
        completed = s540GspCancellationCommitLeaveState(state, lease);
        if (status != NV_OK) return status;
        if (completed != NV_OK) return completed;
    }
    else
    {
        /* The selected actual gpuWriteBusConfigReg_GM107 owns the OP-only
         * BME-enable commit. Do not nest a second nonrecursive reservation. */
        status = GPU_BUS_CFG_WR32(pGpu, NV_XVE_DEV_CTRL, regVal);
        if (status != NV_OK) return status;
    }
    /* Readback is a distinct actual endpoint. Revocation may refuse it after
     * an earlier accepted write returned; preserve that truthful uncertainty. */
    status = s540GspCancellationSubmitEnterState(state, &lease);
    if (status != NV_OK) return status;
    status = GPU_BUS_CFG_RD32(pGpu, NV_XVE_DEV_CTRL, &regVal);
    completed = s540GspCancellationCommitLeaveState(state, lease);
    if (status != NV_OK) return status;
    if (completed != NV_OK) return completed;
    status = s540GspCancellationCheckState(state);
    if (status != NV_OK) return status;
    if (regVal == ~(NvU32)0) return NV_ERR_GPU_IS_LOST;
    if (!!DRF_VAL(_XVE, _DEV_CTRL, _CMD_BUS_MASTER, regVal) == !!bStop)
        return NV_ERR_INVALID_STATE;
    /* Only the BME field was observed. No posted DMA stop receipt is issued. */
    return NV_OK;
}
