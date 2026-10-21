/* Exact original sysConstruct nonzero outcome retains its failed system.
 * No caller-owned create output is assigned; no readiness or release granted. */
NvBool s540FirstTxnGlobalRetainConstruction(const void *system, NV_STATUS actualFailure);
NvBool s540FirstTxnGlobalConstructionRetained(const void *system);
