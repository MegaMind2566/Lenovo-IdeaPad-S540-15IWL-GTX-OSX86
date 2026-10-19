/* Serialized original global construction belongs to the same immutable owner
 * as later device construction. Only the actual ordinary master may enter;
 * HostCaptureAllocation, which also permits genuine callbacks, is insufficient.
 * Snapshot is diagnostic. No API resets the epoch or grants kernel entry. */
enum S540FirstTxnGlobalState { S540_FIRST_GLOBAL_UNUSED=0,
    S540_FIRST_GLOBAL_RESERVED=1, S540_FIRST_GLOBAL_IN_CORE=2,
    S540_FIRST_GLOBAL_RETURNED=3, S540_FIRST_GLOBAL_READY=4,
    S540_FIRST_GLOBAL_RETAINED=5 };
typedef struct S540FirstTxnGlobalSnapshot {
    const void *owner, *nv;
    NvU64 generation, masterThread;
    NvU32 state, firstStatus, originalStatus, validationStatus;
    NvBool originalReturned, validated;
} S540FirstTxnGlobalSnapshot;
/* Exact actual master only; outputs remain unchanged on refusal. */
NV_STATUS s540FirstTxnMasterIdentity(S540FirstTxnHostIdentity *);
NV_STATUS s540FirstTxnGlobalReadMaster(S540FirstTxnGlobalSnapshot *);
NV_STATUS s540FirstTxnGlobalGetSnapshot(S540FirstTxnGlobalSnapshot *);
NV_STATUS s540FirstTxnGlobalEnter(void);
NV_STATUS s540FirstTxnGlobalAbort(NV_STATUS actualFailure);
NV_STATUS s540FirstTxnGlobalOriginalReturned(NV_STATUS actualOriginalStatus);
NV_STATUS s540FirstTxnGlobalValidated(NV_STATUS actualValidationStatus);
