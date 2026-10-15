/* SPDX-License-Identifier: MIT */
/*
 * Narrow interface for three original NVIDIA allocator callers.
 * This is not the complete NvPort MEMORY or tracked-allocator interface.
 * All NVIDIA ABI types and calling conventions reuse the pinned adapter inputs.
 */
#ifndef S540_NVPORT_ALLOCATOR_CALLERS_H
#define S540_NVPORT_ALLOCATOR_CALLERS_H

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

NV_STATUS NV_API_CALL os_alloc_mem(void **, NvU64);
void NV_API_CALL os_free_mem(void *);

void *_portMemAllocPagedUntracked(NvLength);
void *_portMemAllocNonPagedUntracked(NvLength);
void _portMemFreeUntracked(void *);

#ifdef __cplusplus
}
#endif

#endif /* S540_NVPORT_ALLOCATOR_CALLERS_H */
