extern "C" void s540PciTopologyRecordFailure(NvU32 operation, NV_STATUS status) {
    if (status == NV_OK) return;
    const NvU32 producer = operation >= S540_PCI_TOPOLOGY_READ_BYTE &&
        operation <= S540_PCI_TOPOLOGY_WRITE_DWORD ? 600U + operation : 600U;
    // Scalar/void original ABI wrappers cannot return these errors to their
    // callers. Preserve the actual status before the aggregate refusal path.
    s540FirstTxnObserveServiceRefusal(7U, producer, status);
    s540GlobalRmRecordUnavailable(producer);
}
extern "C" NvBool s540PciTopologyUsesOsConfig(const void *exactNv) {
    auto *state = const_cast<nv_state_t *>(static_cast<const nv_state_t *>(exactNv));
    NvU64 before = 0U, after = 0U;
    if (!stateValid(state) || s540FirstTxnOptionalNvlinkActive(exactNv, &before) != NV_OK || !before)
        return NV_FALSE;
    if (!binding.session->topologyReady()) return NV_FALSE;
    return s540FirstTxnOptionalNvlinkActive(exactNv, &after) == NV_OK &&
        after == before ? NV_TRUE : NV_FALSE;
}
extern "C" NV_STATUS s540PciTopologyValidateForGsp(const void *exactNv,
    const S540PciTopologyGspFacts *facts) {
    auto *state = const_cast<nv_state_t *>(static_cast<const nv_state_t *>(exactNv));
    if (!facts || facts->format != 1U || facts->bytes != sizeof(*facts))
        return NV_ERR_INVALID_ARGUMENT;
    if (!stateValid(state)) return NV_ERR_INVALID_STATE;
    NvU64 before = 0U, after = 0U;
    NV_STATUS status = s540FirstTxnOptionalNvlinkActive(exactNv, &before);
    if (status != NV_OK) return status;
    if (!before) return NV_ERR_INVALID_STATE;
    status = binding.session->validateTopology(*facts);
    if (status != NV_OK) return status;
    status = s540FirstTxnOptionalNvlinkActive(exactNv, &after);
    if (status != NV_OK) return status;
    return after == before ? NV_OK : NV_ERR_INVALID_STATE;
}
