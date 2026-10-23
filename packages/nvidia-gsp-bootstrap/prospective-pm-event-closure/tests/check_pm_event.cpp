// SPDX-License-Identifier: MIT
#include "S540NvidiaGspPower.hpp"
#include "S540NvidiaPowerCoupling.h"
#include "S540NvidiaGspCommit.h"
#include "Participants.h"
#include "nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <initializer_list>
#include <mutex>

static thread_local NvU64 tid = 1;
static thread_local NvBool ordinary = NV_TRUE;
static std::atomic<NvU64> clockNs{100};
static std::atomic<unsigned> checks;
static int state, foreign;
static S540GspCancellationToken token;
static std::atomic<unsigned> hookStage;
static bool blockingHook;
static bool requireRevokedInHook;
static void expect(bool value, const char *message) {
    ++checks;
    if (!value) { std::fprintf(stderr, "PM event control: %s\n", message); std::abort(); }
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out) { *out = tid; return NV_OK; }
extern "C" NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep() { return ordinary; }
extern "C" NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns() { return clockNs.load(); }
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32) { return NV_OK; }
extern "C" NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *, NvU32, NvU32 *) { return NV_ERR_INVALID_STATE; }

static NV_STATUS hook(void *) {
    if (requireRevokedInHook) {
        S540GspCancellationSnapshot snapshot{};
        expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && snapshot.revoked,
            "genuine callback closes cancellation before delayed external hook");
    }
    hookStage.store(1);
    if (blockingHook) while (hookStage.load() == 1) std::this_thread::yield();
    return NV_OK;
}
using S540NvidiaGspPower::Lease;
using S540NvidiaGspPower::Revocation;
using IOReturn = int;
constexpr IOReturn kIOPMAckImplied = 0, kDropDeadlineUs = 30000000;
struct IOService {};
static void IOLockLock(std::mutex *guard) { guard->lock(); }
static void IOLockUnlock(std::mutex *guard) { guard->unlock(); }
static void IOLockWakeup(std::mutex *, void *, bool) {}
struct CallbackFixture : IOService {
    std::mutex mutex;
    std::mutex *guard = &mutex;
    bool closing = false;
    S540NvidiaGspPower::Detail::Protocol protocol;
    Revocation revocation{&state, hook};
    NvU32 revocationHooksInFlight = 0;
    IOReturn setPowerState(unsigned long, IOService *);
};
#include "actual-callback.inc"
static void bind() {
    token = 0;
    expect(s540GspCancellationBind(&state, &token) == NV_OK && token, "real exact identity binding");
}
static void start(Lease &power) {
    expect(power.startNativeForTest({&state, hook}) == NV_OK, "actual native Power lease fixture");
}
static void retire(Lease &power, bool finish = true) {
    if (finish) expect(s540GspCancellationFinish(token) == NV_OK, "finish real returned scope");
    expect(power.releaseCancellation() == NV_OK, "release coupling on owner under Power guard");
    expect(power.acknowledgeRevocation() == NV_OK, "fixture explicit PM ack after test cleanup");
    expect(power.stop() == NV_OK, "actual fixture stop after coupling and hook drain");
    expect(s540GspCancellationUnbind(token) == NV_OK, "generation recyclable only after Power release");
}
int main() {
    {
        bind(); Lease power; start(power);
        expect(power.coupleCancellation(&foreign, token) == NV_ERR_INVALID_STATE, "foreign state cannot acquire Power hold");
        expect(power.coupleCancellation(&state, token) == NV_OK, "Power guard couples exact idle binding");
        expect(s540GspCancellationUnbind(token) == NV_ERR_IN_USE, "Power hold blocks unbind before OP");
        expect(power.stop() == NV_ERR_IN_USE, "coupled PM owner cannot be destroyed");
        expect(power.coupleCancellation(&state, token) == NV_ERR_INVALID_STATE, "coupling cannot overwrite prior owner");
        expect(s540GspCancellationBegin(token) == NV_OK, "real operation begins after coupling");
        expect(power.releaseCancellation() == NV_ERR_IN_USE, "active OP cannot release hold");
        S540GspCancellationCommitLease commit = 0;
        expect(s540GspCancellationCommitEnterState(&state, &commit) == NV_OK && commit, "real producer commit acquired before PM");
        blockingHook = requireRevokedInHook = true; hookStage = 0;
        const auto acceptedCommit = commit;
        NV_STATUS revoke = NV_ERR_INVALID_STATE;
        std::thread callback([&] { tid = 2; revoke = power.revokeNativeForTest(); });
        while (!hookStage.load()) std::this_thread::yield();
        expect(s540GspCancellationCheckCurrent() == NV_ERR_OPERATION_ABORTED,
            "blocked external hook does not delay original cancellation");
        expect(s540GspCancellationCommitEnterState(&state, &commit) != NV_OK,
            "new acceptance refuses after actual callback event");
        S540GspCancellationCommitSnapshot commits{};
        expect(s540GspCancellationCommitReadState(&state, &commits) == NV_OK && commits.inFlight,
            "revocation preserves accepted endpoint reservation");
        hookStage = 2; callback.join();
        expect(revoke == NV_OK, "actual delayed hook completed");
        expect(s540GspCancellationCommitLeaveState(&state, acceptedCommit) == NV_OK, "actual accepted endpoint can leave after PM");
        S540GspCancellationSnapshot snapshot{};
        expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && snapshot.deadlineNs == 30000000100ULL,
            "fixed deadline begins at actual callback event");
        expect(s540GspCancellationRevokeAt(token, 0) == NV_OK, "later invalid event preserves existing revocation");
        expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && snapshot.deadlineNs == 30000000100ULL,
            "later invalid event cannot erase valid first deadline");
        blockingHook = requireRevokedInHook = false;
        retire(power);
    }
    for (NvU64 now : {NvU64(0), NvU64(100)}) {
        clockNs = now; bind(); Lease power; start(power);
        expect(power.coupleCancellation(&state, token) == NV_OK, "new generation couples");
        expect(s540GspCancellationBegin(token) == NV_OK, "new OP begins");
        if (now) {
            // Direct producer exercises clock moving backwards between event
            // capture and closure, without manufacturing a cleanup deadline.
            expect(s540GspCancellationPowerRevokeAtState(&state, token, 101) == NV_ERR_INVALID_ARGUMENT,
                "future event from backward clock still reports failure");
        } else {
            requireRevokedInHook = true;
            expect(power.revokeNativeForTest() == NV_ERR_INVALID_ARGUMENT, "zero clock reports real closure error");
            requireRevokedInHook = false;
        }
        S540GspCancellationSnapshot snapshot{};
        expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && snapshot.revoked && !snapshot.deadlineNs,
            "invalid clock closes OP but grants no cleanup authority");
        expect(s540GspCancellationCheckCurrent() == NV_ERR_OPERATION_ABORTED, "invalid clock cannot leave OP running");
        expect(s540GspCancellationBeginCleanupState(&state) == NV_OK, "real owner changes phase only");
        expect(s540GspCancellationCheckCurrent() == NV_ERR_NOT_READY, "no invented deadline permits cleanup MMIO");
        retire(power);
    }
    {
        clockNs = 200; Lease power; start(power);
        expect(power.revokeNativeForTest() == NV_OK, "actual PM event before cancellation binding");
        bind();
        expect(power.coupleCancellation(&state, token) == NV_ERR_OPERATION_ABORTED,
            "late binding atomically inherits the prior real PM event");
        expect(s540GspCancellationBegin(token) == NV_ERR_OPERATION_ABORTED, "late-bound revoked generation cannot start OP");
        retire(power, false);
    }
    for (NvU64 now : {NvU64(300), NvU64(0)}) {
        clockNs = now; bind(); CallbackFixture service;
        service.protocol.requested(); service.protocol.setState(true); service.protocol.completed();
        expect(service.protocol.coupleCancellation(&state, token) == NV_OK, "actual kernel fixture couples idle generation");
        expect(s540GspCancellationBegin(token) == NV_OK, "kernel callback control begins real OP");
        requireRevokedInHook = true; blockingHook = true; hookStage = 0;
        IOReturn returned = kIOPMAckImplied;
        std::thread callback([&] { tid = 2; returned = service.setPowerState(0, &service); });
        while (!hookStage.load()) std::this_thread::yield();
        expect(s540GspCancellationCheckCurrent() == NV_ERR_OPERATION_ABORTED,
            "exact kernel callback closes OP while external hook is delayed");
        S540GspCancellationSnapshot snapshot{};
        expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK &&
            snapshot.deadlineNs == (now ? 30000000300ULL : 0), "actual callback fixes deadline or retains invalid-clock uncertainty");
        hookStage = 2; callback.join();
        expect(returned == kDropDeadlineUs, "actual PM callback leaves acknowledgement pending");
        expect(!service.protocol.snapshot().acknowledgementSent &&
            service.protocol.snapshot().postFailures == (now ? 0U : 1U),
            "real callback reports invalid-clock closure without false PM acknowledgement");
        expect(s540GspCancellationFinish(token) == NV_OK, "actual callback fixture original scope returns");
        expect(service.protocol.releaseCancellation() == NV_OK, "actual callback fixture releases exact generation after return");
        expect(s540GspCancellationUnbind(token) == NV_OK, "actual callback fixture can retire completed generation");
        requireRevokedInHook = blockingHook = false;
    }
    {
        bind(); Lease power; start(power);
        expect(s540GspCancellationBegin(token) == NV_OK, "uncoupled native control OP");
        expect(power.coupleCancellation(&state, token) == NV_ERR_IN_USE, "cannot couple an already-running OP");
        expect(s540GspCancellationFinish(token) == NV_OK, "finish uncoupled control");
        tid = 2;
        expect(power.coupleCancellation(&state, token) == NV_ERR_INVALID_STATE, "foreign thread cannot couple generation");
        tid = 1;
        expect(power.coupleCancellation(&state, token) == NV_OK, "owner can couple after real return");
        expect(s540GspCancellationPowerRevokeAtState(&foreign, token, 200) == NV_ERR_INVALID_STATE,
            "foreign identity cannot borrow callback coupling");
        expect(s540GspCancellationPowerRevokeAtState(&state, token + 1, 200) == NV_ERR_INVALID_STATE,
            "wrong generation cannot borrow callback coupling");
        retire(power, false);
    }
    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,\"kernel_execution\":\"not_tested\",\"hardware_stop_proven\":false}\n", checks.load());
}
