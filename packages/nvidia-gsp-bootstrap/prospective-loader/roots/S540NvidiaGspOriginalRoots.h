/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_PROSPECTIVE_ORIGINAL_ROOTS_H
#define S540_NVIDIA_GSP_PROSPECTIVE_ORIGINAL_ROOTS_H

#include "nvtypes.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Metadata only. These helpers never invoke an original RM entry point. */
NvU32 s540ProspectiveRetainedRootCount(void);
NvBool s540ProspectiveRetainedRootsPresent(void);

#ifdef __cplusplus
}
#endif

#endif
