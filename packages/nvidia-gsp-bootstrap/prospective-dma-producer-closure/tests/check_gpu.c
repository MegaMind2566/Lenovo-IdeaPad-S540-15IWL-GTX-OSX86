/* SPDX-License-Identifier: MIT */
/* Complete transformed original functions, real original layouts and the
 * genuine cancellation translation unit. MMIO/log/assert, clock and thread
 * endpoints below are explicit Linux CPU fixtures; no device is accessed. */
#define NVOC_GPU_H_PRIVATE_ACCESS_ALLOWED
#include "nv.h"
#include "nv-priv.h"
#include "gpu/gpu.h"
#include "gpu/bif/kernel_bif.h"
#include "core/thread_state.h"
#include "published/maxwell/gm107/dev_nv_xve.h"
#include "published/maxwell/gm107/dev_nv_xve1.h"
#include "S540NvidiaDmaProducer.h"
#include "S540NvidiaDarwinServices.h"
#include <stdio.h>
#include <stdlib.h>

static OBJGPU gpu;
static nv_state_t state, foreign;
static THREAD_STATE_NODE threadState;
static NvU64 tid = 1, now = 100;
static NvU32 checks, failures, stores, assertCalls;
static NvU32 lastAddress, lastValue, commitWitnesses;
static THREAD_STATE_NODE *lastThreadState;
static NvBool revokeInStore;
static S540GspCancellationToken token;

static void expect(NvBool value, const char *why) {
    ++checks;
    if (!value) { ++failures; fprintf(stderr, "GPU body: %s\n", why); }
}
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out) {
    *out = tid; return NV_OK;
}
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) { return NV_TRUE; }
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void) { return now; }
NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32 ms) { (void)ms; return NV_OK; }
NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *nv, NvU32 role, NvU32 *origin) {
    (void)nv; (void)role; (void)origin; return NV_ERR_NOT_SUPPORTED;
}

static void writeRegister(OBJGPU *object, NvU32 address, NvU32 value,
                          THREAD_STATE_NODE *node) {
    const NvU32 base = address >= DEVICE_BASE(NV_PCFG1) ?
        DEVICE_BASE(NV_PCFG1) : DEVICE_BASE(NV_PCFG);
    S540GspCancellationCommitSnapshot snapshot = {0};
    expect(object == &gpu, "actual original GPU identity reaches MMIO endpoint");
    if (s540DmaConfigWriteEnablesBusMaster(address - base, 4, value)) {
        expect(s540GspCancellationCommitReadState(&state, &snapshot) == NV_OK &&
            /* Commit origins are genuine internal scope bits (OP=2), not
             * the public cancellation snapshot's phase enum (OP=1). */
            snapshot.inFlight == 1 && snapshot.origin == 2U,
            "genuine commit is still held when actual MMIO endpoint runs");
        ++commitWitnesses;
        if (revokeInStore) {
            revokeInStore = NV_FALSE;
            expect(s540GspCancellationRevokeAt(token, now) == NV_OK,
                "actual revocation may publish during already accepted endpoint");
            expect(s540GspCancellationCommitReadState(&state, &snapshot) == NV_OK &&
                snapshot.inFlight == 1 && snapshot.revoked,
                "accepted endpoint remains in flight after revocation");
            expect(s540GspCancellationFinish(token) == NV_ERR_IN_USE,
                "revocation cannot fabricate completion of accepted MMIO");
        }
    }
    ++stores; lastAddress = address; lastValue = value; lastThreadState = node;
}

#undef GPU_REG_WR32
#define GPU_REG_WR32(g,a,v) writeRegister((g),(a),(v),NULL)
#undef GPU_REG_WR32_EX
#define GPU_REG_WR32_EX(g,a,v,t) writeRegister((g),(a),(v),(t))
#undef NV_PRINTF
#define NV_PRINTF(...) ((void)0)
#undef NV_ASSERT
#define NV_ASSERT(value) do { if (!(value)) ++assertCalls; } while (0)

#include "actual-gpu-config-bodies.inc"

static void start(void) {
    NV_SET_NV_STATE(&gpu, &state);
    expect(s540GspCancellationBind(&state, &token) == NV_OK, "actual nv binding");
    expect(s540GspCancellationBegin(token) == NV_OK, "actual OPERATION entry");
}
static void idle(void) {
    S540GspCancellationCommitSnapshot snapshot = {0};
    expect(s540GspCancellationCommitReadState(&state, &snapshot) == NV_OK &&
        !snapshot.inFlight, "complete original function released actual commit");
    expect(s540GspCancellationPendingLeases() == 0, "no retained commit remains");
}
static NV_STATUS bus(NvU32 index, NvU32 value) {
    return gpuWriteBusConfigReg_GM107(&gpu, index, value);
}
static NV_STATUS function(NvU32 number, NvU32 index, NvU32 value) {
    return gpuWriteFunctionConfigRegEx_GM107(&gpu, number, index, value, &threadState);
}
int main(int argc, char **argv) {
    const int scenario = argc > 1 ? atoi(argv[1]) : 0;
    S540GspCancellationCommitLease commit = 0;
    S540GspCancellationCommitSnapshot snapshot = {0};
    NV_SET_NV_STATE(&gpu, &state);
    if (scenario != 0) start();
    switch (scenario) {
    case 0:
        expect(bus(4, 4) != NV_OK && !stores, "unbound BME enable refuses before MMIO");
        expect(bus(4, 0) == NV_OK && stores == 1,
            "BME clear retains original unguarded cleanup behavior");
        break;
    case 1:
        expect(bus(4, 4) == NV_OK && stores == 1 && commitWitnesses == 1,
            "actual operation reaches exactly one protected BME store");
        expect(lastAddress == DEVICE_BASE(NV_PCFG) + 4 && lastValue == 4 && !lastThreadState,
            "bus write preserves exact original endpoint arguments");
        idle(); break;
    case 2:
        expect(s540GspCancellationRevoke(token) == NV_OK, "actual revoke");
        expect(bus(4, 4) == NV_ERR_OPERATION_ABORTED && !stores,
            "post-revoke BME enable performs no store");
        expect(bus(4, 0) == NV_OK && stores == 1, "post-revoke BME clear is preserved");
        idle(); break;
    case 3:
        expect(function(0, 4, 4) == NV_OK && stores == 1 && commitWitnesses == 1,
            "function-zero protected endpoint runs");
        expect(lastAddress == DEVICE_BASE(NV_PCFG) + 4 && lastThreadState == &threadState,
            "function-zero preserves original thread-state endpoint argument");
        idle(); break;
    case 4:
        expect(function(1, 4, 4) == NV_OK && stores == 1 && commitWitnesses == 1,
            "function-one real protected endpoint runs");
        expect(lastAddress == DEVICE_BASE(NV_PCFG1) + 4 && lastThreadState == &threadState,
            "function-one uses exact PCFG1 base");
        gpu.bIsFmodel = NV_TRUE;
        expect(function(1, 4, 4) == NV_OK && stores == 1 && commitWitnesses == 1,
            "FMODEL function-one no-store path does not acquire a commit");
        idle(); break;
    case 5:
        expect(function(2, 4, 4) == NV_ERR_INVALID_ARGUMENT && !stores,
            "invalid function returns without MMIO or lease");
        expect(s540GspCancellationCommitReadState(&state, &snapshot) == NV_OK &&
            !snapshot.accepted && !snapshot.inFlight, "invalid function has no acceptance effect");
        idle(); break;
    case 6:
        for (NvU32 index = 1; index != 4; ++index) {
            NvU32 value = 4U << ((4U - index) * 8U);
            expect(bus(index, value) == NV_ERR_INVALID_ARGUMENT && !stores,
                "unaligned bus command-byte overlap refuses");
            expect(function(0, index, value) == NV_ERR_INVALID_ARGUMENT && !stores,
                "unaligned function-zero command-byte overlap refuses");
            expect(function(1, index, value) == NV_ERR_INVALID_ARGUMENT && !stores,
                "unaligned function-one command-byte overlap refuses");
        }
        expect(bus(7, 0) == NV_ERR_INVALID_ARGUMENT && !stores,
            "unaligned non-command MMIO also refuses");
        idle(); break;
    case 7:
        expect(bus(4093, 4) == NV_ERR_GENERIC && !stores,
            "original bus bounds refusal precedes new alignment gate");
        expect(bus(~0U, 4) == NV_ERR_GENERIC && !stores && assertCalls == 2,
            "original maximal bus bounds and assertion behavior preserved");
        expect(function(0, 4093, 4) == NV_ERR_INVALID_ARGUMENT && !stores,
            "original function bounds refusal preserved");
        expect(function(1, ~0U, 4) == NV_ERR_INVALID_ARGUMENT && !stores,
            "original maximal function bounds refusal preserved");
        idle(); break;
    case 8:
    case 9:
        revokeInStore = NV_TRUE;
        expect((scenario == 8 ? bus(4, 4) : function(1, 4, 4)) == NV_OK && stores == 1,
            "accepted-before-revoke original endpoint completes normally");
        expect(bus(4, 4) == NV_ERR_OPERATION_ABORTED && stores == 1,
            "subsequent bus enable is closed after genuine revoke");
        expect(function(1, 4, 4) == NV_ERR_OPERATION_ABORTED && stores == 1,
            "subsequent function-one enable is closed after genuine revoke");
        expect(bus(4, 0) == NV_OK && stores == 2, "BME clear can follow completed accepted endpoint");
        idle(); break;
    case 10:
        NV_SET_NV_STATE(&gpu, &foreign);
        expect(bus(4, 4) != NV_OK && !stores, "genuine exact-state mismatch refuses bus MMIO");
        expect(function(0, 4, 4) != NV_OK && !stores, "genuine exact-state mismatch refuses function MMIO");
        NV_SET_NV_STATE(&gpu, &state);
        expect(bus(4, 4) == NV_OK && stores == 1, "actual state identity remains usable");
        idle(); break;
    case 11:
        tid = 2;
        expect(bus(4, 4) != NV_OK && !stores, "unenrolled foreign thread cannot enable BME");
        expect(function(1, 4, 4) != NV_OK && !stores, "foreign function-one enable refuses");
        tid = 1;
        expect(bus(4, 4) == NV_OK && stores == 1, "actual owner still reaches protected endpoint");
        idle(); break;
    case 12:
        expect(s540GspCancellationRevoke(token) == NV_OK, "cleanup actual revoke");
        expect(s540GspCancellationBeginCleanupState(&state) == NV_OK, "genuine cleanup scope");
        expect(bus(4, 4) != NV_OK && !stores, "cleanup cannot upgrade BME enable authority");
        expect(function(1, 4, 4) != NV_OK && !stores, "cleanup function-one cannot enable BME");
        expect(bus(4, 0) == NV_OK && stores == 1, "genuine cleanup may clear BME");
        expect(function(1, 4, 0) == NV_OK && stores == 2, "function-one cleanup clear preserved");
        idle(); break;
    case 13:
        expect(s540GspCancellationCommitEnterState(&state, &commit) == NV_OK && commit,
            "actual shared reservation held before nested enable");
        expect(bus(4, 4) != NV_OK && !stores, "busy actual shared reservation refuses nested enable");
        expect(s540GspCancellationCommitLeaveState(&state, commit) == NV_OK,
            "real outer endpoint completion releases reservation");
        expect(bus(4, 4) == NV_OK && stores == 1, "enable succeeds only after real release");
        idle(); break;
    case 14:
        expect(bus(8, 4) == NV_OK && stores == 1, "bit2 outside command is not BME enable");
        expect(function(0, 0, 4) == NV_OK && stores == 2, "non-overlapping earlier dword preserved");
        expect(function(1, 8, 4) == NV_OK && stores == 3, "function-one other config write preserved");
        expect(s540GspCancellationCommitReadState(&state, &snapshot) == NV_OK &&
            !snapshot.accepted && !snapshot.inFlight, "ordinary writes create no false commit witness");
        idle(); break;
    default: return 2;
    }
    printf("{\"scenario\":%d,\"checks\":%u,\"failures\":%u,\"stores\":%u,\"commit_witnesses\":%u,\"genuine_cancellation\":true,\"hardware_execution\":false}\n",
        scenario, checks, failures, stores, commitWitnesses);
    return failures ? 1 : 0;
}
