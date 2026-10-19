/* SPDX-License-Identifier: MIT */
/* Compile with the pinned original-header profile and forced namespace. */
#include "nv.h"
#include "os-interface.h"
typedef __typeof__(&nv_alias_pages) S540Pinned_nv_alias_pages;
typedef __typeof__(&nv_alloc_user_mapping) S540Pinned_nv_alloc_user_mapping;
typedef __typeof__(&nv_free_user_mapping) S540Pinned_nv_free_user_mapping;
typedef __typeof__(&nv_register_peer_io_mem) S540Pinned_nv_register_peer_io_mem;
typedef __typeof__(&nv_unregister_peer_io_mem) S540Pinned_nv_unregister_peer_io_mem;
typedef __typeof__(&nv_register_phys_pages) S540Pinned_nv_register_phys_pages;
typedef __typeof__(&nv_unregister_phys_pages) S540Pinned_nv_unregister_phys_pages;
typedef __typeof__(&nv_register_user_pages) S540Pinned_nv_register_user_pages;
typedef __typeof__(&nv_unregister_user_pages) S540Pinned_nv_unregister_user_pages;
typedef __typeof__(&nv_register_sgt) S540Pinned_nv_register_sgt;
typedef __typeof__(&nv_unregister_sgt) S540Pinned_nv_unregister_sgt;
typedef __typeof__(&nv_get_phys_pages) S540Pinned_nv_get_phys_pages;
typedef __typeof__(&nv_dma_map_peer) S540Pinned_nv_dma_map_peer;
typedef __typeof__(&nv_dma_unmap_peer) S540Pinned_nv_dma_unmap_peer;
typedef __typeof__(&nv_dma_map_mmio) S540Pinned_nv_dma_map_mmio;
typedef __typeof__(&nv_dma_unmap_mmio) S540Pinned_nv_dma_unmap_mmio;
typedef __typeof__(&nv_dma_import_sgt) S540Pinned_nv_dma_import_sgt;
typedef __typeof__(&nv_dma_release_sgt) S540Pinned_nv_dma_release_sgt;
typedef __typeof__(&nv_dma_import_dma_buf) S540Pinned_nv_dma_import_dma_buf;
typedef __typeof__(&nv_dma_import_from_fd) S540Pinned_nv_dma_import_from_fd;
typedef __typeof__(&nv_dma_release_dma_buf) S540Pinned_nv_dma_release_dma_buf;
typedef __typeof__(&nv_dma_init_sysmem_window_for_fabric_access) S540Pinned_nv_dma_init_sysmem_window_for_fabric_access;
typedef __typeof__(&nv_dma_destroy_sysmem_window_for_fabric_access) S540Pinned_nv_dma_destroy_sysmem_window_for_fabric_access;
typedef __typeof__(&nv_get_device_memory_config) S540Pinned_nv_get_device_memory_config;
typedef __typeof__(&nv_get_egm_info) S540Pinned_nv_get_egm_info;
typedef __typeof__(&os_alloc_pages_node) S540Pinned_os_alloc_pages_node;
typedef __typeof__(&os_get_page) S540Pinned_os_get_page;
typedef __typeof__(&os_put_page) S540Pinned_os_put_page;
typedef __typeof__(&os_get_page_refcount) S540Pinned_os_get_page_refcount;
typedef __typeof__(&os_count_tail_pages) S540Pinned_os_count_tail_pages;
typedef __typeof__(&os_numa_memblock_size) S540Pinned_os_numa_memblock_size;
typedef __typeof__(&os_get_numa_node_memory_usage) S540Pinned_os_get_numa_node_memory_usage;
typedef __typeof__(&os_numa_add_gpu_memory) S540Pinned_os_numa_add_gpu_memory;
typedef __typeof__(&os_numa_remove_gpu_memory) S540Pinned_os_numa_remove_gpu_memory;
typedef __typeof__(&os_offline_page_at_address) S540Pinned_os_offline_page_at_address;
typedef __typeof__(&os_unlock_user_pages) S540Pinned_os_unlock_user_pages;
typedef __typeof__(&os_flush_cpu_cache_all) S540Pinned_os_flush_cpu_cache_all;
typedef __typeof__(&os_flush_user_cache) S540Pinned_os_flush_user_cache;
typedef __typeof__(&os_iommu_sva_bind) S540Pinned_os_iommu_sva_bind;
typedef __typeof__(&os_iommu_sva_unbind) S540Pinned_os_iommu_sva_unbind;
#include "../src/nv_unsupported_memory.h"
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_alias_pages,
                 __typeof__(&s540Global_nv_alias_pages)),
               "Original NVIDIA ABI mismatch: nv_alias_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_alloc_user_mapping,
                 __typeof__(&s540Global_nv_alloc_user_mapping)),
               "Original NVIDIA ABI mismatch: nv_alloc_user_mapping");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_free_user_mapping,
                 __typeof__(&s540Global_nv_free_user_mapping)),
               "Original NVIDIA ABI mismatch: nv_free_user_mapping");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_register_peer_io_mem,
                 __typeof__(&s540Global_nv_register_peer_io_mem)),
               "Original NVIDIA ABI mismatch: nv_register_peer_io_mem");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_unregister_peer_io_mem,
                 __typeof__(&s540Global_nv_unregister_peer_io_mem)),
               "Original NVIDIA ABI mismatch: nv_unregister_peer_io_mem");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_register_phys_pages,
                 __typeof__(&s540Global_nv_register_phys_pages)),
               "Original NVIDIA ABI mismatch: nv_register_phys_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_unregister_phys_pages,
                 __typeof__(&s540Global_nv_unregister_phys_pages)),
               "Original NVIDIA ABI mismatch: nv_unregister_phys_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_register_user_pages,
                 __typeof__(&s540Global_nv_register_user_pages)),
               "Original NVIDIA ABI mismatch: nv_register_user_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_unregister_user_pages,
                 __typeof__(&s540Global_nv_unregister_user_pages)),
               "Original NVIDIA ABI mismatch: nv_unregister_user_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_register_sgt,
                 __typeof__(&s540Global_nv_register_sgt)),
               "Original NVIDIA ABI mismatch: nv_register_sgt");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_unregister_sgt,
                 __typeof__(&s540Global_nv_unregister_sgt)),
               "Original NVIDIA ABI mismatch: nv_unregister_sgt");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_get_phys_pages,
                 __typeof__(&s540Global_nv_get_phys_pages)),
               "Original NVIDIA ABI mismatch: nv_get_phys_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_map_peer,
                 __typeof__(&s540Global_nv_dma_map_peer)),
               "Original NVIDIA ABI mismatch: nv_dma_map_peer");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_unmap_peer,
                 __typeof__(&s540Global_nv_dma_unmap_peer)),
               "Original NVIDIA ABI mismatch: nv_dma_unmap_peer");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_map_mmio,
                 __typeof__(&s540Global_nv_dma_map_mmio)),
               "Original NVIDIA ABI mismatch: nv_dma_map_mmio");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_unmap_mmio,
                 __typeof__(&s540Global_nv_dma_unmap_mmio)),
               "Original NVIDIA ABI mismatch: nv_dma_unmap_mmio");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_import_sgt,
                 __typeof__(&s540Global_nv_dma_import_sgt)),
               "Original NVIDIA ABI mismatch: nv_dma_import_sgt");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_release_sgt,
                 __typeof__(&s540Global_nv_dma_release_sgt)),
               "Original NVIDIA ABI mismatch: nv_dma_release_sgt");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_import_dma_buf,
                 __typeof__(&s540Global_nv_dma_import_dma_buf)),
               "Original NVIDIA ABI mismatch: nv_dma_import_dma_buf");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_import_from_fd,
                 __typeof__(&s540Global_nv_dma_import_from_fd)),
               "Original NVIDIA ABI mismatch: nv_dma_import_from_fd");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_release_dma_buf,
                 __typeof__(&s540Global_nv_dma_release_dma_buf)),
               "Original NVIDIA ABI mismatch: nv_dma_release_dma_buf");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_init_sysmem_window_for_fabric_access,
                 __typeof__(&s540Global_nv_dma_init_sysmem_window_for_fabric_access)),
               "Original NVIDIA ABI mismatch: nv_dma_init_sysmem_window_for_fabric_access");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_dma_destroy_sysmem_window_for_fabric_access,
                 __typeof__(&s540Global_nv_dma_destroy_sysmem_window_for_fabric_access)),
               "Original NVIDIA ABI mismatch: nv_dma_destroy_sysmem_window_for_fabric_access");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_get_device_memory_config,
                 __typeof__(&s540Global_nv_get_device_memory_config)),
               "Original NVIDIA ABI mismatch: nv_get_device_memory_config");
_Static_assert(__builtin_types_compatible_p(S540Pinned_nv_get_egm_info,
                 __typeof__(&s540Global_nv_get_egm_info)),
               "Original NVIDIA ABI mismatch: nv_get_egm_info");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_alloc_pages_node,
                 __typeof__(&s540Global_os_alloc_pages_node)),
               "Original NVIDIA ABI mismatch: os_alloc_pages_node");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_get_page,
                 __typeof__(&s540Global_os_get_page)),
               "Original NVIDIA ABI mismatch: os_get_page");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_put_page,
                 __typeof__(&s540Global_os_put_page)),
               "Original NVIDIA ABI mismatch: os_put_page");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_get_page_refcount,
                 __typeof__(&s540Global_os_get_page_refcount)),
               "Original NVIDIA ABI mismatch: os_get_page_refcount");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_count_tail_pages,
                 __typeof__(&s540Global_os_count_tail_pages)),
               "Original NVIDIA ABI mismatch: os_count_tail_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_numa_memblock_size,
                 __typeof__(&s540Global_os_numa_memblock_size)),
               "Original NVIDIA ABI mismatch: os_numa_memblock_size");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_get_numa_node_memory_usage,
                 __typeof__(&s540Global_os_get_numa_node_memory_usage)),
               "Original NVIDIA ABI mismatch: os_get_numa_node_memory_usage");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_numa_add_gpu_memory,
                 __typeof__(&s540Global_os_numa_add_gpu_memory)),
               "Original NVIDIA ABI mismatch: os_numa_add_gpu_memory");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_numa_remove_gpu_memory,
                 __typeof__(&s540Global_os_numa_remove_gpu_memory)),
               "Original NVIDIA ABI mismatch: os_numa_remove_gpu_memory");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_offline_page_at_address,
                 __typeof__(&s540Global_os_offline_page_at_address)),
               "Original NVIDIA ABI mismatch: os_offline_page_at_address");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_unlock_user_pages,
                 __typeof__(&s540Global_os_unlock_user_pages)),
               "Original NVIDIA ABI mismatch: os_unlock_user_pages");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_flush_cpu_cache_all,
                 __typeof__(&s540Global_os_flush_cpu_cache_all)),
               "Original NVIDIA ABI mismatch: os_flush_cpu_cache_all");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_flush_user_cache,
                 __typeof__(&s540Global_os_flush_user_cache)),
               "Original NVIDIA ABI mismatch: os_flush_user_cache");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_iommu_sva_bind,
                 __typeof__(&s540Global_os_iommu_sva_bind)),
               "Original NVIDIA ABI mismatch: os_iommu_sva_bind");
_Static_assert(__builtin_types_compatible_p(S540Pinned_os_iommu_sva_unbind,
                 __typeof__(&s540Global_os_iommu_sva_unbind)),
               "Original NVIDIA ABI mismatch: os_iommu_sva_unbind");
