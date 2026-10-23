extern "C" NV_STATUS s540FirstTxnServicesSealAndDrain(const void *nv, NvU64 generation) {
    if (!exact(nv, generation)) return NV_ERR_INVALID_STATE;
    // A real completed original lock observation is mandatory before joins.
    // A failure is not permission to block while an RM lock may be held.
    NV_STATUS first = s540FirstTxnOriginalLocksReleased(nv);
    if (first != NV_OK) return first;
    auto observe = [&first](NV_STATUS status) {
        if (first == NV_OK && status != NV_OK) first = status;
    };
    // Preserve the first error but still close/join every independent CPU
    // producer. None of these operations frees its retained storage or IOVA.
    observe(s540GspTimersStop(static_cast<struct nv_state_t *>(const_cast<void *>(nv))));
    observe(s540FirstTxnQueueSeal(binding.device, nv, generation));
    observe(s540FirstTxnQueueSeal(binding.global, nv, generation));
    observe(s540DarwinWorkQueueStop(binding.device));
    observe(s540DarwinWorkQueueStop(binding.global));
    observe(s540FirstTxnServicesValidateRetired(nv, generation));
    return first;
}
