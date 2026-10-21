/* Birth identity is immutable. Physical release remains preowner-only. */
static Platform *retainedIrqBackends;
static Platform *registeredIrqBackend;
void rememberIrqBackend(Platform *p) {
    NvU32 empty=0;
    if(!__atomic_compare_exchange_n(&p->permanentRetention,&empty,1U,false,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    Platform *prior=__atomic_load_n(&retainedIrqBackends,__ATOMIC_ACQUIRE);
    do {p->retainedNext=prior;}
    while(!__atomic_compare_exchange_n(&retainedIrqBackends,&prior,p,false,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE));
}
struct IrqBackendScope {
    S540FirstTxnHostIdentity identity{};
    NvU64 permit=0;
    NV_STATUS status;
    IrqBackendScope():status(s540FirstTxnBackendBegin(&identity,&permit)){}
    ~IrqBackendScope(){if(permit&&s540FirstTxnBackendEnd(permit)!=NV_OK)__builtin_trap();}
};
struct IrqBackendRelease {
    NvU64 permit=0;
    NV_STATUS status;
    explicit IrqBackendRelease(Platform *p):
        status(NV_ERR_NOT_SUPPORTED) {
        // Reservation-time retention is permanent even if that reservation
        // subsequently rolls back. Its intrusive root may never name freed RAM.
        if(!__atomic_load_n(&p->permanentRetention,__ATOMIC_ACQUIRE))
            status=s540FirstTxnBackendBeginRelease(&p->backendIdentity,&permit);
        if(status!=NV_OK)rememberIrqBackend(p);
    }
    ~IrqBackendRelease(){if(permit&&s540FirstTxnBackendEnd(permit)!=NV_OK)__builtin_trap();}
};
NvU64 irqThread() {
    NvU64 tid=0;
    return s540Darwin_os_get_current_thread(&tid)==NV_OK?tid:0;
}
bool scheduleBottomHalf(Platform *p) {
    uint64_t deadline=0;clock_get_uptime(&deadline);
    if(p->bottomHalf.schedule(deadline))return true;
    s540FirstTxnObserveServiceRefusal(11,1,NV_ERR_OPERATING_SYSTEM);return false;
}
