// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include "../../nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.h"
#include <cstdio>
#include <unistd.h>

int main()
{
    NvU32 checks = 0;
#define EXPECT(condition) do { ++checks; if (!(condition)) { \
    std::fprintf(stderr, "Global RM check failed at line %d\n", __LINE__); return 1; } } while (0)
    S540NvidiaGlobalRmPlatformFacts facts = {};
    facts.format = 1;
    facts.known = S540_GLOBAL_FACT_ALL;
    // Explicit unit-test platform/privileged-CPU fixture. These values are not
    // evidence of physical Darwin queries or of kernel GPU execution.
    facts.cpuCount = 1;
#if !defined(__APPLE__)
    facts.cpuCount = static_cast<NvU32>(sysconf(_SC_NPROCESSORS_CONF));
#endif
    facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25;
    facts.osVersion = "native-unit-fixture";
    facts.osDate = "native-unit-fixture";
    S540NvidiaGlobalRmHostSnapshot host = {};
    S540NvidiaGlobalRmResult result = {};
    S540NvidiaGlobalCryptoSnapshot crypto = {};
#if defined(__APPLE__)
    S540NvidiaDarwinServicesNative::setCpuFixture(0);
#endif
    EXPECT(s540DarwinLiveObjects() == 0);
    EXPECT(!s540GlobalRmIsInitialized());
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    EXPECT(s540GlobalRmInitialize(&result) == NV_OK);
    EXPECT(result.initialized && result.startupStatus == NV_OK);
    EXPECT(result.systemObject && result.children && result.presentChildren == 15);
    EXPECT(result.resourceServer && result.memoryExportClient);
    EXPECT(result.unavailableCalls == 0 && result.osServiceMask != 0);
    EXPECT(s540GlobalRmIsInitialized());
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.liveAllocations != 0 && host.liveBytes != 0);
    EXPECT(host.largestAllocation >= 24604904ULL);
    EXPECT(host.peakAllocations >= 100);
    EXPECT(host.invalidFrees == 0 && host.unavailableCalls == 0);
    s540GlobalRmShutdown(&result);
    EXPECT(result.cleanShutdown);
    EXPECT(!s540GlobalRmIsInitialized());
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.liveBytes == 0 && host.liveAllocations == 0);
    EXPECT(host.allocations == host.frees);
    EXPECT(host.invalidFrees == 0 && host.unavailableCalls == 0);
    EXPECT(s540DarwinLiveObjects() == 0);
    s540Global_crypto_snapshot(&crypto);
    EXPECT(crypto.unavailable_calls == 0 && crypto.unavailable_symbol_mask == 0 &&
           crypto.unavailable_symbol_mask_high == 0 && crypto.counter_overflow == 0);
    EXPECT(s540GlobalRmHostShutdown());
    EXPECT(s540GlobalRmHostShutdown());
    std::printf("{\"format\":1,\"component\":\"nvidia-global-rm-native\","
        "\"status\":\"passed\",\"checks\":%u,\"full_rm_initialized\":true,"
        "\"failures\":0,\"execution\":\"native-user-space\","
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
        "\"kernel_runtime\":\"not_tested\","
        "\"original_system_children\":15,\"original_memory_export_client\":true,"
        "\"cleanup\":true,\"host_allocations\":%llu,\"host_frees\":%llu,"
        "\"peak_host_allocations\":%u,\"peak_host_bytes\":%llu,"
        "\"largest_allocation\":%llu,\"unavailable_calls\":0,"
        "\"crypto_calls\":0,\"privileged_cpu_fixture\":true,"
        "\"platform_facts_fixture\":true,\"kernel_executed\":false,"
        "\"adapter_initialized\":false,\"gsp_initialized\":false,"
        "\"gpu_operations\":false,\"observed_services\":%u,\"service_calls\":{", checks,
        static_cast<unsigned long long>(host.allocations),
        static_cast<unsigned long long>(host.frees), host.peakAllocations,
        static_cast<unsigned long long>(host.peakBytes),
        static_cast<unsigned long long>(host.largestAllocation),
        s540GlobalRmObservedServices());
    bool comma = false;
    for (NvU32 slot = 0; slot != 512; ++slot) {
        const char *name = s540GlobalRmServiceName(slot);
        if (!name) continue;
        std::printf("%s\"%s\":%llu", comma ? "," : "", name,
            static_cast<unsigned long long>(s540GlobalRmServiceCalls(slot)));
        comma = true;
    }
    std::puts("}}");
    return 0;
#undef EXPECT
}
