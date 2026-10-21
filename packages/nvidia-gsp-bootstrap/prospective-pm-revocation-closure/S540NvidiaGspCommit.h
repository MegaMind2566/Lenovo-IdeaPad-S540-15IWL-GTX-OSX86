/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GSP_COMMIT_H
#define S540_NVIDIA_GSP_COMMIT_H
#include "../cancellation/S540NvidiaGspCancellation.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef NvU64 S540GspCancellationCommitLease;
typedef struct S540GspCancellationCommitSnapshot {
    NvU64 generation;
    NvU32 inFlight, origin, accepted, completed, refused;
    NvBool revoked, publicationInFlight;
} S540GspCancellationCommitSnapshot;
/* Exact bound state and the actual enrolled OPERATION scope are required.
 * This serializes acceptance against cancellation publication, not against
 * the earlier PM event or the physical device endpoint. No waiting occurs.
 */
NV_STATUS s540GspCancellationCommitEnterState(const void *state,
    S540GspCancellationCommitLease *out);
/* Genuine CLEANUP transport may submit until the existing fixed PM deadline.
 * The actual current scope supplies that authority; callers supply no phase.
 */
NV_STATUS s540GspCancellationSubmitEnterState(const void *state,
    S540GspCancellationCommitLease *out);
/* Call only after the exact accepted endpoint actually returned. A failure
 * preserves the reservation and binding; it never proves endpoint rollback.
 */
NV_STATUS s540GspCancellationCommitLeaveState(const void *state,
    S540GspCancellationCommitLease lease);
/* Includes reservation publication/retirement windows. No lease token is
 * disclosed. A zero observation is not ingress closure or hardware drain.
 */
NV_STATUS s540GspCancellationCommitReadState(const void *state,
    S540GspCancellationCommitSnapshot *out);
struct OBJGPU;
/* Typed original bridge obtains the actual NV_GET_NV_STATE identity. */
NV_STATUS s540GspCancellationSubmitEnterGpu(struct OBJGPU *gpu,
    S540GspCancellationCommitLease *out);
NV_STATUS s540GspCancellationCommitLeaveGpu(struct OBJGPU *gpu,
    S540GspCancellationCommitLease lease);
#ifdef __cplusplus
}
#endif
#endif
