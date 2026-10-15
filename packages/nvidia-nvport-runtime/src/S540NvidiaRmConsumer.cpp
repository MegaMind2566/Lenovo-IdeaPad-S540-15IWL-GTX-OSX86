// SPDX-License-Identifier: MIT
#include "S540NvidiaRmConsumer.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../upstream/consumer/include/containers/vector.h"
#include "../upstream/consumer/include/containers/list.h"

namespace {
using S540NvidiaRmConsumer::Result;

void require(Result &r, bool &group, bool condition)
{
    ++r.checks;
    if (!condition) {
        ++r.failures;
        group = false;
    }
}

bool active(PORT_MEM_ALLOCATOR *allocator, NvU32 expected)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS stats{};
    return portMemExTrackingGetActiveStats(allocator, &stats) == NV_OK &&
        stats.numAllocations == expected;
}

bool vectorEquals(Vector *vector, const NvU32 *values, NvU32 count)
{
    if (vectCount_IMPL(vector) != count)
        return false;
    for (NvU32 i = 0; i < count; ++i) {
        auto *value = static_cast<NvU32 *>(vectAt_IMPL(vector, i));
        if (value == nullptr || *value != values[i])
            return false;
    }
    return true;
}

bool listEquals(NonIntrusiveList *list, const NvU32 *values, NvU32 count)
{
    if (listCount_IMPL(&list->base) != count)
        return false;
    ListIterBase iter = listIterRange_IMPL(&list->base,
        listHead_IMPL(&list->base), listTail_IMPL(&list->base));
    NvU32 index = 0;
    while (listIterNext_IMPL(&iter)) {
        if (index >= count || *static_cast<NvU32 *>(iter.pValue) != values[index])
            return false;
        ++index;
    }
    if (index != count)
        return false;
    void *value = listTail_IMPL(&list->base);
    for (NvU32 i = count; i != 0; --i) {
        if (value == nullptr || *static_cast<NvU32 *>(value) != values[i - 1])
            return false;
        value = listPrev_IMPL(&list->base, value);
    }
    return value == nullptr;
}

void vectors(Result &r, PORT_MEM_ALLOCATOR *allocator)
{
    Vector vector{};
    const NV_STATUS initialized = vectInit_IMPL(&vector, allocator, 2, sizeof(NvU32));
    require(r, r.vector, initialized == NV_OK);
    if (initialized != NV_OK) {
        vectDestroy_IMPL(&vector);
        return;
    }
    require(r, r.vector, vectIsEmpty_IMPL(&vector) == NV_TRUE &&
            vectCapacity_IMPL(&vector) == 2);
    NvU32 expected[20]{};
    for (NvU32 i = 0; i < 12; ++i) {
        expected[i] = i * 17 + 3;
        require(r, r.vector, vectAppend_IMPL(&vector, &expected[i]) != nullptr);
    }
    require(r, r.vector, vectorEquals(&vector, expected, 12));
    require(r, r.vector, vectCapacity_IMPL(&vector) == 16);
    require(r, r.vector, vectReserve_IMPL(&vector, 24) == NV_OK &&
            vectCapacity_IMPL(&vector) == 24 && vectorEquals(&vector, expected, 12));
    require(r, r.vector, vectTrim_IMPL(&vector, 1) == NV_OK &&
            vectCapacity_IMPL(&vector) == 12 && vectorEquals(&vector, expected, 12));
    const NvU32 inserted = 0x1234;
    for (NvU32 i = 12; i > 3; --i)
        expected[i] = expected[i - 1];
    expected[3] = inserted;
    require(r, r.vector, vectInsert_IMPL(&vector, 3, &inserted) != nullptr &&
            vectorEquals(&vector, expected, 13));
    vectRemove_IMPL(&vector, 3);
    for (NvU32 i = 3; i < 12; ++i)
        expected[i] = expected[i + 1];
    require(r, r.vector, vectorEquals(&vector, expected, 12));
    VectorIterBase iter = vectIterRange_IMPL(&vector,
        vectAt_IMPL(&vector, 0), vectAt_IMPL(&vector, 11));
    void *value = nullptr;
    NvU32 index = 0;
    bool ordered = true;
    while (vectIterNext_IMPL(&iter, &value)) {
        if (index >= 12 || *static_cast<NvU32 *>(value) != expected[index])
            ordered = false;
        ++index;
    }
    require(r, r.vector, ordered && index == 12);
    // The documented one-line-position adaptation frees an old empty buffer,
    // while failed allocation/copy keeps the old buffer and capacity intact.
    vectClear_IMPL(&vector);
    require(r, r.vector, vectIsEmpty_IMPL(&vector) == NV_TRUE &&
            vectCount_IMPL(&vector) == 0);
    require(r, r.vector, vectReserve_IMPL(&vector, 32) == NV_OK &&
            vector.pHead != nullptr && vector.capacity == 32 && vector.size == 0);
    require(r, r.vector, vectTrim_IMPL(&vector, 0) == NV_OK &&
            vector.pHead == nullptr && vector.capacity == 0 && vector.size == 0);
    require(r, r.vector, vectReserve_IMPL(&vector, 8) == NV_OK &&
            vector.pHead != nullptr && vector.capacity == 8 && vector.size == 0);
    require(r, r.vector, vectReserve_IMPL(&vector, 16) == NV_OK &&
            vector.pHead != nullptr && vector.capacity == 16 && vector.size == 0);
    vectDestroy_IMPL(&vector);
    require(r, r.cleanup, vector.pHead == nullptr && vector.size == 0 &&
            vector.capacity == 0);
}

void lists(Result &r, PORT_MEM_ALLOCATOR *allocator)
{
    NonIntrusiveList list{};
    listInit_IMPL(&list, allocator, sizeof(NvU32));
    require(r, r.list, listCount_IMPL(&list.base) == 0 &&
            listHead_IMPL(&list.base) == nullptr && listTail_IMPL(&list.base) == nullptr);
    NvU32 expected[6] = {7, 9, 11, 13, 15, 17};
    for (NvU32 i = 0; i < 4; ++i)
        require(r, r.list, listAppendValue_IMPL(&list, &expected[i]) != nullptr);
    const NvU32 head = 5;
    require(r, r.list, listPrependValue_IMPL(&list, &head) != nullptr);
    const NvU32 beforeTail = 12;
    require(r, r.list, listInsertValue_IMPL(&list, listTail_IMPL(&list.base),
            &beforeTail) != nullptr);
    const NvU32 ordered[6] = {5, 7, 9, 11, 12, 13};
    require(r, r.list, listEquals(&list, ordered, 6));
    NvU32 lookup = 9;
    void *found = listFindByValue_IMPL(&list, &lookup);
    require(r, r.list, found != nullptr && *static_cast<NvU32 *>(found) == 9);
    listRemove_IMPL(&list, found);
    const NvU32 removed[5] = {5, 7, 11, 12, 13};
    require(r, r.list, listEquals(&list, removed, 5));
    require(r, r.list, listFindByValue_IMPL(&list, &lookup) == nullptr);
    lookup = 7;
    require(r, r.list, listAppendValue_IMPL(&list, &lookup) != nullptr);
    listRemoveAllByValue_IMPL(&list, &lookup);
    const NvU32 withoutDuplicates[4] = {5, 11, 12, 13};
    require(r, r.list, listEquals(&list, withoutDuplicates, 4));
    lookup = 11;
    listRemoveFirstByValue_IMPL(&list, &lookup);
    const NvU32 withoutFirst[3] = {5, 12, 13};
    require(r, r.list, listEquals(&list, withoutFirst, 3));
    listRemove_IMPL(&list, listHead_IMPL(&list.base));
    listRemove_IMPL(&list, listTail_IMPL(&list.base));
    const NvU32 one[1] = {12};
    require(r, r.list, listEquals(&list, one, 1));
    listDestroy_IMPL(&list);
    require(r, r.cleanup, list.base.count == 0 && list.base.pHead == nullptr &&
            list.base.pTail == nullptr);

    // Intrusive ownership is separate: destruction must not free stack nodes.
    struct Entry { NvU32 value; ListNode link; } entries[3]{};
    IntrusiveList intrusive{};
    listInitIntrusive_IMPL(&intrusive, static_cast<NvS32>(offsetof(Entry, link)));
    listAppendExisting_IMPL(&intrusive, &entries[1]);
    listPrependExisting_IMPL(&intrusive, &entries[0]);
    listAppendExisting_IMPL(&intrusive, &entries[2]);
    require(r, r.list, listCount_IMPL(&intrusive.base) == 3 &&
            listHead_IMPL(&intrusive.base) == &entries[0] &&
            listTail_IMPL(&intrusive.base) == &entries[2]);
    listRemoveIntrusive_IMPL(&intrusive.base, &entries[1]);
    require(r, r.list, listCount_IMPL(&intrusive.base) == 2 &&
            listNext_IMPL(&intrusive.base, &entries[0]) == &entries[2]);
    listDestroyIntrusive_IMPL(&intrusive.base);
    require(r, r.cleanup, intrusive.base.count == 0 &&
            entries[0].link.pNext == nullptr && entries[2].link.pPrev == nullptr);
}

void allocationFailure(Result &r, PORT_MEM_ALLOCATOR *allocator)
{
    using namespace S540NvidiaReserve;
    Vector vector{};
    NonIntrusiveList list{};
    listInit_IMPL(&list, allocator, sizeof(NvU32));
    const NV_STATUS initialized = vectInit_IMPL(&vector, allocator, 2, sizeof(NvU32));
    require(r, r.allocationFailure, initialized == NV_OK);
    if (initialized != NV_OK) {
        vectDestroy_IMPL(&vector);
        return;
    }
    const NvU32 retained[2] = {0x31, 0x72};
    const bool created = vectAppend_IMPL(&vector, &retained[0]) != nullptr &&
        vectAppend_IMPL(&vector, &retained[1]) != nullptr &&
        listAppendValue_IMPL(&list, &retained[0]) != nullptr;
    require(r, r.allocationFailure, created);
    const NvU32 baselineSlots = liveSlots();
    void *head = vector.pHead;
    void *held[kSlotCount]{};
    NvU32 used = 0;
    for (; used < kSlotCount; ++used) {
        held[used] = PORT_ALLOC(allocator, 1);
        if (held[used] == nullptr)
            break;
    }
    require(r, r.allocationFailure, liveSlots() == kSlotCount &&
            used == kSlotCount - baselineSlots);
    if (created) {
        require(r, r.allocationFailure, vectReserve_IMPL(&vector, 4) == NV_ERR_NO_MEMORY &&
                vector.pHead == head && vector.capacity == 2 &&
                vectorEquals(&vector, retained, 2));
        require(r, r.allocationFailure, vectAppend_IMPL(&vector, &retained[0]) == nullptr &&
                vector.pHead == head && vectorEquals(&vector, retained, 2));
        require(r, r.allocationFailure, listAppendValue_IMPL(&list, &retained[1]) == nullptr &&
                listEquals(&list, retained, 1));
        vectClear_IMPL(&vector);
        require(r, r.allocationFailure, vectReserve_IMPL(&vector, 4) == NV_ERR_NO_MEMORY &&
                vector.pHead == head && vector.capacity == 2 && vector.size == 0);
        // Restoring values needs no new allocation and proves the old buffer
        // remains usable after failed empty-vector growth.
        require(r, r.allocationFailure, vectAppend_IMPL(&vector, &retained[0]) != nullptr &&
                vectAppend_IMPL(&vector, &retained[1]) != nullptr &&
                vectorEquals(&vector, retained, 2));
        Vector failed{};
        require(r, r.allocationFailure,
                vectInit_IMPL(&failed, allocator, 1, sizeof(NvU32)) == NV_ERR_NO_MEMORY &&
                failed.pHead == nullptr && failed.size == 0);
        vectDestroy_IMPL(&failed);
        require(r, r.cleanup, failed.pHead == nullptr && failed.capacity == 0);
    }
    for (void *memory : held)
        PORT_FREE(allocator, memory);
    require(r, r.cleanup, liveSlots() == baselineSlots);
    require(r, r.allocationFailure, created && vectReserve_IMPL(&vector, 8) == NV_OK &&
            vectorEquals(&vector, retained, 2));
    require(r, r.allocationFailure, listAppendValue_IMPL(&list, &retained[1]) != nullptr &&
            listEquals(&list, retained, 2));
    listDestroy_IMPL(&list);
    vectDestroy_IMPL(&vector);
}
}

S540NvidiaRmConsumer::Result S540NvidiaRmConsumer::check(PORT_MEM_ALLOCATOR *allocator)
{
    Result result{0, 0, true, true, true, true};
    const bool allowed = allocator != nullptr && s540NvportMemoryIsInitialized() &&
        S540NvidiaReserve::ready() && s540NvportLifecycleContextAllowed();
    require(result, result.cleanup, allowed);
    if (!allowed) {
        result.vector = result.list = result.allocationFailure = false;
        return result;
    }
    PORT_MEM_TRACK_ALLOCATOR_STATS before{};
    const bool baseline = portMemExTrackingGetActiveStats(allocator, &before) == NV_OK;
    const NvU32 slotsBefore = S540NvidiaReserve::liveSlots();
    require(result, result.cleanup, baseline);
    vectors(result, allocator);
    require(result, result.cleanup, baseline && active(allocator, before.numAllocations) &&
            S540NvidiaReserve::liveSlots() == slotsBefore);
    lists(result, allocator);
    require(result, result.cleanup, baseline && active(allocator, before.numAllocations) &&
            S540NvidiaReserve::liveSlots() == slotsBefore);
    allocationFailure(result, allocator);
    require(result, result.cleanup, baseline && active(allocator, before.numAllocations) &&
            S540NvidiaReserve::liveSlots() == slotsBefore);
    return result;
}
