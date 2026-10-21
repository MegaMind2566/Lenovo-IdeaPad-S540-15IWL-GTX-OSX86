void bottomHalf(void *parameter) {
    auto *p=static_cast<Platform *>(parameter);
    for(;;) {
        const NvU32 work=__atomic_exchange_n(&p->pending,0,__ATOMIC_ACQ_REL);
        if(!work)break;
        __atomic_store_n(&p->bottomOrigin,work>>2,__ATOMIC_RELEASE);
        __atomic_store_n(&p->bottomThread,irqThread(),__ATOMIC_RELEASE);
        __atomic_store_n(&p->bottomStage,NvU32(S540_FIRST_IRQ_BOTTOM),__ATOMIC_RELEASE);
        const NV_STATUS entered=s540FirstTxnIrqEnter(p,S540_FIRST_IRQ_BOTTOM);
        if(entered!=NV_OK) {
            // No original dispatch occurred. Retain the actual pending work.
            __atomic_fetch_or(&p->pending,work,__ATOMIC_RELEASE);
            __atomic_store_n(&p->bottomStage,0U,__ATOMIC_RELEASE);
            return;
        }
        if(work&1U) {
            p->interrupt.lockedBottomHalf(p->interrupt.context);
            __atomic_add_fetch(&p->statistics.lockedBottomHalves,1,__ATOMIC_RELAXED);
        }
        if(work&2U) {
            p->interrupt.unlockedBottomHalf(p->interrupt.context);
            __atomic_add_fetch(&p->statistics.unlockedBottomHalves,1,__ATOMIC_RELAXED);
        }
        (void)s540FirstTxnIrqLeave(p,S540_FIRST_IRQ_BOTTOM);
        __atomic_store_n(&p->bottomStage,0U,__ATOMIC_RELEASE);
    }
}
void interrupt(OSObject *,void *opaque,IOService *,int) {
    auto *p=static_cast<Platform *>(opaque);
    __atomic_add_fetch(&p->callbacks,1,__ATOMIC_ACQ_REL);
    __atomic_add_fetch(&p->statistics.controllerCallbacks,1,__ATOMIC_RELAXED);
    if(__atomic_load_n(&p->accepting,__ATOMIC_ACQUIRE)) {
        IOInterruptState saved=IOSimpleLockLockDisableInterrupt(p->isrLock);
        __atomic_store_n(&p->topThread,irqThread(),__ATOMIC_RELEASE);
        __atomic_store_n(&p->topStage,NvU32(S540_FIRST_IRQ_TOP),__ATOMIC_RELEASE);
        if(s540FirstTxnIrqEnter(p,S540_FIRST_IRQ_TOP)==NV_OK) {
            bool locked=false,unlocked=false;
            if(p->interrupt.top(p->interrupt.context,locked,unlocked))
                __atomic_add_fetch(&p->statistics.rmHandledCallbacks,1,__ATOMIC_RELAXED);
            const NvU32 bits=(locked?1U:0U)|(unlocked?2U:0U);
            if(bits) {
                const NvU32 origin=s540FirstTxnIrqOrigin(p);
                if(!origin)s540FirstTxnObserveServiceRefusal(11,3,NV_ERR_INVALID_STATE);
                else __atomic_fetch_or(&p->pending,bits|(origin<<2),__ATOMIC_RELEASE);
                (void)scheduleBottomHalf(p);
            }
            (void)s540FirstTxnIrqLeave(p,S540_FIRST_IRQ_TOP);
        }
        __atomic_store_n(&p->topStage,0U,__ATOMIC_RELEASE);
        IOSimpleLockUnlockEnableInterrupt(p->isrLock,saved);
    }
    __atomic_sub_fetch(&p->callbacks,1,__ATOMIC_ACQ_REL);
}
NV_STATUS installInterrupt(void *opaque,const InterruptContract &contract) {
    auto *p=static_cast<Platform *>(opaque);
    if(!ordinary(p)||!live(p)||p->irqRegistered||!contract.context||!contract.originalState||
       !contract.top||!contract.lockedBottomHalf||!contract.unlockedBottomHalf||
       !contract.maskHardware||!contract.readyToArm)return NV_ERR_NOT_SUPPORTED;
    IrqBackendScope construction;
    if(construction.status!=NV_OK)return construction.status;
    int type=0;
    if(p->provider->getInterruptType(0,&type)!=kIOReturnSuccess)return NV_ERR_NOT_SUPPORTED;
    p->isrLock=IOSimpleLockAlloc();
    const bool calloutReady=p->isrLock&&p->bottomHalf.initialize(bottomHalf,p);
    if(!calloutReady) {
        IrqBackendRelease release(p);
        if(release.status!=NV_OK)return release.status;
        if(p->isrLock)IOSimpleLockFree(p->isrLock);
        p->isrLock=nullptr;return NV_ERR_NO_MEMORY;
    }
    p->interrupt=contract;p->accepting=false;p->drained=false;
    NV_STATUS bound=s540FirstTxnIrqBind(contract.originalState,p,&p->irqGeneration);
    if(bound!=NV_OK){rememberIrqBackend(p);return bound;}
    __atomic_store_n(&registeredIrqBackend,p,__ATOMIC_RELEASE);
    if(p->provider->registerInterrupt(0,p->owner,interrupt,p)!=kIOReturnSuccess) {
        s540FirstTxnObserveServiceRefusal(11,2,NV_ERR_OPERATING_SYSTEM);
        rememberIrqBackend(p);return NV_ERR_OPERATING_SYSTEM;
    }
    p->irqRegistered=true;__atomic_store_n(&p->controllerAttached,true,__ATOMIC_RELEASE);return NV_OK;
}
NV_STATUS stopInterrupt(void *opaque) {
    auto *p=static_cast<Platform *>(opaque);
    if(!ordinary(p))return NV_ERR_INVALID_STATE;
    if(!p->irqRegistered)return NV_OK;
    if(p->controllerEnableAttempted) {
        if(p->provider->disableInterrupt(0)!=kIOReturnSuccess)return NV_ERR_OPERATING_SYSTEM;
        p->controllerEnableAttempted=false;
    }
    p->irqEnabled=false;
    __atomic_store_n(&p->accepting,false,__ATOMIC_RELEASE);
    if(p->controllerAttached) {
        if(p->provider->unregisterInterrupt(0)!=kIOReturnSuccess)return NV_ERR_OPERATING_SYSTEM;
        __atomic_store_n(&p->controllerAttached,false,__ATOMIC_RELEASE);
    }
    for(NvU32 i=0;__atomic_load_n(&p->callbacks,__ATOMIC_ACQUIRE)&&i<100;++i)IOSleep(1);
    if(__atomic_load_n(&p->callbacks,__ATOMIC_ACQUIRE))return NV_ERR_BUSY_RETRY;
    // Pending RM bottom halves run only through the actual public workloop
    // action. Stop never invokes a residual original callback on its caller.
    if(__atomic_load_n(&p->pending,__ATOMIC_ACQUIRE)&&!scheduleBottomHalf(p))return NV_ERR_OPERATING_SYSTEM;
    for(NvU32 i=0;__atomic_load_n(&p->pending,__ATOMIC_ACQUIRE)&&i<100;++i)IOSleep(1);
    if(__atomic_load_n(&p->pending,__ATOMIC_ACQUIRE))return NV_ERR_BUSY_RETRY;
    if(!p->bottomHalf.drain())return NV_ERR_BUSY_RETRY;
    __atomic_store_n(&p->drained,true,__ATOMIC_RELEASE);
    // The original ownership query requires ISR/DPC transfer exclusion.
    // Controller detach and the real action join establish it before the
    // master acquires original locks. Earlier BH completion may reenable the
    // GPU source only while the OS controller is already disabled/detached.
    if(__atomic_load_n(&p->hardwareMaskRequired,__ATOMIC_ACQUIRE)) {
        const NV_STATUS masked=p->interrupt.maskHardware(p->interrupt.context);
        if(masked!=NV_OK)return masked;
        __atomic_store_n(&p->hardwareMaskRequired,false,__ATOMIC_RELEASE);
    }
    IrqBackendRelease release(p);
    if(release.status!=NV_OK)return release.status;
    if(!p->bottomHalf.retire())return NV_ERR_BUSY_RETRY;
    IOSimpleLockFree(p->isrLock);p->isrLock=nullptr;
    p->interrupt=InterruptContract{};p->irqRegistered=false;return NV_OK;
}
