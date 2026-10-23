// SPDX-License-Identifier: MIT
// Real retained Owner stop/diagnostic bodies and whole Services TU. Only
// original hardware/lock/queue endpoints below are explicit fault seams.
#include "S540NvidiaRetainedStop.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaFirstTxnServices.h"
#include "S540NvidiaGspContext.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
static unsigned checks;
static void expect(bool value, const char *message) {
    ++checks; if (!value) { std::fprintf(stderr, "retained-stop control: %s\n", message); std::abort(); }
}
struct S540GspContext { unsigned fixture; } contextStorage;
static int deviceQueue, globalQueue;
static unsigned scenario, protocolCalls, closingCalls, timerCalls, queueSeals, queueStops, disableCalls, irqCalls, shutdownCalls;
static bool protocolDone, closingDone, disableDone;
static S540FirstTxnSnapshot record;
static S540GspContextSnapshot contextFacts;
static std::vector<unsigned> ordering;
static bool lockHeld() { return (scenario == 12 && protocolDone) || (scenario == 13 && disableDone); }
extern "C" NvBool s540Darwin_os_semaphore_may_sleep(void) { return NV_TRUE; }
extern "C" NV_STATUS s540FirstTxnOriginalLocksReleased(const void *nv) {
    expect(nv == &contextStorage, "actual exact identity lock observation");
    return scenario == 11 || lockHeld() ? NV_ERR_INVALID_LOCK_STATE : NV_OK;
}
extern "C" NV_STATUS s540FirstTxnGetSnapshot(const void *nv, S540FirstTxnSnapshot *out) {
    expect(nv == &contextStorage, "record identity cannot drift"); *out = record;
    return scenario == 7 ? NV_ERR_BUSY_RETRY : NV_OK;
}
extern "C" void *s540GspContextState(S540GspContext *context) { return context; }
extern "C" void *s540GspContextMainStack(S540GspContext *context) { return context; }
extern "C" void s540GspContextSnapshot(S540GspContext *context, S540GspContextSnapshot *out) {
    expect(context == &contextStorage, "context snapshot exact identity"); *out = contextFacts;
}
extern "C" NV_STATUS s540RetainedShutdownRun(void *stack, void *nv, S540RetainedShutdownResult *out) {
    expect(stack == &contextStorage && nv == &contextStorage && !closingDone,
        "genuine protocol boundary before record closing and seal");
    ++protocolCalls; protocolDone = true; ordering.push_back(1);
    *out = {}; out->format = 1; out->bytes = sizeof(*out); out->generation = 19;
    out->claimed = out->originalEntered = out->originalReturned = NV_TRUE;
    out->protocolCompleted = scenario != 1 && scenario != 2 && scenario != 3;
    out->operationStatus = out->originalReturnStatus = scenario == 1 ? NV_ERR_TIMEOUT :
        scenario == 2 ? NV_ERR_NOT_READY : scenario == 3 ? NV_ERR_IN_USE : NV_OK;
    return out->operationStatus;
}
extern "C" NV_STATUS s540FirstTxnBeginClosing(const void *nv) {
    expect(nv == &contextStorage && protocolDone && !lockHeld(), "closing after protocol and real lock recheck");
    ++closingCalls; closingDone = true; ordering.push_back(2);
    return scenario == 4 ? NV_ERR_IN_USE : NV_OK;
}
extern "C" NV_STATUS s540FirstTxnSeal(const void *nv) {
    expect(nv == &contextStorage && timerCalls && queueStops == 2 && !lockHeld(),
        "seal only after actual independent CPU stop attempts");
    ordering.push_back(11); return scenario == 5 ? NV_ERR_NOT_READY : NV_OK;
}
extern "C" NV_STATUS s540GspContextDisableAdapter(S540GspContext *context) {
    expect(context == &contextStorage && !lockHeld(), "never enter disable with unknown retained locks");
    ++disableCalls; disableDone = true; ordering.push_back(12);
    const NV_STATUS status = scenario == 14 ? NV_ERR_NOT_SUPPORTED : NV_OK;
    if (status == NV_OK) contextFacts.adapterDisabled = NV_TRUE;
    return status;
}
extern "C" NV_STATUS s540GspContextShutdownAdapter(S540GspContext *context, NvBool irq) {
    expect(context == &contextStorage && !lockHeld() && irqCalls,
        "shutdown follows actual IRQ attempt and refreshed locks");
    ++shutdownCalls; ordering.push_back(14);
    if (!irq || !contextFacts.adapterDisabled) return NV_ERR_INVALID_STATE;
    return scenario == 16 ? NV_ERR_TIMEOUT : NV_OK;
}
extern "C" NV_STATUS s540FirstTxnQueueBind(struct os_work_queue *, const void *, NvU64) { return NV_OK; }
extern "C" NV_STATUS s540FirstTxnTimersBind(const void *, NvU64) { return NV_OK; }
extern "C" NV_STATUS s540GspTimersStop(struct nv_state_t *nv) {
    expect(nv == reinterpret_cast<struct nv_state_t *>(&contextStorage) && closingDone && !lockHeld(),
        "actual Services stops timers after authority");
    ++timerCalls; ordering.push_back(3); return scenario == 6 ? NV_ERR_TIMEOUT : NV_OK;
}
extern "C" NV_STATUS s540FirstTxnQueueSeal(struct os_work_queue *queue, const void *, NvU64) {
    expect(timerCalls && !lockHeld(), "independent queue seal after timer attempt"); ++queueSeals;
    const bool device = queue == reinterpret_cast<struct os_work_queue *>(&deviceQueue);
    ordering.push_back(device ? 4 : 5);
    return scenario == 17 && device ? NV_ERR_IN_USE : NV_OK;
}
extern "C" NV_STATUS s540DarwinWorkQueueStop(struct os_work_queue *queue) {
    expect(queueSeals == 2 && !lockHeld(), "CPU join after all queue seal attempts"); ++queueStops;
    const bool device = queue == reinterpret_cast<struct os_work_queue *>(&deviceQueue);
    ordering.push_back(device ? 6 : 7);
    return scenario == 18 && device ? NV_ERR_TIMEOUT : NV_OK;
}
extern "C" NV_STATUS s540FirstTxnQueueValidateStopped(struct os_work_queue *queue, const void *, NvU64) {
    const bool device = queue == reinterpret_cast<struct os_work_queue *>(&deviceQueue);
    ordering.push_back(device ? 8 : 9); return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnTimersValidateStopped(const void *, NvU64) { ordering.push_back(10); return NV_OK; }
struct IrqFacts { bool installationAttempted = true; NV_STATUS softwareDrainStatus = NV_ERR_NOT_READY, fullDrainStatus = NV_ERR_NOT_READY; };
struct IrqFixture {
    IrqFacts facts;
    IrqFacts snapshot() const { return facts; }
    NV_STATUS quiesce() {
        expect(!lockHeld(), "never block IRQ join while original locks may remain held");
        ++irqCalls; ordering.push_back(13); facts.softwareDrainStatus = NV_OK;
        facts.fullDrainStatus = scenario == 15 ? NV_ERR_NOT_READY : NV_OK;
        return facts.fullDrainStatus;
    }
};
struct Fixture {
    mutable NvU32 retainedStopGuard = 0;
    NvU32 retainedStopAttempts = 0;
    S540RetainedStopSnapshot retainedStopPublished{};
    S540GspContext *context = &contextStorage;
    NvU64 thread = 44;
    bool diagnosticLifetimeHeld = true;
    struct { bool hardwareDmaLifetimeHeld() const { return true; } } transport;
    IrqFixture irqBinding;
    struct { bool cleanupComplete = false, prepared = true, quarantined = false; NV_STATUS cleanupStatus = NV_OK; } state;
#include "actual-owner-stop.inc"
#include "actual-retained-dispatch.inc"
};
int main() {
    expect(s540FirstTxnServicesBind(&contextStorage, 19,
        reinterpret_cast<struct os_work_queue *>(&deviceQueue),
        reinterpret_cast<struct os_work_queue *>(&globalQueue)) == NV_OK, "real immutable Services binding");
    for (scenario = 0; scenario < 21; ++scenario) {
        protocolCalls = closingCalls = timerCalls = queueSeals = queueStops = disableCalls = irqCalls = shutdownCalls = 0;
        protocolDone = closingDone = disableDone = false; ordering.clear();
        record = {}; record.generation = 19; record.masterThread = 44;
        record.originalReturned = record.originalExitReady = NV_TRUE;
        contextFacts = {}; contextFacts.adapterInitialized = NV_TRUE;
        if (scenario == 8) record.originalInFlight = NV_TRUE;
        if (scenario == 9) record.originalReturned = NV_FALSE;
        if (scenario == 10) record.originalExitReady = NV_FALSE;
        if (scenario == 19) record.inFlightFreePermits = 1;
        if (scenario == 20) record.masterThread = 45;
        Fixture fixture;
        auto empty = fixture.readRetainedStop();
        expect(empty.format == 1 && empty.snapshotStatus == NV_ERR_NOT_READY, "unpublished diagnostics are not release authority");
        const NV_STATUS returned = fixture.stop();
        const auto out = fixture.readRetainedStop();
        expect(out.format == 1 && out.requested && out.retained && out.attempts == 1,
            "actual retained branch attempts stop rather than returning old IN_USE immediately");
        expect(out.status == returned && fixture.state.cleanupStatus == returned && fixture.state.quarantined,
            "truthful status and retained state publication");
        expect(!out.cleanupComplete && !out.physicalReleaseAuthorized && !out.pmAcknowledgementSent,
            "even successful stop endpoints grant no cleanup, release or PM acknowledgement");
        const bool noAuthority = scenario == 7 || scenario == 8 || scenario == 9 || scenario == 10 || scenario == 11 || scenario == 19 || scenario == 20;
        if (noAuthority) {
            expect(!protocolCalls && !timerCalls && !irqCalls && !disableCalls && !shutdownCalls,
                "missing real return/lock identity excludes hardware calls and blocking joins");
        } else if (scenario == 12) {
            expect(protocolCalls == 1 && !timerCalls && !irqCalls && !disableCalls && !shutdownCalls,
                "post-protocol lock failure excludes every later join or hardware stage");
        } else {
            expect(protocolCalls == 1 && closingCalls == 1 && timerCalls == 1 && queueSeals == 2 && queueStops == 2,
                "real protocol then every independent CPU producer attempted despite first failure");
            expect(ordering.size() >= 11 && ordering[0] == 1 && ordering[1] == 2 && ordering[2] == 3,
                "real original shutdown precedes closing, timer and queue seal");
            expect(disableCalls == 1, "checked disable attempted after CPU drains");
            if (scenario == 13) expect(!irqCalls && !shutdownCalls, "failed post-disable lock observation excludes IRQ joins");
            else expect(irqCalls == 1 && shutdownCalls == 1, "independent checked IRQ/shutdown attempts still made after failures");
            if (scenario == 1) expect(out.firstError == NV_ERR_TIMEOUT && out.servicesAttempted,
                "expired cleanup preserves first failure but still joins safe CPU work");
            if (scenario == 2) expect(out.firstError == NV_ERR_NOT_READY && out.servicesAttempted,
                "invalid cleanup clock does not skip independent CPU stops");
            if (scenario == 3) expect(out.firstError == NV_ERR_IN_USE && out.servicesAttempted,
                "in-flight commit refusal does not skip safe CPU stops");
            if (scenario == 6) expect(out.servicesStatus == NV_ERR_TIMEOUT && queueStops == 2,
                "timer cancellation failure does not skip either real queue stop");
            if (scenario == 15) expect(out.interruptSoftwareDrained && !out.interruptFullyDrained,
                "software drain is distinct from refused hardware mask");
            if (scenario == 14) expect(out.disableStatus == NV_ERR_NOT_SUPPORTED &&
                out.firstError == NV_ERR_NOT_SUPPORTED && out.shutdownStatus == NV_ERR_INVALID_STATE,
                "checked disable refusal remains distinct and cannot fabricate shutdown completion");
            if (scenario == 16) expect(out.shutdownStatus == NV_ERR_TIMEOUT && out.firstError == NV_ERR_TIMEOUT,
                "checked shutdown failure survives every diagnostic publication");
            if (scenario == 17) expect(out.servicesStatus == NV_ERR_IN_USE && queueStops == 2,
                "first queue seal failure still attempts both independent queue joins");
            if (scenario == 18) expect(out.servicesStatus == NV_ERR_TIMEOUT && queueStops == 2,
                "first queue stop failure still attempts the second independent queue join");
            if (scenario == 0) expect(out.status == NV_ERR_IN_USE && out.firstError == NV_OK,
                "successful endpoints still retain backing and module until reboot");
        }
        fixture.retainedStopGuard = 1;
        expect(fixture.readRetainedStop().snapshotStatus == NV_ERR_BUSY_RETRY,
            "diagnostic contention returns explicitly without waiting or zero authority");
        fixture.retainedStopGuard = 0;
    }
    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,\"scenarios\":21,\"hardware_executed\":false}\n", checks);
}
