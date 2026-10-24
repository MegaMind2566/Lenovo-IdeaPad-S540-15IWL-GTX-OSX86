/* SPDX-License-Identifier: MIT */
#include "S540ExperimentalTargetState.h"
_Static_assert(sizeof(S540ExperimentalRequest) == 144, "Fixed manual request ABI");
_Static_assert(sizeof(S540ExperimentalBuildIdentity) == 80, "Fixed generated identity ABI");
_Static_assert(sizeof(S540PreparationObservation) == 104, "Fixed preparation observation ABI");
_Static_assert(sizeof(S540PreparationPowerObservation) == 56, "Fixed preparation PM observation ABI");
_Static_assert(sizeof(S540ExperimentalSnapshot) == 568, "Fixed version2 snapshot ABI");
static NvBool equal(const NvU8 *a, const NvU8 *b, NvU32 n) {
    NvU32 different = 0, i;
    for (i = 0; i < n; ++i) different |= a[i] ^ b[i];
    return different == 0;
}
static NvBool nonzero(const NvU8 *value, NvU32 n) {
    NvU32 bits = 0, i;
    for (i = 0; i < n; ++i) bits |= value[i];
    return bits != 0;
}
static NvBool valid(const S540ExperimentalState *state) {
    return state && state->snapshot.format == S540_EXPERIMENTAL_SNAPSHOT_VERSION &&
        state->snapshot.bytes == sizeof(state->snapshot) &&
        !state->snapshot.wholeDmaStopProven && !state->snapshot.pmAcknowledgementAuthorized &&
        !state->snapshot.accelerationTest;
}
NV_STATUS s540ExperimentalModuleEnter(S540ExperimentalState *state) {
    if (!state) return NV_ERR_INVALID_ARGUMENT;
    if (state->snapshot.format) return NV_ERR_STATE_IN_USE;
    state->snapshot = (S540ExperimentalSnapshot){.format=S540_EXPERIMENTAL_SNAPSHOT_VERSION,.bytes=sizeof(state->snapshot),
        .phase=S540_EXPERIMENTAL_MODULE_ENTERED,.lastStatus=NV_ERR_NOT_READY,
        .moduleEntryAccepted=1,.preparationStatus=NV_ERR_NOT_READY,
        .initializationStatus=NV_ERR_NOT_READY,.cancellationStatus=NV_ERR_NOT_READY,
        .stopStatus=NV_ERR_NOT_READY,.runtimeObservationStatus=NV_ERR_NOT_READY,
        .stopObservationStatus=NV_ERR_NOT_READY};
    state->snapshot.retainedStop.format=1;
    state->snapshot.retainedStop.bytes=sizeof(state->snapshot.retainedStop);
    return NV_OK;
}
NV_STATUS s540ExperimentalServiceStart(S540ExperimentalState *state, NvU64 generation) {
    if (!valid(state) || state->snapshot.phase != S540_EXPERIMENTAL_MODULE_ENTERED ||
        !state->snapshot.moduleEntryAccepted || state->snapshot.stopRequested)
        return NV_ERR_INVALID_STATE;
    if (!generation) return NV_ERR_INVALID_ARGUMENT;
    state->snapshot.generation=generation;
    state->snapshot.controlServiceStarted=1;
    state->snapshot.phase=S540_EXPERIMENTAL_CONTROL_STARTED;
    return NV_OK;
}
NV_STATUS s540ExperimentalRequestBegin(S540ExperimentalState *state, NvBool root,
    const S540ExperimentalRequest *request, const S540ExperimentalBuildIdentity *identity,
    const NvU8 contract[32], NvU64 worker, NvU64 irq) {
    static const char build[16]={'2','5','G','2','4','1',0};
    NvU32 i;
    if (!root) return NV_ERR_INSUFFICIENT_PERMISSIONS;
    if (!request || !identity || !contract || request->format != 1 ||
        request->bytes != sizeof(*request) || identity->format != 1 ||
        identity->bytes != sizeof(*identity) || !identity->requiredKernelStackBytes ||
        !worker || !irq || !nonzero(identity->sourceSha256,32) ||
        !nonzero(identity->policySha256,32) || !nonzero(contract,32) ||
        request->manualAcknowledgement != S540_EXPERIMENTAL_MANUAL_ACK ||
        request->observedKernelStackBytes < identity->requiredKernelStackBytes ||
        request->observedKernelStackBytes < worker ||
        !equal((const NvU8 *)request->targetBuild,(const NvU8 *)build,16) ||
        !equal(request->sourceSha256,identity->sourceSha256,32) ||
        !equal(request->policySha256,identity->policySha256,32) ||
        !equal(request->nativeCodeContractSha256,contract,32)) return NV_ERR_INVALID_ARGUMENT;
    if (!valid(state) || !state->snapshot.moduleEntryAccepted ||
        !state->snapshot.controlServiceStarted || state->snapshot.stopRequested)
        return NV_ERR_INVALID_STATE;
    if (state->snapshot.requestConsumed) return NV_ERR_STATE_IN_USE;
    if (state->snapshot.phase != S540_EXPERIMENTAL_CONTROL_STARTED ||
        !request->generation || request->generation != state->snapshot.generation)
        return NV_ERR_INVALID_ARGUMENT;
    state->snapshot.requestConsumed=1;
    state->snapshot.requestRunning=1;
    state->snapshot.retainedUntilReboot=1;
    state->snapshot.phase=S540_EXPERIMENTAL_RUNNING;
    state->snapshot.lastStatus=NV_ERR_NOT_READY;
    state->snapshot.observedKernelStackBytes=request->observedKernelStackBytes;
    state->snapshot.nativeRequiredKernelStackBytes=worker;
    state->snapshot.nativeRequiredIrqStackBytes=irq;
    for (i=0;i<32;++i) {
        state->snapshot.sourceSha256[i]=identity->sourceSha256[i];
        state->snapshot.policySha256[i]=identity->policySha256[i];
        state->snapshot.nativeCodeContractSha256[i]=contract[i];
    }
    return NV_OK;
}
void s540ExperimentalRequestFinish(S540ExperimentalState *state, NV_STATUS status) {
    if (!valid(state) || !state->snapshot.requestConsumed || !state->snapshot.requestRunning) return;
    state->snapshot.requestRunning=0;
    state->snapshot.lastStatus=status;
    state->snapshot.phase=state->snapshot.stopRequested ? S540_EXPERIMENTAL_RETAINED :
        S540_EXPERIMENTAL_RETURNED;
}
NV_STATUS s540ExperimentalRequestStop(S540ExperimentalState *state) {
    if (!valid(state)) return NV_ERR_INVALID_STATE;
    state->snapshot.stopRequested=1;
    state->snapshot.phase=state->snapshot.requestConsumed ? S540_EXPERIMENTAL_RETAINED :
        S540_EXPERIMENTAL_STOPPING;
    return state->snapshot.requestRunning ? NV_ERR_BUSY_RETRY : NV_OK;
}
void s540ExperimentalServiceGone(S540ExperimentalState *state) {
    if (!valid(state)) return;
    state->snapshot.controlServiceStarted=0;
    (void)s540ExperimentalRequestStop(state);
}
