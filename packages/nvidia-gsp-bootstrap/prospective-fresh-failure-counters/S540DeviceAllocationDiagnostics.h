/* SPDX-License-Identifier: MIT */
#ifndef S540_DEVICE_ALLOCATION_DIAGNOSTICS_H
#define S540_DEVICE_ALLOCATION_DIAGNOSTICS_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"

enum {
    S540_DEVICE_ALLOC_DIAG_COUNTS = 1U,
    S540_DEVICE_ALLOC_DIAG_FIRST_FAILURE = 2U
};
enum S540DeviceAllocationFailureStage {
    S540_ALLOC_FAILURE_ARGUMENTS = 1U, S540_ALLOC_FAILURE_GEOMETRY = 2U,
    S540_ALLOC_FAILURE_HOST_PROFILE = 3U, S540_ALLOC_FAILURE_RECORDS = 4U,
    S540_ALLOC_FAILURE_TOKEN = 5U, S540_ALLOC_FAILURE_SESSION = 6U
};
typedef struct S540DeviceAllocationFailure {
    NvU32 stage, status, pages, contiguous, cache, zeroed, unprotected;
    NvS32 node;
    NvU64 pageBytes;
    NvU32 cpuObservedMask, maxBasic, vendorEbx, vendorEdx, vendorEcx;
    NvU32 signature, family, model, leaf1Ecx, leaf7Ecx;
} S540DeviceAllocationFailure;
/* Private, scalar-only in-kernel diagnostic API. This is not a user RPC or
 * lifetime/cleanup authority. Counters are independently sampled, saturating
 * module-lifetime observations. The first tuple is immutable after publication;
 * its winner is the first observer to reserve the publication slot. */
typedef struct S540DeviceAllocationDiagnostics {
    NvU32 format, bytes, observedMask;
    NvU32 allocationAttemptsLifetime, allocationFailuresLifetime;
    NvU32 entryRejectionsLifetime, largestRequestedPagesLifetime, firstFailureState;
    S540DeviceAllocationFailure firstFailure;
} S540DeviceAllocationDiagnostics;
#ifdef __cplusplus
static_assert(sizeof(S540DeviceAllocationDiagnostics) == 112 &&
              sizeof(S540DeviceAllocationFailure) == 80,
              "Private diagnostic C/C++ layout changed");
extern "C" {
#else
_Static_assert(sizeof(S540DeviceAllocationDiagnostics) == 112 &&
               sizeof(S540DeviceAllocationFailure) == 80,
               "Private diagnostic C/C++ layout changed");
#endif
/* Ordinary master thread after actual original-wrapper return only. Failure
 * leaves *out unchanged. No binding, Session or allocation array is read.
 * Exact state identity is compared by the actual FirstTxn record getter. */
NV_STATUS s540DeviceReadAllocationDiagnostics(const void *exactNv,
    S540DeviceAllocationDiagnostics *out);
#ifdef __cplusplus
}
#endif
#endif
