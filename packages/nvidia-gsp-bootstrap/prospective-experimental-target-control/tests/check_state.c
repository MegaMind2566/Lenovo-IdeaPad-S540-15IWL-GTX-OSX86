/* SPDX-License-Identifier: MIT */
#include "../S540ExperimentalTargetState.h"
#include <stdio.h>
#include <string.h>
static unsigned checks, failures;
#define CHECK(condition) do { ++checks; if (!(condition)) { ++failures; fprintf(stderr,"line %u: %s\n",__LINE__,#condition); } } while (0)
static S540ExperimentalBuildIdentity identity;
static S540ExperimentalRequest request;
static NvU8 contract[32];
static void setup(S540ExperimentalState *state) {
    memset(state,0,sizeof(*state)); memset(&identity,0,sizeof(identity)); memset(&request,0,sizeof(request));
    identity.format=1; identity.bytes=sizeof(identity); identity.requiredKernelStackBytes=16384;
    for (unsigned i=0;i<32;++i) { identity.sourceSha256[i]=(NvU8)(i+1); identity.policySha256[i]=(NvU8)(i+2); contract[i]=(NvU8)(i+3); }
    request.format=1; request.bytes=sizeof(request); request.generation=91;
    request.observedKernelStackBytes=16384; request.manualAcknowledgement=S540_EXPERIMENTAL_MANUAL_ACK;
    memcpy(request.sourceSha256,identity.sourceSha256,32); memcpy(request.policySha256,identity.policySha256,32);
    memcpy(request.nativeCodeContractSha256,contract,32); memcpy(request.targetBuild,"25G241",7);
    CHECK(s540ExperimentalModuleEnter(state)==NV_OK);
    CHECK(s540ExperimentalServiceStart(state,91)==NV_OK);
}
static NV_STATUS begin(S540ExperimentalState *state) {
    return s540ExperimentalRequestBegin(state,NV_TRUE,&request,&identity,contract,16384,16384);
}
int main(void) {
    S540ExperimentalState state, before;
    setup(&state); CHECK(s540ExperimentalModuleEnter(&state)==NV_ERR_STATE_IN_USE);
    CHECK(begin(&state)==NV_OK); CHECK(state.snapshot.requestRunning && state.snapshot.requestConsumed && state.snapshot.retainedUntilReboot);
    CHECK(!state.snapshot.wholeDmaStopProven && !state.snapshot.pmAcknowledgementAuthorized && !state.snapshot.accelerationTest);
    CHECK(begin(&state)==NV_ERR_STATE_IN_USE);
    CHECK(s540ExperimentalRequestStop(&state)==NV_ERR_BUSY_RETRY);
    CHECK(state.snapshot.stopRequested && state.snapshot.retainedUntilReboot);
    s540ExperimentalRequestFinish(&state,NV_ERR_TIMEOUT);
    CHECK(state.snapshot.lastStatus==NV_ERR_TIMEOUT && !state.snapshot.requestRunning && state.snapshot.phase==S540_EXPERIMENTAL_RETAINED);
    CHECK(s540ExperimentalRequestStop(&state)==NV_OK); CHECK(state.snapshot.lastStatus==NV_ERR_TIMEOUT);
    before=state; s540ExperimentalRequestFinish(&state,NV_OK); CHECK(!memcmp(&before,&state,sizeof(state)));
    CHECK(begin(&state)==NV_ERR_INVALID_STATE);
    for (unsigned field=0;field<16;++field) {
        setup(&state);
        switch (field) {
            case 0: request.format=2;break; case 1: --request.bytes;break;
            case 2: ++request.generation;break; case 3: --request.observedKernelStackBytes;break;
            case 4: request.manualAcknowledgement=0;break; case 5: request.sourceSha256[31]^=1;break;
            case 6: request.policySha256[31]^=1;break; case 7: request.nativeCodeContractSha256[31]^=1;break;
            case 8: request.targetBuild[15]=1;break; case 9: identity.format=0;break;
            case 10: --identity.bytes;break; case 11: identity.requiredKernelStackBytes=0;break;
            case 12: memset(identity.sourceSha256,0,32);memset(request.sourceSha256,0,32);break;
            case 13: memset(identity.policySha256,0,32);memset(request.policySha256,0,32);break;
            case 14: memset(contract,0,32);memset(request.nativeCodeContractSha256,0,32);break;
            case 15: request.generation=0;break;
        }
        before=state; CHECK(begin(&state)==NV_ERR_INVALID_ARGUMENT); CHECK(!memcmp(&before,&state,sizeof(state)));
    }
    setup(&state);before=state;
    CHECK(s540ExperimentalRequestBegin(&state,NV_FALSE,&request,&identity,contract,16384,16384)==NV_ERR_INSUFFICIENT_PERMISSIONS);
    CHECK(!memcmp(&before,&state,sizeof(state)));
    CHECK(s540ExperimentalRequestBegin(&state,NV_TRUE,NULL,&identity,contract,16384,16384)==NV_ERR_INVALID_ARGUMENT);
    CHECK(s540ExperimentalRequestBegin(&state,NV_TRUE,&request,NULL,contract,16384,16384)==NV_ERR_INVALID_ARGUMENT);
    CHECK(s540ExperimentalRequestBegin(&state,NV_TRUE,&request,&identity,NULL,16384,16384)==NV_ERR_INVALID_ARGUMENT);
    CHECK(s540ExperimentalRequestBegin(&state,NV_TRUE,&request,&identity,contract,0,16384)==NV_ERR_INVALID_ARGUMENT);
    CHECK(s540ExperimentalRequestBegin(&state,NV_TRUE,&request,&identity,contract,16384,0)==NV_ERR_INVALID_ARGUMENT);
    CHECK(s540ExperimentalRequestBegin(&state,NV_TRUE,&request,&identity,contract,32768,16384)==NV_ERR_INVALID_ARGUMENT);
    setup(&state);state.snapshot.wholeDmaStopProven=1;CHECK(begin(&state)==NV_ERR_INVALID_STATE);
    setup(&state);state.snapshot.pmAcknowledgementAuthorized=1;CHECK(begin(&state)==NV_ERR_INVALID_STATE);
    setup(&state);state.snapshot.accelerationTest=1;CHECK(begin(&state)==NV_ERR_INVALID_STATE);
    setup(&state);s540ExperimentalServiceGone(&state);CHECK(begin(&state)==NV_ERR_INVALID_STATE);
    setup(&state);CHECK(begin(&state)==NV_OK);s540ExperimentalRequestFinish(&state,NV_OK);
    CHECK(state.snapshot.lastStatus==NV_OK && state.snapshot.phase==S540_EXPERIMENTAL_RETURNED && state.snapshot.retainedUntilReboot);
    CHECK(begin(&state)==NV_ERR_STATE_IN_USE);
    printf("{\"status\":\"%s\",\"checks\":%u,\"failures\":%u,\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n",failures?"failed":"passed",checks,failures);
    return failures!=0;
}
