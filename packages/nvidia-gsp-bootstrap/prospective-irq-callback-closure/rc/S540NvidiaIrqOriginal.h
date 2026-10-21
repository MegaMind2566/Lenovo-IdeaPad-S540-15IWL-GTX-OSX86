/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_IRQ_ORIGINAL_H
#define S540_NVIDIA_IRQ_ORIGINAL_H
#include "nvtypes.h"
#include "nvstatus.h"
struct nvidia_stack_s;
struct nv_state_t;
#ifdef __cplusplus
extern "C" {
#endif
/* Internal typed original-ABI helpers. Only the exact ordinary transaction
 * master may call these with its retained stack and live original nv owner.
 * Successful masking is no hardware-DMA-stop or final-release receipt. */
NV_STATUS s540FirstTxnIrqMaskHardware(struct nvidia_stack_s *, struct nv_state_t *);
NV_STATUS s540FirstTxnDrainQueued1Hz(struct nvidia_stack_s *, struct nv_state_t *);
#ifdef __cplusplus
}
#endif
#endif
