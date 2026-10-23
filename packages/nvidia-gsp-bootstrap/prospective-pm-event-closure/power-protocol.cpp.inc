NV_STATUS Protocol::coupleCancellation(const void *state, NvU64 token) {
    if (state_.stopped || cancellationState_ || !state || !token)
        return NV_ERR_INVALID_STATE;
    const NV_STATUS status = s540GspCancellationPowerAcquireState(state, token);
    if (status != NV_OK) return status;
    cancellationState_ = state; cancellationToken_ = token;
    // A PM event may precede ContextCreate and cancellation binding. Carry the
    // first real event through the same guard before original work can begin.
    if (state_.revoked) {
        const NV_STATUS revoked = s540GspCancellationPowerRevokeAtState(
            cancellationState_, cancellationToken_, state_.revokedAtNs);
        return revoked != NV_OK ? revoked : NV_STATUS(NV_ERR_OPERATION_ABORTED);
    }
    return NV_OK;
}
NV_STATUS Protocol::releaseCancellation() {
    if (!cancellationState_) return NV_OK;
    const NV_STATUS status = s540GspCancellationPowerReleaseState(cancellationState_, cancellationToken_);
    if (status != NV_OK) return status;
    cancellationState_ = nullptr; cancellationToken_ = 0;
    return NV_OK;
}
NV_STATUS Protocol::closeCancellation(NvU64 eventNs) {
    if (!cancellationState_) return NV_OK;
    return s540GspCancellationPowerRevokeAtState(
        cancellationState_, cancellationToken_, eventNs);
}
bool Protocol::cancellationCoupled() const { return cancellationState_ != nullptr; }
