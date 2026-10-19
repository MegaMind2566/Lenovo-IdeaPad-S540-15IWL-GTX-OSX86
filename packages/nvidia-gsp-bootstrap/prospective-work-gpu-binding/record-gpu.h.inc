/* SPDX-License-Identifier: MIT
 * Isolated successor fragment; append to the strong record header only.
 * Calls originate at reviewed real attach/work/private-state source boundaries.
 * No API accepts a caller thread, generation, readiness flag or callback policy.
 */
#ifndef S540_FIRST_TXN_GPU_RECORD_EXTENSION_H
#define S540_FIRST_TXN_GPU_RECORD_EXTENSION_H
#ifdef __cplusplus
extern "C" {
#endif
enum { S540_FIRST_GPU_REQUIRES_GPU = 4U };
NV_STATUS s540FirstTxnGpuAttachReserve(const void *exactNv,
    const void *actualGpu, NvU32 gpuInstance);
NV_STATUS s540FirstTxnGpuAttachPublish(const void *exactNv,
    const void *actualGpu, NvU32 gpuInstance);
NV_STATUS s540FirstTxnGpuCheckResolvedWork(const void *exactNv,
    const void *actualWork, const void *actualGpu, NvU32 gpuInstance);
NV_STATUS s540FirstTxnGpuRejectWork(const void *actualWork, NV_STATUS failure);
/* There is deliberately no final private-state release issuer in this scope. */
NV_STATUS s540FirstTxnGpuPrivateStateMayChange(const void *actualNv);
#ifdef __cplusplus
}
#endif
#endif
