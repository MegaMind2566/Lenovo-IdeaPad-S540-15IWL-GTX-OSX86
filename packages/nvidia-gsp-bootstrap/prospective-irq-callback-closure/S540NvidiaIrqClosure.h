/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_IRQ_CLOSURE_H
#define S540_NVIDIA_IRQ_CLOSURE_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
enum { S540_FIRST_IRQ_TOP=1, S540_FIRST_IRQ_BOTTOM=2 };
/* Pulled from the actual registered backend. No exported readiness setter. */
typedef struct S540FirstTxnIrqContext {
    const void *nv;
    NvU64 generation, thread;
    NvU32 stage, pending, callbacks, topStage, bottomStage, origin;
    NvBool accepting, controllerAttached, drained, maskRequired;
} S540FirstTxnIrqContext;
NV_STATUS s540FirstTxnIrqReadContext(const void *backend, NvU32 role,
    S540FirstTxnIrqContext *);
NV_STATUS s540FirstTxnIrqBind(const void *nv, const void *backend, NvU64 *generation);
NV_STATUS s540FirstTxnIrqCheckArm(const void *backend);
NV_STATUS s540FirstTxnIrqEnter(const void *backend, NvU32 role);
NV_STATUS s540FirstTxnIrqLeave(const void *backend, NvU32 role);
NvU32 s540FirstTxnIrqOrigin(const void *backend);
NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *nv,NvU32 role,NvU32 *origin);
NV_STATUS s540FirstTxnIrqValidateDrained(void);
NV_STATUS s540FirstTxnIrqValidateSoftwareDrained(void);
#ifdef __cplusplus
}
#endif
#endif
