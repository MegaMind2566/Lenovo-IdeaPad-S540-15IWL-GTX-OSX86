extern "C" NV_STATUS s540DeviceReadAllocationDiagnostics(const void *exactNv,
    S540DeviceAllocationDiagnostics *out) {
    if (!exactNv || !out) return NV_ERR_INVALID_ARGUMENT;
    if (!ordinary()) return NV_ERR_INVALID_STATE;
    S540FirstTxnSnapshot record;
    NV_STATUS status = s540FirstTxnGetSnapshot(exactNv, &record);
    if (status != NV_OK) return status;
    NvU64 thread = 0;
    status = s540Darwin_os_get_current_thread(&thread);
    if (status != NV_OK) return status;
    if (!thread || thread != record.masterThread) return NV_ERR_INVALID_STATE;
    if (!record.originalReturned || record.originalInFlight) return NV_ERR_NOT_READY;
    S540DeviceAllocationDiagnostics captured{};
    captured.format = 1U;
    captured.bytes = sizeof(captured);
    captured.observedMask = S540_DEVICE_ALLOC_DIAG_COUNTS;
    captured.allocationAttemptsLifetime = __atomic_load_n(
        &allocationObservation.attempts, __ATOMIC_RELAXED);
    captured.allocationFailuresLifetime = __atomic_load_n(
        &allocationObservation.failures, __ATOMIC_RELAXED);
    captured.entryRejectionsLifetime = __atomic_load_n(
        &allocationObservation.entryRejections, __ATOMIC_RELAXED);
    captured.largestRequestedPagesLifetime = __atomic_load_n(
        &allocationObservation.largestPages, __ATOMIC_RELAXED);
    captured.firstFailureState = __atomic_load_n(
        &allocationObservation.firstFailureState, __ATOMIC_ACQUIRE);
    if (captured.firstFailureState == 2U) {
        captured.observedMask |= S540_DEVICE_ALLOC_DIAG_FIRST_FAILURE;
        captured.firstFailure = allocationObservation.firstFailure;
    }
    *out = captured;
    return NV_OK;
}
