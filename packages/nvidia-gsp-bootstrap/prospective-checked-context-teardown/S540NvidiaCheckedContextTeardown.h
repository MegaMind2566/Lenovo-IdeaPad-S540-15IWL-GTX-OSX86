/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_CHECKED_CONTEXT_TEARDOWN_H
#define S540_NVIDIA_CHECKED_CONTEXT_TEARDOWN_H
/* The selected source includes nv.h before this private bridge. The composed
 * namespace maps these exact original-owned symbols to their private names. */
#include "nv.h"
NV_STATUS NV_API_CALL s540RmDisableAdapterChecked(nvidia_stack_t *, nv_state_t *);
NV_STATUS NV_API_CALL s540RmShutdownAdapterChecked(nvidia_stack_t *, nv_state_t *);
#endif
