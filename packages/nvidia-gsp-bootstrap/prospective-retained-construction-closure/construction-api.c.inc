/* Only these exact original sysConstruct failure/ancestor-cleanup hooks use
 * this protocol. A sticky failure cannot invalidate immutable master identity.
 * The actual core return is recorded later by GlobalOriginalReturned. */
NvBool s540FirstTxnGlobalRetainConstruction(const void *system, NV_STATUS failure)
{
    if(!system||failure==NV_OK||!exactGlobalMaster()||
        LD(&globalEpoch.state)!=S540_FIRST_GLOBAL_IN_CORE||
        LD(&globalEpoch.originalReturned))return NV_FALSE;
    if(LD(&globalEpoch.constructionRetained))
        return LD(&globalEpoch.retainedSystem)==system&&
            LD(&globalEpoch.constructionStatus)==(NvU32)failure;
    ST(&globalEpoch.retainedSystem,system);
    ST(&globalEpoch.constructionStatus,(NvU32)failure);
    ST(&globalEpoch.constructionRetained,1U);
    (void)refuse(failure,SITE_GLOBAL);
    return NV_TRUE;
}
NvBool s540FirstTxnGlobalConstructionRetained(const void *system)
{
    return system&&exactGlobalMaster()&&
        LD(&globalEpoch.state)==S540_FIRST_GLOBAL_IN_CORE&&
        !LD(&globalEpoch.originalReturned)&&
        LD(&globalEpoch.constructionRetained)&&
        LD(&globalEpoch.retainedSystem)==system&&
        LD(&globalEpoch.constructionStatus)!=NV_OK&&first()!=NV_OK;
}
