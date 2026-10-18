// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <cstdio>
#include <cstring>
#include <thread>
#include <atomic>

int main()
{
    NvU32 checks = 0;
#define EXPECT(value) do { ++checks; if (!(value)) { std::fprintf(stderr, \
    "Host domain check failed at line %d\n", __LINE__); return 1; } } while (0)
    S540NvidiaGlobalRmPlatformFacts facts{};
    facts.format = 1; facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1; facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25; facts.osVersion = facts.osDate = "native-domain-fixture";
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    auto *first = static_cast<unsigned char *>(s540GlobalRmHostAllocate(48));
    auto *second = static_cast<unsigned char *>(s540GlobalRmHostAllocate(64));
    auto *original = static_cast<unsigned char *>(s540GlobalRmHostAllocateOriginal(32));
    void *temporary = s540GlobalRmHostAllocateOriginal(96);
    EXPECT(first && second && original && temporary);
    std::memset(first, 0x39, 48); std::memset(second, 0x71, 64);
    std::memset(original, 0xA5, 32);
    S540NvidiaGlobalRmHostSnapshot snapshot{};
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.liveAllocations == 4 && snapshot.liveBytes == 240);
    EXPECT(snapshot.originalLiveAllocations == 2 && snapshot.originalLiveBytes == 128);
    EXPECT(snapshot.externalLiveAllocations == 2 && snapshot.externalLiveBytes == 112);
    s540GlobalRmHostFreeOriginal(temporary);
    s540GlobalRmHostFreeOriginal(first); // Wrong domain: retain the exact pointer.
    s540GlobalRmHostFree(original);      // Wrong domain: retain original storage.
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.invalidFrees == 2 && snapshot.unavailableCalls == 0);
    EXPECT(snapshot.originalLiveAllocations == 1 && snapshot.originalLiveBytes == 32);
    EXPECT(snapshot.externalLiveAllocations == 2 && snapshot.externalLiveBytes == 112);
    EXPECT(first[0] == 0x39 && first[47] == 0x39);
    EXPECT(original[0] == 0xA5 && original[31] == 0xA5);
    s540GlobalRmHostFreeOriginal(original);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.originalLiveAllocations == 0 && snapshot.originalLiveBytes == 0);
    EXPECT(snapshot.externalLiveAllocations == 2 && snapshot.externalLiveBytes == 112);
    EXPECT(!s540GlobalRmHostShutdown());
    EXPECT(first[0] == 0x39 && second[63] == 0x71);
    S540NvidiaGlobalRmNative::failAllocationAt(5);
    EXPECT(s540GlobalRmHostAllocateOriginal(300) == nullptr);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.originalLiveAllocations == 0 && snapshot.originalLiveBytes == 0);
    EXPECT(snapshot.externalLiveAllocations == 2 && snapshot.allocationFailures == 1);

    std::atomic<NvU32> failures{0};
    std::thread workers[6];
    for (NvU32 index = 0; index != 6; ++index) workers[index] = std::thread([&, index] {
        const bool rm = (index & 1) != 0;
        for (NvU32 iteration = 0; iteration != 128; ++iteration) {
            void *p = rm ? s540GlobalRmHostAllocateOriginal(33 + iteration)
                         : s540GlobalRmHostAllocate(33 + iteration);
            if (!p) { ++failures; continue; }
            if (rm) s540GlobalRmHostFreeOriginal(p); else s540GlobalRmHostFree(p);
        }
    });
    for (auto &worker : workers) worker.join();
    EXPECT(failures == 0);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.originalLiveAllocations == 0 && snapshot.originalLiveBytes == 0);
    EXPECT(snapshot.externalLiveAllocations == 2 && snapshot.externalLiveBytes == 112);
    EXPECT(snapshot.liveAllocations == snapshot.originalLiveAllocations + snapshot.externalLiveAllocations);
    EXPECT(snapshot.liveBytes == snapshot.originalLiveBytes + snapshot.externalLiveBytes);
    s540GlobalRmHostFree(first);
    EXPECT(!s540GlobalRmHostShutdown());
    s540GlobalRmHostFree(second);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.liveAllocations == 0 && snapshot.liveBytes == 0);
    EXPECT(snapshot.originalLiveAllocations == 0 && snapshot.externalLiveAllocations == 0);
    EXPECT(snapshot.originalLiveBytes == 0 && snapshot.externalLiveBytes == 0);
    EXPECT(snapshot.allocations == snapshot.frees && snapshot.allocations == 772);
    EXPECT(snapshot.invalidFrees == 2 && snapshot.unavailableCalls == 0);
    EXPECT(s540GlobalRmHostShutdown());
    std::printf("{\"format\":1,\"component\":\"nvidia-host-domains\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"wrong_domain_frees_retained\":2,\"concurrent_mixed_allocations\":768,"
        "\"external_storage_preserved\":true,\"cleanup\":true,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
