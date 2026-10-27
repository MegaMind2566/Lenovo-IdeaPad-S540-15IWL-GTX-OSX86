/* SPDX-License-Identifier: MIT; scalar diagnostics, never admission. */
#ifndef S540_ATTACH_FAILURE_WITNESS_H
#define S540_ATTACH_FAILURE_WITNESS_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
enum S540AttachWitnessStage {
    S540_ATTACH_GPU_CREATE=1, S540_ATTACH_DPC=2, S540_ATTACH_OS=3,
    S540_ATTACH_CAPS=4, S540_ATTACH_POST_CONSTRUCT=5,
    S540_ATTACH_CONF_COMPUTE=6, S540_ATTACH_COMPLETE=7
};
enum S540AttachWitnessConstructorStage {
    S540_CTOR_CLASS_INFO=1, S540_CTOR_DYNAMIC_CREATE=2,
    S540_CTOR_CONCRETE_CHECK=3, S540_CTOR_CHILD_CAST=4,
    S540_CTOR_ENGSTATE_CAST=5, S540_CTOR_BASE=6,
    S540_CTOR_ENGINE=7, S540_CTOR_MISSING=8, S540_CTOR_COMPLETE=9
};
enum { S540_ATTACH_OBS_MISSING=1U, S540_ATTACH_OBS_GSP_CLIENT=2U };
typedef struct S540AttachFailureWitness {
    NvU32 format, bytes;
    NvU64 generation;
    NvU32 complete, lastAttachStage, lastClassId, lastCtorStage;
    NvU64 lastInstance;
    NvU32 firstFailureValid, firstAttachStage, firstClassId, firstCtorStage;
    NvU64 firstInstance;
    NvU32 firstStatus, observedMask, missing, gspClient;
} S540AttachFailureWitness;
/* instance is the actual loop ordinal, not an address. No API resets this
 * once-per-boot observer, changes FirstTxn status, or grants cleanup authority. */
void s540AttachWitnessBegin(const void *exactNv);
void s540AttachWitnessProgress(const void *exactNv, NvU32 attachStage);
void s540AttachWitnessChildProgress(const void *exactNv, NvU32 classId,
    NvU64 instance, NvU32 ctorStage);
void s540AttachWitnessChildFailure(const void *exactNv, NvU32 classId,
    NvU64 instance, NvU32 ctorStage, NV_STATUS status, NvU32 observedMask,
    NvU32 missing, NvU32 gspClient);
void s540AttachWitnessAttachFailure(const void *exactNv, NvU32 attachStage,
    NV_STATUS status);
void s540AttachWitnessComplete(const void *exactNv);
/* Output remains unchanged on refusal; wrapper must actually have returned. */
NV_STATUS s540AttachWitnessRead(const void *exactNv, S540AttachFailureWitness *);
#ifdef __cplusplus
}
#endif
#endif
