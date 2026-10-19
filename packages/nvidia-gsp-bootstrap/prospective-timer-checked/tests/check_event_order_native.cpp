// SPDX-License-Identifier: MIT
#include "nvtypes.h"
#include "nvstatus.h"
#include <cstdio>
extern "C" {
NV_STATUS s540TimerOrderRun(NvU32, NvU32, NV_STATUS);
NvU32 s540TimerOrderCalls(void), s540TimerOrderDestroyCalls(void), s540TimerOrderPhaseErrors(void);
NvU32 s540TimerOrderIdentityErrors(void), s540TimerOrderEventFrees(void), s540TimerOrderUserFrees(void);
NvU32 s540TimerOrderProspectiveHelpers(void);
NvBool s540TimerOrderFailureRetained(void), s540TimerOrderSuccessList(void);
NvBool s540TimerOrderSuccessFlags(NvBool), s540TimerOrderSuccessFreeSequence(NvBool, NvBool);
}
static unsigned checks, failures;
static void expect(bool value, const char *why) {
    ++checks; if (!value) { ++failures; std::fprintf(stderr, "Timer ordering: %s\n", why); }
}
int main() {
    const NV_STATUS statuses[] = {NV_OK, NV_ERR_TIMEOUT, NV_ERR_IN_USE, NV_ERR_ILLEGAL_ACTION, NV_ERR_NOT_SUPPORTED};
    for (NvU32 operation = 0; operation < 4; ++operation) {
        const bool destroying = (operation & 1U) != 0, ctrl = operation >= 2;
        for (NvU32 position = 0; position < 3; ++position) {
            for (NV_STATUS status : statuses) {
                const NV_STATUS result = s540TimerOrderRun(operation, position, status);
                expect(result == (ctrl ? status : NV_STATUS(NV_OK)),
                    "statusful original caller preserves exact refusal and void public ABI is retained");
                expect(s540TimerOrderCalls() == 1 && s540TimerOrderDestroyCalls() == unsigned(destroying),
                    "exact one checked backend cancellation or destruction is invoked");
                expect(!s540TimerOrderIdentityErrors(), "exact GPU state, event and callback identity are forwarded");
                expect(!s540TimerOrderPhaseErrors(), "complete list, in-use flag and payload reach backend unchanged");
                if (status != NV_OK) {
                    expect(s540TimerOrderFailureRetained(), "every event link, payload, queued flag and allocation survives refusal");
                    expect(!s540TimerOrderEventFrees() && !s540TimerOrderUserFrees(), "refused callback and API wrapper storage remain owned");
                } else {
                    expect(s540TimerOrderSuccessList(), "successful backend precedes original list removal and in-use mutation");
                    expect(s540TimerOrderSuccessFlags(destroying), "only queued bit changes and successful destruction clears stale handle");
                    expect(s540TimerOrderEventFrees() == unsigned(destroying) &&
                        s540TimerOrderUserFrees() == unsigned(destroying && ctrl), "only successful destruction releases event or wrapper");
                    expect(s540TimerOrderSuccessFreeSequence(destroying, ctrl), "event releases after backend and wrapper releases after event");
                }
            }
        }
    }
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-timer-event-order\",\"checks\":%u,"
        "\"failures\":%u,\"status\":\"%s\",\"actual_original_bodies\":9,\"prospective_helpers\":%u,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
        "\"callback_return_proven\":false,\"accepted_work_borrowers_closed\":false,"
        "\"all_void_owner_callers_statusful\":false,\"original_entry_admission\":false}\n",
        checks, failures, failures ? "failed" : "passed", s540TimerOrderProspectiveHelpers());
}
