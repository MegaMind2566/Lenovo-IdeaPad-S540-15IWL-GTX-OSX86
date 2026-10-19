// SPDX-License-Identifier: MIT
#include "S540NvidiaGspCancellation.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>
namespace {
unsigned checks;
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { std::fprintf(stderr, "Cancellation: %s\n", reason); std::abort(); }
}
}
int main() {
    int state = 0, foreign = 0;
    S540GspCancellationToken token = 71;
    S540GspCancellationSnapshot snapshot{};
    expect(s540GspCancellationBind(nullptr, &token) == NV_ERR_INVALID_ARGUMENT && token == 71,
        "failed bind preserves output");
    expect(s540GspCancellationBind(&state, nullptr) == NV_ERR_INVALID_ARGUMENT,
        "bind requires token storage");
    expect(s540GspCancellationBind(&state, &token) == NV_OK && token,
        "exact identity binds on ordinary owner");
    S540GspCancellationToken other = 29;
    expect(s540GspCancellationBind(&foreign, &other) == NV_ERR_IN_USE && other == 29,
        "second binding cannot replace first");
    expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && snapshot.bound &&
        !snapshot.revoked && snapshot.phase == S540_GSP_CANCEL_IDLE,
        "binding does not fabricate operation or revocation");
    expect(s540GspCancellationCheckState(&state) == NV_OK,
        "idle identity has no operation to cancel");
    expect(!s540GspCancellationCurrentScopeActive() &&
        s540GspCancellationPauseCurrent() == NV_ERR_INVALID_STATE,
        "idle owner cannot start a lock-wait pause");
    expect(s540GspCancellationBegin(token) == NV_OK, "owner begins original operation");
    expect(s540GspCancellationCurrentScopeActive() && s540GspCancellationCheckCurrent() == NV_OK,
        "current-scope query derives active bound worker identity");
    expect(s540GspCancellationRevokeAt(token,
        s540Darwin_os_get_monotonic_time_ns() + 30000000000ULL) == NV_ERR_INVALID_ARGUMENT &&
        s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && !snapshot.revoked,
        "future event cannot manufacture a later PM deadline");
    expect(s540GspCancellationBegin(token) == NV_ERR_IN_USE, "nested operation refused");
    expect(s540GspCancellationUnbind(token) == NV_ERR_IN_USE,
        "active operation retains binding");
    NV_STATUS foreignBegin = NV_OK, foreignFinish = NV_OK, foreignUnbind = NV_OK;
    bool foreignScope = true;
    std::thread wrongOwner([&] {
        foreignBegin = s540GspCancellationBegin(token);
        foreignFinish = s540GspCancellationFinish(token);
        foreignUnbind = s540GspCancellationUnbind(token);
        foreignScope = s540GspCancellationCurrentScopeActive();
    });
    wrongOwner.join();
    expect(foreignBegin == NV_ERR_INVALID_STATE && foreignFinish == NV_ERR_INVALID_STATE &&
        foreignUnbind == NV_ERR_INVALID_STATE, "foreign thread cannot mutate operation ownership");
    expect(!foreignScope, "callout thread cannot borrow the operation worker's lock scope");
    std::atomic<unsigned> failures{0};
    std::vector<std::thread> producers;
    for (unsigned n = 0; n != 16; ++n) producers.emplace_back([&] {
        if (s540GspCancellationRevoke(token) != NV_OK) ++failures;
    });
    NV_STATUS observed;
    do { observed = s540GspCancellationCheckState(&state); } while (observed == NV_OK);
    expect(observed == NV_ERR_OPERATION_ABORTED,
        "active exact original operation observes revocation before producer join");
    expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && snapshot.revoked &&
        !snapshot.publicationInFlight && snapshot.revokedAtNs &&
        snapshot.deadlineNs - snapshot.revokedAtNs == 30000000000ULL,
        "first real monotonic revocation publishes fixed thirty-second deadline");
    const auto revokedAt = snapshot.revokedAtNs;
    expect(s540GspCancellationRevoke(token) == NV_OK &&
        s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK &&
        snapshot.revokedAtNs == revokedAt, "repeat revocation cannot extend deadline");
    expect(s540GspCancellationCheckCurrent() == NV_ERR_OPERATION_ABORTED &&
        s540GspCancellationPauseCurrent() == NV_ERR_OPERATION_ABORTED,
        "cancellable lock pause returns before sleeping after revocation");
    S540NvidiaDarwinServicesNative::setContext(false, false);
    const NV_STATUS disabledCheck = s540GspCancellationCheckCurrent();
    const NV_STATUS disabledPause = s540GspCancellationPauseCurrent();
    S540NvidiaDarwinServicesNative::setContext(false, true);
    expect(disabledCheck == NV_ERR_OPERATION_ABORTED && disabledPause == NV_ERR_INVALID_STATE,
        "atomic check remains valid with CPU interrupts disabled while pause is refused");
    expect(s540GspCancellationCheckState(&foreign) == NV_OK,
        "foreign identity receives no fabricated cancellation state");
    expect(s540GspCancellationBeginCleanupState(&foreign) == NV_ERR_INVALID_STATE,
        "foreign identity cannot enter retained cleanup");
    expect(s540GspCancellationBeginCleanupState(&state) == NV_OK,
        "actual unwind explicitly changes operation phase");
    expect(s540GspCancellationCheckState(&state) == NV_OK,
        "immediate unwind sees complete deadline before revocation producers join");
    for (auto &producer : producers) producer.join();
    expect(!failures, "concurrent asynchronous revocations accepted without RM locks");
    expect(s540GspCancellationPauseCurrent() == NV_OK,
        "cleanup lock retry performs a real ordinary-thread pause within its deadline");
    expect(s540GspCancellationUnbind(token) == NV_ERR_IN_USE,
        "cleanup phase retains exact binding");
    expect(s540GspCancellationFinish(token) == NV_OK, "owner records original call completion");
    expect(s540GspCancellationBegin(token) == NV_ERR_OPERATION_ABORTED,
        "completed call cannot resurrect a revoked session");
    expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK &&
        snapshot.operationAborts == 4 && snapshot.cleanupExpirations == 0,
        "operation refusal and cleanup expiry are distinct observations");
    expect(s540GspCancellationUnbind(token) == NV_OK, "quiescent owner removes binding");
    expect(s540GspCancellationRevoke(token) == NV_ERR_INVALID_STATE,
        "detached generation refuses late revocation");
    const auto previous = token;
    const NvU64 earlierEvent = s540Darwin_os_get_monotonic_time_ns();
    expect(s540GspCancellationBind(&state, &token) == NV_OK && token > previous,
        "reused state address receives a new generation");
    expect(s540GspCancellationRevoke(previous) == NV_ERR_INVALID_STATE,
        "stale producer cannot revoke a later session");
    expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK && !snapshot.revoked,
        "later binding retains independent revocation state");
    expect(s540GspCancellationRevokeAt(token, earlierEvent) == NV_OK &&
        s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK &&
        snapshot.revokedAtNs == earlierEvent && snapshot.deadlineNs == earlierEvent + 30000000000ULL,
        "event preceding a binding keeps its original absolute deadline");
    expect(s540GspCancellationRevoke(token) == NV_OK &&
        s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK &&
        snapshot.deadlineNs == earlierEvent + 30000000000ULL,
        "later publication cannot restart an earlier event's budget");
    expect(s540GspCancellationUnbind(token) == NV_OK, "final idle binding released");
    expect(!s540DarwinLiveObjects(), "fixed record creates no leaked service owners");
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-cancellation\",\"status\":\"passed\","
        "\"checks\":%u,\"failures\":0,\"execution\":\"native-user-space\","
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
        "\"concurrent_revocation_producers\":16,\"deadline_extension_refused\":true,"
        "\"cleanup_phase_distinct\":true,\"original_entry_admission\":false}\n", checks);
}
