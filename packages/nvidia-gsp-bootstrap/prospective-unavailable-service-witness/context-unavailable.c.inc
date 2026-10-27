/* Diagnostic only, called after the actual public wrapper has returned. */
static void s540LogUnavailableServiceWitness(S540GspContext *context)
{
    S540HostUnavailableDiagnostics diagnostic;
    NV_STATUS status = s540GlobalRmReadUnavailableDiagnostics(&context->nv, &diagnostic);
    if (status != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 unavailable witness: available=0 status=%u\n", (NvU32)status);
        return;
    }
    const NvU32 firstObserved =
        (diagnostic.observedMask & S540_HOST_UNAVAILABLE_DIAG_FIRST) != 0U;
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 unavailable witness: available=1 status=0 scope=module-lifetime "
        "independentlySampled=1 observedMask=0x%x total=%u siteMask=0x%x firstState=%u "
        "firstObserved=%u firstSite=%u firstService=%u externalSiteAmbiguous=1\n",
        diagnostic.observedMask, diagnostic.unavailableCallsLifetime,
        diagnostic.sitesObservedMask, diagnostic.firstState, firstObserved,
        firstObserved ? diagnostic.firstSite : 0U,
        firstObserved ? diagnostic.firstService : 0U);
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 unavailable sites: external=%u shutdownOrdinary=%u allocationOrdinary=%u "
        "freeOrdinary=%u freePermit=%u freeCompletion=%u snapshotOrdinary=%u serviceRange=%u "
        "nullServiceName=%u serviceTableFull=%u\n",
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_EXTERNAL],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_SHUTDOWN_ORDINARY],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_ALLOCATE_ORDINARY],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_FREE_ORDINARY],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_FREE_PERMIT],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_FREE_COMPLETION],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_SNAPSHOT_ORDINARY],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_SERVICE_RANGE],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_NULL_SERVICE_NAME],
        diagnostic.siteCallsLifetime[S540_HOST_UNAVAILABLE_SERVICE_TABLE_FULL]);
}
