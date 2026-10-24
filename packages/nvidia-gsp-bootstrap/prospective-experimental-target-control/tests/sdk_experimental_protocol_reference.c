/* SPDX-License-Identifier: MIT */
#include "../S540ExperimentalTargetProtocol.h"
#include "S540ExperimentalRuntime.h"
#include <stddef.h>
const NvU32 s540ExperimentalProtocolOffsets[]={
    sizeof(S540ExperimentalRequest),sizeof(S540ExperimentalBuildIdentity),sizeof(S540ExperimentalSnapshot),
    sizeof(S540ExperimentalNativeProfile),offsetof(S540ExperimentalRequest,generation),
    offsetof(S540ExperimentalRequest,observedKernelStackBytes),offsetof(S540ExperimentalRequest,sourceSha256),
    offsetof(S540ExperimentalRequest,policySha256),offsetof(S540ExperimentalRequest,nativeCodeContractSha256),
    offsetof(S540ExperimentalRequest,targetBuild),offsetof(S540ExperimentalBuildIdentity,requiredKernelStackBytes),
    offsetof(S540ExperimentalNativeProfile,codeContractSha256),offsetof(S540ExperimentalNativeProfile,workerStackBytes),
    S540_EXPERIMENTAL_SNAPSHOT_VERSION,sizeof(S540PreparationObservation),sizeof(S540PreparationPowerObservation),
    offsetof(S540ExperimentalSnapshot,preparation),offsetof(S540PreparationObservation,power),
    offsetof(S540PreparationObservation,firstFailureStatus),offsetof(S540PreparationPowerObservation,rawIOReturn),
    offsetof(S540PreparationPowerObservation,observedMask)};
