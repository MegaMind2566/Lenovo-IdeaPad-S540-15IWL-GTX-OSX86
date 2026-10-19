extern "C" NV_STATUS s540GlobalRmHostRetentionPreflight(void)
{
    if (!s540Darwin_os_semaphore_may_sleep()) return NV_ERR_INVALID_STATE;
    HostUse use;
    if (!use) return NV_ERR_INVALID_STATE;
    lock();
    retention.preexistingOriginalAllocations = counters.originalLiveAllocations;
    S540NvidiaGlobalCryptoSnapshot crypto = {};
    s540Global_crypto_snapshot(&crypto);
    const S540DeviceMemoryStatistics memory = s540DeviceMemoryStatistics();
    const bool cold = counters.initialized && !counters.originalLiveAllocations &&
        !retention.retiredAllocations && !retention.pendingAllocations && !retention.pendingFrees && !retention.firstStatus &&
        !__atomic_load_n(&counters.invalidFrees, __ATOMIC_ACQUIRE) && !__atomic_load_n(&counters.unavailableCalls, __ATOMIC_ACQUIRE) &&
        !crypto.unavailable_calls && !crypto.counter_overflow && !crypto.unavailable_symbol_mask && !crypto.unavailable_symbol_mask_high &&
        !memory.unavailableOperationsEver && !memory.lifetimeViolationsEver;
    unlock();
#if !defined(KERNEL)
    auto observer = __atomic_load_n(&freeObserver, __ATOMIC_ACQUIRE);
    if (observer) observer(6, nullptr, 0, nullptr, 0);
#endif
    return cold ? NV_OK : NV_ERR_STATE_IN_USE;
}
extern "C" void s540GlobalRmHostRetentionSnapshot(S540GlobalRmHostRetentionSnapshot *out)
{
    if (!out) return;
    *out = {};
    if (!s540Darwin_os_semaphore_may_sleep()) return;
    HostUse use;
    if (!use) return;
    lock(); *out = retention; out->format = 1; unlock();
}
extern "C" NV_STATUS s540GlobalRmHostRetentionInspect(const void *pointer,
    S540GlobalRmHostAllocationSnapshot *out)
{
    if (!pointer || !out || !s540Darwin_os_semaphore_may_sleep())
        return NV_ERR_INVALID_ARGUMENT;
    HostUse use;
    if (!use) return NV_ERR_INVALID_STATE;
    lock();
    NvU32 slot = 0;
    while (slot != kCapacity && records[slot].pointer != pointer) ++slot;
    if (slot == kCapacity) { unlock(); return NV_ERR_OBJECT_NOT_FOUND; }
    const Allocation &record = records[slot];
    *out = {record.identity, record.serial, record.bytes, record.original ? NV_TRUE : NV_FALSE,
            record.retired ? NV_TRUE : NV_FALSE, record.pending ? NV_TRUE : NV_FALSE};
    unlock();
    return NV_OK;
}
#if !defined(KERNEL)
void S540HostRetentionNative::observePhysicalFree(void (*observer)(NvU32, const void *, NvU64,
    const S540FirstTxnHostIdentity *, S540FirstTxnHostFreePermit))
{
    HostUse use;
    if (!use) return;
    __atomic_store_n(&freeObserver, observer, __ATOMIC_RELEASE);
}
#endif
