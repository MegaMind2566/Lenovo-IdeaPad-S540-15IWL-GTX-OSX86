/* SPDX-License-Identifier: MIT; actual original-header bridge declarations. */
#ifndef S540_FIRST_TXN_GPU_ORIGINAL_EXTENSION_H
#define S540_FIRST_TXN_GPU_ORIGINAL_EXTENSION_H
#ifdef __cplusplus
extern "C" {
#endif
struct OBJGPU;
NV_STATUS s540FirstTxnOriginalGpuAttachBegin(struct OBJGPU *, void *osInfo);
NV_STATUS s540FirstTxnOriginalGpuAttachCommit(struct OBJGPU *, void *osInfo);
NV_STATUS s540FirstTxnOriginalCheckWorkGpu(const void *actualWork, struct OBJGPU *);
NV_STATUS s540FirstTxnOriginalRejectWorkGpu(const void *actualWork, NV_STATUS);
NV_STATUS s540FirstTxnOriginalGpuDetach(struct OBJGPU *);
NV_STATUS s540FirstTxnOriginalGpuAttachFailed(void *osInfo, NV_STATUS);
#ifdef __cplusplus
}
#endif
#endif
