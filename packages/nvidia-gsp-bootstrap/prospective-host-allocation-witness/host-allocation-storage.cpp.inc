struct HostAllocationObservation {
    NvU32 producerTotal, producerMask, producerFirstState;
    NvU32 producerFirstId, producerFirstService;
    NvU32 producerCalls[S540_HOST_ALLOCATION_PRODUCER_COUNT];
    NvU32 allocationFailures, allocationStagesMask, allocationFirstState;
    NvU32 allocationFirstStage, allocationFirstStatus, allocationFirstOriginal;
    NvU64 allocationFirstBytes;
};
HostAllocationObservation hostAllocationObservation = {};
static void hostAllocationIncrement(NvU32 &target) {
    NvU32 value = __atomic_load_n(&target, __ATOMIC_RELAXED);
    while (value != ~0U && !__atomic_compare_exchange_n(&target, &value,
        value + 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}
static void observeHostProducer(NvU32 service, NvU32 producer) {
    if (producer >= S540_HOST_ALLOCATION_PRODUCER_COUNT)
        producer = S540_HOST_ALLOCATION_PRODUCER_UNKNOWN;
    hostAllocationIncrement(hostAllocationObservation.producerTotal);
    hostAllocationIncrement(hostAllocationObservation.producerCalls[producer]);
    __atomic_fetch_or(&hostAllocationObservation.producerMask,
        NvU32(1U) << producer, __ATOMIC_RELAXED);
    NvU32 empty = 0U;
    if (__atomic_compare_exchange_n(&hostAllocationObservation.producerFirstState,
        &empty, 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
        hostAllocationObservation.producerFirstId = producer;
        hostAllocationObservation.producerFirstService = service;
        __atomic_store_n(&hostAllocationObservation.producerFirstState, 2U, __ATOMIC_RELEASE);
    }
}
static void observeHostAllocation(NV_STATUS status, NvU32 stage, NvU64 bytes,
    bool original) {
    hostAllocationIncrement(hostAllocationObservation.allocationFailures);
    if (stage >= 1U && stage <= 10U)
        __atomic_fetch_or(&hostAllocationObservation.allocationStagesMask,
            NvU32(1U) << (stage - 1U), __ATOMIC_RELAXED);
    NvU32 empty = 0U;
    if (__atomic_compare_exchange_n(&hostAllocationObservation.allocationFirstState,
        &empty, 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
        hostAllocationObservation.allocationFirstStage = stage;
        hostAllocationObservation.allocationFirstStatus = status;
        hostAllocationObservation.allocationFirstOriginal = original ? 1U : 0U;
        hostAllocationObservation.allocationFirstBytes = bytes;
        __atomic_store_n(&hostAllocationObservation.allocationFirstState, 2U, __ATOMIC_RELEASE);
    }
}
