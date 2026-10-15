/* SPDX-License-Identifier: MIT */
/*
 * Narrow interface for the adapted NVIDIA uptime caller and Darwin backend.
 * NVIDIA types and calling-convention definitions are included unchanged.
 * The three OS hook declarations match reference/os-interface.h exactly.
 * The four portTime declarations match the extracted source signatures.
 */
#ifndef S540_NVPORT_TIME_UPTIME_H
#define S540_NVPORT_TIME_UPTIME_H

#include "include/nvtypes.h"
#include "include/nv-kernel-interface-api.h"

#ifdef __cplusplus
extern "C" {
#endif

NvU64 NV_API_CALL os_get_monotonic_time_ns(void);
NvU64 NV_API_CALL os_get_monotonic_time_ns_hr(void);
NvU64 NV_API_CALL os_get_monotonic_tick_resolution_ns(void);

NvU64 portTimeGetUptimeMicroseconds(void);
NvU64 portTimeGetUptimeNanoseconds(void);
NvU64 portTimeGetUptimeNanosecondsHighPrecision(void);
NvU64 portTimeGetUptimeResolution(void);

#ifdef __cplusplus
}
#endif

#endif /* S540_NVPORT_TIME_UPTIME_H */
