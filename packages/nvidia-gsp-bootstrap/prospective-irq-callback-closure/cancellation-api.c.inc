/* Two fixed scopes reflect the serialized hard ISR and workloop bottom half.
 * They support a hard interrupt of the actual owner or an enrolled callback;
 * generic one-shot leases intentionally reject those nested contexts. */
static struct { NvU64 binding,thread;NvU32 active,origin; } irqScopes[2];
static NvBool irqScopePending(void) {
    return __atomic_load_n(&irqScopes[0].active,__ATOMIC_ACQUIRE)||
           __atomic_load_n(&irqScopes[1].active,__ATOMIC_ACQUIRE);
}
static NvU64 irqScopeOrigin(NvU64 value,NvU64 tid) {
    NvU32 i;
    /* The hard ISR overrides an interrupted bottom-half origin. */
    for(i=0;i<2;++i)
        if(__atomic_load_n(&irqScopes[i].active,__ATOMIC_ACQUIRE)==2U&&
           __atomic_load_n(&irqScopes[i].binding,__ATOMIC_RELAXED)==generation(value)&&
           __atomic_load_n(&irqScopes[i].thread,__ATOMIC_RELAXED)==tid)
            return __atomic_load_n(&irqScopes[i].origin,__ATOMIC_RELAXED);
    return 0;
}
NV_STATUS s540GspCancellationEnterIrqScope(const void *state,NvU32 role,NvU32 inherited) {
    NvU64 value=word(),origin,tid=thread();NvU32 index,empty=0,actualOrigin=0;
    if(!state||state!=__atomic_load_n(&slot.state,__ATOMIC_ACQUIRE)||role<1||role>2||
       !tid||!generation(value)||!(value&BOUND)||!(value&(OPERATION|CLEANUP)))return NV_ERR_INVALID_STATE;
    /* The strong record must already be inside the genuine registered
     * platform stage. The public cancellation call alone cannot enroll a
     * foreign thread or turn caller-supplied inherited bits into authority. */
    if(s540FirstTxnIrqReadEnteredScope(state,role,&actualOrigin)!=NV_OK||actualOrigin!=inherited)
        return NV_ERR_INVALID_STATE;
    /* The pending packed word carries the genuine top-half origin. A merged
     * OP+CLEANUP set preserves OP: revocation cannot upgrade old accepted work. */
    if(role==1) {
        if(inherited)return NV_ERR_INVALID_ARGUMENT;
        origin=currentOrigin(value);
        if(!origin)origin=value&CLEANUP?CLEANUP:OPERATION;
    } else {
        if(!inherited||(inherited&~(OPERATION|CLEANUP)))return NV_ERR_INVALID_STATE;
        origin=inherited&OPERATION?OPERATION:CLEANUP;
    }
    /* The authenticated record anchor predates controller arm and survives
     * complete IRQ drain. Do not acquire CAPTURE_BUSY here: the hard ISR may
     * have interrupted the thread that owns that publication bit. */
    index=role-1;
    if(!__atomic_compare_exchange_n(&irqScopes[index].active,&empty,1U,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_ERR_IN_USE;
    __atomic_store_n(&irqScopes[index].binding,generation(value),__ATOMIC_RELAXED);
    __atomic_store_n(&irqScopes[index].thread,tid,__ATOMIC_RELAXED);
    __atomic_store_n(&irqScopes[index].origin,(NvU32)origin,__ATOMIC_RELEASE);
    __atomic_store_n(&irqScopes[index].active,2U,__ATOMIC_RELEASE);return NV_OK;
}
NV_STATUS s540GspCancellationLeaveIrqScope(const void *state,NvU32 role) {
    NvU32 index;if(!state||state!=__atomic_load_n(&slot.state,__ATOMIC_ACQUIRE)||role<1||role>2)
        return NV_ERR_INVALID_ARGUMENT;
    index=role-1;
    if(!__atomic_load_n(&irqScopes[index].active,__ATOMIC_ACQUIRE)||
       __atomic_load_n(&irqScopes[index].thread,__ATOMIC_RELAXED)!=thread())return NV_ERR_INVALID_STATE;
    __atomic_store_n(&irqScopes[index].origin,0U,__ATOMIC_RELEASE);
    __atomic_store_n(&irqScopes[index].thread,0ULL,__ATOMIC_RELAXED);
    __atomic_store_n(&irqScopes[index].active,0U,__ATOMIC_RELEASE);return NV_OK;
}
NvU32 s540GspCancellationIrqOrigin(NvU32 role) {
    NvU32 index;if(role<1||role>2)return 0;index=role-1;
    return __atomic_load_n(&irqScopes[index].active,__ATOMIC_ACQUIRE)==2U&&
        __atomic_load_n(&irqScopes[index].thread,__ATOMIC_RELAXED)==thread()?
        __atomic_load_n(&irqScopes[index].origin,__ATOMIC_ACQUIRE):0;
}
