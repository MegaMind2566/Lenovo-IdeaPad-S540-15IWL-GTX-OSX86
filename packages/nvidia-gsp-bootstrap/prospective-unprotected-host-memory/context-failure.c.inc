/* Diagnostic only: the public original wrapper has already returned. */
static void s540LogRetainedProfileFailure(S540GspContext *context, NV_STATUS profileError)
{
    S540FirstTxnSnapshot record;
    NV_STATUS snapshotStatus = s540FirstTxnGetSnapshot(&context->nv, &record);
    if (snapshotStatus != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 retained profile failure: profile=%u snapshot=unavailable snapshotStatus=%u\n",
            (NvU32)profileError, (NvU32)snapshotStatus);
        return;
    }
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 retained profile failure: profile=%u snapshot=available firstStatus=%u firstSite=%u phase=%u "
        "hostUnavailable=%llu invalidFrees=%llu memoryUnavailableEver=%llu violationsEver=%llu "
        "cryptoUnavailable=%llu cryptoMaskLow=0x%llx cryptoMaskHigh=0x%llx cryptoOverflow=%u\n",
        (NvU32)profileError, (NvU32)record.firstStatus, (NvU32)record.firstSite,
        (NvU32)record.phase, (unsigned long long)record.counters.hostUnavailable,
        (unsigned long long)record.counters.hostInvalidFrees,
        (unsigned long long)record.counters.memoryUnavailableEver,
        (unsigned long long)record.counters.memoryViolationsEver,
        (unsigned long long)record.counters.cryptoUnavailable,
        (unsigned long long)record.counters.cryptoMaskLow,
        (unsigned long long)record.counters.cryptoMaskHigh,
        (NvU32)record.counters.cryptoOverflow);
}
