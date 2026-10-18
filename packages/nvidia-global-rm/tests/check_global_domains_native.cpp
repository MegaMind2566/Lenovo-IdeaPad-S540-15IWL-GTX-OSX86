// SPDX-License-Identifier: MIT
// Complete checked original global RM runs while project-owned context/firmware
// representative storage remains alive in the separate external domain.
#include "../src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include "../../nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.h"
#include <cstdio>
#include <cstring>
#include <unistd.h>

static bool bytesEqual(const unsigned char *p, size_t bytes, unsigned char value)
{
    for (size_t i = 0; i != bytes; ++i) if (p[i] != value) return false;
    return true;
}

int main()
{
    NvU32 checks = 0;
#define EXPECT(value) do { ++checks; if (!(value)) { std::fprintf(stderr, \
    "Global domain check failed at line %d\n", __LINE__); return 1; } } while (0)
    S540NvidiaGlobalRmPlatformFacts facts{};
    facts.format = 1; facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1;
#if !defined(__APPLE__)
    facts.cpuCount = static_cast<NvU32>(sysconf(_SC_NPROCESSORS_CONF));
#else
    S540NvidiaDarwinServicesNative::setCpuFixture(0);
#endif
    facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25; facts.osVersion = facts.osDate = "native-global-domain-fixture";
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    auto *context = static_cast<unsigned char *>(s540GlobalRmHostAllocate(4096));
    auto *firmware = static_cast<unsigned char *>(s540GlobalRmHostAllocate(257));
    EXPECT(context && firmware && context != firmware);
    std::memset(context, 0x53, 4096); std::memset(firmware, 0xA7, 257);
    S540NvidiaGlobalRmResult result{};
    S540NvidiaGlobalRmHostSnapshot host{};
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.externalLiveAllocations == 2 && host.externalLiveBytes == 4353);
    EXPECT(host.originalLiveAllocations == 0 && host.originalLiveBytes == 0);
    EXPECT(s540GlobalRmInitialize(&result) == NV_OK);
    EXPECT(result.initialized && result.children && result.resourceServer && result.memoryExportClient);
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.originalLiveAllocations > 0 && host.originalLiveBytes >= 24604904ULL);
    EXPECT(host.externalLiveAllocations == 2 && host.externalLiveBytes == 4353);
    EXPECT(bytesEqual(context, 4096, 0x53) && bytesEqual(firmware, 257, 0xA7));
    s540GlobalRmShutdown(&result);
    EXPECT(result.cleanShutdown && !s540GlobalRmIsInitialized());
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.originalLiveAllocations == 0 && host.originalLiveBytes == 0);
    EXPECT(host.externalLiveAllocations == 2 && host.externalLiveBytes == 4353);
    EXPECT(host.liveAllocations == 2 && host.liveBytes == 4353);
    EXPECT(host.invalidFrees == 0 && host.unavailableCalls == 0);
    EXPECT(bytesEqual(context, 4096, 0x53) && bytesEqual(firmware, 257, 0xA7));
    EXPECT(!s540GlobalRmHostShutdown());
    s540GlobalRmHostFree(context);
    EXPECT(!s540GlobalRmHostShutdown());
    EXPECT(bytesEqual(firmware, 257, 0xA7));
    s540GlobalRmHostFree(firmware);
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.liveAllocations == 0 && host.liveBytes == 0);
    EXPECT(host.allocations == host.frees && host.invalidFrees == 0 && host.unavailableCalls == 0);
    S540NvidiaGlobalCryptoSnapshot crypto{};
    s540Global_crypto_snapshot(&crypto);
    EXPECT(crypto.unavailable_calls == 0 && crypto.unavailable_symbol_mask == 0 &&
           crypto.unavailable_symbol_mask_high == 0 && crypto.counter_overflow == 0);
    EXPECT(s540DarwinLiveObjects() == 0);
    EXPECT(s540GlobalRmHostShutdown());
    std::printf("{\"format\":1,\"component\":\"nvidia-global-domains\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"real_original_global_lifecycle\":true,\"external_storage_preserved\":true,"
        "\"external_allocations\":2,\"privileged_cpu_fixture\":true,"
        "\"platform_facts_fixture\":true,\"cleanup\":true,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
