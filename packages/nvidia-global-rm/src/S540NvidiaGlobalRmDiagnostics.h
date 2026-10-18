/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GLOBAL_RM_DIAGNOSTICS_H
#define S540_NVIDIA_GLOBAL_RM_DIAGNOSTICS_H

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Platform implementation behind the original-header ABI facade. No original
 * RM object layout, device ownership or caller readiness Boolean crosses here.
 */
NvS32 s540GlobalRmDeviceLogV(NvU32 domain, NvU32 bus, NvU32 slot,
                           NvU32 function, NvU32 level, NvBool xid,
                           NvU32 error, const char *format, va_list arguments);
void s540GlobalRmBugCheck(NvU32 code, const char *text)
    __attribute__((noreturn));

#ifdef __cplusplus
}
#endif
#endif
