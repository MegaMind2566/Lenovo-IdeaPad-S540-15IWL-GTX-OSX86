extern "C" NV_STATUS s540GlobalRmReadUnavailableDiagnostics(const void *exactNv,
    S540HostUnavailableDiagnostics *out) {
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
    S540HostUnavailableDiagnostics captured{};
    captured.format = 1U;
    captured.bytes = sizeof(captured);
    captured.observedMask = S540_HOST_UNAVAILABLE_DIAG_COUNTS;
    captured.unavailableCallsLifetime = __atomic_load_n(
        &hostUnavailableObservation.total, __ATOMIC_RELAXED);
    captured.sitesObservedMask = __atomic_load_n(
        &hostUnavailableObservation.sitesMask, __ATOMIC_RELAXED);
    for (NvU32 site = 0; site != S540_HOST_UNAVAILABLE_SITE_COUNT; ++site)
        captured.siteCallsLifetime[site] = __atomic_load_n(
            &hostUnavailableObservation.siteCalls[site], __ATOMIC_RELAXED);
    captured.firstState = __atomic_load_n(
        &hostUnavailableObservation.firstState, __ATOMIC_ACQUIRE);
    if (captured.firstState == 2U) {
        captured.observedMask |= S540_HOST_UNAVAILABLE_DIAG_FIRST;
        captured.firstSite = hostUnavailableObservation.firstSite;
        captured.firstService = hostUnavailableObservation.firstService;
    }
    *out = captured;
    return NV_OK;
}
