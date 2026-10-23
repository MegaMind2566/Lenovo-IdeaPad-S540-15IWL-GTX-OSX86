NV_STATUS Owner::experimentalInitialize(const S540ExperimentalRuntimeRequest &request) {
    if(!impl_)return NV_ERR_INVALID_STATE;
    impl_->runtimeRequest=request;
    return impl_->dispatcher.invoke(ExperimentalInitialize);
}
NV_STATUS Owner::cancelExperimental() {
    // The external control holds a publication reference across this call.
    // No facade destruction/ordinary stop is permitted until that caller joins.
    if(!impl_)return NV_ERR_INVALID_STATE;
    const auto token=__atomic_load_n(&impl_->cancellationToken,__ATOMIC_ACQUIRE);
    if(!token)return NV_ERR_NOT_READY;
    const NV_STATUS revoked=s540GspCancellationRevoke(token);
    const NV_STATUS posted=impl_->dispatcher.post(Stop);
    return revoked!=NV_OK?revoked:posted;
}
S540ExperimentalRuntimeSnapshot Owner::runtimeSnapshot() const {
    if(impl_)return impl_->readRuntime();
    S540ExperimentalRuntimeSnapshot result{};result.format=1;result.bytes=sizeof(result);
    result.snapshotStatus=NV_ERR_NOT_READY;return result;
}
