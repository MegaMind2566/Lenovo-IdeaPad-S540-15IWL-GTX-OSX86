/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_IRQ_IDENTITY_H
#define S540_NVIDIA_GSP_IRQ_IDENTITY_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
struct S540GspContext;
typedef struct S540GspIrqIdentity {
    const void *context;
    void *nv,*mainStack,*isrStack,*lockedStack,*unlockedStack,*privateState,*isrGuard,*pciHandle;
    NvU64 ownerThread,generation;
} S540GspIrqIdentity;
/* These facts are pulled from the actual Darwin backend's bounded PCI
 * inventory and getInterruptType result. There is no mode/readiness setter. */
typedef struct S540GspIrqModeFacts {
    const void *nv;
    NvU64 generation;
    NvU32 interruptType,msiVectors;
    NvBool known,messageSignaled,msiCapable,msixCapable;
} S540GspIrqModeFacts;
typedef struct S540GspIrqInstallationSnapshot {
    NvU64 generation,hardwareDmaGeneration;
    NvU32 stopAttempts;
    NV_STATUS installStatus,modeStatus,armStatus,stopStatus,softwareDrainStatus,fullDrainStatus;
    NvBool installationAttempted,modeSelected,sessionInstalled,sessionArmed;
} S540GspIrqInstallationSnapshot;
#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS s540GspContextReadIrqIdentity(struct S540GspContext *,S540GspIrqIdentity *);
NvBool s540GspContextMatchIrqIdentity(struct S540GspContext *,const S540GspIrqIdentity *);
NV_STATUS s540GspContextSelectMessageInterrupt(struct S540GspContext *,const S540GspIrqIdentity *);
NV_STATUS s540GspIrqReadBackendMode(const void *nv,S540GspIrqModeFacts *);
NV_STATUS s540GspIrqInstallationCheckContext(struct S540GspContext *);
#ifdef __cplusplus
}
#endif
#endif
