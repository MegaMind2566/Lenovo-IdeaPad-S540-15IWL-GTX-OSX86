NV_STATUS Lease::coupleCancellation(const void *state, NvU64 token) {
    if (!impl_ || !ordinaryThread() || ordinaryThread() != impl_->ownerThread)
        return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    auto *service = impl_->service;
    IOLockLock(service->guard);
    const NV_STATUS status = service->closing ? NV_STATUS(NV_ERR_INVALID_STATE) :
        service->protocol.coupleCancellation(state, token);
    IOLockUnlock(service->guard);
    return status;
#else
    std::lock_guard<std::mutex> lock(impl_->guard);
    return impl_->protocol.coupleCancellation(state, token);
#endif
}
NV_STATUS Lease::releaseCancellation() {
    if (!impl_) return NV_OK;
    if (!impl_ || !ordinaryThread() || ordinaryThread() != impl_->ownerThread)
        return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    auto *service = impl_->service;
    IOLockLock(service->guard);
    const NV_STATUS status = service->protocol.releaseCancellation();
    IOLockUnlock(service->guard);
    return status;
#else
    std::lock_guard<std::mutex> lock(impl_->guard);
    return impl_->protocol.releaseCancellation();
#endif
}
