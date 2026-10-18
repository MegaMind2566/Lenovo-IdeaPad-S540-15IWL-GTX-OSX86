// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include "../../nvidia-global-rm-crypto/src/S540NvidiaGlobalCrypto.h"
#include <cstdio>
#include <cstdlib>
#include <unistd.h>

// Run each allocation ordinal in a separate child process. This tests genuine
// original construction/teardown, rather than resetting original global state.
int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    char *end = nullptr;
    const unsigned long long ordinal = std::strtoull(argv[1], &end, 10);
    if (!ordinal || !end || *end) return 2;
    S540NvidiaGlobalRmPlatformFacts facts = {};
    facts.format = 1;
    facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1;
#if !defined(__APPLE__)
    facts.cpuCount = static_cast<NvU32>(sysconf(_SC_NPROCESSORS_CONF));
#else
    S540NvidiaDarwinServicesNative::setCpuFixture(0);
#endif
    facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25;
    facts.osVersion = "native-unit-fixture";
    facts.osDate = "native-unit-fixture";
    if (s540GlobalRmHostInitialize(&facts) != NV_OK) return 3;
    S540NvidiaGlobalRmNative::failAllocationAt(ordinal);
    S540NvidiaGlobalRmResult result = {};
    const NV_STATUS status = s540GlobalRmInitialize(&result);
    if (status == NV_OK) s540GlobalRmShutdown(&result);
    S540NvidiaGlobalRmHostSnapshot host = {};
    s540GlobalRmHostSnapshot(&host);
    S540NvidiaGlobalCryptoSnapshot crypto = {};
    s540Global_crypto_snapshot(&crypto);
    // Some upstream allocations are optional (diagnostics/caches). A legitimate
    // successful fallback is accepted only with all global invariants and the
    // same complete teardown as an allocation that refuses construction.
    const bool validOutcome = (status != NV_OK && result.cleanShutdown) ||
        (result.initialized && result.systemObject && result.children &&
         result.resourceServer && result.memoryExportClient && result.cleanShutdown);
    const bool passed = validOutcome && host.allocationFailures == 1 &&
        host.liveAllocations == 0 && host.liveBytes == 0 &&
        host.invalidFrees == 0 && host.unavailableCalls == 0 &&
        host.allocations == host.frees && !s540GlobalRmIsInitialized() &&
        s540DarwinLiveObjects() == 0 && crypto.unavailable_calls == 0 &&
        crypto.unavailable_symbol_mask == 0 && crypto.unavailable_symbol_mask_high == 0 &&
        crypto.counter_overflow == 0;
    const bool released = s540GlobalRmHostShutdown();
    std::printf("{\"format\":1,\"component\":\"nvidia-global-rm-fault\","
        "\"status\":\"%s\",\"ordinal\":%llu,\"original_status\":%u,"
        "\"live_allocations\":%u,\"live_bytes\":%llu,"
        "\"allocation_failures\":%u,\"invalid_frees\":%u,"
        "\"unavailable_calls\":%u,\"host_released\":%s,"
        "\"privileged_cpu_fixture\":true,\"platform_facts_fixture\":true,"
        "\"kernel_executed\":false,\"gpu_access\":false}\n",
        passed && released ? "passed" : "failed", ordinal, status,
        host.liveAllocations, static_cast<unsigned long long>(host.liveBytes),
        host.allocationFailures, host.invalidFrees, host.unavailableCalls,
        released ? "true" : "false");
    return passed && released ? 0 : 1;
}
