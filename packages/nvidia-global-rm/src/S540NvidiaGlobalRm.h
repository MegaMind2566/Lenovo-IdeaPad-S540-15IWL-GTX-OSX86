// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_GLOBAL_RM_H
#define S540_NVIDIA_GLOBAL_RM_H

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    S540_GLOBAL_FACT_NOTEBOOK = 1U << 0,
    S540_GLOBAL_FACT_BATTERY = 1U << 1,
    S540_GLOBAL_FACT_EFI = 1U << 2,
    S540_GLOBAL_FACT_VGPU_HYPERVISOR = 1U << 3,
    S540_GLOBAL_FACT_NVSWITCH = 1U << 4,
    S540_GLOBAL_FACT_S0IX = 1U << 5,
    S540_GLOBAL_FACT_CPU = 1U << 6,
    S540_GLOBAL_FACT_OS_VERSION = 1U << 7,
    S540_GLOBAL_FACT_ALL = 255U
};

// Every known bit represents a provider/platform query actually completed by
// the caller. Unknown facts refuse startup; this is not a default-value table.
typedef struct S540NvidiaGlobalRmPlatformFacts {
    NvU32 format;
    NvU32 known;
    NvBool notebook;
    NvBool battery;
    NvBool efi;
    NvBool vgpuHypervisor;
    NvBool nvSwitch;
    NvBool s0ix;
    NvU32 cpuCount;
    NvU64 cpuFrequencyHz;
    NvU32 osMajor;
    NvU32 osMinor;
    NvU32 osBuild;
    const char *osVersion;
    const char *osDate;
} S540NvidiaGlobalRmPlatformFacts;

typedef struct S540NvidiaGlobalRmHostSnapshot {
    NvU64 liveBytes;
    NvU64 peakBytes;
    NvU64 largestAllocation;
    NvU64 allocations;
    NvU64 frees;
    NvU32 liveAllocations;
    NvU32 peakAllocations;
    NvU32 allocationFailures;
    NvU32 invalidFrees;
    NvU32 unavailableCalls;
    NvBool initialized;
} S540NvidiaGlobalRmHostSnapshot;

typedef struct S540NvidiaGlobalRmResult {
    NvU32 format;
    NvU32 startupStatus;
    NvBool initialized;
    NvBool systemObject;
    NvBool children;
    NvBool resourceServer;
    NvBool memoryExportClient;
    NvBool cleanShutdown;
    NvU32 presentChildren;
    NvU32 expectedChildren;
    NvU32 unavailableCalls;
    NvU64 osServiceMask;
} S540NvidiaGlobalRmResult;

// Host context persists through adapter shutdown. It must not be initialized
// while any v9 standalone runtime is active. All calls require ordinary thread
// context under the outer startup lease; this API does not take a second lease.
NV_STATUS s540GlobalRmHostInitialize(const S540NvidiaGlobalRmPlatformFacts *facts);
NvBool s540GlobalRmHostShutdown(void);
void s540GlobalRmHostSnapshot(S540NvidiaGlobalRmHostSnapshot *out);
void *s540GlobalRmHostAllocate(NvU64 bytes);
void s540GlobalRmHostFree(void *pointer);
void s540GlobalRmRecordUnavailable(NvU32 service);
void s540GlobalRmRecordService(NvU32 service);
NvU64 s540GlobalRmServiceMask(void);
void s540GlobalRmRecordServiceName(const char *staticName);
NvU32 s540GlobalRmObservedServices(void);
const char *s540GlobalRmServiceName(NvU32 slot);
NvU64 s540GlobalRmServiceCalls(NvU32 slot);
const S540NvidiaGlobalRmPlatformFacts *s540GlobalRmPlatformFacts(void);

// Development boundary: kernel builds currently refuse before any original
// entry. Native tests execute the actual RS_STANDALONE=0 coreInitializeRm ->
// OBJSYS -> sysConstruct path with explicit CPU/platform fixtures. On native
// success the original global state remains alive until the original global
// destructor path is called. This API does not establish adapter readiness.
NV_STATUS s540GlobalRmInitialize(S540NvidiaGlobalRmResult *out);
void s540GlobalRmShutdown(S540NvidiaGlobalRmResult *out);
NvBool s540GlobalRmIsInitialized(void);

#ifdef __cplusplus
}
#if !defined(KERNEL)
namespace S540NvidiaGlobalRmNative {
// Consumed once by the matching allocation request, before OS allocation.
// Set only under the native harness's outer lifecycle serialization.
void failAllocationAt(NvU64 ordinal);
}
#endif
#endif
#endif
