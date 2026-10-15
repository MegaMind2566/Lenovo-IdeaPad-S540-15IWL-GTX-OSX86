// SPDX-License-Identifier: MIT
// Native CPU execution of the production bounded reserve, not an IRQ test.
#include "../src/S540NvidiaReserve.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <pthread.h>
#include <sched.h>

namespace {

unsigned gChecks;
constexpr unsigned kWorkers = 8;
constexpr unsigned kIterations = 4096;
NvUPtr gFirstSlot;
NvU32 gOwners[S540NvidiaReserve::kSlotCount];
NvU32 gStarted;
NvU32 gStart;
NvU32 gWorkerErrors;
NvU32 gWorkerAttempts;
NvU32 gWorkerCompleted;
NvU32 gWorkerRefusals;

void require(bool condition, const char *message)
{
    ++gChecks;
    if (!condition) {
        std::fprintf(stderr, "Reserve check failed: %s\n", message);
        std::exit(1);
    }
}

void outputFailure(NvU64 size, NV_STATUS expected, const char *message)
{
    void *output = reinterpret_cast<void *>(NvUPtr{1});
    const NV_STATUS result = os_alloc_mem(&output, size);
    require(result == expected && output == nullptr, message);
}

void boundaryAndExhaustion()
{
    using namespace S540NvidiaReserve;
    require(!ready() && liveSlots() == 0, "initial reserve is unavailable");
    require(shutdown(), "shutdown of absent reserve");
    require(os_alloc_mem(nullptr, 1) == NV_ERR_INVALID_ARGUMENT,
            "null output address is invalid");
    outputFailure(0, NV_ERR_INVALID_ARGUMENT, "zero size clears output");
    outputFailure(1, NV_ERR_NO_MEMORY, "uninitialized reserve clears output");
    outputFailure(kSlotBytes + 1, NV_ERR_NO_MEMORY,
                  "oversize allocation is refused");
    outputFailure(~NvU64{0}, NV_ERR_NO_MEMORY,
                  "maximum ABI size is refused without truncation");
    os_free_mem(nullptr);

    require(initialize() && ready(), "initialize backing reserve");
    require(initialize() && liveSlots() == 0, "initialization is idempotent");

    // The smallest supported request still has the full slot's alignment.
    void *small = nullptr;
    require(os_alloc_mem(&small, 1) == NV_OK && small != nullptr,
            "one-byte allocation");
    require(reinterpret_cast<NvUPtr>(small) % kAlignment == 0,
            "one-byte pointer alignment");
    *static_cast<NvU8 *>(small) = 0xa5;
    require(*static_cast<NvU8 *>(small) == 0xa5, "one-byte content");
    os_free_mem(small);
    require(liveSlots() == 0, "one-byte allocation released");

    void *slots[kSlotCount] = {};
    for (NvU32 slot = 0; slot < kSlotCount; ++slot) {
        require(os_alloc_mem(&slots[slot], kSlotBytes) == NV_OK &&
                    slots[slot] != nullptr,
                "maximum-size allocation");
        require(reinterpret_cast<NvUPtr>(slots[slot]) % kAlignment == 0,
                "slot alignment");
        for (NvU32 earlier = 0; earlier < slot; ++earlier)
            require(slots[slot] != slots[earlier], "live pointers never alias");
        std::memset(slots[slot], static_cast<int>(slot + 1),
                    static_cast<size_t>(kSlotBytes));
    }
    gFirstSlot = reinterpret_cast<NvUPtr>(slots[0]);
    require(liveSlots() == kSlotCount, "all slots are live");
    outputFailure(1, NV_ERR_NO_MEMORY, "exhaustion clears output");
    require(!shutdown() && ready() && liveSlots() == kSlotCount,
            "shutdown refuses live slots without destroying backing");
    require(initialize() && liveSlots() == kSlotCount,
            "repeat initialize preserves live slots");

    // Reject values that are not exact slot starts without dereferencing them.
    os_free_mem(static_cast<NvU8 *>(slots[0]) + 1);
    os_free_mem(reinterpret_cast<void *>(gFirstSlot - 1));
    os_free_mem(reinterpret_cast<void *>(gFirstSlot + kReserveBytes));
    NvU8 unrelated = 0;
    os_free_mem(&unrelated);
    require(liveSlots() == kSlotCount, "non-slot pointers preserve occupancy");

    for (NvU32 slot = 0; slot < kSlotCount; ++slot) {
        const auto *bytes = static_cast<const NvU8 *>(slots[slot]);
        bool correct = true;
        for (NvU64 index = 0; index < kSlotBytes; ++index)
            correct = correct && bytes[index] == static_cast<NvU8>(slot + 1);
        require(correct, "full slot content survives exhaustion and refusal");
    }

    for (NvU32 slot = 1; slot < kSlotCount; slot += 2)
        os_free_mem(slots[slot]);
    require(liveSlots() == kSlotCount / 2, "alternate slots released");
    for (NvU32 slot = 1; slot < kSlotCount; slot += 2) {
        void *reused = nullptr;
        require(os_alloc_mem(&reused, kSlotBytes - 1) == NV_OK &&
                    reused == slots[slot],
                "released slot is reusable without losing other allocations");
        slots[slot] = reused;
    }
    require(liveSlots() == kSlotCount, "reused slots restore capacity");
    for (void *slot : slots)
        os_free_mem(slot);
    require(liveSlots() == 0, "all slots released after reuse");
}

void workerError()
{
    __atomic_fetch_add(&gWorkerErrors, NvU32{1}, __ATOMIC_RELAXED);
}

void *churn(void *argument)
{
    using namespace S540NvidiaReserve;
    const NvU32 token = *static_cast<const NvU32 *>(argument);
    __atomic_fetch_add(&gStarted, NvU32{1}, __ATOMIC_RELEASE);
    while (__atomic_load_n(&gStart, __ATOMIC_ACQUIRE) == 0)
        sched_yield();

    for (unsigned iteration = 0; iteration < kIterations; ++iteration) {
        const NvU64 size = 1 + ((iteration * 8191ULL + token * 97) % kSlotBytes);
        void *output = nullptr;
        __atomic_fetch_add(&gWorkerAttempts, NvU32{1}, __ATOMIC_RELAXED);
        const NV_STATUS result = os_alloc_mem(&output, size);
        if (result == NV_ERR_NO_MEMORY) {
            // Holes may move behind a single bounded scan under contention.
            // Refusal is allowed; no retry or scheduling guarantee is assumed.
            if (output != nullptr)
                workerError();
            __atomic_fetch_add(&gWorkerRefusals, NvU32{1}, __ATOMIC_RELAXED);
            continue;
        }
        if (result != NV_OK || output == nullptr) {
            workerError();
            return nullptr;
        }
        const NvUPtr value = reinterpret_cast<NvUPtr>(output);
        if (value < gFirstSlot || value - gFirstSlot >= kReserveBytes ||
            (value - gFirstSlot) % kSlotBytes != 0) {
            workerError();
            return nullptr;
        }
        const NvU32 slot = static_cast<NvU32>((value - gFirstSlot) / kSlotBytes);
        NvU32 expected = 0;
        // Independent ownership ledger: a duplicate allocation is detected
        // before two workers can access the same plain payload concurrently.
        if (!__atomic_compare_exchange_n(&gOwners[slot], &expected, token,
                                          false, __ATOMIC_ACQ_REL,
                                          __ATOMIC_ACQUIRE)) {
            workerError();
            return nullptr;
        }
        auto *bytes = static_cast<NvU8 *>(output);
        const NvU8 pattern = static_cast<NvU8>(token + iteration);
        bytes[0] = pattern;
        bytes[size - 1] = pattern;
        if ((iteration & 7U) == 0)
            sched_yield();
        if (bytes[0] != pattern || bytes[size - 1] != pattern)
            workerError();
        __atomic_store_n(&gOwners[slot], NvU32{0}, __ATOMIC_RELEASE);
        os_free_mem(output);
        __atomic_fetch_add(&gWorkerCompleted, NvU32{1}, __ATOMIC_RELAXED);
    }
    return nullptr;
}

void concurrency()
{
    pthread_t threads[kWorkers];
    NvU32 tokens[kWorkers];
    for (unsigned worker = 0; worker < kWorkers; ++worker) {
        tokens[worker] = worker + 1;
        require(pthread_create(&threads[worker], nullptr, churn,
                               &tokens[worker]) == 0,
                "create native worker");
    }
    while (__atomic_load_n(&gStarted, __ATOMIC_ACQUIRE) != kWorkers)
        sched_yield();
    __atomic_store_n(&gStart, NvU32{1}, __ATOMIC_RELEASE);
    for (pthread_t thread : threads)
        require(pthread_join(thread, nullptr) == 0, "join native worker");

    require(__atomic_load_n(&gWorkerErrors, __ATOMIC_RELAXED) == 0,
            "concurrent allocation/free has no alias or content failures");
    const NvU32 attempts = __atomic_load_n(&gWorkerAttempts, __ATOMIC_RELAXED);
    const NvU32 successes = __atomic_load_n(&gWorkerCompleted, __ATOMIC_RELAXED);
    const NvU32 refusals = __atomic_load_n(&gWorkerRefusals, __ATOMIC_RELAXED);
    require(attempts == kWorkers * kIterations,
            "every bounded worker iteration attempts an allocation");
    require(successes > 0, "concurrent churn includes successful allocations");
    require(successes + refusals == attempts,
            "all attempts have a completed success or legitimate refusal");
    for (NvU32 owner : gOwners)
        require(owner == 0, "ownership ledger is empty after joins");
    require(S540NvidiaReserve::liveSlots() == 0,
            "bitmap is empty after all workers join");

    // Recovering all capacity catches slots lost during contended frees.
    void *slots[S540NvidiaReserve::kSlotCount] = {};
    for (void *&slot : slots)
        require(os_alloc_mem(&slot, 1) == NV_OK, "full capacity after churn");
    outputFailure(1, NV_ERR_NO_MEMORY, "capacity remains bounded after churn");
    for (void *slot : slots)
        os_free_mem(slot);
}

} // namespace

int main()
{
    boundaryAndExhaustion();
    concurrency();
    require(S540NvidiaReserve::shutdown(), "quiescent empty reserve shuts down");
    require(!S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0,
            "shutdown clears readiness and bitmap");
    outputFailure(1, NV_ERR_NO_MEMORY, "allocation refused after shutdown");
    require(S540NvidiaReserve::initialize(), "reserve can initialize again");
    require(S540NvidiaReserve::shutdown(), "reinitialized reserve shuts down");

    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,"
                "\"slot_count\":%u,\"slot_bytes\":%llu,"
                "\"concurrent_operations\":%u,"
                "\"concurrent_attempts\":%u,\"concurrent_successes\":%u,"
                "\"concurrent_refusals\":%u,"
                "\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",
                gChecks, S540NvidiaReserve::kSlotCount,
                static_cast<unsigned long long>(S540NvidiaReserve::kSlotBytes),
                __atomic_load_n(&gWorkerAttempts, __ATOMIC_RELAXED),
                __atomic_load_n(&gWorkerAttempts, __ATOMIC_RELAXED),
                __atomic_load_n(&gWorkerCompleted, __ATOMIC_RELAXED),
                __atomic_load_n(&gWorkerRefusals, __ATOMIC_RELAXED));
    return 0;
}
