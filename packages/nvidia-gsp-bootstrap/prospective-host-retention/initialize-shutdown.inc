extern "C" NV_STATUS s540GlobalRmHostInitialize(const S540NvidiaGlobalRmPlatformFacts *facts)
{
    if (!s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_STATE;
    if (!facts || facts->format != 1 || facts->known != S540_GLOBAL_FACT_ALL ||
        !facts->cpuCount || !facts->cpuFrequencyHz || !facts->osMajor ||
        !facts->osVersion || !facts->osDate) return NV_ERR_NOT_SUPPORTED;
    NvU64 expected = kHostClosed;
    if (!__atomic_compare_exchange_n(&hostLifetime, &expected, kHostClosed | kHostTransition,
        false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_STATE_IN_USE;
#ifdef KERNEL
    guard = IOLockAlloc();
#else
    guard = new (std::nothrow) std::mutex;
#endif
    if (!guard) {
        __atomic_store_n(&hostLifetime, kHostClosed, __ATOMIC_RELEASE);
        return NV_ERR_NO_MEMORY;
    }
    // The two producer counters are lifetime-monotonic atomic streams. Do not
    // overwrite them while an IRQ/foreign refusal can concurrently publish.
    counters.liveBytes = counters.peakBytes = counters.largestAllocation = 0;
    counters.allocations = counters.frees = 0;
    counters.liveAllocations = counters.peakAllocations = counters.allocationFailures = 0;
    counters.originalLiveBytes = counters.externalLiveBytes = 0;
    counters.originalLiveAllocations = counters.externalLiveAllocations = 0;
    __atomic_store_n(&serviceMask, 0ULL, __ATOMIC_RELEASE);
#if !defined(KERNEL)
    allocationOrdinal = 0;
#endif
    platformFacts = *facts;
    counters.initialized = NV_TRUE;
    __atomic_store_n(&hostLifetime, 0ULL, __ATOMIC_RELEASE);
    return NV_OK;
}

extern "C" NvBool s540GlobalRmHostShutdown(void)
{
    if (!s540Darwin_os_semaphore_may_sleep()) { s540GlobalRmRecordUnavailable(0); return NV_FALSE; }
    NvU64 expected = 0;
    if (!__atomic_compare_exchange_n(&hostLifetime, &expected, kHostClosed | kHostTransition,
        false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return expected == kHostClosed ? NV_TRUE : NV_FALSE;
    // Open state guarantees a published guard. No new user can acquire one
    // until this exclusive transition either reopens or completes deletion.
    lock();
    const bool cold = counters.liveAllocations == 0 && counters.liveBytes == 0 &&
        !retention.pendingAllocations && !retention.pendingFrees &&
        !retention.retiredAllocations && !retention.firstStatus;
    if (cold) counters.initialized = NV_FALSE;
    unlock();
    if (!cold) { __atomic_store_n(&hostLifetime, 0ULL, __ATOMIC_RELEASE); return NV_FALSE; }
#ifdef KERNEL
    IOLockFree(guard);
#else
    delete guard;
#endif
    guard = nullptr;
    // Borrowed platform facts are static storage. Their consumers still need
    // the outer epoch lease across a later reinitialization; never clear the
    // old epoch while an already returned pointer can still be inspected.
    __atomic_store_n(&hostLifetime, kHostClosed, __ATOMIC_RELEASE);
    return NV_TRUE;
}

