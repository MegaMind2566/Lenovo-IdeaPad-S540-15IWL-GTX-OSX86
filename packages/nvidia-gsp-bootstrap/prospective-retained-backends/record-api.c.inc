/* Actual strong-record participant. No caller can declare an active epoch.
 * Scope count precedes the phase read. BeginOwner reserves phase first and
 * then refuses a nonzero count, so a physical preowner release cannot cross
 * successful owner publication. Failed/reserving acquisitions touch nothing. */
NV_STATUS s540FirstTxnBackendBegin(S540FirstTxnHostIdentity *identity, NvU64 *permit) {
    NvU32 count, i, phase; NvU64 id, empty; NV_STATUS status=NV_OK;
    if(!identity||!permit)return NV_ERR_INVALID_ARGUMENT;
    identity->owner=0;identity->generation=0;*permit=0;
    count=LD(&backendScopes);
    do { if(count>=CAPACITY)return NV_ERR_BUSY_RETRY; }
    while(!__atomic_compare_exchange_n(&backendScopes,&count,count+1U,NV_FALSE,
        __ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST));
    phase=__atomic_load_n(&record.phase,__ATOMIC_SEQ_CST);
    if(phase==S540_FIRST_UNBOUND && !bound()) {
        /* Ordinary startup/shutdown before the one permanent owner. */
    } else if(bound()) {
        if(!authorized())status=refuse(NV_ERR_INVALID_STATE,SITE_BACKEND);
        else if(first()!=NV_OK)status=first();
        else {identity->owner=LD(&record.owner);identity->generation=LD(&record.generation);}
    } else status=NV_ERR_NOT_READY;
    if(status==NV_OK) {
        id=nextId();
        if(!id)status=NV_ERR_INSUFFICIENT_RESOURCES;
        else {
            for(i=0;i<CAPACITY;++i){
                empty=0;
                if(__atomic_compare_exchange_n(&backendPermits[i].id,&empty,~0ULL,NV_FALSE,
                    __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))break;
            }
            if(i==CAPACITY)status=NV_ERR_INSUFFICIENT_RESOURCES;
            else {ST(&backendPermits[i].thread,currentThread());ST(&backendPermits[i].id,id);*permit=id;}
        }
    }
    if(status!=NV_OK){identity->owner=0;identity->generation=0;
        __atomic_fetch_sub(&backendScopes,1U,__ATOMIC_ACQ_REL);}
    return status;
}
NV_STATUS s540FirstTxnBackendEnd(NvU64 permit) {
    NvU32 i;NvU64 expected=permit;
    if(!permit||permit==~0ULL)return NV_ERR_INVALID_ARGUMENT;
    for(i=0;i<CAPACITY;++i)if(LD(&backendPermits[i].id)==permit)break;
    if(i==CAPACITY||LD(&backendPermits[i].thread)!=currentThread())return NV_ERR_INVALID_STATE;
    if(!__atomic_compare_exchange_n(&backendPermits[i].id,&expected,0ULL,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_ERR_INVALID_STATE;
    __atomic_fetch_sub(&backendScopes,1U,__ATOMIC_ACQ_REL);return NV_OK;
}
NV_STATUS s540FirstTxnBackendBeginRelease(const S540FirstTxnHostIdentity *birth, NvU64 *permit) {
    S540FirstTxnHostIdentity actual={0};NV_STATUS status;
    if(!birth||!permit)return NV_ERR_INVALID_ARGUMENT;
    *permit=0;status=s540FirstTxnBackendBegin(&actual,permit);
    if(status!=NV_OK)return status;
    if(!actual.generation && !actual.owner && !birth->generation && !birth->owner)return NV_OK;
    (void)s540FirstTxnBackendEnd(*permit);*permit=0;
    /* Even an old/unassociated object is preserved. It is NEVER retagged as
     * belonging to this epoch. A mismatched nonzero tuple is a real refusal. */
    if((birth->owner||birth->generation) &&
       (birth->owner!=actual.owner||birth->generation!=actual.generation))
        return refuse(NV_ERR_INVALID_STATE,SITE_BACKEND);
    return NV_ERR_NOT_SUPPORTED;
}
