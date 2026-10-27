/* Diagnostics run only after the original adapter wrapper has returned.
 * They cannot replace its status, refresh its cached seal, or grant cleanup. */
static void s540LogFreshServiceCounters(S540GspContext *context)
{
    S540FirstTxnServiceCounters fresh;
    NV_STATUS status = s540FirstTxnOriginalReadServiceCounters(&context->nv, &fresh);
    if (status != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 fresh service counters: available=0 status=%u\n", (NvU32)status);
        return;
    }
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 fresh service counters: available=1 status=0 hostInitialized=%u "
        "hostUnavailable=%llu invalidFrees=%llu memoryUnavailableEver=%llu violationsEver=%llu "
        "cryptoUnavailable=%llu cryptoMaskLow=0x%llx cryptoMaskHigh=0x%llx cryptoOverflow=%u\n",
        (NvU32)fresh.hostInitialized, (unsigned long long)fresh.hostUnavailable,
        (unsigned long long)fresh.hostInvalidFrees,
        (unsigned long long)fresh.memoryUnavailableEver,
        (unsigned long long)fresh.memoryViolationsEver,
        (unsigned long long)fresh.cryptoUnavailable,
        (unsigned long long)fresh.cryptoMaskLow, (unsigned long long)fresh.cryptoMaskHigh,
        (NvU32)fresh.cryptoOverflow);
}

static void s540LogAllocationCounters(S540GspContext *context)
{
    S540DeviceAllocationDiagnostics allocation;
    NV_STATUS status = s540DeviceReadAllocationDiagnostics(&context->nv, &allocation);
    if (status != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 allocation counters: available=0 status=%u\n", (NvU32)status);
        return;
    }
    if (allocation.format != 1U || allocation.bytes != sizeof(allocation) ||
        !(allocation.observedMask & S540_DEVICE_ALLOC_DIAG_COUNTS) ||
        (allocation.observedMask & ~(S540_DEVICE_ALLOC_DIAG_COUNTS |
                                    S540_DEVICE_ALLOC_DIAG_FIRST_FAILURE)) ||
        allocation.firstFailureState > 2U ||
        !!(allocation.observedMask & S540_DEVICE_ALLOC_DIAG_FIRST_FAILURE) !=
            (allocation.firstFailureState == 2U)) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 allocation counters: available=0 status=0 shapeValid=0\n");
        return;
    }
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 allocation counters: available=1 status=0 scope=module-lifetime "
        "independentlySampled=1 observedMask=0x%x attempts=%u failures=%u "
        "entryRejections=%u largestRequestedPages=%u firstFailureState=%u firstFailureObserved=%u\n",
        allocation.observedMask, allocation.allocationAttemptsLifetime,
        allocation.allocationFailuresLifetime, allocation.entryRejectionsLifetime,
        allocation.largestRequestedPagesLifetime, allocation.firstFailureState,
        !!(allocation.observedMask & S540_DEVICE_ALLOC_DIAG_FIRST_FAILURE));
    if (allocation.observedMask & S540_DEVICE_ALLOC_DIAG_FIRST_FAILURE) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 first published allocation failure: stage=%u status=%u pages=%u "
            "pageBytes=%llu contiguous=%u cache=%u zeroed=%u unprotected=%u node=%d cpuObserved=0x%x\n",
            allocation.firstFailure.stage, allocation.firstFailure.status,
            allocation.firstFailure.pages, (unsigned long long)allocation.firstFailure.pageBytes,
            allocation.firstFailure.contiguous, allocation.firstFailure.cache,
            allocation.firstFailure.zeroed, allocation.firstFailure.unprotected,
            allocation.firstFailure.node, allocation.firstFailure.cpuObservedMask);
        if (allocation.firstFailure.cpuObservedMask)
            nv_printf(NV_DBG_ERRORS,
                "NVRM: S540 first allocation CPU observations: observedMask=0x%x maxBasic=0x%x "
                "vendor=%08x:%08x:%08x signature=0x%x family=0x%x model=0x%x "
                "leaf1Ecx=0x%x leaf7Ecx=0x%x\n",
                allocation.firstFailure.cpuObservedMask, allocation.firstFailure.maxBasic,
                allocation.firstFailure.vendorEbx, allocation.firstFailure.vendorEdx,
                allocation.firstFailure.vendorEcx, allocation.firstFailure.signature,
                allocation.firstFailure.family, allocation.firstFailure.model,
                allocation.firstFailure.leaf1Ecx, allocation.firstFailure.leaf7Ecx);
    }
}

static void s540LogAttachFailureWitness(S540GspContext *context)
{
    S540AttachFailureWitness witness;
    NV_STATUS status = s540AttachWitnessRead(&context->nv, &witness);
    if (status != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 attach witness: available=0 status=%u\n", (NvU32)status);
        return;
    }
    if (witness.format != 1U || witness.bytes != sizeof(witness)) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 attach witness: available=0 status=0 shapeValid=0\n");
        return;
    }
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 attach witness: available=1 status=0 complete=%u lastAttachStage=%u "
        "lastClassId=0x%x lastInstance=%llu lastCtorStage=%u firstFailureValid=%u\n",
        witness.complete, witness.lastAttachStage, witness.lastClassId,
        (unsigned long long)witness.lastInstance, witness.lastCtorStage,
        witness.firstFailureValid);
    if (witness.firstFailureValid)
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 first attach failure: stage=%u classId=0x%x instance=%llu "
            "ctorStage=%u status=%u observedMask=0x%x missingObserved=%u missing=%u "
            "gspClientObserved=%u gspClient=%u\n",
            witness.firstAttachStage, witness.firstClassId,
            (unsigned long long)witness.firstInstance, witness.firstCtorStage,
            witness.firstStatus, witness.observedMask,
            !!(witness.observedMask & S540_ATTACH_OBS_MISSING),
            (witness.observedMask & S540_ATTACH_OBS_MISSING) ? witness.missing : 0U,
            !!(witness.observedMask & S540_ATTACH_OBS_GSP_CLIENT),
            (witness.observedMask & S540_ATTACH_OBS_GSP_CLIENT) ? witness.gspClient : 0U);
}

static void s540LogRetainedProfileFailure(S540GspContext *context, NV_STATUS profileError)
{
    S540FirstTxnSnapshot record;
    NV_STATUS snapshotStatus = s540FirstTxnGetSnapshot(&context->nv, &record);
    if (snapshotStatus != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 retained profile failure: profile=%u snapshot=unavailable snapshotStatus=%u\n",
            (NvU32)profileError, (NvU32)snapshotStatus);
    } else {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 retained profile failure: profile=%u snapshot=available firstStatus=%u firstSite=%u phase=%u "
            "counters=cached hostUnavailable=%llu invalidFrees=%llu memoryUnavailableEver=%llu violationsEver=%llu "
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
    s540LogFreshServiceCounters(context);
    s540LogAllocationCounters(context);
    s540LogAttachFailureWitness(context);
}
