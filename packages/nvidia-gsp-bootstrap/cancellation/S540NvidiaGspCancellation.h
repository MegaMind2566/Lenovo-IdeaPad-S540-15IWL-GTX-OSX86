/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_CANCELLATION_H
#define S540_NVIDIA_GSP_CANCELLATION_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef NvU64 S540GspCancellationToken;
enum S540GspCancellationPhase {
    S540_GSP_CANCEL_IDLE = 0,
    S540_GSP_CANCEL_OPERATION = 1,
    S540_GSP_CANCEL_CLEANUP = 2
};
typedef struct S540GspCancellationSnapshot {
    NvU32 format, phase;
    NvBool bound, revoked, publicationInFlight;
    NvU64 generation, ownerThread, revokedAtNs, deadlineNs;
    NvU32 checks, operationAborts, cleanupExpirations;
} S540GspCancellationSnapshot;
/* One exact retained nv_state identity; bind/begin/cleanup/finish/unbind are
 * owned by the same ordinary worker. This is cancellation, not admission.
 * No API changes a GPU lost/reset/shutdown bit or proves hardware quiescence.
 */
NV_STATUS s540GspCancellationBind(void *state, S540GspCancellationToken *out);
NV_STATUS s540GspCancellationBegin(S540GspCancellationToken);
/* Actual PM revocation producer: no allocation, sleep or RM lock. */
NV_STATUS s540GspCancellationRevoke(S540GspCancellationToken);
/* Carries the actual PM callback's earlier monotonic event into a binding
 * created later. A future timestamp is refused; callers cannot extend an
 * already published deadline by repeating the request.
 */
NV_STATUS s540GspCancellationRevokeAt(S540GspCancellationToken, NvU64 eventNs);
/* Exact operation owner only. Unbound/other identities and callout threads
 * have no matching operation here; NV_OK does not attest their readiness.
 */
NV_STATUS s540GspCancellationCheckState(const void *state);
/* Lock-owner boundaries may have no OBJGPU yet. The scope is derived from the
 * bound worker and actual phase, never a caller readiness flag. Check may run
 * while CPU interrupts are disabled; Pause requires restored ordinary context.
 */
NvBool s540GspCancellationCurrentScopeActive(void);
NV_STATUS s540GspCancellationCheckCurrent(void);
NV_STATUS s540GspCancellationPauseCurrent(void);
/* The original unwind must explicitly enter cleanup. Revocation then stops
 * new initialization work but permits real teardown until its fixed PM
 * deadline; timeout preserves ownership and is never an acknowledgement.
 */
NV_STATUS s540GspCancellationBeginCleanupState(const void *state);
NV_STATUS s540GspCancellationFinish(S540GspCancellationToken);
/* Requires completed original calls and PM callback exclusion. Refuses an
 * active operation or a revocation publication still in flight. Storage is
 * fixed, generation tagged, and contains no callback-owner pointer.
 */
NV_STATUS s540GspCancellationUnbind(S540GspCancellationToken);
NV_STATUS s540GspCancellationGetSnapshot(S540GspCancellationToken,
                                         S540GspCancellationSnapshot *out);
#ifdef __cplusplus
}
#endif
#endif
