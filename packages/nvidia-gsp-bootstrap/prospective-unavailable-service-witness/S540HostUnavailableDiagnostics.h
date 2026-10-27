/* SPDX-License-Identifier: MIT */
#ifndef S540_HOST_UNAVAILABLE_DIAGNOSTICS_H
#define S540_HOST_UNAVAILABLE_DIAGNOSTICS_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
enum S540HostUnavailableSite {
    S540_HOST_UNAVAILABLE_EXTERNAL = 0U,
    S540_HOST_UNAVAILABLE_SHUTDOWN_ORDINARY = 1U,
    S540_HOST_UNAVAILABLE_ALLOCATE_ORDINARY = 2U,
    S540_HOST_UNAVAILABLE_FREE_ORDINARY = 3U,
    S540_HOST_UNAVAILABLE_FREE_PERMIT = 4U,
    S540_HOST_UNAVAILABLE_FREE_COMPLETION = 5U,
    S540_HOST_UNAVAILABLE_SNAPSHOT_ORDINARY = 6U,
    S540_HOST_UNAVAILABLE_SERVICE_RANGE = 7U,
    S540_HOST_UNAVAILABLE_NULL_SERVICE_NAME = 8U,
    S540_HOST_UNAVAILABLE_SERVICE_TABLE_FULL = 9U,
    S540_HOST_UNAVAILABLE_SITE_COUNT = 10U
};
enum {
    S540_HOST_UNAVAILABLE_DIAG_COUNTS = 1U,
    S540_HOST_UNAVAILABLE_DIAG_FIRST = 2U
};
/* Private in-kernel scalar observations, never a user RPC or cleanup permit.
 * Module-lifetime counters are independently sampled and saturating. Site0
 * denotes the external aggregate API; service0 at that site remains ambiguous.
 * The immutable first tuple belongs to the first successful reservation winner.
 */
typedef struct S540HostUnavailableDiagnostics {
    NvU32 format, bytes, observedMask, unavailableCallsLifetime;
    NvU32 sitesObservedMask, firstState, firstSite, firstService;
    NvU32 siteCallsLifetime[S540_HOST_UNAVAILABLE_SITE_COUNT];
} S540HostUnavailableDiagnostics;
#ifdef __cplusplus
static_assert(sizeof(S540HostUnavailableDiagnostics) == 72,
              "Private unavailable diagnostic layout changed");
extern "C" {
#else
_Static_assert(sizeof(S540HostUnavailableDiagnostics) == 72,
               "Private unavailable diagnostic layout changed");
#endif
/* Exact bound nv, ordinary master thread after the actual wrapper returned.
 * Failure preserves *out. Reads only private atomic observation storage and
 * an acquire-published immutable first tuple; never calls HostSnapshot.
 */
NV_STATUS s540GlobalRmReadUnavailableDiagnostics(const void *exactNv,
    S540HostUnavailableDiagnostics *out);
#ifdef __cplusplus
}
#endif
#endif
