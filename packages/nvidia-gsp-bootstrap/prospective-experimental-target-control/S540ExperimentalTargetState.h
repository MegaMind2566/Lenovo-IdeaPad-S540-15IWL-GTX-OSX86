/* SPDX-License-Identifier: MIT */
#ifndef S540_EXPERIMENTAL_TARGET_STATE_H
#define S540_EXPERIMENTAL_TARGET_STATE_H
#include "S540ExperimentalTargetProtocol.h"
typedef struct S540ExperimentalState { S540ExperimentalSnapshot snapshot; } S540ExperimentalState;
#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS s540ExperimentalModuleEnter(S540ExperimentalState *);
NV_STATUS s540ExperimentalServiceStart(S540ExperimentalState *, NvU64 actualRegistryEntryID);
NV_STATUS s540ExperimentalRequestBegin(S540ExperimentalState *, NvBool actualCallerRoot,
    const S540ExperimentalRequest *, const S540ExperimentalBuildIdentity *,
    const NvU8 actualNativeCodeContract[32], NvU64 actualWorkerMinimum, NvU64 actualIrqMinimum);
void s540ExperimentalRequestFinish(S540ExperimentalState *, NV_STATUS actualStatus);
NV_STATUS s540ExperimentalRequestStop(S540ExperimentalState *);
void s540ExperimentalServiceGone(S540ExperimentalState *);
#ifdef __cplusplus
}
#endif
#endif
