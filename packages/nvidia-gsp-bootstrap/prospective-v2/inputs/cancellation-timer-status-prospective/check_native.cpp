// SPDX-License-Identifier: MIT
#include "nvtypes.h"
#include "nvstatus.h"
#include <cstdio>
extern "C" {
NV_STATUS s540TimerStatusCancel(NvU32), s540TimerStatusUnload(NvU32, NvU32, NvU64);
NvU32 s540TimerStatusCalls(void), s540TimerStatusFlag(NvU32), s540TimerStatusExpectedFlag(NvBool);
NvU32 s540TimerStatusInterrupts(void), s540TimerStatusIdentityErrors(void);
NvU64 s540TimerStatusRemaining(NvU32);
NvBool s540TimerStatusListPreserved(void);
}
static unsigned checks, failures;
static void expect(bool value, const char *why) {
    ++checks; if (!value) { ++failures; std::fprintf(stderr, "Timer status: %s\n", why); }
}
int main() {
    for (NvU32 which = 0; which < 7; ++which) {
        const NV_STATUS expected = which < 2 ? NV_STATUS(NV_ERR_INVALID_REQUEST) :
            which == 2 || which == 6 ? NV_STATUS(NV_ERR_TIMEOUT) :
            which == 3 ? NV_STATUS(NV_ERR_IN_USE) : NV_STATUS(NV_OK);
        expect(s540TimerStatusCancel(which) == expected, "original cancel preserves exact backend status");
        expect(s540TimerStatusFlag(0) == s540TimerStatusExpectedFlag(which < 4),
            "queued bit clears only on actual NV_OK and unrelated flags are retained");
        expect(s540TimerStatusCalls() == (which < 2 ? 0U : 1U),
            "valid already-completed timer still calls cancellation service");
        expect(!s540TimerStatusIdentityErrors(), "exact GPU information and timer identity are forwarded");
    }
    for (NvU32 fail = 1; fail <= 3; ++fail) {
        expect(s540TimerStatusUnload(3, fail, 100) == NV_ERR_TIMEOUT,
            "unload returns first exact cancellation refusal");
        expect(s540TimerStatusCalls() == fail && s540TimerStatusInterrupts() == 2,
            "actual first refusal prevents later callbacks from being assumed stopped");
        expect(s540TimerStatusListPreserved(), "partial unload retains event list and every borrowed payload");
        expect(s540TimerStatusRemaining(fail - 1) == 1000 &&
            s540TimerStatusFlag(fail - 1) == s540TimerStatusExpectedFlag(NV_TRUE),
            "failed timer keeps pending metadata and remaining-time record");
        expect(!s540TimerStatusIdentityErrors() &&
            (fail == 1 || (s540TimerStatusFlag(0) == s540TimerStatusExpectedFlag(NV_FALSE) &&
             s540TimerStatusRemaining(0) == 910)),
            "earlier successful cancellations retain original time accounting");
    }
    expect(s540TimerStatusUnload(3, 0, 100) == NV_OK && s540TimerStatusCalls() == 3,
        "fully successful actual unload cancels every original timer");
    expect(s540TimerStatusListPreserved() && s540TimerStatusInterrupts() == 2,
        "successful unload preserves existing list/storage ownership");
    expect(s540TimerStatusRemaining(0) == 910 && s540TimerStatusRemaining(2) == 910 &&
        s540TimerStatusFlag(0) == s540TimerStatusExpectedFlag(NV_FALSE) &&
        s540TimerStatusFlag(2) == s540TimerStatusExpectedFlag(NV_FALSE),
        "successful unload retains original remaining-time adjustment");
    expect(s540TimerStatusUnload(0, 0, 100) == NV_OK && !s540TimerStatusCalls() &&
        s540TimerStatusInterrupts() == 2, "empty event list remains valid");
    expect(s540TimerStatusUnload(1, 0, 5) == NV_OK && s540TimerStatusRemaining(0) == 1000,
        "backwards clock preserves existing remaining-time fallback");
    expect(s540TimerStatusUnload(1, 0, 2000) == NV_OK && s540TimerStatusRemaining(0) == 1000,
        "elapsed duration beyond event preserves existing fallback");
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-timer-cancel-status\","
        "\"checks\":%u,\"failures\":%u,\"status\":\"%s\",\"actual_original_bodies\":2,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"backend_cancellation_status_proven\":false,"
        "\"callback_return_proven\":false,\"original_entry_admission\":false}\n",
        checks, failures, failures ? "failed" : "passed");
}
