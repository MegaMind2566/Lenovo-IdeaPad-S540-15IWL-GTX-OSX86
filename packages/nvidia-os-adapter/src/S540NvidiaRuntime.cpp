// SPDX-License-Identifier: MIT
#include "S540NvidiaRuntime.hpp"
#include "S540NvidiaClock.hpp"
#include "S540NvidiaMemory.hpp"
#include "S540NvidiaAtomic.h"
#include "S540NvidiaAllocator.hpp"
#include "S540NvidiaSync.hpp"

namespace {
bool record(S540NvidiaRuntime::Result &result, bool value) {
    ++result.checks;
    return value;
}
}

S540NvidiaRuntime::Result S540NvidiaRuntime::check() {
    Result result = {0, false, false, false, false, false};
    const bool ready = S540NvidiaClock::backendReady();
    result.timer = record(result, ready);
    if (ready) {
        const NvU64 before = portTimeGetUptimeNanosecondsHighPrecision();
        const NvU64 ordinary = portTimeGetUptimeNanoseconds();
        const NvU64 after = portTimeGetUptimeNanosecondsHighPrecision();
        const NvU64 quantum = portTimeGetUptimeResolution();
        result.timer &= record(result, quantum == 1000000ULL);
        result.timer &= record(result, before <= after);
        result.timer &= record(result, ordinary <= after);
        result.timer &= record(result, ordinary % 1000000ULL == 0);
        result.timer &= record(result, ordinary >= before - before % 1000000ULL);
    }

    NvU8 source[64], destination[64];
    for (unsigned index = 0; index < 64; ++index)
        source[index] = static_cast<NvU8>(index * 13U + 1U);
    result.memory = record(result, portMemSet(destination, 0, sizeof(destination)) == destination);
    result.memory &= record(result, portMemCopy(destination, sizeof(destination),
                                                source, sizeof(source)) == destination);
    result.memory &= record(result, portMemCmp(destination, source, sizeof(source)) == 0);
    destination[31] ^= 1U;
    result.memory &= record(result, portMemCmp(destination, source, sizeof(source)) != 0);

    PORT_ATOMIC NvU32 value32 = 0;
    PORT_ATOMIC NvU64 value64 = 0;
    portAtomicSetU32(&value32, 7U);
    result.atomics = record(result, portAtomicAddU32(&value32, 3U) == 10U);
    result.atomics &= record(result, portAtomicCompareAndSwapU32(&value32, 11U, 10U) != 0);
    result.atomics &= record(result, portAtomicAddU32(&value32, 0U) == 11U);
    portAtomicExSetU64(&value64, 0x100000000ULL);
    result.atomics &= record(result, portAtomicExAddU64(&value64, 3ULL) == 0x100000003ULL);
    result.atomics &= record(result, portAtomicExAddU64(&value64, 0ULL) == 0x100000003ULL);
    portAtomicMemoryFenceFull();

    void *buffer = nullptr;
    const NV_STATUS allocated = os_alloc_mem(&buffer, 256ULL);
    result.allocation = record(result, allocated == NV_OK && buffer != nullptr);
    if (allocated == NV_OK && buffer) {
        result.allocation &= record(result, (reinterpret_cast<NvUPtr>(buffer) & 15U) == 0);
        result.allocation &= record(result, portMemSet(buffer, 0xa5, 256ULL) == buffer);
        const NvU8 *bytes = static_cast<const NvU8 *>(buffer);
        bool contents = true;
        for (unsigned index = 0; index < 256; ++index)
            contents &= bytes[index] == 0xa5U;
        result.allocation &= record(result, contents);
        os_free_mem(buffer);
    }

    void *mutex = nullptr;
    const NV_STATUS created = os_alloc_mutex(&mutex);
    result.mutex = record(result, created == NV_OK && mutex != nullptr);
    if (created == NV_OK && mutex) {
        const NV_STATUS acquired = os_cond_acquire_mutex(mutex);
        result.mutex &= record(result, acquired == NV_OK);
        if (acquired == NV_OK) {
            result.mutex &= record(result, os_cond_acquire_mutex(mutex) == NV_ERR_TIMEOUT_RETRY);
            os_release_mutex(mutex);
            const NV_STATUS reacquired = os_acquire_mutex(mutex);
            result.mutex &= record(result, reacquired == NV_OK);
            if (reacquired == NV_OK)
                os_release_mutex(mutex);
        }
        os_free_mutex(mutex);
    }
    return result;
}
