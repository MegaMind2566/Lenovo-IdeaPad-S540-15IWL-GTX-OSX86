/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_RETAINED_OWNER_H
#define S540_NVIDIA_RETAINED_OWNER_H
#include "S540NvidiaGspContext.h"
#ifdef __cplusplus
extern "C" {
#endif
/* No caller quiescence flag, stop receipt, final free, or unbind interface. */
NV_STATUS s540GspContextStopRetainedServices(S540GspContext *);
NV_STATUS s540GspContextRunRetainedShutdownProtocol(S540GspContext *);
NV_STATUS s540GspContextReadRetainedShutdown(S540GspContext *,NvBool *,NvBool *);
#ifdef __cplusplus
}
#endif
#endif
