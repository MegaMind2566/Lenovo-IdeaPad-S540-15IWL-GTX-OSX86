extern "C" void s540GlobalRmRecordUnavailableProducer(NvU32 service,
    NvU32 producer) {
    s540GlobalRmRecordUnavailable(service);
    observeHostProducer(service, producer);
}

extern "C" NV_STATUS s540GlobalRmReadAllocationDiagnostics(const void *exactNv,
    S540HostAllocationDiagnostics *out) {
    if (!exactNv || !out) return NV_ERR_INVALID_ARGUMENT;
    if (!s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_STATE;
    S540FirstTxnSnapshot record;
    NV_STATUS status = s540FirstTxnGetSnapshot(exactNv, &record);
    if (status != NV_OK) return status;
    NvU64 thread = 0;
    status = s540Darwin_os_get_current_thread(&thread);
    if (status != NV_OK) return status;
    if (!thread || thread != record.masterThread) return NV_ERR_INVALID_STATE;
    if (!record.originalReturned || record.originalInFlight) return NV_ERR_NOT_READY;
    S540HostAllocationDiagnostics captured{};
    captured.format = 1U;
    captured.bytes = sizeof(captured);
    captured.observedMask = S540_HOST_ALLOCATION_DIAG_PRODUCER_COUNTS |
        S540_HOST_ALLOCATION_DIAG_ALLOCATION_COUNTS;
    captured.producerCallsLifetime = __atomic_load_n(
        &hostAllocationObservation.producerTotal, __ATOMIC_RELAXED);
    captured.producerMask = __atomic_load_n(
        &hostAllocationObservation.producerMask, __ATOMIC_RELAXED);
    for (NvU32 producer = 0U; producer != S540_HOST_ALLOCATION_PRODUCER_COUNT; ++producer)
        captured.producerCalls[producer] = __atomic_load_n(
            &hostAllocationObservation.producerCalls[producer], __ATOMIC_RELAXED);
    captured.producerFirstState = __atomic_load_n(
        &hostAllocationObservation.producerFirstState, __ATOMIC_ACQUIRE);
    if (captured.producerFirstState == 2U) {
        captured.observedMask |= S540_HOST_ALLOCATION_DIAG_PRODUCER_FIRST;
        captured.producerFirstId = hostAllocationObservation.producerFirstId;
        captured.producerFirstService = hostAllocationObservation.producerFirstService;
    }
    captured.allocationFailuresLifetime = __atomic_load_n(
        &hostAllocationObservation.allocationFailures, __ATOMIC_RELAXED);
    captured.allocationStagesMask = __atomic_load_n(
        &hostAllocationObservation.allocationStagesMask, __ATOMIC_RELAXED);
    captured.allocationFirstState = __atomic_load_n(
        &hostAllocationObservation.allocationFirstState, __ATOMIC_ACQUIRE);
    if (captured.allocationFirstState == 2U) {
        captured.observedMask |= S540_HOST_ALLOCATION_DIAG_ALLOCATION_FIRST;
        captured.allocationFirstStage = hostAllocationObservation.allocationFirstStage;
        captured.allocationFirstStatus = hostAllocationObservation.allocationFirstStatus;
        captured.allocationFirstOriginal = hostAllocationObservation.allocationFirstOriginal;
        captured.allocationFirstBytes = hostAllocationObservation.allocationFirstBytes;
    }
    *out = captured;
    return NV_OK;
}
