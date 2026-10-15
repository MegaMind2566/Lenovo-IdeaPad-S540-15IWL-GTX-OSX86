// SPDX-License-Identifier: MIT
#include "../S540NvidiaRmMemory.hpp"
#include <cstdio>
#include <thread>

namespace {
using namespace S540NvidiaRmMemory;
NvU32 checks = 0;
NvU32 failures = 0;
void expect(bool condition) {
    ++checks;
    if (!condition)
        ++failures;
}
bool cold() {
    const auto stats = statistics();
    return stats.allocations == 0 && stats.mappings == 0 && stats.deferred == 0 &&
           stats.bytes == 0 && nativeIllegalOperations() == 0;
}
NV_STATUS allocate(NvU32 pages, NvU64 *ptes, void **handle, NvBool zero = NV_TRUE) {
    return nv_alloc_pages(nullptr, pages, kPageBytes, NV_FALSE,
                          S540_NV_MEMORY_CACHED, zero, NV_FALSE, -1, ptes, handle);
}
void clearProfiles() {
    NvU64 ptes[kMaxPages + 2];
    void *handle = nullptr;
    const auto reset = [&]() {
        for (NvU32 i = 0; i < kMaxPages + 2; ++i)
            ptes[i] = 0xdead;
        handle = reinterpret_cast<void *>(0xdead);
    };
    reset();
    expect(nv_alloc_pages(reinterpret_cast<nv_state_t *>(1), 2, kPageBytes,
        NV_FALSE, 0, NV_TRUE, NV_FALSE, -1, ptes + 1, &handle) == NV_ERR_NOT_SUPPORTED);
    expect(!handle && ptes[0] == 0xdead && ptes[1] == 0 && ptes[2] == 0 && ptes[3] == 0xdead);
    reset();
    expect(nv_alloc_pages(nullptr, 2, kPageBytes, NV_TRUE, 0, NV_TRUE,
        NV_FALSE, -1, ptes + 1, &handle) == NV_ERR_NOT_SUPPORTED);
    expect(!handle && ptes[1] == 0 && ptes[2] == 0xdead);
    reset();
    expect(nv_alloc_pages(nullptr, 2, kPageBytes, NV_FALSE, 1, NV_TRUE,
        NV_FALSE, -1, ptes + 1, &handle) == NV_ERR_NOT_SUPPORTED);
    expect(!handle && ptes[1] == 0 && ptes[2] == 0 && ptes[3] == 0xdead);
    reset();
    expect(nv_alloc_pages(nullptr, 2, 65536, NV_FALSE, 0, NV_TRUE,
        NV_FALSE, -1, ptes + 1, &handle) == NV_ERR_NOT_SUPPORTED);
    expect(!handle && ptes[1] == 0 && ptes[2] == 0);
    reset();
    expect(nv_alloc_pages(nullptr, 2, kPageBytes, NV_FALSE, 0, NV_TRUE,
        NV_TRUE, -1, ptes + 1, &handle) == NV_ERR_NOT_SUPPORTED);
    expect(!handle && ptes[1] == 0 && ptes[2] == 0);
    reset();
    expect(nv_alloc_pages(nullptr, 2, kPageBytes, NV_FALSE, 0, NV_TRUE,
        NV_FALSE, 0, ptes + 1, &handle) == NV_ERR_NOT_SUPPORTED);
    expect(!handle && ptes[1] == 0 && ptes[2] == 0);
    reset();
    expect(allocate(kMaxPages + 1, ptes + 1, &handle) == NV_ERR_NOT_SUPPORTED);
    expect(!handle && ptes[0] == 0xdead && ptes[kMaxPages] == 0 &&
           ptes[kMaxPages + 1] == 0xdead);
    reset();
    expect(allocate(0, ptes + 1, &handle) == NV_ERR_INVALID_ARGUMENT);
    expect(!handle && ptes[1] == 0xdead);
    reset();
    expect(nv_alloc_pages(nullptr, 1, 0, NV_FALSE, 0, NV_TRUE,
        NV_FALSE, -1, ptes + 1, &handle) == NV_ERR_INVALID_ARGUMENT);
    expect(!handle && ptes[1] == 0);
    reset();
    expect(nv_alloc_pages(nullptr, 1, kPageBytes, NV_FALSE, 0, NvBool(2),
        NV_FALSE, -1, ptes + 1, &handle) == NV_ERR_INVALID_ARGUMENT);
    expect(!handle && ptes[1] == 0);
    reset();
    expect(allocate(1, nullptr, &handle) == NV_ERR_INVALID_ARGUMENT && !handle);
    expect(allocate(1, ptes + 1, nullptr) == NV_ERR_INVALID_ARGUMENT && ptes[1] == 0);
    expect(cold());
}

void invalidHandlesAndBounds() {
    NvU64 ptes[kMaxPages]{};
    void *owner = nullptr;
    expect(allocate(kMaxPages, ptes, &owner) == NV_OK);
    void *mapHandle = nullptr;
    auto *address = static_cast<NvU8 *>(nv_alloc_kernel_mapping(nullptr, owner,
        15, kPageBytes - 1, 1, &mapHandle));
    expect(address && mapHandle);
    if (address) {
        expect(*address == 0);
        *address = 0xa5;
    }
    void *invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owner, 16, 0, 1, &invalid) == nullptr && !invalid);
    invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owner, ~NvU64(0), 1, 1, &invalid) == nullptr && !invalid);
    invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owner, 0, kPageBytes, 1, &invalid) == nullptr && !invalid);
    invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owner, 0, 0, 0, &invalid) == nullptr && !invalid);
    invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owner, 0, 0, ~NvU64(0), &invalid) == nullptr && !invalid);
    expect(nv_alloc_kernel_mapping(nullptr, owner, 0, 0, 1, nullptr) == nullptr);
    invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, reinterpret_cast<void *>(0xdeadcafe),
        0, 0, 1, &invalid) == nullptr && !invalid);
    expect(nv_free_pages(nullptr, kMaxPages, NV_FALSE, 0,
        reinterpret_cast<void *>(0xdeadcafe)) == NV_ERR_INVALID_ARGUMENT);
    expect(nv_free_pages(nullptr, kMaxPages - 1, NV_FALSE, 0, owner) == NV_ERR_INVALID_ARGUMENT);
    expect(nv_free_pages(nullptr, kMaxPages, NV_TRUE, 0, owner) == NV_ERR_NOT_SUPPORTED);
    expect(nv_free_pages(nullptr, kMaxPages, NV_FALSE, 1, owner) == NV_ERR_NOT_SUPPORTED);
    const NvU32 rejected = statistics().rejected;
    nv_free_kernel_mapping(nullptr, owner, reinterpret_cast<void *>(0xdeadcafe), mapHandle);
    nv_free_kernel_mapping(nullptr, reinterpret_cast<void *>(0xdeadcafe), address, mapHandle);
    nv_free_kernel_mapping(nullptr, owner, address, reinterpret_cast<void *>(0xdeadcafe));
    expect(statistics().rejected == rejected + 3 && statistics().mappings == 1);
    expect(nv_free_pages(nullptr, kMaxPages, NV_FALSE, 0, owner) == NV_OK);
    expect(statistics().deferred == 1 && statistics().allocations == 1 &&
           statistics().bytes == kMaxPages * kPageBytes && !shutdown());
    expect(nv_free_pages(nullptr, kMaxPages, NV_FALSE, 0, owner) == NV_ERR_INVALID_STATE);
    invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owner, 0, 0, 1, &invalid) == nullptr && !invalid);
    if (address) {
        expect(*address == 0xa5);
        nv_free_kernel_mapping(nullptr, owner, address, mapHandle);
    }
    expect(cold());
    nv_free_kernel_mapping(nullptr, owner, address, mapHandle);
    expect(statistics().rejected == rejected + 4 && cold());
    expect(nv_free_pages(nullptr, kMaxPages, NV_FALSE, 0, owner) == NV_ERR_INVALID_ARGUMENT);
    void *newOwner = nullptr;
    expect(allocate(1, ptes, &newOwner, NV_FALSE) == NV_OK && newOwner != owner);
    expect(nv_free_pages(nullptr, 1, NV_FALSE, 0, owner) == NV_ERR_INVALID_ARGUMENT);
    expect(statistics().allocations == 1);
    expect(nv_free_pages(nullptr, 1, NV_FALSE, 0, newOwner) == NV_OK && cold());
}

void capacities() {
    void *owners[kMaxAllocations]{};
    NvU64 ptes[kMaxPages]{};
    for (NvU32 i = 0; i < kMaxAllocations; ++i)
        expect(allocate(1, ptes, &owners[i]) == NV_OK && owners[i]);
    void *extra = reinterpret_cast<void *>(1);
    expect(allocate(1, ptes, &extra) == NV_ERR_NO_MEMORY && !extra && ptes[0] == 0);
    expect(statistics().allocations == kMaxAllocations && !shutdown());
    void *handles[kMaxMappings]{};
    void *addresses[kMaxMappings]{};
    for (NvU32 i = 0; i < kMaxMappings; ++i) {
        addresses[i] = nv_alloc_kernel_mapping(nullptr, owners[0], 0, 0, kPageBytes, &handles[i]);
        expect(addresses[i] && handles[i]);
    }
    extra = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owners[0], 0, 0, 1, &extra) == nullptr && !extra);
    expect(statistics().mappings == kMaxMappings);
    expect(nv_free_pages(nullptr, 1, NV_FALSE, 0, owners[0]) == NV_OK);
    for (NvU32 i = 0; i < kMaxMappings; ++i)
        nv_free_kernel_mapping(nullptr, owners[0], addresses[i], handles[i]);
    expect(statistics().allocations == kMaxAllocations - 1 && statistics().mappings == 0);
    for (NvU32 i = 1; i < kMaxAllocations; ++i)
        expect(nv_free_pages(nullptr, 1, NV_FALSE, 0, owners[i]) == NV_OK);
    expect(cold());
}
}

int main()
{
    using namespace S540NvidiaRmMemory;
    setNativeFault(Fault::None);
    const Result startup = S540NvidiaRmMemory::check();
    expect(startup.passed());
    expect(!ready() && nativeLiveResources() == 0 && nativeIllegalOperations() == 0);
    expect(initialize());
    clearProfiles();
    invalidHandlesAndBounds();
    capacities();
    expect(shutdown() && nativeLiveResources() == 0);

    NvU32 faultCases = 0;
    for (NvU32 i = NvU32(Fault::Context); i <= NvU32(Fault::BufferComplete); ++i) {
        setNativeFault(static_cast<Fault>(i));
        const Result failed = S540NvidiaRmMemory::check();
        ++faultCases;
        expect(!failed.passed() && failed.failures != 0);
        expect(!ready() && nativeLiveResources() == 0 && nativeIllegalOperations() == 0);
        setNativeFault(Fault::None);
        const Result recovered = S540NvidiaRmMemory::check();
        expect(recovered.passed());
        expect(!ready() && nativeLiveResources() == 0 && nativeIllegalOperations() == 0);
    }

    expect(initialize());
    NvU64 ptes[1]{};
    void *owner = nullptr;
    expect(allocate(1, ptes, &owner) == NV_OK);
    const NvU64 physical = ptes[0];
    void *inout = owner;
    expect(nv_dma_map_alloc(nullptr, 1, ptes, NV_FALSE, NV_FALSE, &inout) == NV_ERR_NOT_SUPPORTED);
    expect(inout == owner && ptes[0] == physical && statistics().allocations == 1);
    expect(nv_dma_unmap_alloc(nullptr, 1, ptes, &inout) == NV_ERR_NOT_SUPPORTED);
    expect(inout == owner && ptes[0] == physical && statistics().allocations == 1);
    setNativeFault(Fault::Context);
    void *invalid = reinterpret_cast<void *>(1);
    NvU64 contextPte = 1;
    expect(allocate(1, &contextPte, &invalid) == NV_ERR_INVALID_REQUEST && !invalid && contextPte == 0);
    expect(nv_free_pages(nullptr, 1, NV_FALSE, 0, owner) == NV_ERR_INVALID_REQUEST);
    invalid = reinterpret_cast<void *>(1);
    expect(nv_alloc_kernel_mapping(nullptr, owner, 0, 0, 1, &invalid) == nullptr && !invalid);
    expect(!shutdown());
    setNativeFault(Fault::None);
    expect(statistics().allocations == 1);
    expect(nv_free_pages(nullptr, 1, NV_FALSE, 0, owner) == NV_OK);

    NvU32 workerFailures = 0;
    constexpr NvU32 threadCount = 4;
    constexpr NvU32 cyclesPerThread = 64;
    std::thread workers[threadCount];
    for (NvU32 thread = 0; thread < threadCount; ++thread) {
        workers[thread] = std::thread([&, thread]() {
            for (NvU32 cycle = 0; cycle < cyclesPerThread; ++cycle) {
                NvU64 page[1]{};
                void *handle = nullptr;
                if (allocate(1, page, &handle) != NV_OK) {
                    __atomic_add_fetch(&workerFailures, 1U, __ATOMIC_RELAXED);
                    continue;
                }
                void *mapHandle = nullptr;
                auto *mapped = static_cast<NvU8 *>(nv_alloc_kernel_mapping(nullptr,
                    handle, 0, 0, kPageBytes, &mapHandle));
                if (!mapped || !mapHandle)
                    __atomic_add_fetch(&workerFailures, 1U, __ATOMIC_RELAXED);
                else {
                    mapped[kPageBytes - 1] = static_cast<NvU8>(thread + cycle);
                    if (mapped[kPageBytes - 1] != static_cast<NvU8>(thread + cycle))
                        __atomic_add_fetch(&workerFailures, 1U, __ATOMIC_RELAXED);
                    nv_free_kernel_mapping(nullptr, handle, mapped, mapHandle);
                }
                if (nv_free_pages(nullptr, 1, NV_FALSE, 0, handle) != NV_OK)
                    __atomic_add_fetch(&workerFailures, 1U, __ATOMIC_RELAXED);
            }
        });
    }
    for (auto &worker : workers)
        worker.join();
    expect(workerFailures == 0 && cold());
    expect(shutdown() && !ready() && nativeLiveResources() == 0 && nativeIllegalOperations() == 0);
    std::printf("{\"format\":1,\"component\":\"nvidia-rm-memory-services\","
                "\"status\":\"%s\",\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false,"
                "\"checks\":%u,\"failures\":%u,\"startup_checks\":%u,"
                "\"startup_failures\":%u,\"fault_cases\":%u,\"threads\":%u,"
                "\"lifecycle_cycles\":%u,\"worker_failures\":%u}\n",
                failures ? "failed" : "passed", checks, failures,
                startup.checks, startup.failures, faultCases, threadCount,
                threadCount * cyclesPerThread, workerFailures);
    return failures ? 1 : 0;
}
