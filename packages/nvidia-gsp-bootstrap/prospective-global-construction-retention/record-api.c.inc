NV_STATUS s540FirstTxnGlobalRetainFailedSystem(const void *system,NV_STATUS failure)
{
    NV_STATUS status;
    if(!system||failure==NV_OK||!exactGlobalMaster()||
        LD(&globalEpoch.state)!=S540_FIRST_GLOBAL_IN_CORE||
        LD(&globalEpoch.originalReturned))return NV_ERR_INVALID_STATE;
    status=s540FirstTxnGlobalOriginalSystemFailure(system,failure);
    if(status!=NV_OK)return status;
    if(LD(&failedGlobalSystem.system)){
        if(LD(&failedGlobalSystem.system)!=system||
            failedGlobalSystem.owner!=LD(&record.owner)||
            failedGlobalSystem.generation!=LD(&record.generation)||
            failedGlobalSystem.masterThread!=LD(&record.masterThread)||
            failedGlobalSystem.originalFailure!=failure)
            return refuse(NV_ERR_INVALID_STATE,SITE_GLOBAL);
        return NV_OK;
    }
    failedGlobalSystem.owner=LD(&record.owner);
    failedGlobalSystem.generation=LD(&record.generation);
    failedGlobalSystem.masterThread=LD(&record.masterThread);
    failedGlobalSystem.originalFailure=failure;
    (void)refuse(failure,SITE_GLOBAL);
    ST(&failedGlobalSystem.system,system);
    /* Only the failed construction fields have been retained. The original
     * failure and the global epoch's completion state remain unchanged. */
    return NV_OK;
}
NvBool s540FirstTxnGlobalFailedSystemRetained(const void *system)
{
    return system && exactGlobalMaster() && first()!=NV_OK &&
        LD(&globalEpoch.state)==S540_FIRST_GLOBAL_IN_CORE &&
        !LD(&globalEpoch.originalReturned) &&
        system==LD(&failedGlobalSystem.system) &&
        failedGlobalSystem.owner==LD(&record.owner) &&
        failedGlobalSystem.generation==LD(&record.generation) &&
        failedGlobalSystem.masterThread==LD(&record.masterThread) &&
        failedGlobalSystem.originalFailure!=NV_OK;
}
NV_STATUS s540FirstTxnGlobalGetConstructionRetention(S540FirstTxnGlobalConstructionRetention *out)
{
    S540FirstTxnGlobalConstructionRetention view={0};
    if(!out)return NV_ERR_INVALID_ARGUMENT;
    view.system=LD(&failedGlobalSystem.system);
    if(view.system){view.owner=failedGlobalSystem.owner;view.generation=failedGlobalSystem.generation;
        view.masterThread=failedGlobalSystem.masterThread;view.originalFailure=failedGlobalSystem.originalFailure;}
    *out=view;return NV_OK;
}
