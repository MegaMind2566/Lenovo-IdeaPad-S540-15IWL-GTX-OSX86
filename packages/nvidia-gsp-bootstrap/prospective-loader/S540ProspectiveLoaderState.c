/* SPDX-License-Identifier: MIT */
#include "S540ProspectiveLoaderState.h"
_Static_assert(sizeof(S540ProspectiveSnapshot) == 64, "Fixed loader snapshot ABI");
_Static_assert(sizeof(S540ProspectiveRequest) == 16, "Fixed request ABI");
static NvBool valid(const S540ProspectiveState *state)
{
    return state && state->snapshot.format == S540_PROSPECTIVE_PROTOCOL_VERSION &&
        state->snapshot.bytes == sizeof(S540ProspectiveSnapshot) &&
        state->snapshot.entryPolicyClosed == 1 && !state->snapshot.targetLoaderAdmissionProven &&
        !state->snapshot.originalCalls && !state->snapshot.providerPreparations &&
        !state->snapshot.pmRegistrations;
}
NV_STATUS s540ProspectiveModuleEnter(S540ProspectiveState *state)
{
    if (!state) return NV_ERR_INVALID_ARGUMENT;
    /* A load instance has no reset API. BSS must be new; an existing request,
     * refusal, partial stop or failed start cannot be cleared by re-entry.
     */
    if (state->snapshot.format) return NV_ERR_STATE_IN_USE;
    state->snapshot = (S540ProspectiveSnapshot){
        .format = S540_PROSPECTIVE_PROTOCOL_VERSION, .bytes = sizeof(S540ProspectiveSnapshot),
        .phase = S540_PROSPECTIVE_MODULE_ENTERED, .lastStatus = NV_ERR_NOT_READY,
        .moduleEntryAccepted = 1, .entryPolicyClosed = 1};
    return NV_OK;
}
NV_STATUS s540ProspectiveServiceStart(S540ProspectiveState *state, NvU64 generation, NvBool resources)
{
    if (!valid(state) || state->snapshot.phase != S540_PROSPECTIVE_MODULE_ENTERED ||
        !state->snapshot.moduleEntryAccepted || state->snapshot.stopping)
        return NV_ERR_INVALID_STATE;
    if (!generation || !resources) return NV_ERR_INVALID_ARGUMENT;
    state->snapshot.generation = generation;
    state->snapshot.controlServiceStarted = 1;
    state->snapshot.phase = S540_PROSPECTIVE_CONTROL_STARTED;
    return NV_OK;
}
NV_STATUS s540ProspectiveRequestOnce(S540ProspectiveState *state, NvBool root,
                                   const S540ProspectiveRequest *request)
{
    if (!root) return NV_ERR_INSUFFICIENT_PERMISSIONS;
    if (!request || request->format != S540_PROSPECTIVE_PROTOCOL_VERSION ||
        request->bytes != sizeof(*request)) return NV_ERR_INVALID_ARGUMENT;
    if (!valid(state) || !state->snapshot.moduleEntryAccepted ||
        !state->snapshot.controlServiceStarted || state->snapshot.stopping)
        return NV_ERR_INVALID_STATE;
    if (state->snapshot.rootRequestConsumed) return NV_ERR_STATE_IN_USE;
    if (state->snapshot.phase != S540_PROSPECTIVE_CONTROL_STARTED) return NV_ERR_INVALID_STATE;
    if (!request->generation || request->generation != state->snapshot.generation)
        return NV_ERR_INVALID_ARGUMENT;
    state->snapshot.rootRequestConsumed = 1;
    state->snapshot.requestsAccepted = 1;
    /* This is the actual fixed backend policy. Neither module entry, service
     * start, root privilege nor a generation supplies target-link/runtime
     * admission. The prototype has no path or callback to original RM.
     */
    state->snapshot.lastStatus = NV_ERR_NOT_READY;
    state->snapshot.phase = S540_PROSPECTIVE_ENTRY_BLOCKED;
    return NV_ERR_NOT_READY;
}
NV_STATUS s540ProspectiveBeginStop(S540ProspectiveState *state)
{
    if (!valid(state)) return NV_ERR_INVALID_STATE;
    if (state->snapshot.phase == S540_PROSPECTIVE_STOPPED) return NV_OK;
    state->snapshot.stopping = 1;
    state->snapshot.phase = S540_PROSPECTIVE_STOPPING;
    return NV_OK;
}
void s540ProspectiveServiceGone(S540ProspectiveState *state)
{
    if (!valid(state)) return;
    state->snapshot.controlServiceStarted = 0;
    state->snapshot.stopping = 1;
    state->snapshot.phase = S540_PROSPECTIVE_STOPPING;
}
NV_STATUS s540ProspectiveFinishStop(S540ProspectiveState *state, NvU32 services, NvU32 clients)
{
    NV_STATUS status = s540ProspectiveBeginStop(state);
    if (status != NV_OK) return status;
    if (services || clients) return NV_ERR_IN_USE;
    state->snapshot.phase = S540_PROSPECTIVE_STOPPED;
    state->snapshot.moduleEntryAccepted = 0;
    state->snapshot.controlServiceStarted = 0;
    return NV_OK;
}
