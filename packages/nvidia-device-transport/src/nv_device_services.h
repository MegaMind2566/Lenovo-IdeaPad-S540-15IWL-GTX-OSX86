// SPDX-License-Identifier: MIT
#ifndef S540_NV_DEVICE_SERVICES_H
#define S540_NV_DEVICE_SERVICES_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"
typedef struct nv_state_t nv_state_t;
typedef struct nv_dma_device nv_dma_device_t;
#ifdef __cplusplus
extern "C" {
#endif
// Exact NVIDIA nv.h signatures, link-isolated for the complete RM profile.
NV_STATUS NV_API_CALL s540Global_nv_alloc_pages(nv_state_t *, NvU32, NvU64,
    NvBool, NvU32, NvBool, NvBool, NvS32, NvU64 *, void **);
NV_STATUS NV_API_CALL s540Global_nv_free_pages(nv_state_t *, NvU32, NvBool,
    NvU32, void *);
void *NV_API_CALL s540Global_nv_alloc_kernel_mapping(nv_state_t *, void *,
    NvU64, NvU32, NvU64, void **);
void NV_API_CALL s540Global_nv_free_kernel_mapping(nv_state_t *, void *, void *, void *);
NV_STATUS NV_API_CALL s540Global_nv_dma_map_alloc(nv_dma_device_t *, NvU64,
    NvU64 *, NvBool, NvBool, void **);
NV_STATUS NV_API_CALL s540Global_nv_dma_unmap_alloc(nv_dma_device_t *, NvU64,
    NvU64 *, void **);
void NV_API_CALL s540Global_nv_set_dma_address_size(nv_state_t *, NvU32);
NvBool NV_API_CALL s540Global_nv_requires_dma_remap(nv_state_t *);
NV_STATUS NV_API_CALL s540Global_nv_get_num_phys_pages(void *, NvU32 *);
NvU64 NV_API_CALL s540Global_nv_get_kern_phys_address(NvU64);
void *NV_API_CALL s540Global_os_pci_init_handle(NvU32, NvU8, NvU8, NvU8, NvU16 *, NvU16 *);
NV_STATUS NV_API_CALL s540Global_os_pci_read_byte(void *, NvU32, NvU8 *);
NV_STATUS NV_API_CALL s540Global_os_pci_read_word(void *, NvU32, NvU16 *);
NV_STATUS NV_API_CALL s540Global_os_pci_read_dword(void *, NvU32, NvU32 *);
NV_STATUS NV_API_CALL s540Global_os_pci_write_byte(void *, NvU32, NvU8);
NV_STATUS NV_API_CALL s540Global_os_pci_write_word(void *, NvU32, NvU16);
NV_STATUS NV_API_CALL s540Global_os_pci_write_dword(void *, NvU32, NvU32);
void *NV_API_CALL s540Global_os_map_kernel_space(NvU64, NvU64, NvU32);
void NV_API_CALL s540Global_os_unmap_kernel_space(void *, NvU64);
NvBool NV_API_CALL s540Global_nv_is_gpu_accessible(nv_state_t *);
NvBool NV_API_CALL s540Global_nv_match_gpu_os_info(nv_state_t *, void *);
void NV_API_CALL s540Global_nv_flush_coherent_cpu_cache_range(nv_state_t *, NvU64, NvU64);
void NV_API_CALL s540Global_nv_dma_cache_invalidate(nv_dma_device_t *, void *);
#ifdef __cplusplus
}
#include "S540NvidiaDeviceTransport.hpp"
namespace S540NvidiaDeviceTransport {
// All binding and ABI calls are ordinary-thread and externally serialized by
// the complete RM device owner. Opaque identities are compared, not dereferenced.
NV_STATUS bindRmDevice(Session *session, nv_state_t *state, nv_dma_device_t *dma);
NV_STATUS unbindRmDevice(Session *session);
// Call after a successful real interrupt drain and before unbinding. Progress
// is recorded per allocation; a failed backend completion retains its owner.
NV_STATUS drainRmRetirements(Session *session);
// Unlike the original scalar ABI, the admission query can report unknown
// policy. A coordinator must check it before allowing an RM entry to execute.
NV_STATUS queryRmDmaRemap(nv_state_t *state, NvBool &required);
struct AbiStatistics {
    NvU32 allocations; NvU32 mappings; NvU32 dmaMappings; bool bound;
    NvU32 retiredAllocations; NvU32 retiredDmaMappings;
};
AbiStatistics abiStatistics();
Session *boundRmSession();
void *boundPciHandle();
}
#endif
#endif
