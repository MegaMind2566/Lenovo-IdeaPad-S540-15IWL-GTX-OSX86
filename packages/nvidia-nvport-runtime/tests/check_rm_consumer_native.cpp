// SPDX-License-Identifier: MIT
// Original RM container code against the real tracked reserve allocator.
// Native-only deterministic allocation failures and bounded model stress.
#include "../src/S540NvidiaRmConsumer.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
#include "../upstream/consumer/include/containers/vector.h"
#include "../upstream/consumer/include/containers/list.h"
#include <cstdio>
#include <cstdlib>

namespace {
NvU32 checks = 0;
NvU32 failures = 0;
PortMemAllocatorAlloc *originalAllocate = nullptr;
NvU32 allocationAttempt = 0;
NvU32 failureAttempt = 0;

void expect(bool value)
{
    ++checks;
    if (!value)
        ++failures;
}

void *failNth(PORT_MEM_ALLOCATOR *allocator, NvLength length)
{
    ++allocationAttempt;
    if (allocationAttempt == failureAttempt)
        return nullptr;
    return originalAllocate(allocator, length);
}

bool same(Vector &vector, NvU32 *model, NvU32 count)
{
    if (vectCount_IMPL(&vector) != count)
        return false;
    for (NvU32 i = 0; i < count; ++i) {
        auto *value = static_cast<NvU32 *>(vectAt_IMPL(&vector, i));
        if (value == nullptr || *value != model[i])
            return false;
    }
    return true;
}

bool count(PORT_MEM_ALLOCATOR *allocator, NvU32 expected)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS stats{};
    return portMemExTrackingGetActiveStats(allocator, &stats) == NV_OK &&
        stats.numAllocations == expected;
}

void injectedFailures(PORT_MEM_ALLOCATOR *allocator)
{
    // Hook the existing allocator callback in native user space only. NVIDIA
    // tracking, allocation/free callers and actual reserve backing stay live.
    originalAllocate = allocator->_portAlloc;
    const NvU32 slots = S540NvidiaReserve::liveSlots();
    for (failureAttempt = 1; failureAttempt <= 12; ++failureAttempt) {
        allocationAttempt = 0;
        allocator->_portAlloc = failNth;
        Vector vector{};
        NonIntrusiveList list{};
        listInit_IMPL(&list, allocator, sizeof(NvU32));
        NvU32 model[12]{};
        NvU32 size = 0;
        const NV_STATUS status = vectInit_IMPL(&vector, allocator, 1, sizeof(NvU32));
        expect(status == NV_OK || status == NV_ERR_NO_MEMORY);
        if (status == NV_OK) {
            for (NvU32 i = 0; i < 12; ++i) {
                const NvU32 value = i * 3 + 5;
                void *old = vector.pHead;
                const NvU32 capacity = vector.capacity;
                void *inserted = vectAppend_IMPL(&vector, &value);
                if (inserted != nullptr)
                    model[size++] = value;
                else
                    expect(vector.pHead == old && vector.capacity == capacity);
                expect(same(vector, model, size));
            }
            // Exercise the fixed empty-buffer path both succeeding and
            // failing; failure never discards the old allocation.
            vectClear_IMPL(&vector);
            void *old = vector.pHead;
            const NvU32 capacity = vector.capacity;
            const NV_STATUS reserve = vectReserve_IMPL(&vector, 64);
            expect(reserve == NV_OK || (reserve == NV_ERR_NO_MEMORY &&
                   vector.pHead == old && vector.capacity == capacity));
            expect(vector.size == 0);
            expect(vectTrim_IMPL(&vector, 0) == NV_OK);
            expect(vector.pHead == nullptr && vector.capacity == 0);
        }
        for (NvU32 value = 0; value < 8; ++value) {
            const NvU32 before = list.base.count;
            void *head = list.base.pHead;
            void *tail = list.base.pTail;
            void *inserted = listAppendValue_IMPL(&list, &value);
            expect(inserted != nullptr ? list.base.count == before + 1 :
                   list.base.count == before && list.base.pHead == head &&
                   list.base.pTail == tail);
        }
        listDestroy_IMPL(&list);
        vectDestroy_IMPL(&vector);
        allocator->_portAlloc = originalAllocate;
        expect(count(allocator, 0) && S540NvidiaReserve::liveSlots() == slots);
    }
}

void boundedStress(PORT_MEM_ALLOCATOR *allocator)
{
    NvU32 random = 0x49183527;
    const NvU32 slots = S540NvidiaReserve::liveSlots();
    for (NvU32 cycle = 0; cycle < 64; ++cycle) {
        Vector vector{};
        expect(vectInit_IMPL(&vector, allocator, 1, sizeof(NvU32)) == NV_OK);
        NvU32 model[32]{};
        NvU32 size = 0;
        for (NvU32 step = 0; step < 128; ++step) {
            random = random * 1664525U + 1013904223U;
            if (size == 0 || (size < 24 && (random & 3) != 0)) {
                const NvU32 index = size == 0 ? 0 : random % (size + 1);
                // Original vector insert accepts append or an existing index.
                for (NvU32 i = size; i > index; --i)
                    model[i] = model[i - 1];
                model[index] = random;
                expect(vectInsert_IMPL(&vector, index, &random) != nullptr);
                ++size;
            } else {
                const NvU32 index = random % size;
                vectRemove_IMPL(&vector, index);
                for (NvU32 i = index; i + 1 < size; ++i)
                    model[i] = model[i + 1];
                --size;
            }
            expect(same(vector, model, size));
        }
        vectClear_IMPL(&vector);
        expect(vectReserve_IMPL(&vector, 64) == NV_OK);
        expect(vectTrim_IMPL(&vector, 0) == NV_OK);
        vectDestroy_IMPL(&vector);
        expect(count(allocator, 0) && S540NvidiaReserve::liveSlots() == slots);

        NonIntrusiveList list{};
        listInit_IMPL(&list, allocator, sizeof(NvU32));
        for (NvU32 i = 0; i < 12; ++i)
            expect(listAppendValue_IMPL(&list, &i) != nullptr);
        for (NvU32 i = 0; i < 12; ++i) {
            auto *head = static_cast<NvU32 *>(listHead_IMPL(&list.base));
            expect(head != nullptr && *head == i);
            listRemove_IMPL(&list, head);
        }
        listDestroy_IMPL(&list);
        expect(count(allocator, 0) && S540NvidiaReserve::liveSlots() == slots);
    }
}
}

int main()
{
    const NvU32 mutexes = S540NvidiaMutex::liveObjects();
    const NvU32 spinlocks = S540NvidiaSpinlock::liveObjects();
    expect(S540NvidiaReserve::initialize());
    const NV_STATUS initialized = s540NvportMemoryInitialize();
    expect(initialized == NV_OK);
    S540NvidiaRmConsumer::Result result{};
    if (initialized == NV_OK) {
        PORT_MEM_ALLOCATOR *allocator = portMemAllocatorCreateNonPaged();
        expect(allocator != nullptr);
        if (allocator != nullptr) {
            result = S540NvidiaRmConsumer::check(allocator);
            expect(result.passed());
            injectedFailures(allocator);
            boundedStress(allocator);
            expect(count(allocator, 0));
            portMemAllocatorRelease(allocator);
        }
        portMemShutdown(NV_TRUE);
    }
    expect(s540NvportMemoryIsCold() && S540NvidiaReserve::liveSlots() == 0 &&
           S540NvidiaMutex::liveObjects() == mutexes &&
           S540NvidiaSpinlock::liveObjects() == spinlocks);
    expect(S540NvidiaReserve::shutdown());
    const bool cold = !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0;
    const bool passed = result.passed() && failures == 0 && cold;
    std::printf("{\"format\":1,\"component\":\"nvport-rm-consumer\","
                "\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
                "\"consumer_checks\":%u,\"vector\":%s,\"list\":%s,"
                "\"allocation_failure\":%s,\"cleanup\":%s,"
                "\"model_cycles\":64,\"model_steps_per_cycle\":128,"
                "\"injected_failure_positions\":12,\"reserve_cold_after\":%s,"
                "\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",
                passed ? "passed" : "failed", checks + result.checks,
                failures + result.failures, result.checks,
                result.vector ? "true" : "false", result.list ? "true" : "false",
                result.allocationFailure ? "true" : "false", result.cleanup ? "true" : "false",
                cold ? "true" : "false");
    return passed ? 0 : 1;
}
