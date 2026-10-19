/* SPDX-License-Identifier: MIT; CPU-only introspection, never authorization. */
#ifndef S540_GLOBAL_OWNER_CHECK_PROBE_H
#define S540_GLOBAL_OWNER_CHECK_PROBE_H
#include "S540NvidiaGlobalRm.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct S540GlobalOwnerCheckProbe {
    NvU64 generation, masterThread;
    const void *owner, *nv;
    NvU32 phase, firstStatus, firstSite, unknownRetainedObjects, inFlightFreePermits;
} S540GlobalOwnerCheckProbe;
void s540GlobalOwnerCheckProbe(S540GlobalOwnerCheckProbe *out);
#ifdef __cplusplus
}
#endif
#endif
