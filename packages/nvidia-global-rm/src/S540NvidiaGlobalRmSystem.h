/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GLOBAL_RM_SYSTEM_H
#define S540_NVIDIA_GLOBAL_RM_SYSTEM_H

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"

/* Selected Darwin x86_64 user-map limit, not a kernel-task map limit. The
 * production source additionally checks this against the public Mach header.
 * XNU vm_map_set_64bit/vm_compute_max_offset use MACH_VM_MAX_ADDRESS on x86.
 * This source profile still requires separate actual-target kernel admission.
 */
#define S540_DARWIN_X86_64_USER_MAP_LIMIT 0x00007FFFFFE00000ULL
#define S540_DARWIN_NVIDIA_RECYCLING_PAGE_POOLS 0
#define S540_GLOBAL_RM_STACK_TRACE_FRAMES 32U

#ifdef __cplusplus
extern "C" {
#endif
NvU64 s540GlobalRmSystemUserAddressLimit(void);
NvU32 s540GlobalRmSystemDumpStack(void);
#ifdef __cplusplus
}
#endif
#endif
