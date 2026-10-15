// SPDX-License-Identifier: MIT
#ifndef S540_NV_MEMORY_SERVICES_H
#define S540_NV_MEMORY_SERVICES_H

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

// Exact opaque struct tags and function prototypes transcribed from
// NVIDIA/open-gpu-kernel-modules at 1a82fbfda8f321b056eb3568850f9316c5e465c5,
// kernel-open/common/inc/nv.h lines 450, 464, 961-976 and 994-995.
// No Linux nv_state_t/nv_alloc_t/nv_dma_device layout is redefined here.
typedef struct nv_state_t nv_state_t;
typedef struct nv_dma_device nv_dma_device_t;

// Exact cache value from src/nvidia/inc/kernel/os/nv_memory_type.h line 30.
#define S540_NV_MEMORY_CACHED 0

#ifdef __cplusplus
extern "C" {
#endif

NV_STATUS NV_API_CALL nv_alloc_pages(nv_state_t *, NvU32, NvU64, NvBool,
                                    NvU32, NvBool, NvBool, NvS32,
                                    NvU64 *, void **);
NV_STATUS NV_API_CALL nv_free_pages(nv_state_t *, NvU32, NvBool, NvU32, void *);
void * NV_API_CALL nv_alloc_kernel_mapping(nv_state_t *, void *, NvU64,
                                          NvU32, NvU64, void **);
void NV_API_CALL nv_free_kernel_mapping(nv_state_t *, void *, void *, void *);

// This selected profile has no nv_dma_device owner. These two entry points
// explicitly return NOT_SUPPORTED and preserve their IN/OUT allocation/PTE
// inputs, matching upstream error ownership. No device mapping is fabricated.
NV_STATUS NV_API_CALL nv_dma_map_alloc(nv_dma_device_t *, NvU64, NvU64 *,
                                      NvBool, NvBool, void **);
NV_STATUS NV_API_CALL nv_dma_unmap_alloc(nv_dma_device_t *, NvU64,
                                        NvU64 *, void **);

#ifdef __cplusplus
}
#endif
#endif
