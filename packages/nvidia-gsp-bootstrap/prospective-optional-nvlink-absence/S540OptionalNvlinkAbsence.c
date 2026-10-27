/* SPDX-License-Identifier: MIT */
#include "S540OptionalNvlinkAbsence.h"
#include "S540NvidiaGspFirstTransaction.h"

/* 0 unused, 1 reserved, 2 published. Only the actual ordinary original-call
 * master can reserve or publish. A failed reservation remains retained. No
 * object pointer is stored and no reset exists. The guard itself reads the
 * real library and original registry before this final authority recheck. */
static NvU32 absenceState;
static S540OptionalNvlinkAbsence absence;
_Static_assert(sizeof(S540OptionalNvlinkAbsence) == 32, "Private absence layout changed");
_Static_assert(__atomic_always_lock_free(sizeof(NvU32), 0), "No new runtime lock permitted");

NV_STATUS s540OptionalNvlinkCommitAbsent(const void *nv)
{
    NvU64 generation = 0, checkedGeneration = 0;
    NvU32 empty = 0;
    NV_STATUS status = s540FirstTxnOptionalNvlinkActive(nv, &generation);
    if (status != NV_OK) return status;
    if (!__atomic_compare_exchange_n(&absenceState, &empty, 1U, NV_FALSE,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return NV_ERR_IN_USE;
    status = s540FirstTxnOptionalNvlinkActive(nv, &checkedGeneration);
    if (status != NV_OK) return status;
    if (!generation || checkedGeneration != generation) return NV_ERR_INVALID_STATE;
    absence.format = 1U;
    absence.bytes = sizeof(absence);
    absence.generation = generation;
    absence.absent = 1U;
    absence.classId = 0xce6818U;
    absence.instance = 0;
    __atomic_store_n(&absenceState, 2U, __ATOMIC_RELEASE);
    return NV_OK;
}

NV_STATUS s540OptionalNvlinkRead(const void *nv, S540OptionalNvlinkAbsence *out)
{
    NV_STATUS status;
    if (!nv || !out) return NV_ERR_INVALID_ARGUMENT;
    if (__atomic_load_n(&absenceState, __ATOMIC_ACQUIRE) != 2U)
        return NV_ERR_NOT_READY;
    status = s540FirstTxnOptionalNvlinkReturned(nv, absence.generation);
    if (status != NV_OK) return status;
    *out = absence;
    return NV_OK;
}
