/* SPDX-License-Identifier: MIT */
/* Isolated prospective integration; no production header includes this file. */
#ifndef S540_NVIDIA_FIRST_TXN_SERVICES_H
#define S540_NVIDIA_FIRST_TXN_SERVICES_H
#include "S540NvidiaDarwinServices.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Exact immutable binding, before either queue has accepted work. The global
 * queue remains registered even after sealing; NULL must not bypass the seal. */
NV_STATUS s540FirstTxnServicesBind(const void *nv, NvU64 generation,
    struct os_work_queue *device, struct os_work_queue *global);
NV_STATUS s540FirstTxnServicesSealAndDrain(const void *nv, NvU64 generation);
NV_STATUS s540FirstTxnServicesValidateRetired(const void *nv, NvU64 generation);
/* Tests and service adapters inspect actual state, never set a readiness flag. */
NV_STATUS s540FirstTxnQueueBind(struct os_work_queue *, const void *, NvU64);
NV_STATUS s540FirstTxnQueueSeal(struct os_work_queue *, const void *, NvU64);
NV_STATUS s540FirstTxnQueueValidateStopped(struct os_work_queue *, const void *, NvU64);
NV_STATUS s540FirstTxnTimersValidateStopped(const void *, NvU64);
NV_STATUS s540FirstTxnTimersBind(const void *, NvU64);
#ifdef __cplusplus
}
#endif
#endif
