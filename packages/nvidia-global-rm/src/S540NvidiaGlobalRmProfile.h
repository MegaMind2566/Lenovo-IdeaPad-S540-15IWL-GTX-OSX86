/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GLOBAL_RM_PROFILE_H
#define S540_NVIDIA_GLOBAL_RM_PROFILE_H

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"

/* These are selected backend capabilities, not observations about hardware.
 * Darwin platform power ownership remains a separate mandatory admission gate.
 */
#define S540_GLOBAL_RM_PROFILE_VERSION 2U
#define S540_GLOBAL_RM_ACPI_EVENTS_ENABLED 0

#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS s540GlobalRmInitializeRegistryProfile(void);
NV_STATUS s540GlobalRmCheckRegistryProfile(void);
NV_STATUS s540GlobalRmCheckRegistryCold(void);
#ifdef __cplusplus
}
#endif

#endif
