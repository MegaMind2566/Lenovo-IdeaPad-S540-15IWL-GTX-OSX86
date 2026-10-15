// SPDX-License-Identifier: MIT
// Real bounded backend fault, ownership, TLS isolation and contention checks.
#include "../src/S540NvidiaResourceBackend.hpp"
#include "../../nvidia-nvport-runtime/upstream/nvport_runtime.h"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include <pthread.h>
#include <sched.h>

extern "C" void nvAssertFailedNoLog(const char *, const char *, NvU32);
extern "C" void nvCheckOkFailedNoLog(NvU32, NvU32, const char *, const char *, NvU32);

namespace {
NvU32 checks;
NvU32 workerErrors;
void require(bool condition, const char *message) {
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "Resource backend contract failed: %s\n", message);
        std::exit(1);
    }
}
void workerRequire(bool condition) {
    if (!condition)
        __atomic_add_fetch(&workerErrors, NvU32{1}, __ATOMIC_RELAXED);
}
void waitFor(NvU32 *value, NvU32 expected) {
    while (__atomic_load_n(value, __ATOMIC_ACQUIRE) != expected)
        sched_yield();
}
NvU32 ready;
NvU32 releaseWorkers;
void *tlsWorker(void *argument) {
    const auto identity = reinterpret_cast<NvUPtr>(argument);
    NvP64 *entry = tlsEntryAcquire(1);
    workerRequire(entry != nullptr);
    if (entry != nullptr) {
        *entry = reinterpret_cast<void *>(identity);
        workerRequire(tlsEntryGet(1) == reinterpret_cast<void *>(identity));
    }
    __atomic_add_fetch(&ready, NvU32{1}, __ATOMIC_RELEASE);
    waitFor(&releaseWorkers, 1);
    if (entry != nullptr) {
        workerRequire(tlsEntryGet(1) == reinterpret_cast<void *>(identity));
        workerRequire(tlsEntryRelease(1) == 0);
    }
    return nullptr;
}
struct LockWorker {
    PORT_RWLOCK *lock;
    NvU32 *value;
    bool conditionalOnly;
};
void *lockWorker(void *argument) {
    auto &state = *static_cast<LockWorker *>(argument);
    if (state.conditionalOnly) {
        const NvBool acquired = portSyncRwLockAcquireReadConditional(state.lock);
        workerRequire(acquired == NV_FALSE);
        if (acquired == NV_TRUE)
            portSyncRwLockReleaseRead(state.lock);
        return nullptr;
    }
    for (NvU32 index = 0; index < 1200; ++index) {
        portSyncRwLockAcquireWrite(state.lock);
        ++*state.value;
        portSyncRwLockReleaseWrite(state.lock);
        portSyncRwLockAcquireRead(state.lock);
        workerRequire(*state.value > 0);
        portSyncRwLockReleaseRead(state.lock);
    }
    return nullptr;
}
} // namespace

int main() {
    using namespace S540NvidiaResourceBackendNative;
    require(s540RsBackendIsCold() == NV_TRUE &&
            s540RsBackendInitialize() == NV_ERR_INVALID_STATE,
            "missing checked memory core is refused");
    require(tlsEntryAcquire(1) == nullptr && tlsEntryGet(1) == NvP64_NULL &&
            tlsEntryRelease(1) == ~NvU32{0}, "cold TLS is unavailable");
    require(S540NvidiaReserve::initialize() && s540NvportRuntimeInitialize() == NV_OK,
            "real reserve and checked NVPort core initialize");
    const NvU32 coreSlots = S540NvidiaReserve::liveSlots();
    const NvU32 coreSpins = S540NvidiaSpinlock::liveObjects();
    failNext(Failure::InitializeGuard);
    require(s540RsBackendInitialize() == NV_ERR_NO_MEMORY &&
            s540RsBackendIsCold() == NV_TRUE &&
            S540NvidiaSpinlock::liveObjects() == coreSpins,
            "guard creation failure does not publish or leak a backend");
    require(s540RsBackendInitialize() == NV_OK &&
            S540NvidiaSpinlock::liveObjects() == coreSpins + 1,
            "real backend guard is owned");
    require(s540RsBackendInitialize() == NV_ERR_INVALID_STATE,
            "duplicate initialization preserves original ownership");
    require(tlsEntryAcquire(7) == nullptr && tlsEntryAcquire(0xfffff) == nullptr,
            "unallocated dynamic TLS identifiers are refused");
    S540NvidiaSpinlockNative::setContext(true, true);
    require(tlsEntryAcquire(1) == nullptr && s540RsBackendShutdown() == NV_FALSE,
            "interrupt TLS and destruction are refused");
    S540NvidiaSpinlockNative::setContext(false, true);
    failNext(Failure::TlsEntry);
    require(tlsEntryAcquire(1) == nullptr && s540RsBackendLiveTlsEntries() == 0,
            "TLS acquisition failure leaves no thread or entry");
    NvP64 *entry = tlsEntryAcquire(1);
    require(entry != nullptr && *entry == NvP64_NULL, "new TLS starts empty");
    *entry = reinterpret_cast<void *>(NvUPtr{0x1234});
    require(tlsEntryAcquire(1) == entry && tlsEntryGet(1) == *entry &&
            s540RsBackendLiveTlsEntries() == 1, "nested TLS acquisition shares one thread entry");
    require(s540RsBackendShutdown() == NV_FALSE, "outstanding TLS refuses shutdown");
    require(tlsEntryRelease(1) == 1 && tlsEntryGet(1) == *entry &&
            tlsEntryRelease(1) == 0 && tlsEntryGet(1) == NvP64_NULL &&
            tlsEntryRelease(1) == ~NvU32{0}, "balanced release removes the entry exactly once");
    for (NvU32 index = 0; index < 16; ++index)
        require(tlsEntryAcquire(0x100000 + index) != nullptr, "bounded tagged entry acquired");
    require(tlsEntryAcquire(0x100010) == nullptr && s540RsBackendLiveTlsEntries() == 16,
            "per-thread entry capacity refuses overflow without eviction");
    for (NvU32 index = 0; index < 16; ++index)
        require(tlsEntryRelease(0x100000 + index) == 0, "tagged entry released");
    pthread_t tlsWorkers[32];
    for (NvU32 index = 0; index < 32; ++index)
        require(pthread_create(&tlsWorkers[index], nullptr, tlsWorker,
                               reinterpret_cast<void *>(NvUPtr{index + 1})) == 0,
                "TLS isolation worker starts");
    waitFor(&ready, 32);
    require(s540RsBackendLiveTlsEntries() == 32 && tlsEntryAcquire(1) == nullptr,
            "32 live thread identities are isolated and the 33rd is refused");
    __atomic_store_n(&releaseWorkers, NvU32{1}, __ATOMIC_RELEASE);
    for (auto worker : tlsWorkers)
        require(pthread_join(worker, nullptr) == 0, "TLS isolation worker joins");
    require(workerErrors == 0 && s540RsBackendLiveTlsEntries() == 0 &&
            S540NvidiaReserve::liveSlots() == coreSlots,
            "TLS workers release entries and consume no reserve slots");
    PORT_MEM_ALLOCATOR *allocator = portMemAllocatorCreateNonPaged();
    require(allocator != nullptr, "real tracked allocator for RW ownership");
    const NvU32 allocatorSlots = S540NvidiaReserve::liveSlots();
    require(portSyncRwLockCreate(nullptr) == nullptr, "null RW allocator refused");
    for (Failure failure : {Failure::RwStorage, Failure::RwBacking}) {
        failNext(failure);
        require(portSyncRwLockCreate(allocator) == nullptr &&
                s540RsBackendLiveLocks() == 0 && S540NvidiaMutex::liveObjects() == 0 &&
                S540NvidiaReserve::liveSlots() == allocatorSlots,
                "RW storage/backing failure unwinds tracked ownership");
    }
    PORT_RWLOCK *lock = portSyncRwLockCreate(allocator);
    require(lock != nullptr && s540RsBackendLiveLocks() == 1 &&
            S540NvidiaMutex::liveObjects() == 1, "RW lock owns a real OS mutex");
    require(s540RsBackendShutdown() == NV_FALSE, "live RW lock refuses backend shutdown");
    portSyncRwLockAcquireWrite(lock);
    require(portSyncRwLockAcquireReadConditional(lock) == NV_FALSE &&
            portSyncRwLockAcquireWriteConditional(lock) == NV_FALSE,
            "owner recursive conditional acquire is refused");
    NvU32 counter = 0;
    LockWorker conditional{lock, &counter, true};
    pthread_t conditionalWorker;
    require(pthread_create(&conditionalWorker, nullptr, lockWorker, &conditional) == 0 &&
            pthread_join(conditionalWorker, nullptr) == 0,
            "held writer excludes another thread conditional reader");
    portSyncRwLockReleaseWrite(lock);
    require(portSyncRwLockAcquireReadConditional(lock) == NV_TRUE,
            "released RW token is available for reading");
    portSyncRwLockReleaseRead(lock);
    LockWorker contention{lock, &counter, false};
    pthread_t lockWorkers[4];
    for (auto &worker : lockWorkers)
        require(pthread_create(&worker, nullptr, lockWorker, &contention) == 0,
                "RW contention worker starts");
    for (auto worker : lockWorkers)
        require(pthread_join(worker, nullptr) == 0, "RW contention worker joins");
    require(counter == 4800 && workerErrors == 0,
            "real read/write exclusion preserves all 4800 worker updates");
    portSyncRwLockDestroy(lock);
    require(s540RsBackendLiveLocks() == 0 && S540NvidiaMutex::liveObjects() == 0 &&
            S540NvidiaReserve::liveSlots() == allocatorSlots,
            "RW destruction returns tracked and OS allocations");
    portMemAllocatorRelease(allocator);
    nvAssertFailedNoLog("native expected assertion", __FILE__, __LINE__);
    nvCheckOkFailedNoLog(0, NV_ERR_NOT_SUPPORTED, "native expected check", __FILE__, __LINE__);
    S540NvidiaSpinlockNative::setContext(false, false);
    nvAssertFailedNoLog("native expected masked assertion", __FILE__, __LINE__);
    nvCheckOkFailedNoLog(0, NV_ERR_NOT_SUPPORTED, "native expected masked check", __FILE__, __LINE__);
    S540NvidiaSpinlockNative::setContext(false, true);
    require(s540RsBackendAssertionFailures() == 2 && s540RsBackendCheckFailures() == 2,
            "debug failures remain observable including contexts that cannot log");
    require(s540RsBackendShutdown() == NV_TRUE && s540RsBackendIsCold() == NV_TRUE &&
            S540NvidiaSpinlock::liveObjects() == coreSpins,
            "backend releases guard and returns cold");
    require(s540NvportRuntimeShutdown() == NV_OK && S540NvidiaReserve::shutdown() &&
            s540NvportRuntimeIsCold() == NV_TRUE && !S540NvidiaReserve::ready() &&
            S540NvidiaReserve::liveSlots() == 0 && S540NvidiaMutex::liveObjects() == 0 &&
            S540NvidiaSpinlock::liveObjects() == 0, "entire checked core returns cold");
    std::printf("{\"format\":1,\"component\":\"resource-server-backend\","
                "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
                "\"tls_threads\":32,\"entries_per_thread\":16,\"rw_updates\":4800,"
                "\"execution\":\"native-user-space\",\"gpu_access\":false,"
                "\"kernel_runtime\":\"not_tested\",\"cleanup\":true}\n", checks);
}
