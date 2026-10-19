/* SPDX-License-Identifier: MIT */
#ifndef S540_PROSPECTIVE_LOADER_STATE_H
#define S540_PROSPECTIVE_LOADER_STATE_H
#include "S540ProspectiveLoaderProtocol.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Internal state only; the IOKit backend owns the lock and authentic facts.
 * No user mapping, ready flag, policy override or original-entry callback.
 */
typedef struct S540ProspectiveState { S540ProspectiveSnapshot snapshot; } S540ProspectiveState;
NV_STATUS s540ProspectiveModuleEnter(S540ProspectiveState *);
NV_STATUS s540ProspectiveServiceStart(S540ProspectiveState *, NvU64 actualRegistryEntryID,
                                    NvBool actualIOResourcesProvider);
NV_STATUS s540ProspectiveRequestOnce(S540ProspectiveState *, NvBool actualCallerIsRoot,
                                   const S540ProspectiveRequest *);
NV_STATUS s540ProspectiveBeginStop(S540ProspectiveState *);
void s540ProspectiveServiceGone(S540ProspectiveState *);
NV_STATUS s540ProspectiveFinishStop(S540ProspectiveState *, NvU32 actualServices, NvU32 actualClients);
#ifdef __cplusplus
}
#endif
#endif
