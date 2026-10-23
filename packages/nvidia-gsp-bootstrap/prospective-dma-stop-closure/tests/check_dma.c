/* SPDX-License-Identifier: MIT
 * Complete selected BIF bodies and genuine cancellation/commit implementation.
 * PCI/config/thread/clock/timeout endpoints are explicit CPU fixtures. */
#include "S540NvidiaGspCommit.h"
#include "nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include "nvmisc.h"
#include "published/maxwell/gm107/dev_nv_xve.h"
#include <stdio.h>
#include <stdlib.h>
typedef struct OBJGPU { const void *nv; } OBJGPU;
typedef struct KernelBif { NvU32 unused; } KernelBif;
typedef struct RMTIMEOUT { NvU32 unused; } RMTIMEOUT;
static OBJGPU gpu;
static KernelBif bif;
static int nv, foreignNv, pciHandle;
static S540GspCancellationToken token;
static NvU64 now = 100, tid = 7;
static NvU32 scenario, checks, failures, configReads, configWrites, pciReads, handleCalls, timeoutCalls;
static NvU32 configInitial, configObserved, written;
static NV_STATUS readFirst, readSecond, writeStatus, timeoutStatus;
static NvBool stop, nullHandle;
#undef NV_GET_NV_STATE
#define NV_GET_NV_STATE(p) ((p)->nv)
#define GPU_TIMEOUT_DEFAULT 1000U
static void expect(NvBool value, const char *why) {
    ++checks; if (!value) { ++failures; fprintf(stderr, "DMA stop: %s\n", why); }
}
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out) { *out = tid; return NV_OK; }
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) { return NV_TRUE; }
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void) { return now; }
NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32 ms) { (void)ms; return NV_OK; }
NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *state, NvU32 role, NvU32 *origin) {
    (void)state; (void)role; (void)origin; return NV_ERR_INVALID_STATE;
}
static NV_STATUS configRead(OBJGPU *object, NvU32 address, NvU32 *out) {
    expect(object == &gpu && address == NV_XVE_DEV_CTRL, "exact BME config read");
    ++configReads; *out = configReads == 1 ? configInitial : configObserved;
    return configReads == 1 ? readFirst : readSecond;
}
static NV_STATUS configWrite(OBJGPU *object, NvU32 address, NvU32 value) {
    expect(object == &gpu && address == NV_XVE_DEV_CTRL, "exact BME config write");
    ++configWrites; written = value; return writeStatus;
}
#define GPU_BUS_CFG_RD32 configRead
#define GPU_BUS_CFG_WR32 configWrite
#undef NV_ASSERT_OK_OR_RETURN
#define NV_ASSERT_OK_OR_RETURN(value) do { NV_STATUS actual = (value); if (actual != NV_OK) return actual; } while (0)
static NvU32 gpuGetDomain(OBJGPU *object) { expect(object == &gpu, "actual GPU domain"); return 0; }
static NvU8 gpuGetBus(OBJGPU *object) { expect(object == &gpu, "actual GPU bus"); return 1; }
static NvU8 gpuGetDevice(OBJGPU *object) { expect(object == &gpu, "actual GPU device"); return 0; }
static void *osPciInitHandle(NvU32 domain, NvU8 bus, NvU8 device, NvU8 function, NvU16 *vendor, NvU16 *id) {
    expect(domain == 0 && bus == 1 && device == 0 && function == 0, "exact requested PCI function");
    ++handleCalls; *vendor = 0x10de; *id = 0x1f91;
    if (scenario == 21) expect(s540GspCancellationRevoke(token) == NV_OK, "real revocation during accepted handle endpoint");
    return nullHandle ? NULL : &pciHandle;
}
static NvU32 osPciReadDword(void *handle, NvU32 offset) {
    S540GspCancellationCommitSnapshot commit = {0};
    expect(handle == &pciHandle && offset == NV_XVE_DEVICE_CONTROL_STATUS, "exact TP config read");
    expect(s540GspCancellationCommitReadState(&nv, &commit) == NV_OK && commit.inFlight,
        "real reservation held across actual PCI read");
    ++pciReads;
    if (scenario == 20) expect(s540GspCancellationRevoke(token) == NV_OK, "real revocation during accepted zero read");
    if (scenario == 23) return ~(NvU32)0;
    if ((scenario == 24 && pciReads == 1) || scenario == 25 || scenario == 26) return 1U << 21;
    return 0;
}
static void gpuSetTimeout(OBJGPU *object, NvU32 amount, RMTIMEOUT *timeout, NvU32 flags) {
    expect(object == &gpu && amount == GPU_TIMEOUT_DEFAULT && timeout && !flags, "actual timeout setup");
}
static NV_STATUS gpuCheckTimeout(OBJGPU *object, RMTIMEOUT *timeout) {
    expect(object == &gpu && timeout, "actual timeout poll"); ++timeoutCalls; return timeoutStatus;
}
#include "actual-dma-bodies.inc"
int main(int argc, char **argv) {
    NV_STATUS expected = NV_OK, result;
    S540GspCancellationCommitLease held = 0;
    if (argc != 2) return 2;
    scenario = (NvU32)strtoul(argv[1], NULL, 10);
    gpu.nv = &nv; stop = NV_TRUE; configInitial = 0x84; configObserved = 0x80;
    if (scenario < 16) {
        switch (scenario) {
        case 0: break;
        case 1: stop = NV_FALSE; configInitial = 0x80; configObserved = 0x84; break;
        case 2: readFirst = expected = NV_ERR_OPERATING_SYSTEM; break;
        case 3: configObserved = 0x84; expected = NV_ERR_INVALID_STATE; break;
        case 4: configInitial = ~(NvU32)0; expected = NV_ERR_GPU_IS_LOST; break;
        case 5: writeStatus = expected = NV_ERR_OPERATING_SYSTEM; break;
        case 6: readSecond = expected = NV_ERR_OPERATING_SYSTEM; break;
        case 7: configObserved = ~(NvU32)0; expected = NV_ERR_GPU_IS_LOST; break;
        case 8: stop = NV_FALSE; configInitial = configObserved = 0x80; expected = NV_ERR_INVALID_STATE; break;
        case 9: configInitial = 0xf6; configObserved = 0xf2; break;
        case 10: readFirst = expected = NV_ERR_TIMEOUT; break;
        case 11: writeStatus = expected = NV_ERR_OPERATION_ABORTED; break;
        case 12: readSecond = expected = NV_ERR_OPERATION_ABORTED; break;
        case 13: stop = NV_FALSE; configObserved = 0x84; break;
        case 14: configInitial = 0x80; break;
        case 15: stop = 2; break;
        }
        result = kbifStopSysMemRequests_GM107(&gpu, &bif, stop);
        expect(result == expected, "BME status truthful");
        if (scenario == 2 || scenario == 4 || scenario == 10)
            expect(configWrites == 0 && configReads == 1, "failed initial read prevents store");
        else {
            expect(configWrites == 1, "single actual config store");
            expect(written == (stop ? (configInitial & ~4U) : (configInitial | 4U)), "only BME field modified");
            expect(configReads == ((scenario == 5 || scenario == 11) ? 1U : 2U), "successful store gets actual readback");
        }
    } else {
        expect(s540GspCancellationBind(&nv, &token) == NV_OK, "actual cancellation binding");
        if (scenario != 19) expect(s540GspCancellationBegin(token) == NV_OK, "actual enrolled operation scope");
        switch (scenario) {
        case 16: break;
        case 17: expected = NV_ERR_INVALID_ARGUMENT; break;
        case 18: gpu.nv = &foreignNv; expected = NV_ERR_INVALID_STATE; break;
        case 19: expected = NV_ERR_INVALID_STATE; break;
        case 20: case 21: expected = NV_ERR_OPERATION_ABORTED; break;
        case 22: nullHandle = NV_TRUE; expected = NV_ERR_INVALID_STATE; break;
        case 23: expected = NV_ERR_GPU_IS_LOST; break;
        case 24: break;
        case 25: timeoutStatus = expected = NV_ERR_TIMEOUT; break;
        case 26: timeoutStatus = expected = NV_ERR_INVALID_STATE; break;
        case 27: expect(s540GspCancellationRevoke(token) == NV_OK, "real pre-poll revocation"); expected = NV_ERR_OPERATION_ABORTED; break;
        case 28: case 29:
            expect(s540GspCancellationRevoke(token) == NV_OK, "real cleanup revocation");
            expect(s540GspCancellationBeginCleanupState(&nv) == NV_OK, "real cleanup phase");
            if (scenario == 29) { now += 30000000001ULL; expected = NV_ERR_TIMEOUT; }
            break;
        case 30: expect(s540GspCancellationSubmitEnterState(&nv, &held) == NV_OK, "real existing endpoint held"); expected = NV_ERR_IN_USE; break;
        case 31: tid = 13; expected = NV_ERR_INVALID_STATE; break;
        default: return 2;
        }
        result = kbifWaitForTransactionsComplete_TU102(scenario == 17 ? NULL : &gpu, &bif);
        expect(result == expected, "TP poll status truthful");
        if (scenario == 17 || scenario == 18 || scenario == 19 || scenario == 27 || scenario == 29 || scenario == 30 || scenario == 31)
            expect(!handleCalls && !pciReads, "refused scope performs no PCI endpoint");
        if (scenario == 20) expect(pciReads == 1, "revoked zero read cannot become success");
        if (scenario == 21 || scenario == 22) expect(handleCalls == 1 && !pciReads, "invalid handle boundary prevents TP read");
        if (scenario == 24) expect(pciReads == 2 && timeoutCalls == 1, "pending poll progresses to real zero");
        if (scenario == 25 || scenario == 26) expect(pciReads == 1 && timeoutCalls == 1, "every timeout error propagates");
        if (scenario == 30) expect(s540GspCancellationCommitLeaveState(&nv, held) == NV_OK, "actual prior endpoint returns");
        else {
            S540GspCancellationCommitSnapshot commit = {0};
            expect(s540GspCancellationCommitReadState(&nv, &commit) == NV_OK && !commit.inFlight,
                "all actual returned endpoints retire their reservations");
        }
    }
    printf("{\"scenario\":%u,\"checks\":%u,\"failures\":%u}\n", scenario, checks, failures);
    return failures ? 1 : 0;
}
