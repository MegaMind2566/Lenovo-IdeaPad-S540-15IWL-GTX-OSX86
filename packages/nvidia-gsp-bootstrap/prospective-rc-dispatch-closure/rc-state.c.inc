/* One permanent diagnostic epoch. All actual 1Hz list mutations in the pinned
 * source are below in this TU. GPU/device locks retain their original role;
 * the serial detects callback-driven remove/reinsert, including same-slot ABA.
 * Cross-GPU mutation may conservatively retain this diagnostic epoch too.
 * There is no reset, readiness flag, callback whitelist or time-bound claim. */
_Static_assert(TMR_NUM_CALLBACKS_OS > 0 && TMR_NUM_CALLBACKS_OS <= 64,
    "The original fixed callback table must fit the pass bitmap");
static NvU64 s540RcMutationSerial;
static NvU32 s540RcFirstFailure;

static NV_STATUS s540RcRefuse(NV_STATUS status)
{
    NvU32 expected = NV_OK;
    if (status == NV_OK) return NV_OK;
    (void)__atomic_compare_exchange_n(&s540RcFirstFailure, &expected,
        (NvU32)status, NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
    s540FirstTxnObserveServiceRefusal(14, 1, status);
    return status;
}

static NV_STATUS s540RcCheck(OBJGPU *pGpu)
{
    S540FirstTxnSnapshot snapshot;
    NV_STATUS status = (NV_STATUS)__atomic_load_n(&s540RcFirstFailure, __ATOMIC_ACQUIRE);
    if (status != NV_OK) return status;
    status = s540GspCancellationCheckGpu(pGpu);
    if (status != NV_OK) return s540RcRefuse(status);
    /* A diagnostic pull supplies no admission authority. Only an exact live
     * record's existing failure is consumed; unbound/foreign pull refusal is
     * not converted into a callback capability. */
    if (s540FirstTxnGetSnapshot(NV_GET_NV_STATE(pGpu), &snapshot) == NV_OK &&
        snapshot.firstStatus != NV_OK)
        return s540RcRefuse((NV_STATUS)snapshot.firstStatus);
    return NV_OK;
}

static NV_STATUS s540RcMutating(void)
{
    NvU64 serial = __atomic_load_n(&s540RcMutationSerial, __ATOMIC_ACQUIRE);
    /* Single attempt, never a hidden retry loop. Saturation/contention retains
     * all live registrations rather than reusing a lifecycle identity. */
    if (serial == ~0ULL) return s540RcRefuse(NV_ERR_INSUFFICIENT_RESOURCES);
    if (!__atomic_compare_exchange_n(&s540RcMutationSerial, &serial, serial + 1,
        NV_FALSE, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return s540RcRefuse(NV_ERR_BUSY_RETRY);
    return NV_OK;
}

static NvBool s540RcEntry(OBJTMR *pTmr, const OS1HZTIMERENTRY *entry)
{
    NvUPtr address = (NvUPtr)entry;
    NvUPtr first = (NvUPtr)&pTmr->os1HzCallbackTable[0];
    NvUPtr last = (NvUPtr)&pTmr->os1HzCallbackTable[TMR_NUM_CALLBACKS_OS];
    return address >= first && address < last &&
        (address - first) % sizeof(*entry) == 0;
}
