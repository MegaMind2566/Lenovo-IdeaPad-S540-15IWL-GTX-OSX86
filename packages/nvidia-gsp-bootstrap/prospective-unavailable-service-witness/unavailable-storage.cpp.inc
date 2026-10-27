struct HostUnavailableObservation {
    NvU32 total, sitesMask, firstState, firstSite, firstService;
    NvU32 siteCalls[S540_HOST_UNAVAILABLE_SITE_COUNT];
};
static HostUnavailableObservation hostUnavailableObservation;
static_assert(__atomic_always_lock_free(sizeof(NvU32), nullptr),
              "Unavailable observations must not add a runtime lock");
static void unavailableIncrement(NvU32 &counter) {
    NvU32 value = __atomic_load_n(&counter, __ATOMIC_RELAXED);
    while (value != ~NvU32(0) && !__atomic_compare_exchange_n(&counter,
        &value, value + 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}
static void observeHostUnavailable(NvU32 service, NvU32 site) {
    /* Only fixed internal enum sites call this helper. A future invalid site
     * is conservatively attributed to the explicitly ambiguous external site.
     */
    if (site >= S540_HOST_UNAVAILABLE_SITE_COUNT) site = S540_HOST_UNAVAILABLE_EXTERNAL;
    unavailableIncrement(hostUnavailableObservation.total);
    unavailableIncrement(hostUnavailableObservation.siteCalls[site]);
    __atomic_fetch_or(&hostUnavailableObservation.sitesMask, NvU32(1U) << site,
                      __ATOMIC_RELAXED);
    NvU32 empty = 0;
    if (__atomic_compare_exchange_n(&hostUnavailableObservation.firstState,
        &empty, 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
        hostUnavailableObservation.firstSite = site;
        hostUnavailableObservation.firstService = service;
        __atomic_store_n(&hostUnavailableObservation.firstState, 2U, __ATOMIC_RELEASE);
    }
}
static void recordUnavailableAt(NvU32 service, NvU32 site) {
    /* Preserve the original refusal publication / aggregate increment order.
     * The diagnostic observation is additive and cannot grant admission.
     */
    s540FirstTxnObserveServiceRefusal(1, service, NV_ERR_NOT_SUPPORTED);
    NvU32 current = __atomic_load_n(&counters.unavailableCalls, __ATOMIC_RELAXED);
    while (current != ~0U &&
           !__atomic_compare_exchange_n(&counters.unavailableCalls, &current,
                                         current + 1U, false,
                                         __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
    s540FirstTxnObserveServiceRefusal(1, service, NV_ERR_NOT_SUPPORTED);
    observeHostUnavailable(service, site);
}
