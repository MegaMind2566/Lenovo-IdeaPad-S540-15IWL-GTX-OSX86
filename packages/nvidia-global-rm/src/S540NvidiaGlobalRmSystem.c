/* SPDX-License-Identifier: MIT */
/* Exact pinned RM declarations and private namespace are forced by builders. */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRmSystem.h"

typedef NvU64 (NV_API_CALL *S540SystemQueryAbi)(void);
typedef void (NV_API_CALL *S540StackDumpAbi)(void);
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_get_max_user_va),
                                           S540SystemQueryAbi),
               "Original maximum user VA ABI changed");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_get_reclaimable_memory_usage),
                                           S540SystemQueryAbi),
               "Original reclaimable pool ABI changed");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_dump_stack),
                                           S540StackDumpAbi),
               "Original stack diagnostic ABI changed");
_Static_assert(S540_DARWIN_NVIDIA_RECYCLING_PAGE_POOLS == 0,
               "A recycling page pool requires actual owned-pool accounting");

NvU64 NV_API_CALL os_get_max_user_va(void)
{
    return s540GlobalRmSystemUserAddressLimit();
}

void NV_API_CALL os_dump_stack(void)
{
    (void)s540GlobalRmSystemDumpStack();
}

NvU64 NV_API_CALL os_get_reclaimable_memory_usage(void)
{
    /* Linux sums NVIDIA's sysmem_page_pools, not free host memory. This
     * selected backend has no recycling page pool: every Host/Session buffer
     * remains owned until released. Deferred DMA retirements remain owned and
     * are never reusable/reclaimable memory. Pool introduction requires this
     * compile-time profile and callback to change together.
     */
    return 0;
}
