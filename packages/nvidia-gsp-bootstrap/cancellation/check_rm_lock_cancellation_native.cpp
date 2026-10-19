// SPDX-License-Identifier: MIT
#include "rm_lock_cancellation_fixture.hpp"
#include "rm_lock_actual_bodies.inc"
namespace {
unsigned checks, failures;
PORT_SPINLOCK fixtureSpin{};
PORT_RWLOCK fixtureRw{};
PORT_SEMAPHORE fixtureSema[3]{};
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "RM lock cancellation: %s\n", reason); }
}
void pause() { PORT_ASSERT(s540Darwin_os_delay(1) == NV_OK); }
void wait(std::atomic<bool> &ready) { while (!ready.load()) pause(); }
void reset() {
    g_RmApiLock = {}; g_RmApiLock.pLock = &fixtureRw; g_RmApiLock.threadId = ~NvU64{0};
    rmGpuLockInfo = {}; rmGpuLockInfo.pLock = &fixtureSpin; rmGpuLockInfo.gpusLockableMask = 3;
    for (unsigned i = 0; i < 3; ++i) {
        auto &lock = i == 2 ? rmGpuLockInfo.gpuAllocLock : rmGpuLockInfo.gpuLocks[i];
        lock.count = 1; lock.pWaitSema = &fixtureSema[i]; lock.threadId = ~NvU64{0};
    }
    fixtureAcquireMasks = fixtureReleaseMasks = 0;
    fixtureAcquireFlags = fixtureReleaseFlags = 0;
    fixtureTlsFailure = false;
}
struct Scope {
    int state = 0;
    S540GspCancellationToken token = 0;
    Scope() {
        PORT_ASSERT(s540GspCancellationBind(&state, &token) == NV_OK);
        PORT_ASSERT(s540GspCancellationBegin(token) == NV_OK);
    }
    ~Scope() {
        PORT_ASSERT(s540GspCancellationFinish(token) == NV_OK);
        PORT_ASSERT(s540GspCancellationUnbind(token) == NV_OK);
    }
};
void apiContention(NvU32 flags) {
    reset(); Scope scope;
    std::atomic<bool> held{false}, release{false};
    std::thread holder([&] {
        PORT_ASSERT(rmapiLockAcquire(0, RM_LOCK_MODULES_INIT) == NV_OK);
        held = true; wait(release); rmapiLockRelease();
    });
    wait(held);
    std::thread revoker([&] {
        pause(); pause();
        PORT_ASSERT(s540GspCancellationRevoke(scope.token) == NV_OK);
        pause(); pause(); release = true;
    });
    const auto status = rmapiLockAcquire(flags, RM_LOCK_MODULES_INIT);
    expect(status == NV_ERR_OPERATION_ABORTED, "contended API acquisition observes actual asynchronous revocation");
    expect(status != NV_OK && !rmapiLockIsOwner(), "cancelled API waiter owns no token or TLS lease");
    if (status == NV_OK) rmapiLockRelease(); // Baseline must also leave the test quiescent.
    revoker.join(); holder.join();
    expect(g_RmApiLock.contentionCount == 0, "writer contention counter balances after cancellation");
    expect(portSyncRwLockAcquireWriteConditional(&fixtureRw), "successor can acquire actual rwlock after cancelled waiter");
    portSyncRwLockReleaseWrite(&fixtureRw);
}
bool allGpuFree() {
    return rmGpuLockInfo.gpuAllocLock.count == 1 && !rmGpuLockInfo.gpuAllocLock.bRunning &&
        rmGpuLockInfo.gpuLocks[0].count == 1 && !rmGpuLockInfo.gpuLocks[0].bRunning &&
        rmGpuLockInfo.gpuLocks[1].count == 1 && !rmGpuLockInfo.gpuLocks[1].bRunning &&
        rmGpuLockInfo.gpusLockedMask == 0;
}
}
int main(int argc, char **argv) {
    const bool baseline = argc == 2 && std::strcmp(argv[1], "--baseline") == 0;
    PORT_ASSERT(s540Darwin_os_alloc_spinlock(&fixtureSpin.lock) == NV_OK);
    fixtureRw.rwlock = s540Darwin_os_alloc_rwlock(); PORT_ASSERT(fixtureRw.rwlock);
    for (auto &semaphore : fixtureSema) { semaphore.sem = s540Darwin_os_alloc_semaphore(0); PORT_ASSERT(semaphore.sem); }
    apiContention(0);
    apiContention(RMAPI_LOCK_FLAGS_READ);

    {
        reset(); Scope scope;
        PORT_ASSERT(s540GspCancellationRevoke(scope.token) == NV_OK);
        expect(rmapiLockAcquire(0, RM_LOCK_MODULES_INIT) == NV_ERR_OPERATION_ABORTED,
            "revoked free API lock cannot publish ownership");
        if (rmapiLockIsOwner()) rmapiLockRelease();
        expect(!rmapiLockIsOwner(), "revoked free API attempt has no TLS owner");
    }
    {
        reset(); Scope scope;
        fixtureRevokeAfterWriterContention = scope.token;
        const auto status = rmapiLockAcquire(0, RM_LOCK_MODULES_INIT);
        expect(status == NV_ERR_OPERATION_ABORTED && !rmapiLockIsOwner(),
            "revocation racing acquired API token releases it before publishing TLS");
        if (status == NV_OK) rmapiLockRelease();
        expect(portSyncRwLockAcquireWriteConditional(&fixtureRw), "racing cancellation returns actual API token to successor");
        portSyncRwLockReleaseWrite(&fixtureRw);
    }
    {
        reset(); Scope scope;
        expect(rmapiLockAcquire(RMAPI_LOCK_FLAGS_LOW_PRIORITY, RM_LOCK_MODULES_INIT) == NV_ERR_NOT_SUPPORTED,
            "experimental low-priority aging refuses before token acquisition");
        if (rmapiLockIsOwner()) rmapiLockRelease();
        expect(!g_RmApiLock.contentionCount, "unsupported priority does not change waiter accounting");
    }
    {
        reset(); Scope scope; fixtureTlsFailure = true;
        expect(rmapiLockAcquire(0, RM_LOCK_MODULES_INIT) == NV_ERR_INSUFFICIENT_RESOURCES,
            "original TLS allocation failure remains statusful");
        fixtureTlsFailure = false;
        expect(portSyncRwLockAcquireWriteConditional(&fixtureRw), "TLS failure releases actual acquired token");
        portSyncRwLockReleaseWrite(&fixtureRw);
    }
    {
        reset(); Scope scope;
        expect(rmapiLockAcquire(0, RM_LOCK_MODULES_INIT) == NV_OK && rmapiLockIsOwner(),
            "healthy scoped original API acquisition publishes real ownership");
        expect(rmapiLockAcquire(0, RM_LOCK_MODULES_INIT) == NV_ERR_INVALID_LOCK_STATE,
            "recursive API acquisition retains original invalid-lock error");
        rmapiLockRelease();
    }
    {
        reset(); Scope scope;
        std::atomic<bool> held{false}, release{false};
        std::atomic<bool> noPartialCounts{false};
        std::thread holder([&] {
            NvU32 mask = 0;
            PORT_ASSERT(_rmGpuLocksAcquire(2, 0, 1, nullptr, &mask) == NV_OK && mask == 2);
            held = true; wait(release);
            const auto status = _rmGpuLocksRelease(mask, 0, nullptr, nullptr);
            PORT_ASSERT(status == NV_OK || status == NV_ERR_MORE_PROCESSING_REQUIRED);
        });
        wait(held);
        std::thread revoker([&] {
            S540GspCancellationSnapshot state{};
            for (unsigned n = 0; n < 20; ++n) {
                if (s540GspCancellationGetSnapshot(scope.token, &state) == NV_OK && state.checks >= 4) break;
                pause();
            }
            portSyncSpinlockAcquire(&fixtureSpin);
            noPartialCounts = rmGpuLockInfo.gpuAllocLock.count == 1 &&
                rmGpuLockInfo.gpuLocks[0].count == 1 && !rmGpuLockInfo.gpuLocks[0].bRunning &&
                rmGpuLockInfo.gpuLocks[1].count == 0 && rmGpuLockInfo.gpusLockedMask == 2;
            portSyncSpinlockRelease(&fixtureSpin);
            PORT_ASSERT(s540GspCancellationRevoke(scope.token) == NV_OK);
            pause(); release = true;
        });
        NvU32 mask = 99;
        const auto status = _rmGpuLocksAcquire(GPUS_LOCK_ALL, 0, 1, nullptr, &mask);
        expect(status == NV_ERR_OPERATION_ABORTED && mask == 0,
            "contended multi-GPU acquisition returns cancellation with empty acquired mask");
        expect(noPartialCounts, "unavailable final GPU leaves alloc and earlier GPU counts untouched");
        if (status == NV_OK) (void)_rmGpuLocksRelease(mask, 0, nullptr, nullptr);
        revoker.join(); holder.join();
        expect(allGpuFree(), "all real GPU counts and owner bits balance after contended cancellation");
    }
    {
        reset(); Scope scope; fixtureRevokeAfterMask = scope.token;
        NvU32 mask = 99;
        const auto status = _rmGpuLocksAcquire(GPUS_LOCK_ALL, 0, 1, nullptr, &mask);
        expect(status == NV_ERR_OPERATION_ABORTED && mask == 0,
            "post-commit GPU cancellation executes original coherent rollback");
        if (status == NV_OK) (void)_rmGpuLocksRelease(mask, 0, nullptr, nullptr);
        expect(allGpuFree(), "post-commit rollback returns alloc and GPU tokens exactly once");
        expect(fixtureAcquireMasks == 2 && fixtureReleaseMasks == 2 &&
            fixtureAcquireFlags == 0 && fixtureReleaseFlags == 0,
            "retry mechanism preserves original ordinary interrupt flags in acquire and release");
    }
    {
        reset(); Scope scope;
        NvU32 mask = 0;
        expect(_rmGpuLocksAcquire(1, 0, 1, nullptr, &mask) == NV_OK && mask == 1 && _rmGpuLockIsOwner(mask),
            "healthy scoped original GPU acquire owns requested real count");
        NvU32 recursive = 99;
        expect(_rmGpuLocksAcquire(1, 0, 1, nullptr, &recursive) == NV_ERR_INVALID_LOCK_STATE && recursive == 0,
            "normal recursive GPU acquisition retains ordering validation");
        NvU32 upgrade = 0;
        expect(_rmGpuLocksAcquire(GPUS_LOCK_ALL, GPU_LOCK_FLAGS_SAFE_LOCK_UPGRADE, 1, nullptr, &upgrade) == NV_OK && upgrade == 2,
            "safe upgrade preserves already-owned mask and acquires only missing targets");
        (void)_rmGpuLocksRelease(upgrade, GPU_LOCK_FLAGS_SAFE_LOCK_UPGRADE, nullptr, nullptr);
        expect(rmGpuLocksGetOwnedMask() == 1, "safe-upgrade release preserves pre-existing GPU token");
        (void)_rmGpuLocksRelease(mask, 0, nullptr, nullptr);
        expect(allGpuFree(), "healthy GPU acquire/upgrade/release balances every token");
    }
    s540Darwin_os_free_rwlock(fixtureRw.rwlock);
    s540Darwin_os_free_spinlock(fixtureSpin.lock);
    for (auto &semaphore : fixtureSema) s540Darwin_os_free_semaphore(semaphore.sem);
    expect(s540DarwinLiveObjects() == 0, "original lock tests release all actual Darwin service owners");
    std::printf("{\"format\":1,\"component\":\"rm-lock-cancellation-prospective\","
        "\"checks\":%u,\"failed_assertions\":%u,\"baseline\":%s,"
        "\"actual_cancellation_record\":true,\"actual_darwin_services\":true,"
        "\"abi_validation\":false,\"hardware_execution\":false,\"callout_binding_proved\":false,"
        "\"original_entry_admission\":false}\n", checks, failures, baseline ? "true" : "false");
    return baseline ? (failures ? 0 : 1) : (failures ? 1 : 0);
}
