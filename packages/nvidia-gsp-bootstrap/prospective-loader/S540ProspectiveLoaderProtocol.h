/* SPDX-License-Identifier: MIT */
#ifndef S540_PROSPECTIVE_LOADER_PROTOCOL_H
#define S540_PROSPECTIVE_LOADER_PROTOCOL_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#define S540_PROSPECTIVE_PROTOCOL_VERSION 1U
#define S540_PROSPECTIVE_CONNECTION_TYPE 0x53353430U
#define S540_PROSPECTIVE_SELECTOR_SNAPSHOT 0U
#define S540_PROSPECTIVE_SELECTOR_REQUEST 1U
/* The interface accepts a generation and request only, never an admission or
 * target-link Boolean. All production entry policies remain closed.
 */
typedef enum S540ProspectivePhase {
    S540_PROSPECTIVE_COLD = 0,
    S540_PROSPECTIVE_MODULE_ENTERED = 1,
    S540_PROSPECTIVE_CONTROL_STARTED = 2,
    S540_PROSPECTIVE_ENTRY_BLOCKED = 3,
    S540_PROSPECTIVE_STOPPING = 4,
    S540_PROSPECTIVE_STOPPED = 5
} S540ProspectivePhase;
typedef struct S540ProspectiveSnapshot {
    NvU32 format;
    NvU32 bytes;
    NvU32 phase;
    NV_STATUS lastStatus;
    NvU64 generation;
    NvU32 moduleEntryAccepted;
    NvU32 controlServiceStarted;
    NvU32 rootRequestConsumed;
    NvU32 requestsAccepted;
    NvU32 entryPolicyClosed;
    NvU32 targetLoaderAdmissionProven;
    NvU32 originalCalls;
    NvU32 providerPreparations;
    NvU32 pmRegistrations;
    NvU32 stopping;
} S540ProspectiveSnapshot;
typedef struct S540ProspectiveRequest {
    NvU32 format;
    NvU32 bytes;
    NvU64 generation;
} S540ProspectiveRequest;
#endif
