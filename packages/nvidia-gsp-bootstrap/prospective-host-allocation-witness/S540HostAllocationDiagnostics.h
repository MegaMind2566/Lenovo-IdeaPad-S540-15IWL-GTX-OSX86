/* SPDX-License-Identifier: MIT */
#ifndef S540_HOST_ALLOCATION_DIAGNOSTICS_H
#define S540_HOST_ALLOCATION_DIAGNOSTICS_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
enum S540HostAllocationProducer {
    S540_HOST_ALLOCATION_PRODUCER_UNKNOWN = 0U,
    S540_HOST_ALLOCATION_PRODUCER_OS_ALLOC_CONTEXT = 1U,
    S540_HOST_ALLOCATION_PRODUCER_ACPI_D3COLD = 2U,
    S540_HOST_ALLOCATION_PRODUCER_ACPI_DDC = 3U,
    S540_HOST_ALLOCATION_PRODUCER_ACPI_DOD = 4U,
    S540_HOST_ALLOCATION_PRODUCER_ACPI_DSM = 5U,
    S540_HOST_ALLOCATION_PRODUCER_ACPI_POWERSOURCE = 6U,
    S540_HOST_ALLOCATION_PRODUCER_ACPI_MUX = 7U,
    S540_HOST_ALLOCATION_PRODUCER_ACPI_INIT_NULL = 8U,
    S540_HOST_ALLOCATION_PRODUCER_COUNT = 9U
};
enum {
    S540_HOST_ALLOCATION_DIAG_PRODUCER_COUNTS = 1U,
    S540_HOST_ALLOCATION_DIAG_ALLOCATION_COUNTS = 2U,
    S540_HOST_ALLOCATION_DIAG_PRODUCER_FIRST = 4U,
    S540_HOST_ALLOCATION_DIAG_ALLOCATION_FIRST = 8U
};
/* Private scalar data. Producer counts cover only instrumented producers;
 * other generic unavailable calls are deliberately outside this subset.
 * Both counter families concern module lifetime and are sampled separately.
 * Immutable first tuples belong to reservation winners, not a causal order.
 * No value grants admission, cleanup, physical release or a retry.
 */
typedef struct S540HostAllocationDiagnostics {
    NvU32 format, bytes, observedMask, producerCallsLifetime;
    NvU32 producerMask, producerFirstState, producerFirstId, producerFirstService;
    NvU32 producerCalls[S540_HOST_ALLOCATION_PRODUCER_COUNT];
    NvU32 allocationFailuresLifetime, allocationStagesMask, allocationFirstState;
    NvU32 allocationFirstStage, allocationFirstStatus, allocationFirstOriginal;
    NvU32 reserved;
    NvU64 allocationFirstBytes;
} S540HostAllocationDiagnostics;
#ifdef __cplusplus
static_assert(sizeof(S540HostAllocationDiagnostics) == 104,
              "Private Host allocation observation layout changed");
extern "C" {
#else
_Static_assert(sizeof(S540HostAllocationDiagnostics) == 104,
               "Private Host allocation observation layout changed");
#endif
/* Calls the unchanged aggregate observer first, then observes this producer.
 * Invalid producer IDs are attributed to the explicit unknown bucket.
 */
void s540GlobalRmRecordUnavailableProducer(NvU32 service, NvU32 producer);
/* Exact nv, ordinary master thread, after actual original wrapper returned.
 * Failure leaves *out untouched. Fixed atomic/immutable observation storage
 * only; no live allocation traversal, HostSnapshot, reset or wire extension.
 */
NV_STATUS s540GlobalRmReadAllocationDiagnostics(const void *exactNv,
    S540HostAllocationDiagnostics *out);
#ifdef __cplusplus
}
#endif
#endif
