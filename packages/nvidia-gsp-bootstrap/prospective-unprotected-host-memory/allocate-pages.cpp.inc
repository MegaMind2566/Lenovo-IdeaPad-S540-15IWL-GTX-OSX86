extern "C" NV_STATUS NV_API_CALL s540Global_nv_alloc_pages(nv_state_t *state,
    NvU32 pages, NvU64 pageSize, NvBool contiguous, NvU32 cache, NvBool zeroed,
    NvBool unencrypted, NvS32 node, NvU64 *ptes, void **privateData) {
    if (!stateValid(state)) return NV_ERR_INVALID_STATE;
    auto &diagnostics = binding.allocationDiagnostics;
    increment(diagnostics.allocationAttempts);
    if (pages > diagnostics.largestRequestedPages) diagnostics.largestRequestedPages = pages;
    UnprotectedCpuObservation cpu{};
    auto fail = [&](NV_STATUS status, const char *stage) {
        logAllocationRequest(pages, pageSize, contiguous, cache, zeroed, unencrypted,
            node, cpu, stage, status);
        return allocationFailed(pages, pageSize, status);
    };
    if (!ptes || !privateData || !pages || contiguous > 1 || zeroed > 1 || unencrypted > 1)
        return fail(NV_ERR_INVALID_ARGUMENT, "arguments");
    if (pageSize != kPageBytes || pages > kMaximumPages || cache > 2 || node != -1)
        return fail(NV_ERR_NOT_SUPPORTED, "geometry");
    if (unencrypted) {
        cpu = observeUnprotectedCpu();
        if (!supportsUnprotectedOwnedPages(cpu))
            return fail(NV_ERR_NOT_SUPPORTED, "host-profile");
    }
    // A successful unprotected request still obtains the same owned wired,
    // zeroed IOBuffer pages and genuine DMA translation as an ordinary request.
    // This selected profile has no private/confidential-memory allocation path;
    // it neither clears the request flag nor enables/disables host encryption.
    Allocation *entry = nullptr;
    for (auto &candidate : binding.allocations) if (!candidate.token) { entry = &candidate; break; }
    if (!entry) return fail(NV_ERR_INSUFFICIENT_RESOURCES, "records");
    void *id = token(false);
    if (!id) return fail(NV_ERR_INSUFFICIENT_RESOURCES, "token");
    void *sessionToken = nullptr;
    NV_STATUS status = binding.session->allocate(pages, ptes, &sessionToken, contiguous != 0, cache);
    if (status != NV_OK) return fail(status, "session");
    entry->token = id; entry->sessionToken = sessionToken;
    entry->pages = pages; entry->cache = cache; entry->contiguous = contiguous != 0;
    allocationRegistered();
    *privateData = id;
    logAllocationRequest(pages, pageSize, contiguous, cache, zeroed, unencrypted,
        node, cpu, "published", NV_OK);
    return NV_OK;
}
