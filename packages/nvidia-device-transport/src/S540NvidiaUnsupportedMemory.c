/* SPDX-License-Identifier: MIT */
/* Compile against the pinned original RM headers and forced namespace, just
 * like the other C bridges. This profile owns wired pages through Session;
 * it has no Linux page/GEM/DMA-BUF objects, userspace mapping or NUMA hotplug.
 */
#include "nv.h"
#include "os-interface.h"
#include "nv_unsupported_memory.h"

_Static_assert(__atomic_always_lock_free(sizeof(NvU32), 0),
               "Memory callback counters must not add a runtime lock");
static S540DeviceMemoryStatistics statistics;
static void bump(NvU32 *counter)
{
    NvU32 value = __atomic_load_n(counter, __ATOMIC_RELAXED);
    while (value != NV_U32_MAX &&
        !__atomic_compare_exchange_n(counter, &value, value + 1, 0,
                                     __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}
S540DeviceMemoryStatistics s540DeviceMemoryStatistics(void)
{
    S540DeviceMemoryStatistics captured;
    captured.disabledFeatureQueries = __atomic_load_n(&statistics.disabledFeatureQueries, __ATOMIC_RELAXED);
    captured.unavailableOperations = __atomic_load_n(&statistics.unavailableOperations, __ATOMIC_RELAXED);
    captured.officialNoopReleases = __atomic_load_n(&statistics.officialNoopReleases, __ATOMIC_RELAXED);
    captured.lifetimeViolations = __atomic_load_n(&statistics.lifetimeViolations, __ATOMIC_RELAXED);
    captured.unavailableOperationsEver = __atomic_load_n(&statistics.unavailableOperationsEver, __ATOMIC_RELAXED);
    captured.lifetimeViolationsEver = __atomic_load_n(&statistics.lifetimeViolationsEver, __ATOMIC_RELAXED);
    return captured;
}
#if !defined(KERNEL)
void s540DeviceMemoryResetStatistics(void)
{
    __atomic_store_n(&statistics.disabledFeatureQueries, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&statistics.unavailableOperations, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&statistics.officialNoopReleases, 0, __ATOMIC_RELAXED);
    __atomic_store_n(&statistics.lifetimeViolations, 0, __ATOMIC_RELAXED);
}
#endif
static NV_STATUS unavailable(void)
{
    bump(&statistics.unavailableOperations);
    bump(&statistics.unavailableOperationsEver);
    return NV_ERR_NOT_SUPPORTED;
}
static NV_STATUS disabledFeature(void)
{
    bump(&statistics.disabledFeatureQueries);
    return NV_ERR_NOT_SUPPORTED;
}
static void disabledRelease(void)
{
    bump(&statistics.officialNoopReleases);
}
static __attribute__((noreturn)) void lifetimeUnavailable(const char *message)
{
    bump(&statistics.lifetimeViolations);
    bump(&statistics.lifetimeViolationsEver);
    s540DeviceMemoryContractViolation(message);
}

NV_STATUS NV_API_CALL s540Global_nv_alias_pages(nv_state_t *nv, NvU32 pages,
    NvU64 pageSize, NvU32 contiguous, NvU32 cache, NvU64 guest,
    NvU64 *ptes, NvBool carveout, void **privateData)
{
    (void)nv; (void)pages; (void)pageSize; (void)contiguous; (void)cache;
    (void)guest; (void)ptes; (void)carveout; (void)privateData;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_nv_alloc_user_mapping(nv_state_t *nv, void *allocation,
    NvU64 pageIndex, NvU32 offset, NvU64 bytes, NvU32 protection,
    NvU64 *address, void **privateData)
{
    (void)nv; (void)allocation; (void)pageIndex; (void)offset; (void)bytes;
    (void)protection; (void)address; (void)privateData;
    return unavailable();
}
/* The original nv-usermap.c implementation is empty on every platform. It
 * never releases an allocation or creates/removes a userspace virtual map.
 */
void NV_API_CALL s540Global_nv_free_user_mapping(nv_state_t *nv, void *allocation,
    NvU64 address, void *privateData)
{
    (void)nv; (void)allocation; (void)address; (void)privateData;
    disabledRelease();
}
NV_STATUS NV_API_CALL s540Global_nv_register_peer_io_mem(nv_state_t *nv,
    NvU64 *addresses, NvU64 pages, void **privateData)
{
    (void)nv; (void)addresses; (void)pages; (void)privateData;
    return unavailable();
}
void NV_API_CALL s540Global_nv_unregister_peer_io_mem(nv_state_t *nv, void *privateData)
{
    (void)nv; (void)privateData;
    lifetimeUnavailable("peer IO memory was never admitted");
}
NV_STATUS NV_API_CALL s540Global_nv_register_phys_pages(nv_state_t *nv,
    NvU64 *addresses, NvU64 pages, NvU32 cache, void **privateData)
{
    (void)nv; (void)addresses; (void)pages; (void)cache; (void)privateData;
    return unavailable();
}
void NV_API_CALL s540Global_nv_unregister_phys_pages(nv_state_t *nv, void *privateData)
{
    (void)nv; (void)privateData;
    lifetimeUnavailable("external physical memory was never admitted");
}
NV_STATUS NV_API_CALL s540Global_nv_register_user_pages(nv_state_t *nv,
    NvU64 pages, NvU64 *addresses, void *importPrivate, void **privateData, NvBool unencrypted)
{
    (void)nv; (void)pages; (void)addresses; (void)importPrivate;
    (void)privateData; (void)unencrypted;
    return unavailable();
}
void NV_API_CALL s540Global_nv_unregister_user_pages(nv_state_t *nv, NvU64 pages,
    void **importPrivate, void **privateData)
{
    (void)nv; (void)pages; (void)importPrivate; (void)privateData;
    lifetimeUnavailable("Linux user pages were never admitted");
}
NV_STATUS NV_API_CALL s540Global_nv_register_sgt(nv_state_t *nv,
    NvU64 *addresses, NvU64 pages, NvU32 cache, void **privateData,
    struct sg_table *sgt, void *importPrivate, NvBool peerMmio)
{
    (void)nv; (void)addresses; (void)pages; (void)cache; (void)privateData;
    (void)sgt; (void)importPrivate; (void)peerMmio;
    return unavailable();
}
void NV_API_CALL s540Global_nv_unregister_sgt(nv_state_t *nv,
    struct sg_table **sgt, void **importPrivate, void *privateData)
{
    (void)nv; (void)sgt; (void)importPrivate; (void)privateData;
    lifetimeUnavailable("Linux scatterlist memory was never admitted");
}
NV_STATUS NV_API_CALL s540Global_nv_get_phys_pages(void *allocation,
    void *pages, NvU32 *pageCount)
{
    /* Original output is struct page **, not an array of physical addresses. */
    (void)allocation; (void)pages; (void)pageCount;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_nv_dma_map_peer(nv_dma_device_t *dma,
    nv_dma_device_t *peer, NvU8 bar, NvU64 pages, NvU64 *address)
{
    (void)dma; (void)peer; (void)bar; (void)pages; (void)address;
    return unavailable();
}
void NV_API_CALL s540Global_nv_dma_unmap_peer(nv_dma_device_t *dma,
    NvU64 pages, NvU64 address)
{
    (void)dma; (void)pages; (void)address;
    lifetimeUnavailable("peer DMA was never admitted");
}
NV_STATUS NV_API_CALL s540Global_nv_dma_map_mmio(nv_dma_device_t *dma,
    NvU64 pages, NvU64 *address)
{
    (void)dma; (void)pages; (void)address;
    return unavailable();
}
void NV_API_CALL s540Global_nv_dma_unmap_mmio(nv_dma_device_t *dma,
    NvU64 pages, NvU64 address)
{
    (void)dma; (void)pages; (void)address;
    lifetimeUnavailable("MMIO DMA was never admitted");
}
NV_STATUS NV_API_CALL s540Global_nv_dma_import_sgt(nv_dma_device_t *dma,
    struct sg_table *sgt, struct drm_gem_object *gem)
{
    (void)dma; (void)sgt; (void)gem;
    return unavailable();
}
/* Match the actual original CONFIG_DRM-disabled branch. No GEM reference
 * exists in this profile and nv_dma_import_sgt never succeeds.
 */
void NV_API_CALL s540Global_nv_dma_release_sgt(struct sg_table *sgt,
    struct drm_gem_object *gem)
{
    (void)sgt; (void)gem;
    disabledRelease();
}
NV_STATUS NV_API_CALL s540Global_nv_dma_import_dma_buf(nv_dma_device_t *dma,
    struct dma_buf *buffer, NvBool readOnly, NvU32 *bytes,
    struct sg_table **sgt, nv_dma_buf_t **privateData)
{
    (void)dma; (void)buffer; (void)readOnly; (void)bytes; (void)sgt; (void)privateData;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_nv_dma_import_from_fd(nv_dma_device_t *dma,
    NvS32 descriptor, NvBool readOnly, NvU32 *bytes,
    struct sg_table **sgt, nv_dma_buf_t **privateData)
{
    (void)dma; (void)descriptor; (void)readOnly; (void)bytes; (void)sgt; (void)privateData;
    return unavailable();
}
/* Match the original CONFIG_DMA_SHARED_BUFFER-disabled branch. */
void NV_API_CALL s540Global_nv_dma_release_dma_buf(nv_dma_buf_t *privateData)
{
    (void)privateData;
    disabledRelease();
}
NV_STATUS NV_API_CALL s540Global_nv_dma_init_sysmem_window_for_fabric_access(
    nv_state_t *nv, NvU64 alignment, NvU64 *address, NvU64 *bytes, NvBool *identity)
{
    (void)nv; (void)alignment; (void)address; (void)bytes; (void)identity;
    return unavailable();
}
void NV_API_CALL s540Global_nv_dma_destroy_sysmem_window_for_fabric_access(
    nv_state_t *nv, NvU64 address, NvU64 bytes)
{
    (void)nv; (void)address; (void)bytes;
    lifetimeUnavailable("fabric sysmem window was never admitted");
}
/* This is also the exact original nv.c branch for the x86 profile. */
NV_STATUS NV_API_CALL s540Global_nv_get_device_memory_config(nv_state_t *nv,
    NvU64 *compressed, NvU64 *guest, NvU64 *bytes, NvU64 *reserved,
    NvU32 *width, NvS32 *node)
{
    (void)nv; (void)compressed; (void)guest; (void)bytes; (void)reserved;
    (void)width; (void)node;
    return disabledFeature();
}
NV_STATUS NV_API_CALL s540Global_nv_get_egm_info(nv_state_t *nv,
    NvU64 *address, NvU64 *bytes, NvS32 *node)
{
    (void)nv; (void)address; (void)bytes; (void)node;
    return disabledFeature();
}
NV_STATUS NV_API_CALL s540Global_os_alloc_pages_node(NvS32 node,
    NvU32 bytes, NvU32 flags, NvU64 *address)
{
    (void)node; (void)bytes; (void)flags; (void)address;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_os_get_page(NvU64 address)
{
    (void)address;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_os_put_page(NvU64 address)
{
    (void)address;
    return unavailable();
}
NvU32 NV_API_CALL s540Global_os_get_page_refcount(NvU64 address)
{
    (void)address;
    lifetimeUnavailable("Linux page reference count is unavailable");
}
NvU32 NV_API_CALL s540Global_os_count_tail_pages(NvU64 address)
{
    (void)address;
    lifetimeUnavailable("Linux compound-page count is unavailable");
}
NV_STATUS NV_API_CALL s540Global_os_numa_memblock_size(NvU64 *bytes)
{
    (void)bytes;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_os_get_numa_node_memory_usage(NvS32 node,
    NvU64 *freeBytes, NvU64 *totalBytes)
{
    (void)node; (void)freeBytes; (void)totalBytes;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_os_numa_add_gpu_memory(void *handle,
    NvU64 offset, NvU64 bytes, NvU32 *node)
{
    (void)handle; (void)offset; (void)bytes; (void)node;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_os_numa_remove_gpu_memory(void *handle,
    NvU64 offset, NvU64 bytes, NvU32 node)
{
    (void)handle; (void)offset; (void)bytes; (void)node;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_os_offline_page_at_address(NvU64 address)
{
    (void)address;
    return unavailable();
}
NV_STATUS NV_API_CALL s540Global_os_unlock_user_pages(NvU64 pages,
    void *pageArray, NvU32 flags)
{
    (void)pages; (void)pageArray; (void)flags;
    return unavailable();
}
/* Exact original non-AARCH64 branches: no successful cache flush is claimed. */
NV_STATUS NV_API_CALL s540Global_os_flush_cpu_cache_all(void)
{
    return disabledFeature();
}
NV_STATUS NV_API_CALL s540Global_os_flush_user_cache(void)
{
    return disabledFeature();
}
NV_STATUS NV_API_CALL s540Global_os_iommu_sva_bind(void *argument,
    void **handle, NvU32 *pasid)
{
    (void)argument; (void)handle; (void)pasid;
    return unavailable();
}
/* Exact original CONFIG_IOMMU_SVA-disabled branch. Bind never admits a handle. */
void NV_API_CALL s540Global_os_iommu_sva_unbind(void *handle)
{
    (void)handle;
    disabledRelease();
}
