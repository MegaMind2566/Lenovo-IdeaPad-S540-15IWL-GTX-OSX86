/* SPDX-License-Identifier: MIT
 * Complete production first-lock observer and selected ownership reader.
 * Global/record/thread/TLS/GPU ownership endpoints are explicit CPU fixtures;
 * the production caller does not receive any of these fixture Booleans. */
#include "S540NvidiaGspFirstTransaction.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef struct OBJSYS { NvBool PDB_PROP_SYS_DESTRUCTING; void *pSema; } OBJSYS;
#include "actual-lock-types.inc"
static OBJSYS sys, foreignSys;
static OBJSYS *currentSys;
#define SYS_GET_INSTANCE() (currentSys)
static NvU64 threadValue, ownershipThread;
static NvBool maySleep, running, portable, apiOwned, allocationOwned;
static NvU32 gpuMask, checks, failures, globalReads, recordReads, ownershipReads;
static NvU32 scenario;
static NV_STATUS apiStatus, gpuStatus;
static S540FirstTxnGlobalSnapshot epoch;
static S540FirstTxnSnapshot record;
static int nv, ownerObject, foreignNv;
static void expect(NvBool value, const char *why) {
    ++checks; if (!value) { ++failures; fprintf(stderr, "first locks: %s\n", why); }
}
NvBool s540Darwin_os_semaphore_may_sleep(void) { return maySleep; }
NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out) {
    if (scenario == 4) return NV_ERR_OPERATING_SYSTEM;
    *out = threadValue; return NV_OK;
}
NV_STATUS osGetCurrentThread(NvU64 *out) {
    if (scenario == 39) return NV_ERR_OPERATING_SYSTEM;
    *out = ownershipThread; return NV_OK;
}
NvBool s540GlobalRmIsInitialized(void) { return running; }
NvBool portIsInitialized(void) { return portable; }
NV_STATUS s540FirstTxnGlobalGetSnapshot(S540FirstTxnGlobalSnapshot *out) {
    ++globalReads;
    if (scenario == 7 || (scenario == 35 && globalReads == 2)) return NV_ERR_BUSY_RETRY;
    *out = epoch; return NV_OK;
}
NV_STATUS s540FirstTxnGetSnapshot(const void *state, S540FirstTxnSnapshot *out) {
    ++recordReads;
    if (scenario == 8 || (scenario == 36 && recordReads == 2)) return NV_ERR_BUSY_RETRY;
    if (state != &nv) return NV_ERR_INVALID_ARGUMENT;
    *out = record; return NV_OK;
}
NV_STATUS s540ProspectiveOriginalApiOwnership(NvBool *out) {
    if (apiStatus != NV_OK) return apiStatus;
    *out = apiOwned; return NV_OK;
}
NV_STATUS s540ProspectiveOriginalGpuOwnership(NvU32 *mask, NvBool *allocation) {
    ++ownershipReads;
    if (gpuStatus != NV_OK) return gpuStatus;
    *mask = gpuMask; *allocation = allocationOwned;
    if (scenario == 29) currentSys = &foreignSys;
    if (scenario == 30) ++epoch.generation;
    if (scenario == 31) epoch.owner = &foreignNv;
    if (scenario == 32) ++record.generation;
    if (scenario == 33) epoch.firstStatus = record.firstStatus = NV_ERR_TIMEOUT;
    if (scenario == 34) ++threadValue;
    return NV_OK;
}
#include "actual-ownership-bodies.inc"
#include "actual-first-lock-body.inc"
static void reset(void) {
    memset(&sys, 0, sizeof(sys)); memset(&foreignSys, 0, sizeof(foreignSys));
    memset(&epoch, 0, sizeof(epoch)); memset(&record, 0, sizeof(record));
    currentSys = &sys; threadValue = ownershipThread = 7;
    maySleep = running = portable = NV_TRUE; apiOwned = allocationOwned = NV_FALSE;
    gpuMask = 0; globalReads = recordReads = ownershipReads = 0;
    apiStatus = gpuStatus = NV_OK;
    epoch.owner = &ownerObject; epoch.nv = &nv; epoch.generation = 11;
    epoch.masterThread = threadValue; epoch.state = S540_FIRST_GLOBAL_READY;
    epoch.originalReturned = epoch.validated = NV_TRUE;
    record.generation = epoch.generation; record.masterThread = threadValue;
    record.phase = S540_FIRST_OP;
}
int main(int argc, char **argv) {
    NV_STATUS expected = NV_ERR_INVALID_STATE, actual;
    if (argc != 2) return 2;
    scenario = (NvU32)strtoul(argv[1], NULL, 10); reset();
    switch (scenario) {
    case 0: expected = NV_OK; break;
    case 1: epoch.firstStatus = record.firstStatus = NV_ERR_TIMEOUT; record.phase = S540_FIRST_RETAINED; expected = NV_OK; break;
    case 2: expected = NV_ERR_INVALID_REQUEST; break;
    case 3: maySleep = NV_FALSE; expected = NV_ERR_INVALID_REQUEST; break;
    case 4: expected = NV_ERR_OPERATING_SYSTEM; break;
    case 5: threadValue = 0; break;
    case 6: threadValue = ~(NvU64)0; break;
    case 7: case 8: case 35: case 36: expected = NV_ERR_BUSY_RETRY; break;
    case 9: epoch.owner = NULL; break;
    case 10: epoch.nv = &foreignNv; break;
    case 11: epoch.generation = record.generation = 0; break;
    case 12: epoch.masterThread = 13; break;
    case 13: epoch.state = S540_FIRST_GLOBAL_IN_CORE; break;
    case 14: epoch.validated = NV_FALSE; break;
    case 15: epoch.originalReturned = NV_FALSE; break;
    case 16: ++record.generation; break;
    case 17: ++record.masterThread; break;
    case 18: record.firstStatus = NV_ERR_TIMEOUT; break;
    case 19: currentSys = NULL; expected = NV_ERR_NOT_READY; break;
    case 20: running = NV_FALSE; expected = NV_ERR_NOT_READY; break;
    case 21: portable = NV_FALSE; expected = NV_ERR_NOT_READY; break;
    case 22: sys.PDB_PROP_SYS_DESTRUCTING = NV_TRUE; break;
    case 23: sys.pSema = &foreignSys; break;
    case 24: apiOwned = NV_TRUE; expected = NV_ERR_INVALID_LOCK_STATE; break;
    case 25: gpuMask = 2; expected = NV_ERR_INVALID_LOCK_STATE; break;
    case 26: allocationOwned = NV_TRUE; expected = NV_ERR_INVALID_LOCK_STATE; break;
    case 27: apiStatus = expected = NV_ERR_OPERATING_SYSTEM; break;
    case 28: gpuStatus = expected = NV_ERR_BUSY_RETRY; break;
    case 29: case 30: case 31: case 32: case 33: case 34: break;
    case 37: ownershipThread = 0; break;
    case 38: ownershipThread = ~(NvU64)0; break;
    case 39: expected = NV_ERR_OPERATING_SYSTEM; break;
    default: return 2;
    }
    NvU32 stickyBefore = record.firstStatus;
    actual = s540FirstTxnOriginalLocksReleased(scenario == 2 ? NULL : &nv);
    expect(actual == expected, "expected truthful observer outcome");
    if (scenario != 33) expect(record.firstStatus == stickyBefore, "observer never clears sticky first status");
    if (scenario <= 1) {
        expect(globalReads == 2 && recordReads == 2 && ownershipReads == 1, "real before/query/after path");
        expect(currentSys == &sys && !apiOwned && !gpuMask && !allocationOwned, "actual clean ownership fixture observed");
    }
    if (scenario == 26) expect(!gpuMask && ownershipReads == 1, "allocation ownership independent of GPU mask");
    printf("{\"scenario\":%u,\"checks\":%u,\"failures\":%u}\n", scenario, checks, failures);
    return failures ? 1 : 0;
}
