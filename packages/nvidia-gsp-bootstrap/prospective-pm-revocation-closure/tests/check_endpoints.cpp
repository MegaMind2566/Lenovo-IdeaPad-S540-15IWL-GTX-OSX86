// SPDX-License-Identifier: MIT
#include "MockIOKit.hpp"
#include "S540NvidiaDeviceTransport.hpp"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaPublicCallout.hpp"
#include "S540NvidiaGspIrqIdentity.h"
#include "S540NvidiaGspCommit.h"
#include "S540NvidiaDarwinServices.h"
#include <cstdio>
#include <cstdlib>
#include <mutex>
using namespace S540NvidiaDeviceTransport;
class IOService : public OSObject {};
class IOMemoryMap : public OSObject {};
class IOMapper : public OSObject {};
class IOPlatformExpert : public OSObject {};
class IODMACommand : public OSObject {};
using IOSimpleLock = std::mutex;
typedef int nv_state_t; // Opaque exact state identity; no NVIDIA member is read.
static nv_state_t exactNv, otherNv;
static S540GspCancellationToken token;
static NvU64 currentTid = 71, nowNs = 100;
static unsigned checks, enables, timerArms;
static bool readyRevoke, endpointRevoke, wrongReturnThread;
static NV_STATUS timerStatus = NV_OK, armAuthority = NV_OK;
static bool liveState = true;
static void requireAt(bool value, unsigned line) {
    ++checks; if (!value) { std::fprintf(stderr, "endpoint check failed line %u\n", line); std::exit(1); }
}
#define require(v) requireAt((v), __LINE__)
extern "C" NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out) { *out = currentTid; return NV_OK; }
extern "C" NvBool s540Darwin_os_semaphore_may_sleep() { return NV_TRUE; }
extern "C" NvU64 s540Darwin_os_get_monotonic_time_ns() { return nowNs; }
extern "C" NV_STATUS s540Darwin_os_delay(NvU32) { return NV_OK; }
extern "C" NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *, NvU32, NvU32 *) { return NV_ERR_INVALID_STATE; }
static void actualEndpoint() {
    S540GspCancellationCommitSnapshot observed{};
    require(s540GspCancellationCommitReadState(&exactNv, &observed) == NV_OK && observed.inFlight);
    require(s540GspCancellationPendingLeases() == 1);
    require(s540GspCancellationFinish(token) == NV_ERR_IN_USE);
    if (endpointRevoke) {
        require(s540GspCancellationRevokeAt(token, 100) == NV_OK);
        require(s540GspCancellationCommitReadState(&exactNv, &observed) == NV_OK && observed.inFlight && observed.revoked);
    }
    if (wrongReturnThread) currentTid = 72;
}
class IOPCIDevice : public IOService {
public:
    bool enabled = false, failEnable = false;
    IOReturn enableInterrupt(int index) {
        require(index == 0); ++enables; enabled = true; actualEndpoint();
        return failEnable ? kIOReturnError : kIOReturnSuccess;
    }
};
static bool live(void *) { return liveState; }
extern "C" NV_STATUS s540FirstTxnIrqCheckArm(const void *) { return armAuthority; }
static bool ready(void *) {
    if (readyRevoke) require(s540GspCancellationRevokeAt(token, 100) == NV_OK);
    return true;
}
extern "C" NV_STATUS s540DarwinTimerArm(S540DarwinTimer *timer, NvU64 delay) {
    require(timer == reinterpret_cast<S540DarwinTimer *>(&exactNv) && delay == 19);
    ++timerArms; actualEndpoint(); return timerStatus;
}
#include "actual-platform.inc"
#include "actual-arm.inc"
#include "actual-timer-arm.inc"

static void start() {
    currentTid = 71; nowNs = 100;
    readyRevoke = endpointRevoke = wrongReturnThread = false;
    timerStatus = armAuthority = NV_OK; liveState = true;
    require(s540GspCancellationBind(&exactNv, &token) == NV_OK);
    require(s540GspCancellationBegin(token) == NV_OK);
}
static void finish() {
    S540GspCancellationCommitSnapshot observed{};
    require(s540GspCancellationCommitReadState(&exactNv, &observed) == NV_OK && !observed.inFlight);
    require(s540GspCancellationFinish(token) == NV_OK);
    require(s540GspCancellationUnbind(token) == NV_OK);
}
static Platform platform(IOPCIDevice *provider) {
    Platform p{}; p.provider = provider; p.controllerAttached = p.irqRegistered = true;
    p.interrupt.readyToArm = ready; p.interrupt.originalState = &exactNv; return p;
}
int main(int argc, char **argv) {
    IOPCIDevice provider;
    S540DarwinTimer *timer = reinterpret_cast<S540DarwinTimer *>(&exactNv);
    if (argc > 1) {
        start(); Platform p = platform(&provider); wrongReturnThread = true;
        provider.failEnable = argv[1][0] == '2';
        const NV_STATUS expected = provider.failEnable ? NV_STATUS(NV_ERR_OPERATING_SYSTEM) : NV_STATUS(NV_ERR_INVALID_STATE);
        require(armInterrupt(&p) == expected && enables == 1 && !p.accepting);
        require(provider.enabled && p.controllerEnableAttempted && p.hardwareMaskRequired);
        require(p.irqEnabled == !provider.failEnable);
        currentTid = 71; S540GspCancellationCommitSnapshot held{};
        require(s540GspCancellationCommitReadState(&exactNv, &held) == NV_OK && held.inFlight);
        require(s540GspCancellationFinish(token) == NV_ERR_IN_USE);
        std::printf("{\"status\":\"passed\",\"checks\":%u,\"actual_irq_enable_body\":true,\"software_ingress_closed_on_failed_leave\":true,\"hardware_enable_obligation_retained\":true,\"pm_30_second_shutdown_bound_proven\":false}\n", checks);
        return 0;
    }
    start(); Platform p = platform(&provider);
    armAuthority = NV_ERR_NOT_READY;
    require(armInterrupt(&p) != NV_OK && enables == 0 && !p.controllerEnableAttempted);
    armAuthority = NV_OK; p.interrupt.originalState = &otherNv;
    require(armInterrupt(&p) != NV_OK && enables == 0 && !p.controllerEnableAttempted);
    p.interrupt.originalState = &exactNv; readyRevoke = true;
    require(armInterrupt(&p) == NV_ERR_OPERATION_ABORTED && enables == 0 && !p.hardwareMaskRequired);
    require(s540PmTimerArm(&exactNv, timer, 19) == NV_ERR_OPERATION_ABORTED && !timerArms);
    finish();

    start(); p = platform(&provider); endpointRevoke = true;
    require(armInterrupt(&p) == NV_OK && enables == 1 && p.irqEnabled && p.hardwareMaskRequired);
    require(armInterrupt(&p) == NV_ERR_OPERATION_ABORTED && enables == 1);
    finish();

    start(); p = platform(&provider); provider.failEnable = true;
    require(armInterrupt(&p) == NV_ERR_OPERATING_SYSTEM && enables == 2 && !p.accepting && p.hardwareMaskRequired);
    provider.failEnable = false; finish();

    start(); endpointRevoke = true;
    require(s540PmTimerArm(&exactNv, timer, 19) == NV_OK && timerArms == 1);
    require(s540PmTimerArm(&exactNv, timer, 19) == NV_ERR_OPERATION_ABORTED && timerArms == 1);
    finish();

    start(); timerStatus = NV_ERR_OPERATING_SYSTEM;
    require(s540PmTimerArm(&exactNv, timer, 19) == NV_ERR_OPERATING_SYSTEM && timerArms == 2);
    finish();

    start(); require(s540GspCancellationBeginCleanupState(&exactNv) == NV_OK);
    require(s540PmTimerArm(&exactNv, timer, 19) != NV_OK && timerArms == 2);
    p = platform(&provider); require(armInterrupt(&p) != NV_OK && enables == 2);
    finish();

    // A deliberately wrong endpoint-return thread cannot release the token.
    // Preserve the real endpoint error and the actual outstanding obligation.
    start(); wrongReturnThread = true; timerStatus = NV_ERR_OPERATING_SYSTEM;
    require(s540PmTimerArm(&exactNv, timer, 19) == NV_ERR_OPERATING_SYSTEM && timerArms == 3);
    currentTid = 71;
    S540GspCancellationCommitSnapshot observed{};
    require(s540GspCancellationCommitReadState(&exactNv, &observed) == NV_OK && observed.inFlight);
    require(s540GspCancellationFinish(token) == NV_ERR_IN_USE);
    std::printf("{\"status\":\"passed\",\"checks\":%u,\"actual_timer_and_irq_arm_bodies\":true,\"provider_and_record_authority_endpoints_fixture\":true,\"real_cancellation_record\":true,\"retained_failed_leave\":true,\"pm_30_second_shutdown_bound_proven\":false}\n", checks);
    return 0;
}
