/* All fields live in the actual backend allocation; never caller flags. */
struct BackendConstruction {
    S540FirstTxnHostIdentity identity{};
    NvU64 permit=0;
    BackendConstruction() { (void)s540FirstTxnBackendBegin(&identity,&permit); }
    ~BackendConstruction() { if(permit && s540FirstTxnBackendEnd(permit)!=NV_OK)violation("backend construction scope"); }
    bool allowed() const { return permit!=0; }
    BackendConstruction(const BackendConstruction&)=delete;
    BackendConstruction&operator=(const BackendConstruction&)=delete;
};
void retainBackend(Guard *, NvU32);
struct BackendFinalizer {
    NvU64 permit=0;
    BackendFinalizer(Guard &guard,NvU32 bytes) {
        /* A conservative refusal during a reservation is permanent for this
         * object even if owner preflight later fails and reopens UNBOUND.
         * Otherwise a later free could leave a dangling retained-list node. */
        if(__atomic_load_n(&guard.backendRetained,__ATOMIC_ACQUIRE)) {
            retainBackend(&guard,bytes);return;
        }
        if(s540FirstTxnBackendBeginRelease(&guard.backendIdentity,&permit)!=NV_OK)
            retainBackend(&guard,bytes);
    }
    ~BackendFinalizer() { if(permit && s540FirstTxnBackendEnd(permit)!=NV_OK)violation("backend finalizer scope"); }
    bool allowed() const { return permit!=0; }
    BackendFinalizer(const BackendFinalizer&)=delete;
    BackendFinalizer&operator=(const BackendFinalizer&)=delete;
};
struct BackendSnapshot {
    NvU64 retainedObjects,retainedBytes,associatedObjects,legacyObjects,releaseRefusals;
};
BackendSnapshot backendSnapshot();
