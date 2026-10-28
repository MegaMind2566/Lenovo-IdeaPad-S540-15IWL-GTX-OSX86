/* Scalar diagnostics only, after the actual public wrapper returned. */
static void s540LogHostAllocationWitness(S540GspContext *context)
{
    S540HostAllocationDiagnostics diagnostic;
    NV_STATUS status = s540GlobalRmReadAllocationDiagnostics(&context->nv, &diagnostic);
    if (status != NV_OK) {
        nv_printf(NV_DBG_ERRORS,
            "NVRM: S540 host allocation witness: available=0 status=%u\n", (NvU32)status);
        return;
    }
    const NvU32 producerFirst =
        (diagnostic.observedMask & S540_HOST_ALLOCATION_DIAG_PRODUCER_FIRST) != 0U;
    const NvU32 allocationFirst =
        (diagnostic.observedMask & S540_HOST_ALLOCATION_DIAG_ALLOCATION_FIRST) != 0U;
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 refusal producers: available=1 status=0 scope=producer-subset-module-lifetime "
        "independentlySampled=1 firstPublisherOnly=1 observedMask=0x%x total=%u producerMask=0x%x "
        "firstState=%u firstObserved=%u firstProducer=%u firstService=%u "
        "unknown=%u osAllocContext=%u acpiD3cold=%u acpiDdc=%u acpiDod=%u acpiDsm=%u "
        "acpiPowerSource=%u acpiMux=%u acpiInitNull=%u\n",
        diagnostic.observedMask, diagnostic.producerCallsLifetime, diagnostic.producerMask,
        diagnostic.producerFirstState, producerFirst,
        producerFirst ? diagnostic.producerFirstId : 0U,
        producerFirst ? diagnostic.producerFirstService : 0U,
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_UNKNOWN],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_OS_ALLOC_CONTEXT],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_ACPI_D3COLD],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_ACPI_DDC],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_ACPI_DOD],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_ACPI_DSM],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_ACPI_POWERSOURCE],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_ACPI_MUX],
        diagnostic.producerCalls[S540_HOST_ALLOCATION_PRODUCER_ACPI_INIT_NULL]);
    nv_printf(NV_DBG_ERRORS,
        "NVRM: S540 host allocation witness: available=1 status=0 scope=module-lifetime "
        "independentlySampled=1 firstPublisherOnly=1 failures=%u stageMask=0x%x firstState=%u "
        "firstObserved=%u firstStage=%u firstStatus=%u firstBytes=%llu firstOriginal=%u\n",
        diagnostic.allocationFailuresLifetime, diagnostic.allocationStagesMask,
        diagnostic.allocationFirstState, allocationFirst,
        allocationFirst ? diagnostic.allocationFirstStage : 0U,
        allocationFirst ? diagnostic.allocationFirstStatus : 0U,
        (unsigned long long)(allocationFirst ? diagnostic.allocationFirstBytes : 0ULL),
        allocationFirst ? diagnostic.allocationFirstOriginal : 0U);
}
