/* SPDX-License-Identifier: MIT */
#include "S540AttachFailureWitness.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

/* 0 unused, 3 reserving, 1 original attach active, 2 attach returned. The actual
 * ordinary master alone reads/writes payload; atomic publication excludes
 * repeated begin and makes unavailability explicit. No address is retained. */
static NvU32 witnessState;
static S540AttachFailureWitness witness;
_Static_assert(__atomic_always_lock_free(sizeof(NvU32), 0),
               "The witness must not add a runtime lock");
_Static_assert(sizeof(S540AttachFailureWitness) == 80,
               "Private scalar witness layout changed");

static NvBool ordinaryMaster(NvU64 master)
{
    NvU64 actual = 0;
    return master && s540Darwin_os_semaphore_may_sleep() &&
        s540Darwin_os_get_current_thread(&actual) == NV_OK && actual == master;
}

static NvBool active(const void *nv)
{
    S540FirstTxnGlobalSnapshot current;
    if (__atomic_load_n(&witnessState, __ATOMIC_ACQUIRE) != 1U || !nv)
        return NV_FALSE;
    /* Pure diagnostic read: sticky first failures remain observable. */
    if (s540FirstTxnGlobalGetSnapshot(&current) != NV_OK || current.nv != nv ||
        current.generation != witness.generation || !current.owner ||
        !current.validated || !current.originalReturned ||
        current.state != S540_FIRST_GLOBAL_READY || !ordinaryMaster(current.masterThread))
        return NV_FALSE;
    return NV_TRUE;
}

void s540AttachWitnessBegin(const void *nv)
{
    S540FirstTxnSnapshot current;
    NvU32 empty = 0;
    if (!nv || s540FirstTxnGetSnapshot(nv, &current) != NV_OK ||
        !current.generation || current.firstStatus != NV_OK ||
        current.phase != S540_FIRST_OP || !current.originalInFlight ||
        current.originalReturned || !ordinaryMaster(current.masterThread))
        return;
    if (!__atomic_compare_exchange_n(&witnessState, &empty, 3U, NV_FALSE,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return;
    witness.format = 1U;
    witness.bytes = sizeof(witness);
    witness.generation = current.generation;
    __atomic_store_n(&witnessState, 1U, __ATOMIC_RELEASE);
}

void s540AttachWitnessProgress(const void *nv, NvU32 stage)
{
    if (!active(nv) || stage < S540_ATTACH_GPU_CREATE || stage > S540_ATTACH_COMPLETE)
        return;
    witness.lastAttachStage = stage;
}

void s540AttachWitnessChildProgress(const void *nv, NvU32 classId,
    NvU64 instance, NvU32 stage)
{
    if (!active(nv) || stage < S540_CTOR_CLASS_INFO || stage > S540_CTOR_COMPLETE)
        return;
    witness.lastClassId = classId;
    witness.lastInstance = instance;
    witness.lastCtorStage = stage;
}

void s540AttachWitnessChildFailure(const void *nv, NvU32 classId,
    NvU64 instance, NvU32 stage, NV_STATUS status, NvU32 mask,
    NvU32 missing, NvU32 gspClient)
{
    if (!active(nv) || status == NV_OK || witness.firstFailureValid ||
        stage < S540_CTOR_CLASS_INFO || stage > S540_CTOR_COMPLETE ||
        (mask & ~(S540_ATTACH_OBS_MISSING | S540_ATTACH_OBS_GSP_CLIENT)) ||
        ((mask & S540_ATTACH_OBS_MISSING) && missing > 1U) ||
        ((mask & S540_ATTACH_OBS_GSP_CLIENT) && gspClient > 1U))
        return;
    witness.firstAttachStage = witness.lastAttachStage;
    witness.firstClassId = classId;
    witness.firstInstance = instance;
    witness.firstCtorStage = stage;
    witness.firstStatus = status;
    witness.observedMask = mask;
    witness.missing = (mask & S540_ATTACH_OBS_MISSING) ? missing : 0U;
    witness.gspClient = (mask & S540_ATTACH_OBS_GSP_CLIENT) ? gspClient : 0U;
    witness.firstFailureValid = 1U;
}

void s540AttachWitnessAttachFailure(const void *nv, NvU32 stage, NV_STATUS status)
{
    if (!active(nv) || status == NV_OK || witness.firstFailureValid ||
        stage < S540_ATTACH_GPU_CREATE || stage > S540_ATTACH_CONF_COMPUTE)
        return;
    witness.firstAttachStage = stage;
    witness.firstStatus = status;
    witness.firstFailureValid = 1U;
}

void s540AttachWitnessComplete(const void *nv)
{
    if (!active(nv)) return;
    witness.complete = 1U;
    __atomic_store_n(&witnessState, 2U, __ATOMIC_RELEASE);
}

NV_STATUS s540AttachWitnessRead(const void *nv, S540AttachFailureWitness *out)
{
    S540FirstTxnSnapshot current;
    if (!out || !nv) return NV_ERR_INVALID_ARGUMENT;
    if (__atomic_load_n(&witnessState, __ATOMIC_ACQUIRE) != 2U)
        return NV_ERR_NOT_READY;
    if (s540FirstTxnGetSnapshot(nv, &current) != NV_OK ||
        current.generation != witness.generation || !current.originalReturned ||
        current.originalInFlight || !ordinaryMaster(current.masterThread))
        return NV_ERR_INVALID_STATE;
    *out = witness;
    return NV_OK;
}
