/* Fixed source participant; callback stages are pulled from DarwinDevice. */
static struct {
    const void *nv, *backend;
    NvU64 generation, thread[2];
    NvU32 active[2];
} irqParticipant;
static NvBool irqAuthorized(NvU64 tid) {
    return tid && ((LD(&irqParticipant.active[0]) && LD(&irqParticipant.thread[0])==tid) ||
                   (LD(&irqParticipant.active[1]) && LD(&irqParticipant.thread[1])==tid));
}
NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *nv,NvU32 role,NvU32 *origin) {
    S540FirstTxnIrqContext observed={0};NV_STATUS status;NvU32 index;
    if(!origin||nv!=irqParticipant.nv||role<1||role>2)return NV_ERR_INVALID_ARGUMENT;
    /* Bind acquired the real cancellation anchor. Seal discards it only after
     * genuine IRQ drain; it prevents Finish/Unbind during any entering ISR. */
    if(!LD(&record.anchor))return NV_ERR_INVALID_STATE;
    index=role-1;
    if(!LD(&irqParticipant.active[index])||LD(&irqParticipant.thread[index])!=currentThread())
        return NV_ERR_INVALID_STATE;
    status=s540FirstTxnIrqReadContext(LD(&irqParticipant.backend),role,&observed);
    if(status!=NV_OK||observed.nv!=nv||observed.generation!=irqParticipant.generation||
       observed.stage!=role||observed.thread!=currentThread())return NV_ERR_INVALID_STATE;
    *origin=observed.origin;return NV_OK;
}
NV_STATUS s540FirstTxnIrqBind(const void *nv,const void *backend,NvU64 *generation) {
    NV_STATUS status;
    if(!backend||!generation||checkedMaster(nv)!=NV_OK)return NV_ERR_INVALID_ARGUMENT;
    if(first()!=NV_OK)return first();
    if(LD(&record.phase)!=S540_FIRST_OP||LD(&irqParticipant.backend))return NV_ERR_IN_USE;
    status=checkExecution();if(status!=NV_OK)return refuse(status,SITE_IRQ);
    irqParticipant.nv=nv;irqParticipant.generation=LD(&record.generation);
    ST(&irqParticipant.backend,backend);*generation=irqParticipant.generation;return NV_OK;
}
NV_STATUS s540FirstTxnIrqCheckArm(const void *backend) {
    NV_STATUS status;
    if(!backend||backend!=LD(&irqParticipant.backend)||checkedMaster(irqParticipant.nv)!=NV_OK)
        return NV_ERR_INVALID_STATE;
    if(first()!=NV_OK)return first();
    if(LD(&record.phase)!=S540_FIRST_OP||LD(&irqParticipant.active[0])||LD(&irqParticipant.active[1]))
        return NV_ERR_INVALID_STATE;
    status=checkExecution();return status!=NV_OK?refuse(status,SITE_IRQ):NV_OK;
}
NV_STATUS s540FirstTxnIrqEnter(const void *backend,NvU32 role) {
    S540FirstTxnIrqContext observed={0};NvU32 empty=0,index;NV_STATUS status;NvU64 tid=currentThread();
    if(!backend||backend!=LD(&irqParticipant.backend)||role<1||role>2||!tid)return NV_ERR_INVALID_ARGUMENT;
    status=s540FirstTxnIrqReadContext(backend,role,&observed);
    if(status!=NV_OK||observed.nv!=irqParticipant.nv||observed.generation!=irqParticipant.generation||
       observed.stage!=role||observed.thread!=tid)return refuse(NV_ERR_INVALID_STATE,SITE_IRQ);
    if(first()!=NV_OK)return first();
    if(LD(&record.phase)!=S540_FIRST_OP && LD(&record.phase)!=S540_FIRST_DRAINING)
        return refuse(NV_ERR_NOT_READY,SITE_IRQ);
    index=role-1;
    if(!__atomic_compare_exchange_n(&irqParticipant.active[index],&empty,1U,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_IN_USE,SITE_IRQ);
    ST(&irqParticipant.thread[index],tid);
    status=s540GspCancellationEnterIrqScope(irqParticipant.nv,role,observed.origin);
    if(status==NV_OK)status=checkExecution();
    if(status!=NV_OK) {
        (void)s540GspCancellationLeaveIrqScope(irqParticipant.nv,role);
        ST(&irqParticipant.thread[index],0ULL);ST(&irqParticipant.active[index],0U);
        return refuse(status,SITE_IRQ);
    }
    return NV_OK;
}
NV_STATUS s540FirstTxnIrqLeave(const void *backend,NvU32 role) {
    NvU32 index;if(!backend||backend!=LD(&irqParticipant.backend)||role<1||role>2)return NV_ERR_INVALID_ARGUMENT;
    index=role-1;
    if(!LD(&irqParticipant.active[index])||LD(&irqParticipant.thread[index])!=currentThread())
        return refuse(NV_ERR_INVALID_STATE,SITE_IRQ);
    /* Complete the genuine wrapper return even if its body published sticky failure. */
    {
        NV_STATUS status=s540GspCancellationLeaveIrqScope(irqParticipant.nv,role);
        if(status!=NV_OK)return refuse(status,SITE_IRQ);
    }
    ST(&irqParticipant.thread[index],0ULL);ST(&irqParticipant.active[index],0U);return first();
}
NvU32 s540FirstTxnIrqOrigin(const void *backend) {
    if(backend!=LD(&irqParticipant.backend)||!LD(&irqParticipant.active[0])||
       LD(&irqParticipant.thread[0])!=currentThread())return 0;
    return s540GspCancellationIrqOrigin(S540_FIRST_IRQ_TOP);
}
NV_STATUS s540FirstTxnIrqValidateSoftwareDrained(void) {
    S540FirstTxnIrqContext observed={0};const void *backend=LD(&irqParticipant.backend);NV_STATUS status;
    if(!backend)return NV_OK;
    if(LD(&irqParticipant.active[0])||LD(&irqParticipant.active[1]))return NV_ERR_IN_USE;
    status=s540FirstTxnIrqReadContext(backend,0,&observed);if(status!=NV_OK)return status;
    if(observed.nv!=irqParticipant.nv||observed.generation!=irqParticipant.generation||observed.pending||
       observed.callbacks||observed.topStage||observed.bottomStage||observed.accepting||
       observed.controllerAttached||!observed.drained)return NV_ERR_IN_USE;
    return NV_OK;
}
NV_STATUS s540FirstTxnIrqValidateDrained(void) {
    S540FirstTxnIrqContext observed={0};const void *backend=LD(&irqParticipant.backend);
    NV_STATUS status=s540FirstTxnIrqValidateSoftwareDrained();
    if(status!=NV_OK||!backend)return status;
    status=s540FirstTxnIrqReadContext(backend,0,&observed);if(status!=NV_OK)return status;
    return observed.maskRequired?NV_ERR_NOT_READY:NV_OK;
}
