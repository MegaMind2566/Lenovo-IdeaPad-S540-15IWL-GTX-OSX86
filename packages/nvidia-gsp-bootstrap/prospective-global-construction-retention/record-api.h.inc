/* Retain the exact failed original OBJSYS construction. This never reports a
 * completed global epoch. The typed probe reads the actual failure boundary. */
typedef struct S540FirstTxnGlobalConstructionRetention {
    const void *system, *owner;
    NvU64 generation, masterThread;
    NvU32 originalFailure;
} S540FirstTxnGlobalConstructionRetention;
NV_STATUS s540FirstTxnGlobalRetainFailedSystem(const void *actualSystem, NV_STATUS actualFailure);
NV_STATUS s540FirstTxnGlobalOriginalSystemFailure(const void *actualSystem, NV_STATUS actualFailure);
NvBool s540FirstTxnGlobalFailedSystemRetained(const void *actualSystem);
NV_STATUS s540FirstTxnGlobalGetConstructionRetention(S540FirstTxnGlobalConstructionRetention *);
