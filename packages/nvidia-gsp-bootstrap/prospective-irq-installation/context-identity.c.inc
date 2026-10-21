/* Exact retained Context storage and original ABI fields, never caller facts. */
static NvBool irqStackInitialized(nvidia_stack_t *stack)
{
    return stack && !((NvUPtr)stack&15U) && !((NvUPtr)stack->stack&15U) &&
        stack->size==sizeof(stack->stack) && stack->top==stack->stack+stack->size;
}
NvBool s540GspContextMatchIrqIdentity(S540GspContext *context,const S540GspIrqIdentity *id)
{
    S540GspContext *registered=__atomic_load_n(&metadataContext,__ATOMIC_ACQUIRE);
    /* The record/session epoch permanently owns this Context. No mutable
     * adapter-init flag is read by the hard ISR identity check. */
    return context && registered==context && id && id->context==context &&
        id->nv==&context->nv && id->pciHandle==context->nv.handle &&
        id->mainStack==&context->stacks[MAIN] && id->isrStack==&context->stacks[ISR] &&
        id->lockedStack==&context->stacks[LOCKED_BH] && id->unlockedStack==&context->stacks[UNLOCKED_BH] &&
        id->isrGuard==context->isrGuard && id->privateState==context->nv.priv && context->nv.priv &&
        id->ownerThread==context->ownerThread && id->generation==context->firstTxnGeneration &&
        id->generation && irqStackInitialized(&context->stacks[MAIN]) &&
        irqStackInitialized(&context->stacks[ISR]) && irqStackInitialized(&context->stacks[LOCKED_BH]) &&
        irqStackInitialized(&context->stacks[UNLOCKED_BH]);
}
NV_STATUS s540GspContextReadIrqIdentity(S540GspContext *context,S540GspIrqIdentity *out)
{
    S540GspIrqIdentity id={0};S540FirstTxnGlobalSnapshot epoch={0};NV_STATUS status;
    if(!out||!owner(context)||!context->metadataBound||!context->state.created||
       !context->state.eventLocks||!context->state.privateState||context->state.originalReleased||
       context->state.finalDetach||context->state.quarantined||!context->isrGuard||!context->nv.priv||
       !context->firstTxnGeneration)return NV_ERR_INVALID_STATE;
    status=s540FirstTxnGlobalReadMaster(&epoch);if(status!=NV_OK)return status;
    if(epoch.nv!=&context->nv||epoch.generation!=context->firstTxnGeneration||
       epoch.masterThread!=context->ownerThread||!epoch.owner||!epoch.validated||
       epoch.state!=S540_FIRST_GLOBAL_READY)return NV_ERR_INVALID_STATE;
    id.context=context;id.nv=&context->nv;id.mainStack=&context->stacks[MAIN];id.isrStack=&context->stacks[ISR];
    id.lockedStack=&context->stacks[LOCKED_BH];id.unlockedStack=&context->stacks[UNLOCKED_BH];
    id.privateState=context->nv.priv;id.isrGuard=context->isrGuard;id.pciHandle=context->nv.handle;
    id.ownerThread=context->ownerThread;id.generation=context->firstTxnGeneration;
    if(!s540GspContextMatchIrqIdentity(context,&id))return NV_ERR_INVALID_STATE;
    *out=id;return NV_OK;
}
NV_STATUS s540GspContextSelectMessageInterrupt(S540GspContext *context,const S540GspIrqIdentity *id)
{
    S540GspIrqModeFacts facts={0};NV_STATUS status;
    if(!owner(context)||!s540GspContextMatchIrqIdentity(context,id)||context->state.adapterAttempted||
       context->state.originalReleased||context->state.quarantined)return NV_ERR_INVALID_STATE;
    status=s540GspIrqReadBackendMode(&context->nv,&facts);if(status!=NV_OK)return status;
    if(facts.nv!=&context->nv||facts.generation!=context->firstTxnGeneration||!facts.known||
       !facts.messageSignaled||!facts.msiCapable||facts.msixCapable||facts.msiVectors!=1)
        return NV_ERR_NOT_SUPPORTED;
    /* The selected backend has one actual MSI vector and no MSI-X capability.
     * Preserve every unrelated original flag and refuse any prior selection. */
    if(context->nv.flags&(NV_FLAG_USES_MSI|NV_FLAG_USES_MSIX))return NV_ERR_IN_USE;
    context->nv.flags|=NV_FLAG_USES_MSI;return NV_OK;
}
