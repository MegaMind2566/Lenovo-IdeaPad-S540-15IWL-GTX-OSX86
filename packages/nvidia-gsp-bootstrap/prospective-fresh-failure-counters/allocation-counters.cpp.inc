struct AllocationObservation {
    NvU32 attempts, failures, entryRejections, largestPages, firstFailureState;
    S540DeviceAllocationFailure firstFailure;
};
static AllocationObservation allocationObservation;
static_assert(__atomic_always_lock_free(sizeof(NvU32), nullptr),
              "Allocation observation must not add a runtime lock");
static void observeAllocationIncrement(NvU32 &counter) {
    NvU32 count = __atomic_load_n(&counter, __ATOMIC_RELAXED);
    while (count != ~NvU32(0) && !__atomic_compare_exchange_n(
            &counter, &count, count + 1U, false,
            __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}
static void recordAllocationEntryRejection() {
    observeAllocationIncrement(allocationObservation.entryRejections);
}
static void observeAllocationAttempt(NvU32 pages) {
    observeAllocationIncrement(allocationObservation.attempts);
    NvU32 largest = __atomic_load_n(&allocationObservation.largestPages, __ATOMIC_RELAXED);
    while (largest < pages && !__atomic_compare_exchange_n(
            &allocationObservation.largestPages, &largest, pages, false,
            __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}
static void observeAllocationFailure(const S540DeviceAllocationFailure &failure) {
    observeAllocationIncrement(allocationObservation.failures);
    NvU32 empty = 0;
    if (__atomic_compare_exchange_n(&allocationObservation.firstFailureState,
            &empty, 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
        allocationObservation.firstFailure = failure;
        __atomic_store_n(&allocationObservation.firstFailureState, 2U, __ATOMIC_RELEASE);
    }
}
