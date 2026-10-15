/* SPDX-License-Identifier: MIT */
/*
 * Narrow interface for four adapted NVIDIA normal-RAM callers and Darwin hooks.
 * Types and calling conventions come from the unmodified NVIDIA headers.
 * This is not an allocator, user-copy, DMA, MMIO, or complete memory interface.
 */
#ifndef S540_NVPORT_MEMORY_PRIMITIVES_H
#define S540_NVPORT_MEMORY_PRIMITIVES_H

#include "include/nvtypes.h"
#include "include/nv-kernel-interface-api.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void *NV_API_CALL os_mem_copy(void *, const void *, NvU32);
void *NV_API_CALL os_mem_set(void *, NvU8, NvU32);
NvS32 NV_API_CALL os_mem_cmp(const NvU8 *, const NvU8 *, NvU32);

void *portMemCopy(void *, NvLength, const void *, NvLength);
void *portMemCopyAligned(void *, NvLength, const void *, NvLength);
void *portMemSet(void *, NvU8, NvLength);
NvS32 portMemCmp(const void *, const void *, NvLength);

/* Private wide-length bridges. These are adapter symbols, not NVIDIA ABI. */
void *s540NvidiaMemoryCopy(void *, const void *, NvLength);
void *s540NvidiaMemorySet(void *, NvU8, NvLength);
NvS32 s540NvidiaMemoryCompare(const NvU8 *, const NvU8 *, NvLength);

#ifdef __cplusplus
}
#endif

#endif /* S540_NVPORT_MEMORY_PRIMITIVES_H */
