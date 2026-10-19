/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_CONTROL_STATE_H
#define S540_NVIDIA_CONTROL_STATE_H
#include "nvtypes.h"
#include "nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
/* One permanent, non-character-device control state. No descriptor/event
 * registration or final-release interface exists in this selected profile. */
NV_STATUS s540ControlStatePrepare(void);
NV_STATUS s540ControlStateBindAdapter(const void *exactNv);
#ifdef __cplusplus
}
#endif
#endif
