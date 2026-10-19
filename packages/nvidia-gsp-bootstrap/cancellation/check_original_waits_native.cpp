// SPDX-License-Identifier: MIT
#include "S540NvidiaGspCancellation.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <cstdio>
#include <cstdlib>
#include <thread>
extern "C" {
void *s540CancellationWaitFixtureState();
void s540CancellationWaitFixtureReset(NvU32);
NvU32 s540CancellationWaitFixtureReads();
NV_STATUS s540CancellationWaitFixtureRun(NvU32);
}
namespace {
unsigned checks;
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { std::fprintf(stderr, "Original cancellation wait: %s\n", reason); std::abort(); }
}
}
int main() {
    void *state = s540CancellationWaitFixtureState();
    NvU64 maximumObservedNs = 0;
    for (NvU32 kind = 0; kind != 4; ++kind) {
        S540GspCancellationToken token = 0;
        expect(s540GspCancellationBind(state, &token) == NV_OK &&
            s540GspCancellationBegin(token) == NV_OK, "real original wait owner bound");
        s540CancellationWaitFixtureReset(3);
        expect(s540CancellationWaitFixtureRun(kind) == NV_OK,
            "uncancelled actual source body observes its real condition fixture");
        expect(s540GspCancellationFinish(token) == NV_OK &&
            s540GspCancellationUnbind(token) == NV_OK, "baseline binding released");
        expect(s540GspCancellationBind(state, &token) == NV_OK &&
            s540GspCancellationBegin(token) == NV_OK, "cancellation trial has a fresh generation");
        s540CancellationWaitFixtureReset(0);
        NV_STATUS revoke = NV_ERR_NOT_READY;
        std::thread producer([&] {
            while (!s540CancellationWaitFixtureReads()) std::this_thread::yield();
            revoke = s540GspCancellationRevoke(token);
        });
        const NV_STATUS status = s540CancellationWaitFixtureRun(kind);
        const NvU64 returnedAt = s540Darwin_os_get_monotonic_time_ns();
        producer.join();
        expect(revoke == NV_OK && s540CancellationWaitFixtureReads(),
            "revocation occurs during actual original wait body");
        expect(status == NV_ERR_OPERATION_ABORTED,
            "real prospective wait returns the explicit abort through its error boundary");
        S540GspCancellationSnapshot snapshot{};
        expect(s540GspCancellationGetSnapshot(token, &snapshot) == NV_OK &&
            snapshot.operationAborts && snapshot.revokedAtNs <= returnedAt,
            "actual record confirms original body observed asynchronous revocation");
        const NvU64 observed = returnedAt - snapshot.revokedAtNs;
        if (observed > maximumObservedNs) maximumObservedNs = observed;
        expect(observed < 30000000000ULL,
            "observed CPU-fixture return precedes actual fixed PM deadline");
        expect(s540GspCancellationBeginCleanupState(state) == NV_OK &&
            s540GspCancellationCheckState(state) == NV_OK,
            "cleanup remains a separate live phase after original operation abort");
        expect(s540GspCancellationFinish(token) == NV_OK &&
            s540GspCancellationUnbind(token) == NV_OK, "source fixture releases its exact owner");
    }
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-original-wait-cancellation\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"actual_original_wait_bodies\":4,"
        "\"hardware_endpoints\":\"explicit-fixtures\",\"revoked_during_wait\":true,"
        "\"maximum_observed_abort_ns\":%llu,\"hardware_cleanup_proven\":false,"
        "\"original_entry_admission\":false}\n", checks,
        static_cast<unsigned long long>(maximumObservedNs));
}
