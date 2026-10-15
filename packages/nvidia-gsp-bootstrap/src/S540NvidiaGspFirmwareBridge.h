/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_FIRMWARE_BRIDGE_H
#define S540_NVIDIA_GSP_FIRMWARE_BRIDGE_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#ifdef __cplusplus
extern "C" {
#endif
const void *s540GspFirmwareAcquire(const void *, NvU32, NvU32, const void **, NvU32 *);
void s540GspFirmwareRelease(const void *);
#ifdef __cplusplus
}
#endif
#endif
