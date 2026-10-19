// SPDX-License-Identifier: MIT
#include "S540NvidiaGspCancellation.h"
#include "S540NvidiaDarwinServices.h"
#include <cstdio>
#include <thread>
extern "C" {
void s540LogFixtureReset(NvU32, NvBool);
void s540LogFixtureRun(NvU32);
NvU32 s540LogFixtureEntered(void);
void s540LogFixtureRelease(void);
NvU32 s540LogFixtureReads(void), s540LogFixtureCopies(void), s540LogFixtureLogs(void);
NvU32 s540LogFixtureNvlogs(void), s540LogFixturePrints(void);
NvU64 s540LogFixturePreviousPut(void), s540LogFixtureMergedEntries(void);
NvS32 s540LogFixtureLock(void);
}
static unsigned checks, failures;
static void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "Log control: %s\n", reason); }
}
int main() {
    int state = 0;
    expect(!s540GspCancellationSkipOptionalCurrent(), "unbound caller does not fabricate revocation");
    for (NvU32 which = 0; which < 5; ++which) {
        S540GspCancellationToken token = 0;
        expect(s540GspCancellationBind(&state, &token) == NV_OK &&
            s540GspCancellationBegin(token) == NV_OK, "actual worker scope begins");
        s540LogFixtureReset(which, NV_FALSE); s540LogFixtureRun(which);
        expect(!s540GspCancellationSkipOptionalCurrent() &&
            (which != 0 || (s540LogFixtureLogs() == 1 && !s540LogFixtureLock())) &&
            (which != 1 || s540LogFixturePrints() == 1) &&
            (which != 2 || s540LogFixtureMergedEntries() > 0) &&
            (which != 4 || (s540LogFixtureLogs() == 1 && !s540LogFixtureLock())) &&
            (which != 3 || (s540LogFixtureNvlogs() == 1 && s540LogFixturePreviousPut() == 256)),
            "unrevoked actual diagnostic body retains original completion");
        s540LogFixtureReset(which, NV_TRUE);
        NV_STATUS revoke = NV_ERR_NOT_READY;
        bool foreignSkip = true;
        std::thread producer([&] {
            while (!s540LogFixtureEntered()) std::this_thread::yield();
            revoke = s540GspCancellationRevoke(token);
            foreignSkip = s540GspCancellationSkipOptionalCurrent();
            s540LogFixtureRelease();
        });
        s540LogFixtureRun(which); producer.join();
        expect(revoke == NV_OK && !foreignSkip && s540GspCancellationSkipOptionalCurrent(),
            "actual in-body revocation applies only to enrolled operation thread");
        expect((which != 0 || (s540LogFixtureLogs() == 0 && s540LogFixtureLock() == 1)) &&
            (which != 1 || (s540LogFixtureReads() == 1 && !s540LogFixturePrints())) &&
            (which != 2 || (s540LogFixtureCopies() == 1 && !s540LogFixtureMergedEntries())) &&
            (which != 4 || (s540LogFixtureLogs() == 1 && !s540LogFixtureLock())) &&
            (which != 3 || (!s540LogFixtureNvlogs() && s540LogFixturePreviousPut() == 1)),
            "revoked body leaves unowned token/log cursor/merge commit untouched");
        expect(s540GspCancellationBeginCleanupState(&state) == NV_OK &&
            s540GspCancellationCheckCurrent() == NV_OK && s540GspCancellationSkipOptionalCurrent(),
            "hardware cleanup remains permitted while optional diagnostics are skipped");
        s540LogFixtureReset(which, NV_FALSE); s540LogFixtureRun(which);
        expect(s540LogFixtureLogs() == 0 && !s540LogFixturePrints() &&
            !s540LogFixtureCopies() && !s540LogFixtureNvlogs() &&
            s540LogFixturePreviousPut() == 1,
            "cleanup never begins another optional log collection after actual revocation");
        expect(s540GspCancellationFinish(token) == NV_OK &&
            s540GspCancellationUnbind(token) == NV_OK, "actual quiescent scope ends");
    }
    expect(!s540DarwinLiveObjects(), "record and diagnostic fixture leak no services");
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-optional-log-cancellation\","
        "\"checks\":%u,\"failures\":%u,\"status\":\"%s\",\"actual_original_bodies\":4,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"original_entry_admission\":false,"
        "\"aggregate_pm_deadline_proven\":false}\n", checks, failures, failures ? "failed" : "passed");
}
