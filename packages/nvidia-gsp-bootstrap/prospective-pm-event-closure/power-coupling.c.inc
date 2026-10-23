/* A PM service guard owns POWER_COUPLED. Acquire/release run on the exact
 * ordinary cancellation owner; callback revocation only reads the fixed,
 * generation-tagged slot. Unbind cannot recycle it until the PM guard drops
 * this hold. No callback, allocation, lock or sleep occurs inside these APIs. */
NV_STATUS s540GspCancellationPowerAcquireState(const void *state,
    S540GspCancellationToken token)
{
    NvU64 value = word();
    if (!state || !owner() || !matches(value, token) ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE))
        return NV_ERR_INVALID_STATE;
    for (;;) {
        if (!matches(value, token) ||
            state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE))
            return NV_ERR_INVALID_STATE;
        if (value & (POWER_COUPLED | OPERATION | CLEANUP | PUBLISHING |
                     CAPTURE_BUSY | COMMIT_BUSY)) return NV_ERR_IN_USE;
        if (__atomic_compare_exchange_n(&slot.control, &value,
            value | POWER_COUPLED, NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
            return NV_OK;
    }
}
NV_STATUS s540GspCancellationPowerReleaseState(const void *state,
    S540GspCancellationToken token)
{
    NvU64 value = word();
    if (!state || !owner() || !matches(value, token) ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE))
        return NV_ERR_INVALID_STATE;
    for (;;) {
        if (!matches(value, token) || !(value & POWER_COUPLED) ||
            state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE))
            return NV_ERR_INVALID_STATE;
        if (value & (OPERATION | CLEANUP | PUBLISHING | CAPTURE_BUSY | COMMIT_BUSY))
            return NV_ERR_IN_USE;
        if (__atomic_compare_exchange_n(&slot.control, &value,
            value & ~(NvU64)POWER_COUPLED, NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
            return NV_OK;
    }
}
NV_STATUS s540GspCancellationPowerRevokeAtState(const void *state,
    S540GspCancellationToken token, NvU64 eventNs)
{
    const NvU64 value = word();
    if (!state || !matches(value, token) || !(value & POWER_COUPLED) ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE))
        return NV_ERR_INVALID_STATE;
    return s540GspCancellationRevokeAt(token, eventNs);
}
