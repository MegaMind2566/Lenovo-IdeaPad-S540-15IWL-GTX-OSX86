/* SPDX-License-Identifier: MIT */
/* Link with the complete checked original RM, real original registry/nvport,
 * real host allocator and Darwin services. No original global constructor is
 * expected to run: the populated epoch must be refused before construction.
 */
#include "nv.h"
#include "../src/S540NvidiaGlobalRm.h"
#include "../src/S540NvidiaGlobalRmProfile.h"
#include <stdio.h>

extern NV_STATUS portInitialize(void);
extern void portShutdown(void);
extern NvBool portIsInitialized(void);
extern NV_STATUS RmWriteRegistryDword(nv_state_t *, const char *, NvU32);
extern NV_STATUS RmReadRegistryDword(nv_state_t *, const char *, NvU32 *);
extern NV_STATUS RmDestroyRegistry(nv_state_t *);

int main(void)
{
    NvU32 checks = 0, value = 0;
    S540NvidiaGlobalRmPlatformFacts facts = {0};
    S540NvidiaGlobalRmHostSnapshot before = {0}, after = {0};
    S540NvidiaGlobalRmResult result = {0};
#define EXPECT(value) do { ++checks; if (!(value)) { \
    fprintf(stderr, "Registry epoch check failed at line %d\n", __LINE__); return 1; \
    } } while (0)
    facts.format = 1;
    facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1;
    facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25;
    facts.osVersion = "native-platform-fixture";
    facts.osDate = "native-platform-fixture";
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    EXPECT(s540GlobalRmCheckRegistryCold() == NV_OK);
    EXPECT(portInitialize() == NV_OK && portIsInitialized());
    EXPECT(RmWriteRegistryDword(NULL, "ForeignEpoch", 0x1234ABCDU) == NV_OK);
    EXPECT(s540GlobalRmCheckRegistryCold() == NV_ERR_STATE_IN_USE);
    s540GlobalRmHostSnapshot(&before);
    EXPECT(before.liveAllocations > 0 && before.liveBytes > 0);

    EXPECT(s540GlobalRmInitialize(&result) == NV_ERR_STATE_IN_USE);
    EXPECT(result.startupStatus == NV_ERR_STATE_IN_USE && !result.initialized);
    EXPECT(!s540GlobalRmIsInitialized() && portIsInitialized());
    EXPECT(RmReadRegistryDword(NULL, "ForeignEpoch", &value) == NV_OK);
    EXPECT(value == 0x1234ABCDU);
    s540GlobalRmShutdown(&result);
    EXPECT(RmReadRegistryDword(NULL, "ForeignEpoch", &value) == NV_OK);
    EXPECT(value == 0x1234ABCDU && portIsInitialized());
    s540GlobalRmHostSnapshot(&after);
    EXPECT(after.allocations == before.allocations && after.frees == before.frees);
    EXPECT(after.liveAllocations == before.liveAllocations && after.liveBytes == before.liveBytes);
    EXPECT(after.invalidFrees == 0 && after.unavailableCalls == 0);

    // The epoch's actual owner, rather than the refused global lifecycle,
    // performs the original cleanup and releases its portable reference.
    EXPECT(RmDestroyRegistry(NULL) == NV_OK);
    EXPECT(s540GlobalRmCheckRegistryCold() == NV_OK);
    portShutdown();
    EXPECT(!portIsInitialized());
    s540GlobalRmHostSnapshot(&after);
    EXPECT(after.liveAllocations == 0 && after.liveBytes == 0);
    EXPECT(after.allocations == after.frees);
    EXPECT(after.invalidFrees == 0 && after.unavailableCalls == 0);
    EXPECT(s540GlobalRmHostShutdown());
    printf("{\"format\":1,\"component\":\"nvidia-registry-epoch\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"real_original_registry\":true,\"foreign_epoch_preserved\":true,"
           "\"platform_facts_fixture\":true,\"global_constructor_executed\":false,"
           "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
           "\"gpu_access\":false,\"cleanup\":true}\n", checks);
    return 0;
#undef EXPECT
}
