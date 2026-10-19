/* No full lifecycle query is used before original globals exist. This exact
 * basic-lock-model profile excludes the legacy RM semaphore; then the genuine
 * TLS API, per-GPU and allocation-lock owner probes observe the actual master.
 * This is current-thread evidence within the permanent outer epoch only. */
static NV_STATUS postCoreOwnership(void)
{
    OBJSYS *sys=SYS_GET_INSTANCE();
    S540FirstTxnGlobalSnapshot epoch={0};
    NvBool api=NV_FALSE,allocation=NV_FALSE;NvU32 mask=0;NvU64 thread=0;
    NV_STATUS status;
    if(!sys||!portIsInitialized()||sys->PDB_PROP_SYS_DESTRUCTING||sys->pSema)
        return NV_ERR_NOT_READY;
    status=s540FirstTxnGlobalReadMaster(&epoch);if(status!=NV_OK)return status;
    if(epoch.state!=S540_FIRST_GLOBAL_RETURNED||!epoch.originalReturned||
        epoch.originalStatus!=NV_OK||epoch.nv)return NV_ERR_INVALID_STATE;
    status=osGetCurrentThread(&thread);if(status!=NV_OK)return status;
    if(!thread||thread!=epoch.masterThread)return NV_ERR_INVALID_STATE;
    status=s540ProspectiveOriginalApiOwnership(&api);if(status!=NV_OK)return status;
    status=s540ProspectiveOriginalGpuOwnership(&mask,&allocation);if(status!=NV_OK)return status;
    return api||mask||allocation?NV_ERR_INVALID_LOCK_STATE:NV_OK;
}
NV_STATUS s540GlobalRmInitialize(S540NvidiaGlobalRmResult *out)
{
    S540NvidiaGlobalRmHostSnapshot host;
    NV_STATUS status,recordStatus;
    if(!out)return NV_ERR_INVALID_ARGUMENT;
    *out=(S540NvidiaGlobalRmResult){0};out->format=1;
#if defined(KERNEL)
    /* Final kernel stack/native/entry admission has not been established.
     * This immutable successor supplies the owner protocol, not that proof. */
    return out->startupStatus=NV_ERR_NOT_READY;
#endif
    status=s540FirstTxnGlobalEnter();
    if(status!=NV_OK)return out->startupStatus=status;
    if(__atomic_load_n(&running,__ATOMIC_ACQUIRE)){
        status=NV_ERR_STATE_IN_USE;goto beforeCoreFailure;
    }
    s540GlobalRmHostSnapshot(&host);
    if(!host.initialized||host.unavailableCalls||host.invalidFrees||
        !s540GlobalRmPlatformFacts()||!cryptoUnused()){
        status=NV_ERR_NOT_READY;goto beforeCoreFailure;
    }
    /* Ownership of a foreign registry/portable runtime/system is never
     * acquired. No partial failure attempts original shutdown or destruction. */
    if(portIsInitialized()||SYS_GET_INSTANCE()!=NULL){status=NV_ERR_IN_USE;goto beforeCoreFailure;}
    status=s540GlobalRmCheckRegistryCold();if(status!=NV_OK)goto beforeCoreFailure;
    status=coreInitializeRm();
    recordStatus=s540FirstTxnGlobalOriginalReturned(status);
    out->startupStatus=status;
    if(status!=NV_OK||recordStatus!=NV_OK){
        s540GlobalRmHostSnapshot(&host);out->unavailableCalls=host.unavailableCalls;
        out->osServiceMask=s540GlobalRmServiceMask();
        return recordStatus!=NV_OK?recordStatus:status;
    }
    inspect(out);
    s540GlobalRmHostSnapshot(&host);
    status=(!host.initialized||host.invalidFrees||
        !out->systemObject||!out->children||!out->resourceServer||
        !out->memoryExportClient||out->unavailableCalls||!cryptoUnused())
        ?NV_ERR_INVALID_STATE:postCoreOwnership();
    /* Construction may succeed through an upstream optional-allocation
     * fallback while the stronger actual Host record is already sticky. */
    recordStatus=s540FirstTxnGlobalValidated(status);
    if(status!=NV_OK||recordStatus!=NV_OK){
        out->startupStatus=status!=NV_OK?status:recordStatus;
        return recordStatus!=NV_OK?recordStatus:status;
    }
    __atomic_store_n(&running,NV_TRUE,__ATOMIC_RELEASE);
    out->initialized=NV_TRUE;return NV_OK;
beforeCoreFailure:
    out->startupStatus=status;
    recordStatus=s540FirstTxnGlobalAbort(status);
    return recordStatus!=NV_OK?recordStatus:status;
}
void s540GlobalRmShutdown(S540NvidiaGlobalRmResult *out)
{
    S540NvidiaGlobalRmHostSnapshot host;
    /* This profile has no global destruction transition. Keep the genuine
     * global objects and every associated service backing alive until reboot. */
    s540GlobalRmHostSnapshot(&host);
    if(out){out->cleanShutdown=NV_FALSE;out->unavailableCalls=host.unavailableCalls;
        out->osServiceMask=s540GlobalRmServiceMask();}
}
NvBool s540GlobalRmIsInitialized(void)
{
    return __atomic_load_n(&running,__ATOMIC_ACQUIRE);
}
