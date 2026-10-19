// SPDX-License-Identifier: MIT
// Actual global source + strong record + Host; CPU/platform facts are fixtures.
#include "Probe.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaDarwinServices.h"
#include <cstdio>
#include <cstdlib>
#include <unistd.h>

static unsigned checks, failures;
static int retainedOwner;
static void expect(bool value, const char *why) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "global owner: %s\n", why); }
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const unsigned scenario = static_cast<unsigned>(std::strtoul(argv[1], nullptr, 10));
    if (scenario > 2) return 2;
    S540NvidiaGlobalRmPlatformFacts facts = {};
    facts.format = 1; facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1; facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25; facts.osVersion = facts.osDate = "explicit-global-owner-cpu-fixture";
#if defined(__APPLE__)
    S540NvidiaDarwinServicesNative::setCpuFixture(0);
#else
    facts.cpuCount = static_cast<NvU32>(sysconf(_SC_NPROCESSORS_CONF));
#endif
    expect(s540GlobalRmHostInitialize(&facts) == NV_OK, "actual Host starts from cold state");
    if (scenario != 0)
        expect(s540FirstTxnBeginOwner(&retainedOwner) == NV_OK,
               "genuine record owner starts before every original global allocation");
    S540GlobalOwnerCheckProbe before = {}, after = {};
    s540GlobalOwnerCheckProbe(&before);
    if (scenario != 0)
        expect(before.owner == &retainedOwner && before.generation && !before.nv &&
               before.phase == S540_FIRST_OP && !before.firstStatus,
               "owner generation exists while device nv has not attached");
    if (scenario == 2) S540NvidiaGlobalRmNative::failAllocationAt(1);
    S540NvidiaGlobalRmResult result = {};
    const NV_STATUS status = s540GlobalRmInitialize(&result);
    S540NvidiaGlobalRmHostSnapshot host = {};
    S540GlobalRmHostRetentionSnapshot retention = {};
    s540GlobalOwnerCheckProbe(&after);
    s540GlobalRmHostSnapshot(&host);
    s540GlobalRmHostRetentionSnapshot(&retention);
    if (scenario < 2) {
        expect(status == NV_OK && result.initialized && s540GlobalRmIsInitialized(),
               "actual composed global RM constructs under the selected owner policy");
        expect(result.systemObject && result.children && result.presentChildren == 15 &&
               result.resourceServer && result.memoryExportClient,
               "actual original globals, fifteen children and RS memory-export client exist");
        expect(!after.firstStatus && !after.unknownRetainedObjects &&
               !host.unavailableCalls && !host.invalidFrees,
               "global construction performs no refused unknown NVOC deletion or unavailable service");
    } else {
        expect(status == NV_ERR_NO_MEMORY && after.firstStatus == NV_ERR_NO_MEMORY,
               "real first global allocation failure remains sticky through original failure handling");
        expect(!result.initialized && !s540GlobalRmIsInitialized(),
               "a failed actual constructor cannot publish a live global epoch");
    }
    expect(scenario == 0 || (after.owner == before.owner && after.generation == before.generation && !after.nv),
           "global construction does not replace or prematurely bind the original owner identity");
    if (scenario == 0 && status == NV_OK) {
        s540GlobalRmShutdown(&result);
        S540NvidiaGlobalRmHostSnapshot final = {};
        s540GlobalRmHostSnapshot(&final);
        expect(result.cleanShutdown && !s540GlobalRmIsInitialized() &&
               !final.originalLiveAllocations && !final.originalLiveBytes,
               "unbound baseline can execute the same composed global shutdown normally");
        expect(s540GlobalRmHostShutdown(), "unbound baseline releases its real Host");
    } else if (scenario == 1 && status == NV_OK) {
        expect(host.originalLiveAllocations && host.originalLiveBytes && !s540GlobalRmHostShutdown(),
               "bound healthy global epoch and all associated backing remain retained");
    }
    std::printf("{\"format\":1,\"scenario\":%u,\"checks\":%u,\"failures\":%u,"
        "\"global_status\":%u,\"global_initialized\":%s,\"record_status\":%u,"
        "\"record_site\":%u,\"record_phase\":%u,\"unknown_retained_objects\":%u,"
        "\"owner_generation_preserved\":%s,\"nv_not_attached\":%s,"
        "\"original_live_allocations\":%u,\"original_live_bytes\":%llu,"
        "\"host_allocations\":%llu,\"host_frees\":%llu,"
        "\"diagnostic_retired_allocations\":%llu,\"diagnostic_retired_bytes\":%llu,"
        "\"host_unavailable\":%u,\"host_invalid_frees\":%u,"
        "\"actual_composed_core_executed\":true,\"actual_strong_record\":true,"
        "\"privileged_cpu_fixture\":true,\"platform_facts_fixture\":true,"
        "\"kernel_execution\":false,\"gpu_access\":false,\"original_entry_admission\":false}\n",
        scenario, checks, failures, status, result.initialized ? "true" : "false",
        after.firstStatus, after.firstSite, after.phase, after.unknownRetainedObjects,
        scenario == 0 || (after.owner == before.owner && after.generation == before.generation) ? "true" : "false",
        after.nv == nullptr ? "true" : "false", host.originalLiveAllocations,
        static_cast<unsigned long long>(host.originalLiveBytes),
        static_cast<unsigned long long>(host.allocations), static_cast<unsigned long long>(host.frees),
        static_cast<unsigned long long>(retention.diagnosticRetiredAllocations),
        static_cast<unsigned long long>(retention.diagnosticRetiredBytes),
        host.unavailableCalls, host.invalidFrees);
    std::fflush(stdout);
    // The retained diagnostic intentionally keeps all backing and service
    // objects alive. Process exit is not an attempted kernel/module teardown.
    _Exit(failures ? 1 : 0);
}
