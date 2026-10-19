static NvBool globalMaster(void)
{
    return bound() && LD(&record.owner) && master() &&
        s540Darwin_os_semaphore_may_sleep();
}
NV_STATUS s540FirstTxnMasterIdentity(S540FirstTxnHostIdentity *out)
{
    S540FirstTxnHostIdentity identity={0};
    if(!out)return NV_ERR_INVALID_ARGUMENT;
    if(!globalMaster())return NV_ERR_INVALID_STATE;
    if(first()!=NV_OK)return first();
    if(LD(&record.phase)!=S540_FIRST_OP)return NV_ERR_INVALID_STATE;
    identity.owner=LD(&record.owner);identity.generation=LD(&record.generation);
    *out=identity;return NV_OK;
}
NV_STATUS s540FirstTxnGlobalGetSnapshot(S540FirstTxnGlobalSnapshot *out)
{
    S540FirstTxnGlobalSnapshot view={0};
    if(!out)return NV_ERR_INVALID_ARGUMENT;
    view.owner=LD(&record.owner);view.nv=LD(&record.nv);
    view.generation=LD(&record.generation);view.masterThread=LD(&record.masterThread);
    view.state=LD(&globalEpoch.state);view.firstStatus=first();
    view.originalStatus=LD(&globalEpoch.originalStatus);
    view.validationStatus=LD(&globalEpoch.validationStatus);
    view.originalReturned=LD(&globalEpoch.originalReturned)!=0;
    view.validated=LD(&globalEpoch.validated)!=0;
    *out=view;return NV_OK;
}
NV_STATUS s540FirstTxnGlobalReadMaster(S540FirstTxnGlobalSnapshot *out)
{
    S540FirstTxnHostIdentity identity={0};NV_STATUS status;
    if(!out)return NV_ERR_INVALID_ARGUMENT;
    status=s540FirstTxnMasterIdentity(&identity);if(status!=NV_OK)return status;
    return s540FirstTxnGlobalGetSnapshot(out);
}
NV_STATUS s540FirstTxnGlobalEnter(void)
{
    S540FirstTxnHostIdentity identity={0};NV_STATUS status;
    NvU32 unused=S540_FIRST_GLOBAL_UNUSED;
    status=s540FirstTxnMasterIdentity(&identity);if(status!=NV_OK)return status;
    if(LD(&record.nv)||
        LD(&record.originalInFlight)||LD(&record.originalReturned)||
        liveEntries(work)||liveEntries(direct))return NV_ERR_INVALID_STATE;
    if(!__atomic_compare_exchange_n(&globalEpoch.state,&unused,
        (NvU32)S540_FIRST_GLOBAL_RESERVED,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
        return NV_ERR_IN_USE;
    /* The owner/generation are immutable after BeginOwner. They are pulled
     * again by every completion; no caller-supplied identity authorizes it. */
    globalEpoch.owner=identity.owner;globalEpoch.generation=identity.generation;
    globalEpoch.thread=LD(&record.masterThread);
    if(first()!=NV_OK){ST(&globalEpoch.state,(NvU32)S540_FIRST_GLOBAL_RETAINED);return first();}
    ST(&globalEpoch.state,(NvU32)S540_FIRST_GLOBAL_IN_CORE);return NV_OK;
}
static NvBool exactGlobalMaster(void)
{
    return globalMaster() && globalEpoch.owner==LD(&record.owner) &&
        globalEpoch.generation==LD(&record.generation) &&
        globalEpoch.thread==LD(&record.masterThread);
}
NV_STATUS s540FirstTxnGlobalAbort(NV_STATUS failure)
{
    if(!exactGlobalMaster()||LD(&globalEpoch.state)!=S540_FIRST_GLOBAL_IN_CORE||
        LD(&globalEpoch.originalReturned)||failure==NV_OK)return NV_ERR_INVALID_STATE;
    ST(&globalEpoch.validationStatus,(NvU32)failure);
    (void)refuse(failure,SITE_GLOBAL);
    ST(&globalEpoch.state,(NvU32)S540_FIRST_GLOBAL_RETAINED);return first();
}
NV_STATUS s540FirstTxnGlobalOriginalReturned(NV_STATUS outcome)
{
    if(!exactGlobalMaster()||LD(&globalEpoch.state)!=S540_FIRST_GLOBAL_IN_CORE||
        LD(&globalEpoch.originalReturned))return NV_ERR_INVALID_STATE;
    ST(&globalEpoch.originalStatus,(NvU32)outcome);
    ST(&globalEpoch.originalReturned,1U);
    if(outcome!=NV_OK)(void)refuse(outcome,SITE_GLOBAL);
    ST(&globalEpoch.state,(NvU32)(first()==NV_OK?
        S540_FIRST_GLOBAL_RETURNED:S540_FIRST_GLOBAL_RETAINED));
    return first()!=NV_OK?first():outcome;
}
NV_STATUS s540FirstTxnGlobalValidated(NV_STATUS outcome)
{
    if(!exactGlobalMaster()||LD(&globalEpoch.state)!=S540_FIRST_GLOBAL_RETURNED||
        !LD(&globalEpoch.originalReturned)||LD(&globalEpoch.validated)||
        LD(&globalEpoch.originalStatus)!=NV_OK)return NV_ERR_INVALID_STATE;
    ST(&globalEpoch.validationStatus,(NvU32)outcome);
    if(outcome!=NV_OK)(void)refuse(outcome,SITE_GLOBAL);
    if(first()!=NV_OK){ST(&globalEpoch.state,(NvU32)S540_FIRST_GLOBAL_RETAINED);return first();}
    ST(&globalEpoch.validated,1U);
    ST(&globalEpoch.state,(NvU32)S540_FIRST_GLOBAL_READY);
    return first();
}
