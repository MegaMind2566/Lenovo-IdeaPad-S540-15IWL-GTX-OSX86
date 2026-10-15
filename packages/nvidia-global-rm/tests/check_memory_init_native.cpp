// SPDX-License-Identifier: MIT
// Targeted checked-memory overlay control. Requires the original full RM
// closure, the explicit user-space CR4 fixture and all reviewed cleanup overlays.
#include "../src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <cstdio>
#include <unistd.h>

extern "C" NV_STATUS s540Global_portInitialize(void);
extern "C" void s540Global_portShutdown(void);
extern "C" NvBool s540Global_portIsInitialized(void);

int main()
{
    NvU32 checks = 0;
#define EXPECT(value) do { ++checks; if (!(value)) { \
    std::fprintf(stderr, "Checked memory initialization failed at line %d\n", __LINE__); return 1; } } while (0)
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
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    EXPECT(!s540Global_portIsInitialized());

    // Fail the raw tracking-lock allocation before any allocator is linked.
    S540NvidiaGlobalRmNative::failAllocationAt(1);
    EXPECT(s540Global_portInitialize() == NV_ERR_NO_MEMORY);
    EXPECT(!s540Global_portIsInitialized());
    S540NvidiaGlobalRmHostSnapshot host = {};
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.liveAllocations == 0 && host.liveBytes == 0);
    EXPECT(host.allocationFailures == 1 && host.invalidFrees == 0);
    EXPECT(host.unavailableCalls == 0 && s540DarwinLiveObjects() == 0);

    // The same failure through global RM also runs its original failure cleanup.
    // That cleanup must not decrement the portable reference a second time.
    S540NvidiaGlobalRmNative::failAllocationAt(2);
    S540NvidiaGlobalRmResult result = {};
    EXPECT(s540GlobalRmInitialize(&result) == NV_ERR_NO_MEMORY);
    EXPECT(result.cleanShutdown && !s540GlobalRmIsInitialized());
    EXPECT(!s540Global_portIsInitialized());
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.liveAllocations == 0 && host.liveBytes == 0);
    EXPECT(host.allocationFailures == 2 && host.unavailableCalls == 0);
    EXPECT(s540DarwinLiveObjects() == 0);

    // Separately fail the real OS lock acquisition after raw storage exists.
    // The checked initializer must free that storage without destroying a lock
    // it never acquired, and must remain reusable.
    S540NvidiaDarwinServicesNative::failNext(S540NvidiaDarwinServicesNative::Failure::Storage);
    EXPECT(s540GlobalRmInitialize(&result) == NV_ERR_NO_MEMORY);
    EXPECT(result.cleanShutdown && !s540Global_portIsInitialized());
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.liveAllocations == 0 && host.liveBytes == 0);
    EXPECT(host.allocations == 1 && host.frees == 1);
    EXPECT(host.invalidFrees == 0 && host.unavailableCalls == 0);
    EXPECT(s540DarwinLiveObjects() == 0);

    // Retry the complete original lifecycle in the same process and host
    // context. This catches hidden init-count underflow and poisoned globals.
    EXPECT(s540GlobalRmInitialize(&result) == NV_OK);
    EXPECT(result.initialized && result.children && result.presentChildren == 15);
    EXPECT(result.resourceServer && result.memoryExportClient);
    EXPECT(s540Global_portIsInitialized());
    s540GlobalRmShutdown(&result);
    EXPECT(result.cleanShutdown && !s540Global_portIsInitialized());
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.liveAllocations == 0 && host.liveBytes == 0);
    EXPECT(host.allocations == host.frees);
    EXPECT(host.invalidFrees == 0 && host.unavailableCalls == 0);
    EXPECT(s540DarwinLiveObjects() == 0);
    EXPECT(s540GlobalRmHostShutdown());
    std::printf("{\"format\":1,\"component\":\"nvidia-memory-init-native\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"raw_lock_failure\":true,\"global_failure_cleanup\":true,"
        "\"backing_lock_failure\":true,\"same_process_full_rm_retry\":true,"
        "\"original_system_children\":15,\"cleanup\":true,"
        "\"privileged_cpu_fixture\":true,\"platform_facts_fixture\":true,"
        "\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\","
        "\"kernel_executed\":false,\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
