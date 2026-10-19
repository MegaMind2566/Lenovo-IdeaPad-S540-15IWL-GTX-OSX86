static void noteInvalidFree(void)
{
    s540FirstTxnObserveServiceRefusal(1, 1, NV_ERR_INVALID_ARGUMENT);
    NvU32 value = __atomic_load_n(&counters.invalidFrees, __ATOMIC_RELAXED);
    while (value != ~0U && !__atomic_compare_exchange_n(&counters.invalidFrees,
        &value, value + 1U, false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
    s540FirstTxnObserveServiceRefusal(1, 1, NV_ERR_INVALID_ARGUMENT);
}

static void *allocationFailure(NV_STATUS status, NvU32 site)
{
    // Source failure publication precedes NULL and any caller's inner cleanup.
    // The strong record observes RESERVING/bound attempts; UNBOUND is a no-op.
    // This is allocation evidence, never an unavailable-operation counter.
    s540FirstTxnObserveServiceRefusal(4, site, status);
    return nullptr;
}

static void *allocateTracked(NvU64 bytes, bool original)
{
    if (!s540Darwin_os_semaphore_may_sleep()) {
        allocationFailure(NV_ERR_INVALID_STATE, 1);
        s540GlobalRmRecordUnavailable(0);
        return nullptr;
    }
    if (!bytes) return allocationFailure(NV_ERR_INVALID_STATE, 2);
    if (bytes > kSingleLimit || bytes > static_cast<NvU64>(~static_cast<size_t>(0)))
        return allocationFailure(NV_ERR_NO_MEMORY, 3);
    HostUse use;
    if (!use) return allocationFailure(NV_ERR_INVALID_STATE, 4);
    S540FirstTxnHostIdentity identity = {};
    const NV_STATUS captured = s540FirstTxnHostCaptureAllocation(&identity);
    const bool unassociated = captured == NV_ERR_OBJECT_NOT_FOUND && !identity.owner && !identity.generation;
    if (captured != NV_OK && !unassociated) return allocationFailure(captured, 5);
    if (captured == NV_OK && (!identity.owner || !identity.generation)) return allocationFailure(NV_ERR_INVALID_STATE, 6);
#if !defined(KERNEL)
    auto allocationObserver = __atomic_load_n(&freeObserver, __ATOMIC_ACQUIRE);
    if (allocationObserver) allocationObserver(0, nullptr, bytes, &identity, 0);
#endif
    lock();
#if !defined(KERNEL)
    if (++allocationOrdinal == failureOrdinal) {
        failureOrdinal = 0;
        ++counters.allocationFailures;
        unlock();
        return allocationFailure(NV_ERR_NO_MEMORY, 7);
    }
#endif
    NvU32 slot = 0;
    while (slot != kCapacity && records[slot].pointer) ++slot;
    if (!counters.initialized || slot == kCapacity || nextAllocationSerial == ~(NvU64)0 ||
        bytes > kTotalLimit - counters.liveBytes) {
        ++counters.allocationFailures;
        const NV_STATUS failure = counters.initialized ? NV_ERR_NO_MEMORY : NV_ERR_INVALID_STATE;
        unlock();
        return allocationFailure(failure, 8);
    }
    records[slot] = {reinterpret_cast<void *>(static_cast<NvUPtr>(1)), bytes, original,
                     identity, ++nextAllocationSerial, false, false, false};
    counters.liveBytes += bytes;
    ++counters.liveAllocations;
    ++retention.pendingAllocations;
    if (original) { counters.originalLiveBytes += bytes; ++counters.originalLiveAllocations; }
    unlock();
#if !defined(KERNEL)
    if (allocationObserver) allocationObserver(4, nullptr, bytes, &identity, 0);
#endif
    // Recheck outside the allocator guard after publishing the reservation,
    // before allocating backing. An intervening BeginOwner cannot adopt a
    // legacy reservation; BeginOwner's preflight sees its original-live count.
    S540FirstTxnHostIdentity confirmed = {};
    const NV_STATUS checked = s540FirstTxnHostCaptureAllocation(&confirmed);
    const bool same = confirmed.owner == identity.owner && confirmed.generation == identity.generation &&
        ((captured == NV_OK && checked == NV_OK) ||
         (unassociated && checked == NV_ERR_OBJECT_NOT_FOUND));
    if (!same) {
        lock();
        records[slot] = {};
        --retention.pendingAllocations;
        counters.liveBytes -= bytes;
        --counters.liveAllocations;
        if (original) { counters.originalLiveBytes -= bytes; --counters.originalLiveAllocations; }
        ++counters.allocationFailures;
        unlock();
        return allocationFailure(checked != NV_OK && checked != NV_ERR_OBJECT_NOT_FOUND ? checked : NV_ERR_INVALID_STATE, 9);
    }
    void *pointer = allocate(bytes);
    if (!pointer) allocationFailure(NV_ERR_NO_MEMORY, 10);
    lock();
    --retention.pendingAllocations;
    if (!pointer) {
        records[slot] = {};
        counters.liveBytes -= bytes;
        --counters.liveAllocations;
        if (original) { counters.originalLiveBytes -= bytes; --counters.originalLiveAllocations; }
        ++counters.allocationFailures;
    } else {
        records[slot].pointer = pointer;
        ++counters.allocations;
        if (identity.owner) {
            if (retention.taggedAllocations != ~(NvU64)0) ++retention.taggedAllocations;
        } else if (retention.unassociatedAllocations != ~(NvU64)0) ++retention.unassociatedAllocations;
        if (counters.liveBytes > counters.peakBytes) counters.peakBytes = counters.liveBytes;
        if (counters.liveAllocations > counters.peakAllocations) counters.peakAllocations = counters.liveAllocations;
        if (bytes > counters.largestAllocation) counters.largestAllocation = bytes;
    }
    unlock();
    return pointer;
}

static void freeTracked(void *pointer, bool original)
{
    if (!pointer) return;
    if (!s540Darwin_os_semaphore_may_sleep()) {
        s540GlobalRmRecordUnavailable(0);
        return;
    }
    HostUse use;
    if (!use) { noteInvalidFree(); return; }
    lock();
    NvU32 slot = 0;
    while (slot != kCapacity && records[slot].pointer != pointer) ++slot;
    if (slot == kCapacity || pointer == reinterpret_cast<void *>(static_cast<NvUPtr>(1)) ||
        records[slot].original != original || records[slot].pending || records[slot].retired) {
        unlock();
        noteInvalidFree();
        return;
    }
    const Allocation saved = records[slot];
    records[slot].pending = true;
    ++retention.pendingFrees;
    unlock();
    // No FirstTransaction API runs while the allocator guard is held. A real
    // permit and first refusal share one atomic record word: physical frees
    // already admitted before refusal complete; later requests retain bytes.
    S540FirstTxnHostFreePermit permit = 0;
    const NV_STATUS status = s540FirstTxnHostAcquireFree(&saved.identity, &permit);
    const bool unassociated = !saved.identity.owner && !saved.identity.generation &&
        status == NV_ERR_OBJECT_NOT_FOUND && !permit;
    const bool admitted = (status == NV_OK && saved.identity.owner && saved.identity.generation && permit) || unassociated;
    lock();
    // The pending marker excludes duplicate frees and the immutable serial
    // excludes ABA reuse. This slot remains reserved through physical release.
    if (records[slot].pointer != pointer || records[slot].serial != saved.serial || !records[slot].pending) {
        unlock();
        noteInvalidFree();
        // The physical release did not happen. Keep any admitted permit
        // outstanding; never present an unperformed IOFree as completion.
        return;
    }
    if (!admitted) {
        records[slot].pending = false;
        records[slot].retired = true;
        --retention.pendingFrees;
        ++retention.retiredAllocations;
        retention.retiredBytes += saved.bytes;
        if (retention.acquireFailures != ~0U) ++retention.acquireFailures;
        if (!retention.firstStatus) retention.firstStatus = status == NV_OK ? NV_ERR_INVALID_STATE : status;
        unlock();
        s540GlobalRmRecordUnavailable(0);
        return;
    }
    records[slot].pointer = reinterpret_cast<void *>(static_cast<NvUPtr>(1));
    unlock();
    release(pointer, saved.bytes);
    lock();
    // Keep this metadata slot reserved until real permit completion. The
    // physical backing has gone: live-byte counters must no longer claim it.
    records[slot].bytes = 0;
    records[slot].released = true;
    ++retention.releasedPendingCompletions;
    counters.liveBytes -= saved.bytes;
    --counters.liveAllocations;
    if (original) { counters.originalLiveBytes -= saved.bytes; --counters.originalLiveAllocations; }
    ++counters.frees;
    unlock();
    // Completion is outside the allocator guard and after IOFree. The record
    // cannot issue retirement while an earlier committed free is outstanding.
#if !defined(KERNEL)
    auto observer = __atomic_load_n(&freeObserver, __ATOMIC_ACQUIRE);
    if (observer) observer(3, pointer, saved.bytes, &saved.identity, permit);
#endif
    const NV_STATUS completed = permit ? s540FirstTxnHostCompleteFree(&saved.identity, permit) : NV_OK;
    lock();
    if (completed == NV_OK) {
        records[slot] = {};
        --retention.pendingFrees;
        --retention.releasedPendingCompletions;
    } else {
        // No retry of IOFree: the reserved zero-byte node records only the
        // outstanding completion. This is not retained physical memory.
        if (retention.completionFailures != ~0U) ++retention.completionFailures;
        if (!retention.firstStatus) retention.firstStatus = completed;
    }
    unlock();
    if (completed != NV_OK) s540GlobalRmRecordUnavailable(0);
}

