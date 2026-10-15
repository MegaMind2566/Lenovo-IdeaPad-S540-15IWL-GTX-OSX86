NV_STATUS
serverConstruct
(
    RsServer *pServer,
    RS_PRIV_LEVEL privilegeLevel,
    NvU32 maxDomains
)
{
    NvU32 i;
    PORT_MEM_ALLOCATOR *pAllocator;
    NvBool listsReady = NV_FALSE;
    (void)maxDomains;
    /* Scoped Darwin adaptation: callers provide a zero-initialized server.
     * Check every acquired lock, publish readiness last, and reset ownership
     * after failure. Original serverDestruct remains the successful unwind. */
    if (pServer == NULL || pServer->bConstructed)
        return NV_ERR_INVALID_STATE;
    portMemSet(pServer, 0, sizeof(*pServer));
    pAllocator = portMemAllocatorCreateNonPaged();
    if (pAllocator == NULL)
        return NV_ERR_INSUFFICIENT_RESOURCES;
    pServer->privilegeLevel = privilegeLevel;
    pServer->pAllocator = pAllocator;
    pServer->bRsAccessEnabled = NV_TRUE;
    pServer->allClientLockOwnerTid = ~0ULL;
    pServer->internalHandleBase = RS_CLIENT_INTERNAL_HANDLE_BASE;
    pServer->clientHandleBase = RS_CLIENT_HANDLE_BASE;
    pServer->pClientSortedList = PORT_ALLOC(pAllocator,
        sizeof(RsClientList) * RS_CLIENT_HANDLE_BUCKET_COUNT);
    if (pServer->pClientSortedList == NULL)
        goto fail;
    for (i = 0; i < RS_CLIENT_HANDLE_BUCKET_COUNT; ++i)
        listInitIntrusive(&pServer->pClientSortedList[i]);
    pServer->pClientListLock = portSyncSpinlockCreate(pAllocator);
    if (pServer->pClientListLock == NULL)
        goto fail;
#if RS_STANDALONE
    pServer->pTopLock = portSyncRwLockCreate(pAllocator);
    if (pServer->pTopLock == NULL)
        goto fail;
    pServer->pResLock = portSyncRwLockCreate(pAllocator);
    if (pServer->pResLock == NULL)
        goto fail;
    pServer->topLockOwnerTid = ~0ULL;
#endif
    pServer->pShareMapLock = portSyncSpinlockCreate(pAllocator);
    if (pServer->pShareMapLock == NULL)
        goto fail;
    mapInitIntrusive(&pServer->shareMap);
    listInit(&pServer->defaultInheritedSharePolicyList, pAllocator);
    listInit(&pServer->globalInternalSharePolicyList, pAllocator);
    listInitIntrusive(&pServer->disabledClientList);
    listsReady = NV_TRUE;
    if (serverInitGlobalSharePolicies(pServer) != NV_OK)
        goto fail;
    pServer->pDisabledClientListLock = portSyncSpinlockCreate(pAllocator);
    if (pServer->pDisabledClientListLock == NULL)
        goto fail;
    pServer->bConstructed = NV_TRUE;
    return NV_OK;
fail:
    if (pServer->pDisabledClientListLock != NULL)
        portSyncSpinlockDestroy(pServer->pDisabledClientListLock);
    if (listsReady)
    {
        mapDestroy(&pServer->shareMap);
        listDestroy(&pServer->defaultInheritedSharePolicyList);
        listDestroy(&pServer->globalInternalSharePolicyList);
        listDestroy(&pServer->disabledClientList);
    }
    if (pServer->pShareMapLock != NULL)
        portSyncSpinlockDestroy(pServer->pShareMapLock);
#if RS_STANDALONE
    if (pServer->pResLock != NULL)
        portSyncRwLockDestroy(pServer->pResLock);
    if (pServer->pTopLock != NULL)
        portSyncRwLockDestroy(pServer->pTopLock);
#endif
    if (pServer->pClientListLock != NULL)
        portSyncSpinlockDestroy(pServer->pClientListLock);
    if (pServer->pClientSortedList != NULL)
        PORT_FREE(pAllocator, pServer->pClientSortedList);
    portMemAllocatorRelease(pAllocator);
    portMemSet(pServer, 0, sizeof(*pServer));
    return NV_ERR_INSUFFICIENT_RESOURCES;
}
