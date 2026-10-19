// SPDX-License-Identifier: MIT
#include "nvtypes.h"
#include "nvstatus.h"
#include <cstdio>
extern "C" {
NV_STATUS s540EpochRun(NvU32, NvU32);
NvU32 s540EpochStages(void), s540EpochOldStopSeen(void), s540EpochLastStage(void);
NvU32 s540EpochFrees(void);
NvBool s540EpochStopped(void);
}
static unsigned checks, failures, cases;
static void expect(bool value, const char *why) {
    ++checks; if (!value) { ++failures; std::fprintf(stderr, "Epoch: %s\n", why); }
}
int main() {
    const unsigned faults[][9] = {{1,2,3,4,6,8,9,10,0}, {1,6,8,11,0},
                                 {6,8,11,0}, {6,8,11,0}};
    for (NvU32 mode = 0; mode < 4; ++mode) {
        for (unsigned index = 0; ; ++index) {
            const NvU32 stage = faults[mode][index]; ++cases;
            const NV_STATUS expected = !stage ? NV_STATUS(NV_OK) :
                stage == 8 ? NV_STATUS(NV_ERR_NOT_READY) : NV_STATUS(NV_ERR_GENERIC);
            const NV_STATUS result = s540EpochRun(mode, stage);
            expect(result == expected, "actual body preserves stage success/error status");
            expect(!s540EpochOldStopSeen() && s540EpochStages(),
                "old completion invalidated before first hardware/firmware primitive");
            expect(!s540EpochStopped(),
                "boot error or success never certifies a completed hardware stop");
            expect(s540EpochLastStage() == (stage ? stage : mode ? 11U : 10U),
                "no later primitive executed after fault and every mode reaches correct completion");
            if (!stage) break;
        }
    }
    // A later internal retry receives a fresh stale-marker fixture, proving
    // invalidation is per actual bootstrap call rather than per object creation.
    expect(s540EpochRun(0, 1) == NV_ERR_GENERIC && !s540EpochOldStopSeen() && !s540EpochStopped(),
        "normal retry re-invalidates previous completion before Scrubber");
    expect(s540EpochRun(0, 3) == NV_ERR_GENERIC && !s540EpochOldStopSeen() &&
        !s540EpochStopped() && s540EpochFrees() == 1,
        "FWSEC failure preserves original command disposal without stop certification");
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-bootstrap-stop-epoch\","
        "\"checks\":%u,\"failures\":%u,\"status\":\"%s\",\"actual_original_bodies\":1,"
        "\"phase_fault_cases\":%u,\"boot_modes\":4,\"execution\":\"native-user-space\","
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
        "\"dma_stop_receipt_issued\":false,\"original_entry_admission\":false}\n",
        checks, failures, failures ? "failed" : "passed", cases);
}
