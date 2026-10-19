/* SPDX-License-Identifier: MIT */
/*
 * Compile-only ABI check. Use the pinned original RM bridge include/profile
 * flags and its forced S540GlobalRmNamespace.h, exactly as for production C
 * bridges. No callback is invoked and no device is accessed.
 */
#include "nv.h"

/* Capture the actual original declaration before reading the facade. With the
 * forced namespace this also makes an incompatible facade redeclaration a C
 * compilation error, rather than allowing two differently named prototypes.
 */
typedef __typeof__(&nv_requires_dma_remap) S540PinnedDmaRemapAbi;
typedef __typeof__(&nv_get_num_phys_pages) S540PinnedPageCountAbi;
typedef __typeof__(&nv_pci_read_gpu_pdi_from_dvsec) S540PinnedPciPdiAbi;

#include "../src/nv_device_services.h"

typedef NvBool (NV_API_CALL *S540ExpectedDmaRemapAbi)(nv_state_t *);
_Static_assert(__builtin_types_compatible_p(S540PinnedDmaRemapAbi,
                                           S540ExpectedDmaRemapAbi),
               "Pinned NVIDIA DMA-remap declaration changed");
_Static_assert(__builtin_types_compatible_p(S540PinnedDmaRemapAbi,
                  __typeof__(&s540Global_nv_requires_dma_remap)),
               "Transport DMA-remap facade differs from the original ABI");
_Static_assert(__builtin_types_compatible_p(S540PinnedPageCountAbi,
                  __typeof__(&s540Global_nv_get_num_phys_pages)),
               "Transport physical-page count differs from the original ABI");
_Static_assert(__builtin_types_compatible_p(S540PinnedPciPdiAbi,
                  __typeof__(&s540Global_nv_pci_read_gpu_pdi_from_dvsec)),
               "Transport PCI DVSEC PDI differs from the original ABI");
