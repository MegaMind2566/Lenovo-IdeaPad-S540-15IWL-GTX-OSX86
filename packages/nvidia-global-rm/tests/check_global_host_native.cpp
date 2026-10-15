// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <atomic>
#include <cstdio>
#include <thread>

int main()
{
    NvU32 checks = 0;
#define EXPECT(value) do { ++checks; if (!(value)) { std::fprintf(stderr, \
    "Global host check failed at line %d\n", __LINE__); return 1; } } while (0)
    S540NvidiaGlobalRmPlatformFacts facts = {};
    facts.format = 1;
    facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1;
    facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25;
    facts.osVersion = "native-unit-fixture";
    facts.osDate = "native-unit-fixture";
    auto incomplete = facts;
    incomplete.known &= ~S540_GLOBAL_FACT_EFI;
    EXPECT(s540GlobalRmHostInitialize(&incomplete) == NV_ERR_NOT_SUPPORTED);
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_ERR_STATE_IN_USE);
    EXPECT(s540GlobalRmHostAllocate(0) == nullptr);
    EXPECT(s540GlobalRmHostAllocate(257ULL * 1024 * 1024) == nullptr);
    void *large = s540GlobalRmHostAllocate(24604904);
    EXPECT(large != nullptr);
    EXPECT(!s540GlobalRmHostShutdown());
    s540GlobalRmHostFree(large);
    std::atomic<NvU32> errors{0};
    std::atomic<bool> stop{false};
    std::thread observer([&] {
        while (!stop.load()) {
            S540NvidiaGlobalRmHostSnapshot snapshot = {};
            s540GlobalRmHostSnapshot(&snapshot);
            if (snapshot.invalidFrees || snapshot.unavailableCalls ||
                snapshot.liveAllocations > 8192) ++errors;
        }
    });
    std::thread workers[8];
    for (auto &worker : workers) worker = std::thread([&] {
        for (NvU32 i = 0; i != 256; ++i) {
            void *p = s540GlobalRmHostAllocate(16 + i);
            if (!p) { ++errors; continue; }
            s540GlobalRmRecordService(12);
            s540GlobalRmRecordServiceName("host_observer_fixture");
            s540GlobalRmHostFree(p);
        }
    });
    for (auto &worker : workers) worker.join();
    stop = true;
    observer.join();
    EXPECT(errors == 0);
    EXPECT(s540GlobalRmServiceMask() == (1ULL << 12));
    EXPECT(s540GlobalRmObservedServices() == 1);
    NvU64 observedCalls = 0;
    for (NvU32 slot = 0; slot != 512; ++slot)
        observedCalls += s540GlobalRmServiceCalls(slot);
    EXPECT(observedCalls == 2048);
    S540NvidiaGlobalRmHostSnapshot snapshot = {};
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.allocations == 2049 && snapshot.frees == 2049);
    EXPECT(snapshot.liveAllocations == 0 && snapshot.liveBytes == 0);
    EXPECT(snapshot.invalidFrees == 0 && snapshot.unavailableCalls == 0);
    void *p = s540GlobalRmHostAllocate(64);
    EXPECT(p != nullptr);
    S540NvidiaDarwinServicesNative::setContext(true, false);
    EXPECT(s540GlobalRmHostAllocate(64) == nullptr);
    s540GlobalRmHostFree(p);
    s540GlobalRmRecordServiceName("irq_observer_fixture");
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.unavailableCalls == 3);
    S540NvidiaDarwinServicesNative::setContext(false, true);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.liveAllocations == 1 && snapshot.liveBytes == 64);
    EXPECT(snapshot.unavailableCalls == 3);
    s540GlobalRmHostFree(p);
    s540GlobalRmHostFree(p);
    int foreign = 0;
    s540GlobalRmHostFree(&foreign);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.liveAllocations == 0 && snapshot.liveBytes == 0);
    EXPECT(snapshot.invalidFrees == 2);
    EXPECT(snapshot.allocations == snapshot.frees);
    EXPECT(s540GlobalRmHostShutdown());
    EXPECT(s540GlobalRmHostShutdown());
    std::printf("{\"format\":1,\"component\":\"nvidia-global-host-native\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"concurrent_allocations\":2048,\"service_calls\":2048,"
        "\"context_refusals\":3,\"foreign_or_duplicate_frees\":2,"
        "\"cleanup\":true,\"execution\":\"native-user-space\","
        "\"kernel_execution\":\"not_tested\",\"kernel_runtime\":\"not_tested\","
        "\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
