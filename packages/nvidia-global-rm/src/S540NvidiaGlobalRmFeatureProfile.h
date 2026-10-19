/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GLOBAL_RM_FEATURE_PROFILE_H
#define S540_NVIDIA_GLOBAL_RM_FEATURE_PROFILE_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
/* Immutable OS-backend policy, not observations about absent GPU hardware.
 * IMEX=0 is the original documented disabled-channel configuration.
 */
#define S540_GLOBAL_RM_FEATURE_PROFILE_VERSION 1U
#define S540_GLOBAL_RM_IMEX_CHANNEL_COUNT 0
#ifdef __cplusplus
extern "C" {
#endif
/* Inspect the actual original-layout state and completed platform facts.
 * This does not establish queue/IRQ/power/stack readiness or admit RM entry.
 */
NV_STATUS s540GlobalRmFeatureProfilePreflight(const void *originalState);
NvU32 s540GlobalRmFeatureProfileVersion(void);
#ifdef __cplusplus
}
#endif
#endif
