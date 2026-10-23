// Immutable after publication. The actual retained Impl owns every pointer.
struct RuntimeEntry {
    const void *owner=nullptr, *nv=nullptr;
    NvU64 thread=0;
    S540GspCancellationToken cancellation=0;
    S540NvidiaGspPower::Lease *power=nullptr;
    NvU32 stage=S540_RUNTIME_UNUSED;
};
static RuntimeEntry *activeRuntimeEntry=nullptr;
static NvU32 runtimeAttemptClaim=0;
static bool runtimeEqual(const void *a,const void *b,NvU32 bytes) {
    const auto *x=static_cast<const NvU8 *>(a),*y=static_cast<const NvU8 *>(b);
    NvU8 difference=0;for(NvU32 i=0;i<bytes;++i)difference|=NvU8(x[i]^y[i]);
    return !difference;
}
static NV_STATUS runtimeGlobalEntry() {
    const RuntimeEntry *entry=__atomic_load_n(&activeRuntimeEntry,__ATOMIC_ACQUIRE);
    NvU64 tid=0;S540FirstTxnHostIdentity master{};S540FirstTxnGlobalSnapshot global{};
    S540GspCancellationSnapshot cancellation{};
    if(!entry||!entry->owner||!entry->nv||!entry->power||!entry->thread||
       __atomic_load_n(&entry->stage,__ATOMIC_ACQUIRE)!=S540_RUNTIME_GLOBAL||
       !s540Darwin_os_semaphore_may_sleep())return NV_ERR_NOT_READY;
    NV_STATUS status=s540Darwin_os_get_current_thread(&tid);
    if(status!=NV_OK)return status;
    if(tid!=entry->thread)return NV_ERR_INVALID_STATE;
    status=s540FirstTxnMasterIdentity(&master);if(status!=NV_OK)return status;
    status=s540FirstTxnGlobalReadMaster(&global);if(status!=NV_OK)return status;
    if(master.owner!=entry->owner||!master.generation||global.owner!=entry->owner||
       global.generation!=master.generation||global.masterThread!=tid||global.nv||
       global.state!=S540_FIRST_GLOBAL_UNUSED||global.originalReturned||global.validated)
        return NV_ERR_INVALID_STATE;
    status=s540GspCancellationGetSnapshot(entry->cancellation,&cancellation);if(status!=NV_OK)return status;
    if(!cancellation.bound||cancellation.generation!=entry->cancellation||
       cancellation.ownerThread!=tid||cancellation.phase!=S540_GSP_CANCEL_OPERATION||
       cancellation.revoked||cancellation.publicationInFlight)return NV_ERR_OPERATION_ABORTED;
    status=s540GspCancellationCheckState(entry->nv);if(status!=NV_OK)return status;
    return entry->power->status();
}
