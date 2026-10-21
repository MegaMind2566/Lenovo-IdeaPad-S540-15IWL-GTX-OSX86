NvU64 Lease::revocationEventNs() const {
    if (!impl_) return final_.revokedAtNs;
#if defined(KERNEL)
    return impl_->service->protocol.revocationEventNs();
#else
    return impl_->protocol.revocationEventNs();
#endif
}
