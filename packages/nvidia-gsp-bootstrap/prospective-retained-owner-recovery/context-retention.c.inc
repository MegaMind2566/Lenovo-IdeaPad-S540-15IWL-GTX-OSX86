/* SPDX-License-Identifier: MIT */
NV_STATUS s540GspContextStopRetainedServices(S540GspContext *context)
{
    S540GspTimersSnapshot timers;
    NV_STATUS status;
    if(!owner(context)||!context->retainedOwnerGeneration)return NV_ERR_INVALID_STATE;
    if(context->firstTxnGeneration)
        return s540FirstTxnServicesSealAndDrain(&context->nv,context->firstTxnGeneration);
    s540GspTimersGetSnapshot(&timers);
    if(timers.bound){status=s540GspTimersStop(&context->nv);if(status!=NV_OK)return status;}
    if(context->deviceQueue){status=s540DarwinWorkQueueStop(context->deviceQueue);if(status!=NV_OK)return status;}
    if(context->globalQueue){status=s540DarwinWorkQueueStop(context->globalQueue);if(status!=NV_OK)return status;}
    context->state.workStopped=NV_TRUE;
    return NV_OK;
}
NV_STATUS s540GspContextRunRetainedShutdownProtocol(S540GspContext *context)
{
    NV_STATUS status;
    if(!owner(context)||!context->retainedOwnerGeneration||!context->firstTxnGeneration||
        !context->state.adapterInitialized||context->retainedShutdownAttempted)return NV_ERR_INVALID_STATE;
    status=s540IrqParticipantValidateDrained(&context->nv,context->firstTxnGeneration);
    if(status!=NV_OK)return status;
    context->retainedShutdownAttempted=NV_TRUE;
    status=s540ShutdownProtocolRun(&context->stacks[MAIN],&context->nv,&context->retainedShutdown);
    if(status!=NV_OK)context->state.quarantined=NV_TRUE;
    return status;
}
NV_STATUS s540GspContextReadRetainedShutdown(S540GspContext *context,NvBool *attempted,NvBool *completed)
{
    if(!owner(context)||!attempted||!completed)return NV_ERR_INVALID_STATE;
    *attempted=context->retainedShutdownAttempted;
    *completed=context->retainedShutdown.originalReturned&&context->retainedShutdown.protocolCompleted;
    return NV_OK;
}
