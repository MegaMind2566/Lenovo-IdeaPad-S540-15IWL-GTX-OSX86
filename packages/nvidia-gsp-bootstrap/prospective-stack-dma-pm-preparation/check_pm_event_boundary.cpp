// SPDX-License-Identifier: MIT
// Genuine PM Protocol and cancellation bodies; only platform facts are fixtures.
#include "S540NvidiaGspPower.hpp"
#include "S540NvidiaGspCommit.h"
#include "S540NvidiaDarwinServices.h"
#include "Participants.h"
#include <cstdio>
#include <cstdlib>

namespace {
NvU64 nowNs = 1000000000ULL;
unsigned checks, failures;
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) {
        ++failures;
        std::fprintf(stderr, "PM event boundary check failed: %s\n", reason);
    }
}
}

extern "C" {
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) { return NV_TRUE; }
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out) {
    if (!out) return NV_ERR_INVALID_ARGUMENT;
    *out = 17;
    return NV_OK;
}
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void) { return nowNs; }
NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *, NvU32, NvU32 *out) {
    if (out) *out = 0;
    return NV_ERR_INVALID_STATE;
}
}

int main(int argc, char **argv) {
    using S540NvidiaGspPower::Detail::Protocol;
    const bool lateHook = argc == 2 && std::atoi(argv[1]) == 1;
    int nv;
    S540GspCancellationToken token = 0;
    S540GspCancellationCommitLease held = 99, refused = 99;
    S540GspCancellationSnapshot cancel{};
    S540GspCancellationCommitSnapshot commit{};
    expect(s540GspCancellationCommitEnterState(&nv, &held) != NV_OK && held == 0,
        "unbound state has no commit authority");
    expect(s540GspCancellationBind(&nv, &token) == NV_OK && token,
        "actual cancellation binding established");
    expect(s540GspCancellationBegin(token) == NV_OK,
        "actual ordinary worker enters operation");

    Protocol power;
    power.requested(); power.setState(true); power.completed();
    expect(power.ready(), "genuine Protocol completes on transition");
    const NvU64 eventNs = nowNs;
    expect(power.setState(false), "genuine Protocol requests stop on down event");
    power.revocationObserved(eventNs);
    auto powerState = power.snapshot();
    expect(powerState.revoked && powerState.acknowledgementPending &&
        !powerState.acknowledgementSent && power.revocationEventNs() == eventNs,
        "actual earlier PM event is retained without acknowledgement");

    // The actual service releases its guard before invoking the stop hook.
    // This controlled scheduling gap is not represented by a caller readiness flag.
    nowNs += lateHook ? 31000000000ULL : 250000000ULL;
    expect(s540GspCancellationCommitEnterState(&nv, &held) == NV_OK && held,
        "cancellation CAS cannot observe an earlier delayed PM hook");
    expect(s540GspCancellationCommitReadState(&nv, &commit) == NV_OK &&
        commit.inFlight && !commit.revoked,
        "accepted endpoint remains visibly in flight before hook publication");
    expect(s540GspCancellationPendingLeases() == 1,
        "pending count includes the actual endpoint reservation");
    expect(s540GspCancellationFinish(token) != NV_OK,
        "held endpoint prevents Finish");
    expect(s540GspCancellationUnbind(token) != NV_OK,
        "held endpoint prevents binding release");
    expect(s540GspCancellationBeginCleanupState(&nv) != NV_OK,
        "held endpoint prevents phase transition");

    expect(s540GspCancellationRevokeAt(token, power.revocationEventNs()) == NV_OK,
        "actual cancellation hook publishes the earlier PM event");
    expect(s540GspCancellationGetSnapshot(token, &cancel) == NV_OK &&
        cancel.revoked && !cancel.publicationInFlight &&
        cancel.revokedAtNs == eventNs && cancel.deadlineNs == eventNs + 30000000000ULL,
        "hook delay does not move the fixed original deadline");
    expect(s540GspCancellationCommitReadState(&nv, &commit) == NV_OK &&
        commit.inFlight && commit.revoked,
        "revocation cannot fabricate completion of accepted endpoint");
    expect(s540GspCancellationCommitEnterState(&nv, &refused) != NV_OK && refused == 0,
        "no new operation commit after actual revocation publication");
    expect(s540GspCancellationCheckCurrent() != NV_OK,
        "actual operation observes cancellation");
    expect(s540GspCancellationFinish(token) != NV_OK,
        "revoked held endpoint still prevents Finish");

    // The endpoint return is explicitly a CPU fixture; no physical action occurs.
    expect(s540GspCancellationCommitLeaveState(&nv, held) == NV_OK,
        "exact accepted endpoint may report its real return after revocation");
    expect(s540GspCancellationCommitReadState(&nv, &commit) == NV_OK &&
        !commit.inFlight && commit.revoked,
        "only endpoint return clears the reservation, never revocation");
    expect(s540GspCancellationBeginCleanupState(&nv) == NV_OK,
        "actual owner enters cleanup only after endpoint completion");
    expect(s540GspCancellationCommitEnterState(&nv, &refused) != NV_OK && refused == 0,
        "operation-only API cannot upgrade into cleanup authority");

    S540GspCancellationCommitLease cleanup = 99;
    if (!lateHook) {
        expect(s540GspCancellationSubmitEnterState(&nv, &cleanup) == NV_OK && cleanup,
            "genuine cleanup transport may commit before fixed deadline");
        nowNs = cancel.deadlineNs + 1;
        expect(s540GspCancellationCommitReadState(&nv, &commit) == NV_OK && commit.inFlight,
            "deadline expiry cannot invent endpoint completion");
        expect(s540GspCancellationCommitLeaveState(&nv, cleanup) == NV_OK,
            "real late cleanup return may release its own reservation");
    } else {
        expect(nowNs > cancel.deadlineNs,
            "late hook schedule has already exhausted the real PM budget");
    }
    cleanup = 99;
    expect(s540GspCancellationSubmitEnterState(&nv, &cleanup) == NV_ERR_TIMEOUT && cleanup == 0,
        "cleanup transport refuses after the original event deadline");
    expect(s540GspCancellationRevokeAt(token, nowNs) == NV_OK &&
        s540GspCancellationGetSnapshot(token, &cancel) == NV_OK &&
        cancel.deadlineNs == eventNs + 30000000000ULL,
        "repeat revocation cannot extend the PM budget");
    powerState = power.snapshot();
    expect(powerState.acknowledgementPending && !powerState.acknowledgementSent,
        "CPU protocol never acknowledges GPU or DMA quiescence");
    expect(s540GspCancellationFinish(token) == NV_OK &&
        s540GspCancellationUnbind(token) == NV_OK,
        "completed CPU cancellation scope may retire without any PM ack");
    std::printf("{\"format\":1,\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"late_hook\":%s,\"pm_event_ns\":%llu,\"fixed_deadline_ns\":%llu,"
        "\"hook_window_closed\":false,\"hardware_stop_proven\":false,\"kernel_execution\":false,\"gpu_access\":false}\n",
        failures ? "failed" : "passed", checks, failures, lateHook ? "true" : "false",
        static_cast<unsigned long long>(eventNs),
        static_cast<unsigned long long>(eventNs + 30000000000ULL));
    return failures ? 1 : 0;
}
