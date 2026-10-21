/* SPDX-License-Identifier: MIT; actual full cancellation TU, endpoint fixtures. */
#include "Participants.h"
#include "nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include "S540NvidiaGspCommit.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>

static _Thread_local NvU64 tid = 1;
static _Thread_local NvBool ordinary = NV_TRUE;
static _Thread_local NvU32 irqOrigin;
static _Atomic NvU64 now = 100;
static _Atomic unsigned checks, stage;
static int state, foreign;
static S540GspCancellationToken token;
static S540GspCancellationLease callback;
static S540GspCancellationCommitLease transferred;
static NvU32 clockReads, inspectReserved, expireReserved;

static void checkAt(NvBool value, unsigned line) {
    atomic_fetch_add(&checks, 1);
    if (!value) { fprintf(stderr, "commit check failed line %u\n", line); exit(1); }
}
#define check(v) checkAt((v), __LINE__)
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out) { *out = tid; return NV_OK; }
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) { return ordinary; }
NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32 ms) { (void)ms; return NV_OK; }
NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *nv, NvU32 role, NvU32 *origin) {
    if (nv != &state || role < 1 || role > 2) return NV_ERR_INVALID_STATE;
    *origin = role == 1 ? 0 : irqOrigin; return NV_OK;
}
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void) {
    if (inspectReserved && ++clockReads == 2) {
        S540GspCancellationCommitSnapshot observed = {0};
        check(s540GspCancellationCommitReadState(&state, &observed) == NV_OK &&
            observed.inFlight == 1 && observed.origin == 0);
        check(s540GspCancellationPendingLeases() == 1);
        check(s540GspCancellationFinish(token) == NV_ERR_IN_USE);
        check(s540GspCancellationUnbind(token) == NV_ERR_IN_USE);
        check(s540GspCancellationBeginCleanupState(&state) != NV_OK);
        if (expireReserved) atomic_store(&now, 30000000100ULL);
    }
    return atomic_load(&now);
}
static void start(void) {
    inspectReserved = expireReserved = clockReads = 0;
    atomic_store(&now, 100);
    check(s540GspCancellationBind(&state, &token) == NV_OK);
    check(s540GspCancellationBegin(token) == NV_OK);
}
static void finish(void) {
    check(s540GspCancellationPendingLeases() == 0);
    check(s540GspCancellationFinish(token) == NV_OK);
    check(s540GspCancellationUnbind(token) == NV_OK);
}
static void *revoke(void *unused) {
    (void)unused; tid = 9;
    while (atomic_load(&stage) == 0) { }
    check(s540GspCancellationRevokeAt(token, 100) == NV_OK);
    atomic_store(&stage, 2); return NULL;
}
static void *callbackCommit(void *unused) {
    (void)unused; tid = 2;
    check(s540GspCancellationEnterLease(callback, &state) == NV_OK);
    check(s540GspCancellationCommitEnterState(&state, &transferred) == NV_OK);
    atomic_store(&stage, 1);
    while (atomic_load(&stage) == 1) { }
    check(s540GspCancellationCommitLeaveState(&state, transferred) == NV_OK);
    check(s540GspCancellationLeaveLease(callback, &state) == NV_OK);
    return NULL;
}
static void *foreignCaller(void *unused) {
    S540GspCancellationCommitLease lease = 91;
    (void)unused; tid = 3;
    check(s540GspCancellationCommitEnterState(&state, &lease) != NV_OK && !lease);
    check(s540GspCancellationCommitLeaveState(&state, transferred) == NV_ERR_INVALID_STATE);
    return NULL;
}
int main(void) {
    S540GspCancellationCommitLease lease = 44, stale = 0;
    S540GspCancellationCommitSnapshot observed = {0};
    pthread_t worker;
    check(s540GspCancellationCommitEnterState(&state, &lease) != NV_OK && !lease);
    check(s540GspCancellationSubmitEnterState(NULL, &lease) != NV_OK && !lease);
    check(s540GspCancellationCommitReadState(&state, &observed) != NV_OK);
    check(s540GspCancellationCommitLeaveState(&state, 4) != NV_OK);
    check(s540GspCancellationBind(&state, &token) == NV_OK);
    check(s540GspCancellationCommitEnterState(&state, &lease) != NV_OK && !lease);
    check(s540GspCancellationBegin(token) == NV_OK);
    check(s540GspCancellationCommitEnterState(&foreign, &lease) != NV_OK && !lease);
    check(s540GspCancellationCommitEnterState(&state, NULL) != NV_OK);
    check(s540GspCancellationCommitEnterState(&state, &lease) == NV_OK && lease);
    stale = lease;
    check(s540GspCancellationCommitReadState(&state, &observed) == NV_OK && observed.inFlight && observed.origin == 2);
    check(s540GspCancellationPendingLeases() == 1);
    check(s540GspCancellationFinish(token) == NV_ERR_IN_USE);
    check(s540GspCancellationUnbind(token) == NV_ERR_IN_USE);
    check(s540GspCancellationBeginCleanupState(&state) != NV_OK);
    { S540GspCancellationCommitLease nested = 8;
      check(s540GspCancellationCommitEnterState(&state, &nested) != NV_OK && !nested); }
    check(s540GspCancellationCommitLeaveState(&foreign, lease) != NV_OK);
    check(s540GspCancellationCommitLeaveState(&state, lease + 1) != NV_OK);
    check(s540GspCancellationCommitLeaveState(&state, lease) == NV_OK);
    check(s540GspCancellationCommitLeaveState(&state, lease) != NV_OK);
    check(s540GspCancellationCommitReadState(&state, &observed) == NV_OK && !observed.inFlight);
    finish();

    /* Genuine enrolled callback identity, no identity/readiness fixture. */
    start(); atomic_store(&stage, 0);
    check(s540GspCancellationCaptureCurrent(&state, &callback) == NV_OK);
    check(!pthread_create(&worker, NULL, callbackCommit, NULL));
    while (!atomic_load(&stage)) { }
    check(s540GspCancellationCommitLeaveState(&state, transferred) == NV_ERR_INVALID_STATE);
    { pthread_t other; check(!pthread_create(&other, NULL, foreignCaller, NULL)); check(!pthread_join(other, NULL)); }
    check(s540GspCancellationRevokeAt(token, 100) == NV_OK);
    check(s540GspCancellationCommitReadState(&state, &observed) == NV_OK && observed.inFlight && observed.revoked);
    check(s540GspCancellationFinish(token) == NV_ERR_IN_USE);
    atomic_store(&stage, 2); check(!pthread_join(worker, NULL));
    check(s540GspCancellationCommitEnterState(&state, &lease) == NV_ERR_OPERATION_ABORTED && !lease);
    check(s540GspCancellationBeginCleanupState(&state) == NV_OK);
    check(s540GspCancellationCommitEnterState(&state, &lease) != NV_OK && !lease);
    check(s540GspCancellationSubmitEnterState(&state, &lease) == NV_OK && lease != stale);
    check(s540GspCancellationCommitLeaveState(&state, stale) != NV_OK);
    /* Deadline expiry cannot fabricate completion of accepted endpoint work. */
    atomic_store(&now, 30000000100ULL);
    check(s540GspCancellationCommitReadState(&state, &observed) == NV_OK && observed.inFlight);
    check(s540GspCancellationCommitLeaveState(&state, lease) == NV_OK);
    check(s540GspCancellationSubmitEnterState(&state, &lease) == NV_ERR_TIMEOUT && !lease);
    finish();

    /* The post-CAS clock callback observes busy before payload publication. */
    start(); check(s540GspCancellationRevokeAt(token, 100) == NV_OK);
    check(s540GspCancellationBeginCleanupState(&state) == NV_OK);
    inspectReserved = expireReserved = 1; clockReads = 0;
    check(s540GspCancellationSubmitEnterState(&state, &lease) == NV_ERR_TIMEOUT && !lease);
    inspectReserved = 0;
    check(s540GspCancellationCommitReadState(&state, &observed) == NV_OK && !observed.inFlight);
    finish();

    /* Hard IRQ inherits the actual operation; nested busy admission refuses. */
    start(); ordinary = NV_FALSE;
    check(s540GspCancellationEnterIrqScope(&state, 1, 0) == NV_OK);
    check(s540GspCancellationCommitEnterState(&state, &lease) == NV_OK);
    check(s540GspCancellationRevokeAt(token, 100) == NV_OK);
    check(s540GspCancellationCommitLeaveState(&state, lease) == NV_OK);
    check(s540GspCancellationLeaveIrqScope(&state, 1) == NV_OK);
    ordinary = NV_TRUE; finish();

    /* Real pthread revocation races with a real shared-word reservation. */
    for (unsigned i = 0; i != 48; ++i) {
        NV_STATUS accepted;
        start(); atomic_store(&stage, 0);
        check(!pthread_create(&worker, NULL, revoke, NULL));
        atomic_store(&stage, 1);
        accepted = s540GspCancellationCommitEnterState(&state, &lease);
        if (accepted == NV_OK) {
            while (atomic_load(&stage) != 2) { }
            check(s540GspCancellationCommitReadState(&state, &observed) == NV_OK && observed.inFlight && observed.revoked);
            check(s540GspCancellationCommitLeaveState(&state, lease) == NV_OK);
        } else check(!lease);
        check(!pthread_join(worker, NULL));
        check(s540GspCancellationCommitEnterState(&state, &lease) == NV_ERR_OPERATION_ABORTED && !lease);
        finish();
    }
    printf("{\"status\":\"passed\",\"checks\":%u,\"genuine_cancellation_translation_unit\":true,\"clock_thread_and_irq_record_endpoints_fixture\":true,\"pm_30_second_shutdown_bound_proven\":false}\n", atomic_load(&checks));
    return 0;
}
