// SPDX-License-Identifier: MIT
// Native fault and concurrency contracts. Never linked into kernel startup.
#include "../src/S540NvidiaLifecycleRuntime.hpp"
#include "../src/S540NvidiaSpinlock.hpp"
#include "../upstream/nvport_lifecycle.h"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"

#include <cstdio>
#include <cstdlib>
#include <csignal>
#include <initializer_list>
#include <pthread.h>
#include <sched.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {

NvU32 gChecks;
constexpr NvU32 kWorkers = 4;
constexpr NvU32 kIterations = 1000;
NvU32 gStart;
NvU32 gErrors;
NvU32 gCompleted;
NvU32 gRefusals;
NvU32 gMutexUpdates;
NvU32 gSpinlockUpdates;
PORT_MUTEX *gSharedMutex;
PORT_SPINLOCK *gSharedSpinlock;

void require(bool condition, const char *message)
{
    ++gChecks;
    if (!condition) {
        std::fprintf(stderr, "Lifecycle contract failed: %s\n", message);
        std::exit(1);
    }
}

bool activeCount(PORT_MEM_ALLOCATOR *allocator, NvU32 count)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS stats{};
    return portMemExTrackingGetActiveStats(allocator, &stats) == NV_OK &&
        stats.numAllocations == count && stats.allocatedSize == 0 &&
        stats.usefulSize == 0 && stats.metaSize == 0;
}

void fillReserve(void **slots, NvU32 &count)
{
    count = 0;
    for (; count < S540NvidiaReserve::kSlotCount; ++count) {
        if (os_alloc_mem(&slots[count], 1) != NV_OK)
            break;
        require(slots[count] != nullptr, "successful raw allocation has storage");
    }
    require(S540NvidiaReserve::liveSlots() == S540NvidiaReserve::kSlotCount,
            "reserve exhausted at a bounded capacity");
}

void freeSlots(void **slots, NvU32 count)
{
    for (NvU32 index = 0; index < count; ++index) {
        os_free_mem(slots[index]);
        slots[index] = nullptr;
    }
}

void bootstrapFaults()
{
    using namespace S540NvidiaSpinlockNative;
    require(s540NvportMemoryIsCold() == NV_TRUE &&
            !S540NvidiaReserve::ready(), "cold initial components");
    setContext(true, true);
    require(s540NvportMemoryInitialize() == NV_ERR_INVALID_STATE &&
            s540NvportMemoryIsCold() == NV_TRUE,
            "interrupt-context bootstrap refuses publication");
    setContext(false, false);
    require(s540NvportMemoryInitialize() == NV_ERR_INVALID_STATE &&
            s540NvportMemoryIsCold() == NV_TRUE,
            "disabled-interrupt bootstrap refuses publication");
    setContext(false, true);
    require(s540NvportMemoryInitialize() == NV_ERR_NO_MEMORY &&
            s540NvportMemoryIsCold() == NV_TRUE,
            "absent reserve bootstrap unwinds");
    require(S540NvidiaReserve::initialize(), "reserve for bootstrap faults");
    const NvU32 spinBaseline = S540NvidiaSpinlock::liveObjects();
    void *slots[S540NvidiaReserve::kSlotCount] = {};
    NvU32 count = 0;
    fillReserve(slots, count);
    require(s540NvportMemoryInitialize() == NV_ERR_NO_MEMORY &&
            s540NvportMemoryIsCold() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == count,
            "bootstrap metadata exhaustion leaves no global state");
    freeSlots(slots, count);
    for (Failure failure : {Failure::Storage, Failure::Initialization}) {
        failNextAllocation(failure);
        require(s540NvportMemoryInitialize() == NV_ERR_NO_MEMORY &&
                s540NvportMemoryIsCold() == NV_TRUE &&
                S540NvidiaReserve::liveSlots() == 0 &&
                S540NvidiaSpinlock::liveObjects() == spinBaseline,
                "bootstrap backend fault releases metadata and backing");
    }
    require(S540NvidiaReserve::shutdown(), "bootstrap fault reserve cleanup");
}

void initializedFaults()
{
    using namespace S540NvidiaSpinlockNative;
    require(S540NvidiaReserve::initialize(), "reserve for owned object faults");
    require(s540NvportMemoryInitialize() == NV_OK,
            "memory tracking bootstrap for faults");
    const NvU32 baseSlots = S540NvidiaReserve::liveSlots();
    const NvU32 baseSpinlocks = S540NvidiaSpinlock::liveObjects();
    const NvU32 baseMutexes = S540NvidiaMutex::liveObjects();
    const NvU32 baseAllocators = s540NvportMemoryAllocatorCount();
    require(s540NvportMemoryInitialize() == NV_OK &&
            S540NvidiaReserve::liveSlots() == baseSlots &&
            S540NvidiaSpinlock::liveObjects() == baseSpinlocks,
            "reference initialization does not duplicate bootstrap resources");
    portMemShutdown(NV_TRUE);
    require(s540NvportMemoryIsInitialized() == NV_TRUE,
            "first reference shutdown preserves initialized state");

    PORT_MEM_ALLOCATOR *allocator = portMemAllocatorCreateNonPaged();
    require(allocator != nullptr && activeCount(allocator, 0),
            "custom allocator for fault contracts");
    const NvU32 allocatedSlots = S540NvidiaReserve::liveSlots();
    void *slots[S540NvidiaReserve::kSlotCount] = {};
    NvU32 count = 0;
    fillReserve(slots, count);
    require(portMemAllocatorCreatePaged() == nullptr &&
            portMemAllocatorCreateNonPaged() == nullptr,
            "custom allocator metadata exhaustion returns null");
    require(portSyncMutexCreate(allocator) == nullptr &&
            portSyncSpinlockCreate(allocator) == nullptr,
            "owned object metadata exhaustion returns null");
    require(activeCount(allocator, 0) &&
            s540NvportMemoryAllocatorCount() == baseAllocators + 1 &&
            S540NvidiaSpinlock::liveObjects() == baseSpinlocks &&
            S540NvidiaMutex::liveObjects() == baseMutexes,
            "metadata failures preserve tracking and OS backing baselines");
    freeSlots(slots, count);
    require(S540NvidiaReserve::liveSlots() == allocatedSlots,
            "raw fault occupancy released");
    for (Failure failure : {Failure::Storage, Failure::Initialization}) {
        failNextAllocation(failure);
        require(portSyncSpinlockCreate(allocator) == nullptr &&
                activeCount(allocator, 0) &&
                S540NvidiaReserve::liveSlots() == allocatedSlots &&
                S540NvidiaSpinlock::liveObjects() == baseSpinlocks,
                "owned spinlock backend failure unwinds tracked object");
    }
    using MutexFailure = S540NvidiaMutexNative::Failure;
    for (MutexFailure failure : {MutexFailure::Storage, MutexFailure::Guard,
                                 MutexFailure::Condition}) {
        S540NvidiaMutexNative::failNextAllocation(failure);
        require(portSyncMutexCreate(allocator) == nullptr &&
                activeCount(allocator, 0) &&
                S540NvidiaReserve::liveSlots() == allocatedSlots &&
                S540NvidiaMutex::liveObjects() == baseMutexes,
                "owned mutex backend failure unwinds tracked object and OS resources");
    }
    portMemAllocatorRelease(allocator);
    require(S540NvidiaReserve::liveSlots() == baseSlots &&
            s540NvportMemoryAllocatorCount() == baseAllocators &&
            activeCount(nullptr, 0), "fault allocator release baseline");
    portMemShutdown(NV_TRUE);
    require(s540NvportMemoryIsCold() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == 0 &&
            S540NvidiaSpinlock::liveObjects() == 0 &&
            S540NvidiaMutex::liveObjects() == baseMutexes,
            "fault shutdown releases bootstrap resources");
    require(S540NvidiaReserve::shutdown(), "fault reserve shutdown");
}

void error()
{
    __atomic_fetch_add(&gErrors, NvU32{1}, __ATOMIC_RELAXED);
}

void *worker(void *argument)
{
    const NvU32 token = *static_cast<const NvU32 *>(argument);
    while (__atomic_load_n(&gStart, __ATOMIC_ACQUIRE) == 0)
        sched_yield();
    for (NvU32 iteration = 0; iteration < kIterations; ++iteration) {
        PORT_MEM_ALLOCATOR *allocator = (iteration & 1U) != 0
            ? portMemAllocatorCreatePaged() : portMemAllocatorCreateNonPaged();
        if (allocator != nullptr) {
            auto *payload = static_cast<NvU32 *>(PORT_ALLOC(allocator, 128));
            PORT_MUTEX *mutex = portSyncMutexCreate(allocator);
            PORT_SPINLOCK *spinlock = portSyncSpinlockCreate(allocator);
            // A bounded reserve scan may refuse under contention even when
            // no simultaneous capacity snapshot was completely full.
            if (payload == nullptr || mutex == nullptr || spinlock == nullptr)
                __atomic_fetch_add(&gRefusals, NvU32{1}, __ATOMIC_RELAXED);
            else
                __atomic_fetch_add(&gCompleted, NvU32{1}, __ATOMIC_RELAXED);
            if (payload != nullptr) {
                payload[0] = token;
                payload[31] = iteration;
            }
            if (mutex != nullptr) {
                portSyncMutexAcquire(mutex);
                if (payload != nullptr &&
                    (payload[0] != token || payload[31] != iteration))
                    error();
                portSyncMutexRelease(mutex);
                portSyncMutexDestroy(mutex);
            }
            if (spinlock != nullptr) {
                portSyncSpinlockAcquire(spinlock);
                const bool masked = !S540NvidiaSpinlockNative::interruptsEnabled();
                portSyncSpinlockRelease(spinlock);
                if (!masked || !S540NvidiaSpinlockNative::interruptsEnabled())
                    error();
                portSyncSpinlockDestroy(spinlock);
            }
            PORT_FREE(allocator, payload);
            if (!activeCount(allocator, 0))
                error();
            portMemAllocatorRelease(allocator);
        } else {
            __atomic_fetch_add(&gRefusals, NvU32{1}, __ATOMIC_RELAXED);
        }
        portSyncMutexAcquire(gSharedMutex);
        ++gMutexUpdates;
        portSyncMutexRelease(gSharedMutex);
        portSyncSpinlockAcquire(gSharedSpinlock);
        ++gSpinlockUpdates;
        portSyncSpinlockRelease(gSharedSpinlock);
    }
    return nullptr;
}

void concurrentTracking()
{
    require(S540NvidiaReserve::initialize(), "concurrency reserve bootstrap");
    require(s540NvportMemoryInitialize() == NV_OK, "concurrency tracking bootstrap");
    const NvU32 baseSlots = S540NvidiaReserve::liveSlots();
    const NvU32 baseSpinlocks = S540NvidiaSpinlock::liveObjects();
    const NvU32 baseMutexes = S540NvidiaMutex::liveObjects();
    const NvU32 baseAllocators = s540NvportMemoryAllocatorCount();
    auto *global = portMemAllocatorGetGlobalNonPaged();
    gSharedMutex = portSyncMutexCreate(global);
    gSharedSpinlock = portSyncSpinlockCreate(global);
    require(gSharedMutex != nullptr && gSharedSpinlock != nullptr,
            "shared allocator-owned synchronization objects");
    pthread_t workers[kWorkers] = {};
    NvU32 tokens[kWorkers] = {};
    NvU32 started = 0;
    for (; started < kWorkers; ++started) {
        tokens[started] = started + 1;
        if (pthread_create(&workers[started], nullptr, worker,
                           &tokens[started]) != 0)
            break;
    }
    __atomic_store_n(&gStart, NvU32{1}, __ATOMIC_RELEASE);
    for (NvU32 index = 0; index < started; ++index)
        require(pthread_join(workers[index], nullptr) == 0, "worker joined");
    require(started == kWorkers, "all bounded native workers started");
    require(gErrors == 0 && gMutexUpdates == kWorkers * kIterations &&
            gSpinlockUpdates == kWorkers * kIterations && gCompleted != 0 &&
            gCompleted + gRefusals == kWorkers * kIterations,
            "simultaneous allocator/object lifecycles and protected publication");
    portSyncMutexDestroy(gSharedMutex);
    portSyncSpinlockDestroy(gSharedSpinlock);
    gSharedMutex = nullptr;
    gSharedSpinlock = nullptr;
    require(s540NvportMemoryAllocatorCount() == baseAllocators &&
            S540NvidiaReserve::liveSlots() == baseSlots &&
            S540NvidiaSpinlock::liveObjects() == baseSpinlocks &&
            S540NvidiaMutex::liveObjects() == baseMutexes &&
            activeCount(nullptr, 0), "joined workers release every owned resource");
    PORT_MEM_TRACK_ALLOCATOR_STATS total{};
    require(portMemExTrackingGetTotalStats(nullptr, &total) == NV_OK &&
            total.numAllocations >= gCompleted * 4,
            "aggregate counts include real concurrent allocation callers");
    portMemShutdown(NV_TRUE);
    require(s540NvportMemoryIsCold() == NV_TRUE &&
            S540NvidiaReserve::liveSlots() == 0 &&
            S540NvidiaSpinlock::liveObjects() == 0,
            "concurrency cleanup returns NvPort and backing resources cold");
    require(S540NvidiaReserve::shutdown(), "concurrency reserve shutdown");
}

void assertionTerminates()
{
    const pid_t child = fork();
    require(child >= 0, "assertion child started");
    if (child == 0) {
        struct rlimit noCore = {0, 0};
        (void)setrlimit(RLIMIT_CORE, &noCore);
        PORT_MUTEX invalid{};
        portSyncMutexAcquire(&invalid);
        _exit(0);
    }
    int status = 0;
    require(waitpid(child, &status, 0) == child && WIFSIGNALED(status) &&
            WTERMSIG(status) == SIGABRT,
            "failed mandatory original mutex assertion cannot return success");
}

struct LeaseObservation { bool ran; bool refused; };

void nestedLease(void *context)
{
    auto &observation = *static_cast<LeaseObservation *>(context);
    observation.ran = true;
    const auto nested = S540NvidiaLifecycleRuntime::checkIntegrated();
    observation.refused = !nested.acquired && !nested.v5.acquired &&
        !nested.lifecycle.passed() && !S540NvidiaReserve::ready() &&
        s540NvportMemoryIsCold() == NV_TRUE;
}

void integratedLease()
{
    LeaseObservation observation{};
    const auto outer = S540NvidiaCallerRuntime::checkIntegrated(
        nestedLease, &observation);
    require(outer.acquired && outer.callers.passed() && observation.ran &&
            observation.refused, "recursive checkpoint is refused under shared lease");
    const auto integrated = S540NvidiaLifecycleRuntime::checkIntegrated();
    require(integrated.acquired && integrated.v5.callers.passed() &&
            integrated.lifecycle.passed() &&
            s540NvportMemoryIsCold() == NV_TRUE && !S540NvidiaReserve::ready(),
            "shared lease released for a complete subsequent lifecycle");
}

} // namespace

int main()
{
    bootstrapFaults();
    initializedFaults();
    concurrentTracking();
    assertionTerminates();
    integratedLease();
    std::printf("{\"format\":1,\"component\":\"nvport-lifecycle-contract\","
                "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
                "\"threads\":%u,\"iterations\":%u,"
                "\"completed\":%u,\"reserve_refusals\":%u,"
                "\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",
                gChecks, kWorkers, kIterations, gCompleted, gRefusals);
    return 0;
}
