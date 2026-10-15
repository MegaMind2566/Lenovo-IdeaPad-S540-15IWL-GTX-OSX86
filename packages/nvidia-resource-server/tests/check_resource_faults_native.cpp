// SPDX-License-Identifier: MIT
// Native-only real allocation-pressure/unwind coverage; no kernel linkage.
#include "../src/S540NvidiaResourceServer.hpp"
#include "../src/S540NvidiaResourceBackend.hpp"
#include "../src/S540NvidiaResourceExercise.h"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
#include <cstdio>
#include <cstdlib>
namespace {
NvU32 checks, constructorCases, resourceCases, failuresObserved, minimumFreeSlots;
void require(bool condition, const char *message) {
    ++checks;
    if (!condition) { std::fprintf(stderr,"ResourceServer fault contract failed: %s\n",message); std::exit(1); }
}
bool cold() { return !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0 &&
    s540NvportRuntimeIsCold() == NV_TRUE && s540RsBackendIsCold() == NV_TRUE &&
    S540NvidiaMutex::liveObjects() == 0 && S540NvidiaSpinlock::liveObjects() == 0; }
void pressure() {
    require(S540NvidiaReserve::initialize(),"pressure reserve starts");
    require(s540NvportRuntimeInitialize() == NV_OK,"pressure real checked core starts");
    require(s540RsBackendInitialize() == NV_OK,"pressure backend starts");
    const NvU32 baseline = S540NvidiaReserve::liveSlots();
    const NvU32 allocators = s540NvportMemoryAllocatorCount();
    const NvU32 mutexes = S540NvidiaMutex::liveObjects();
    const NvU32 spins = S540NvidiaSpinlock::liveObjects();
    minimumFreeSlots = S540NvidiaReserve::kSlotCount;
    for (NvU32 available = 0; available <= S540NvidiaReserve::kSlotCount-baseline; ++available) {
        void *occupied[S540NvidiaReserve::kSlotCount]{};
        const NvU32 held = S540NvidiaReserve::kSlotCount-baseline-available;
        for (NvU32 i=0; i<held; ++i)
            require(os_alloc_mem(&occupied[i],1) == NV_OK,"bounded reserve occupancy");
        const NvU32 before = S540NvidiaReserve::liveSlots();
        require(s540ResourceConstructorProbe() == NV_TRUE,"constructor checked acquisition/unwind");
        ++constructorCases;
        require(S540NvidiaReserve::liveSlots() == before && s540RsBackendLiveLocks() == 0 &&
            s540RsBackendLiveTlsEntries() == 0 && s540NvportMemoryAllocatorCount() == allocators &&
            S540NvidiaMutex::liveObjects() == mutexes && S540NvidiaSpinlock::liveObjects() == spins,
            "constructor restores every existing owner");
        S540_RESOURCE_RESULT result{};
        s540ResourceExercise(&result);
        ++resourceCases;
        if (result.failures != 0) ++failuresObserved;
        else if (available < minimumFreeSlots) minimumFreeSlots = available;
        require(result.cleanup == NV_TRUE && S540NvidiaReserve::liveSlots() == before &&
            s540RsBackendLiveLocks() == 0 && s540RsBackendLiveTlsEntries() == 0 &&
            s540NvportMemoryAllocatorCount() == allocators &&
            S540NvidiaMutex::liveObjects() == mutexes && S540NvidiaSpinlock::liveObjects() == spins,
            "resource API pressure restores every existing owner");
        for (NvU32 i=0; i<held; ++i) os_free_mem(occupied[i]);
        require(S540NvidiaReserve::liveSlots() == baseline,"pressure occupancy released");
    }
    require(failuresObserved != 0 && minimumFreeSlots < S540NvidiaReserve::kSlotCount,
            "real pressure failures and successful full graph both executed");
    require(s540RsBackendShutdown() == NV_TRUE,"pressure backend cold");
    require(s540NvportRuntimeShutdown() == NV_OK,"pressure checked core cold");
    require(S540NvidiaReserve::shutdown() && cold(),"pressure reserve and OS objects cold");
}
}
int main() {
    require(cold(),"initial state cold");
    pressure();
    const auto recovered = S540NvidiaResourceServer::check();
    require(recovered.passed() && cold(),"full production graph recovers after pressure");
    std::printf("{\"format\":1,\"component\":\"nvidia-resource-faults\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"constructor_cases\":%u,\"resource_cases\":%u,\"pressure_failures\":%u,\"minimum_free_slots\":%u,\"recovery\":true,\"cleanup\":true,\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",checks,constructorCases,resourceCases,failuresObserved,minimumFreeSlots);
}
