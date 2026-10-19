/* SPDX-License-Identifier: MIT */
#ifndef S540_NV_UNSUPPORTED_MEMORY_H
#define S540_NV_UNSUPPORTED_MEMORY_H
#include "nv_device_services.h"
struct dma_buf;
struct sg_table;
struct drm_gem_object;
typedef struct nv_dma_buf nv_dma_buf_t;
#ifdef __cplusplus
extern "C" {
#endif
/* These interfaces do not manufacture Linux page, GEM or user-map objects. */
NV_STATUS NV_API_CALL s540Global_nv_alias_pages(nv_state_t *, NvU32, NvU64,
    NvU32, NvU32, NvU64, NvU64 *, NvBool, void **);
NV_STATUS NV_API_CALL s540Global_nv_alloc_user_mapping(nv_state_t *, void *,
    NvU64, NvU32, NvU64, NvU32, NvU64 *, void **);
void NV_API_CALL s540Global_nv_free_user_mapping(nv_state_t *, void *, NvU64, void *);
NV_STATUS NV_API_CALL s540Global_nv_register_peer_io_mem(nv_state_t *, NvU64 *, NvU64, void **);
void NV_API_CALL s540Global_nv_unregister_peer_io_mem(nv_state_t *, void *);
NV_STATUS NV_API_CALL s540Global_nv_register_phys_pages(nv_state_t *, NvU64 *, NvU64, NvU32, void **);
void NV_API_CALL s540Global_nv_unregister_phys_pages(nv_state_t *, void *);
NV_STATUS NV_API_CALL s540Global_nv_register_user_pages(nv_state_t *, NvU64, NvU64 *, void *, void **, NvBool);
void NV_API_CALL s540Global_nv_unregister_user_pages(nv_state_t *, NvU64, void **, void **);
NV_STATUS NV_API_CALL s540Global_nv_register_sgt(nv_state_t *, NvU64 *, NvU64,
    NvU32, void **, struct sg_table *, void *, NvBool);
void NV_API_CALL s540Global_nv_unregister_sgt(nv_state_t *, struct sg_table **, void **, void *);
NV_STATUS NV_API_CALL s540Global_nv_get_phys_pages(void *, void *, NvU32 *);
NV_STATUS NV_API_CALL s540Global_nv_dma_map_peer(nv_dma_device_t *, nv_dma_device_t *, NvU8, NvU64, NvU64 *);
void NV_API_CALL s540Global_nv_dma_unmap_peer(nv_dma_device_t *, NvU64, NvU64);
NV_STATUS NV_API_CALL s540Global_nv_dma_map_mmio(nv_dma_device_t *, NvU64, NvU64 *);
void NV_API_CALL s540Global_nv_dma_unmap_mmio(nv_dma_device_t *, NvU64, NvU64);
NV_STATUS NV_API_CALL s540Global_nv_dma_import_sgt(nv_dma_device_t *, struct sg_table *, struct drm_gem_object *);
void NV_API_CALL s540Global_nv_dma_release_sgt(struct sg_table *, struct drm_gem_object *);
NV_STATUS NV_API_CALL s540Global_nv_dma_import_dma_buf(nv_dma_device_t *, struct dma_buf *,
    NvBool, NvU32 *, struct sg_table **, nv_dma_buf_t **);
NV_STATUS NV_API_CALL s540Global_nv_dma_import_from_fd(nv_dma_device_t *, NvS32,
    NvBool, NvU32 *, struct sg_table **, nv_dma_buf_t **);
void NV_API_CALL s540Global_nv_dma_release_dma_buf(nv_dma_buf_t *);
NV_STATUS NV_API_CALL s540Global_nv_dma_init_sysmem_window_for_fabric_access(nv_state_t *,
    NvU64, NvU64 *, NvU64 *, NvBool *);
void NV_API_CALL s540Global_nv_dma_destroy_sysmem_window_for_fabric_access(nv_state_t *, NvU64, NvU64);
NV_STATUS NV_API_CALL s540Global_nv_get_device_memory_config(nv_state_t *,
    NvU64 *, NvU64 *, NvU64 *, NvU64 *, NvU32 *, NvS32 *);
NV_STATUS NV_API_CALL s540Global_nv_get_egm_info(nv_state_t *, NvU64 *, NvU64 *, NvS32 *);
NV_STATUS NV_API_CALL s540Global_os_alloc_pages_node(NvS32, NvU32, NvU32, NvU64 *);
NV_STATUS NV_API_CALL s540Global_os_get_page(NvU64);
NV_STATUS NV_API_CALL s540Global_os_put_page(NvU64);
NvU32 NV_API_CALL s540Global_os_get_page_refcount(NvU64);
NvU32 NV_API_CALL s540Global_os_count_tail_pages(NvU64);
NV_STATUS NV_API_CALL s540Global_os_numa_memblock_size(NvU64 *);
NV_STATUS NV_API_CALL s540Global_os_get_numa_node_memory_usage(NvS32, NvU64 *, NvU64 *);
NV_STATUS NV_API_CALL s540Global_os_numa_add_gpu_memory(void *, NvU64, NvU64, NvU32 *);
NV_STATUS NV_API_CALL s540Global_os_numa_remove_gpu_memory(void *, NvU64, NvU64, NvU32);
NV_STATUS NV_API_CALL s540Global_os_offline_page_at_address(NvU64);
NV_STATUS NV_API_CALL s540Global_os_unlock_user_pages(NvU64, void *, NvU32);
NV_STATUS NV_API_CALL s540Global_os_flush_cpu_cache_all(void);
NV_STATUS NV_API_CALL s540Global_os_flush_user_cache(void);
NV_STATUS NV_API_CALL s540Global_os_iommu_sva_bind(void *, void **, NvU32 *);
void NV_API_CALL s540Global_os_iommu_sva_unbind(void *);
__attribute__((noreturn)) void s540DeviceMemoryContractViolation(const char *);
typedef struct {
    NvU32 disabledFeatureQueries;
    NvU32 unavailableOperations;
    NvU32 officialNoopReleases;
    NvU32 lifetimeViolations;
    NvU32 unavailableOperationsEver;
    NvU32 lifetimeViolationsEver;
} S540DeviceMemoryStatistics;
S540DeviceMemoryStatistics s540DeviceMemoryStatistics(void);
/* Native controls may reset ordinary telemetry while quiescent. Sticky error
 * counters are lifetime-monotonic, including in native controls. Production
 * has no reset API that could erase an earlier refused operation.
 */
#if !defined(KERNEL)
void s540DeviceMemoryResetStatistics(void);
#endif
#ifdef __cplusplus
}
#endif
#endif
