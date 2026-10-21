/* One fixed, nonrecursive commit reservation. The shared control CAS orders
 * acceptance against RevokeAt's PUBLISHING reservation. Revocation remains
 * nonblocking and preserves COMMIT_BUSY until the real endpoint returns.
 * The serial is monotonic across bindings and never copied into snapshots.
 */
static struct {
    NvU64 nextSerial, serial, binding, thread, origin;
    NvU32 accepted, completed, refused;
} commits;

static NV_STATUS commitRefused(NV_STATUS status)
{
    increment(&commits.refused);
    return status;
}

static NV_STATUS commitEnter(const void *state,
    S540GspCancellationCommitLease *out, NvBool transport)
{
    NvU64 value = word(), origin, tid, serial;
    NV_STATUS status;
    if (out) *out = 0;
    if (!state || !out || !generation(value) || !(value & BOUND) ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE))
        return commitRefused(NV_ERR_INVALID_STATE);
    origin = currentOrigin(value);
    if (!origin || (!transport && origin != OPERATION))
        return commitRefused(NV_ERR_INVALID_STATE);
    if (value & PUBLISHING) return commitRefused(NV_ERR_NOT_READY);
    if (value & (CAPTURE_BUSY | COMMIT_BUSY)) return commitRefused(NV_ERR_IN_USE);
    status = checkOrigin(value, origin);
    if (status != NV_OK) return commitRefused(status);
    tid = thread();
    if (!tid) return commitRefused(NV_ERR_INVALID_STATE);
    /* A single strong CAS refuses contention or changed phase/revocation.
     * It never waits for an interrupted holder to finish. */
    if (!__atomic_compare_exchange_n(&slot.control, &value,
            value | COMMIT_BUSY, NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return commitRefused(NV_ERR_BUSY_RETRY);
    /* A cleanup thread can be preempted between its clock check and CAS.
     * Recheck the real phase/deadline after reservation, before a token or
     * endpoint can escape. Revocation publication in flight also refuses. */
    value = word();
    status = (value & PUBLISHING) ? NV_ERR_NOT_READY : checkOrigin(value, origin);
    if (status != NV_OK) {
        __atomic_fetch_and(&slot.control, ~(NvU64)COMMIT_BUSY, __ATOMIC_RELEASE);
        return commitRefused(status);
    }
    serial = __atomic_load_n(&commits.nextSerial, __ATOMIC_RELAXED);
    if (serial == ~(NvU64)0) {
        __atomic_fetch_and(&slot.control, ~(NvU64)COMMIT_BUSY, __ATOMIC_RELEASE);
        return commitRefused(NV_ERR_INSUFFICIENT_RESOURCES);
    }
    ++serial;
    __atomic_store_n(&commits.nextSerial, serial, __ATOMIC_RELAXED);
    __atomic_store_n(&commits.binding, generation(value), __ATOMIC_RELAXED);
    __atomic_store_n(&commits.thread, tid, __ATOMIC_RELAXED);
    __atomic_store_n(&commits.origin, origin, __ATOMIC_RELAXED);
    increment(&commits.accepted);
    __atomic_store_n(&commits.serial, serial, __ATOMIC_RELEASE);
    *out = serial;
    return NV_OK;
}

NV_STATUS s540GspCancellationCommitEnterState(const void *state,
    S540GspCancellationCommitLease *out)
{
    return commitEnter(state, out, NV_FALSE);
}

NV_STATUS s540GspCancellationSubmitEnterState(const void *state,
    S540GspCancellationCommitLease *out)
{
    return commitEnter(state, out, NV_TRUE);
}

NV_STATUS s540GspCancellationCommitLeaveState(const void *state,
    S540GspCancellationCommitLease lease)
{
    NvU64 value = word(), serial = __atomic_load_n(&commits.serial, __ATOMIC_ACQUIRE);
    if (!state || !lease || serial != lease || !(value & COMMIT_BUSY) ||
        !generation(value) || !(value & BOUND) ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE) ||
        generation(value) != __atomic_load_n(&commits.binding, __ATOMIC_RELAXED) ||
        thread() != __atomic_load_n(&commits.thread, __ATOMIC_RELAXED) ||
        currentOrigin(value) != __atomic_load_n(&commits.origin, __ATOMIC_RELAXED))
        return commitRefused(NV_ERR_INVALID_STATE);
    /* Phase changes and unbind refuse COMMIT_BUSY. Revocation may update the
     * same word; release only our bit and preserve every revocation flag. */
    __atomic_store_n(&commits.serial, (NvU64)0, __ATOMIC_RELEASE);
    increment(&commits.completed);
    __atomic_fetch_and(&slot.control, ~(NvU64)COMMIT_BUSY, __ATOMIC_RELEASE);
    return NV_OK;
}

NV_STATUS s540GspCancellationCommitReadState(const void *state,
    S540GspCancellationCommitSnapshot *out)
{
    NvU64 value = word(), serial;
    S540GspCancellationCommitSnapshot result = {0};
    if (!state || !out || !generation(value) || !(value & BOUND) ||
        state != __atomic_load_n(&slot.state, __ATOMIC_ACQUIRE))
        return NV_ERR_INVALID_STATE;
    serial = __atomic_load_n(&commits.serial, __ATOMIC_ACQUIRE);
    result.generation = generation(value);
    result.inFlight = !!(value & COMMIT_BUSY);
    result.origin = result.inFlight && serial ?
        (NvU32)__atomic_load_n(&commits.origin, __ATOMIC_RELAXED) : 0;
    result.accepted = __atomic_load_n(&commits.accepted, __ATOMIC_RELAXED);
    result.completed = __atomic_load_n(&commits.completed, __ATOMIC_RELAXED);
    result.refused = __atomic_load_n(&commits.refused, __ATOMIC_RELAXED);
    result.revoked = !!(value & REVOKED);
    result.publicationInFlight = !!(value & PUBLISHING);
    if (word() != value || serial != __atomic_load_n(&commits.serial, __ATOMIC_ACQUIRE))
        return NV_ERR_BUSY_RETRY;
    *out = result;
    return NV_OK;
}
