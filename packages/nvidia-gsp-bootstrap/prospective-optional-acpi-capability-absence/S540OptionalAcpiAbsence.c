/* SPDX-License-Identifier: MIT */
#include "S540OptionalAcpiAbsence.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRmProfile.h"

/* Reuse the existing pure strong-record authority checks. Despite their
 * historical NVLink names, these functions inspect only actual transaction,
 * global epoch, ordinary master and stable cancellation state. They do not
 * inspect a library/registry, mutate counters or grant cleanup authority. */
static NvU32 absenceState;
static S540OptionalAcpiAbsence absence;
_Static_assert(sizeof(S540OptionalAcpiAbsence) == 32, "Private ACPI absence layout changed");
_Static_assert(__atomic_always_lock_free(sizeof(NvU32), 0), "No new runtime lock permitted");

NV_STATUS s540OptionalAcpiCommitAbsent(const void *nv, NvU32 query, NvU32 function)
{
    NvU64 generation = 0, confirmed = 0;
    NvU32 expected;
    NV_STATUS status;
    if (S540_GLOBAL_RM_PROFILE_VERSION != 2U || S540_GLOBAL_RM_ACPI_EVENTS_ENABLED != 0)
        return NV_ERR_NOT_SUPPORTED;
    if ((query == S540_OPTIONAL_ACPI_DSM_SUPPORT && function >= S540_OPTIONAL_ACPI_DSM_FUNCTIONS) ||
        (query == S540_OPTIONAL_ACPI_DOD && function != 0U) ||
        (query != S540_OPTIONAL_ACPI_DSM_SUPPORT && query != S540_OPTIONAL_ACPI_DOD))
        return NV_ERR_INVALID_ARGUMENT;
    status = s540FirstTxnOptionalNvlinkActive(nv, &generation);
    if (status != NV_OK) return status;
    expected = __atomic_load_n(&absenceState, __ATOMIC_ACQUIRE);
    if (expected != 0U && expected != 2U) return NV_ERR_IN_USE;
    if (!__atomic_compare_exchange_n(&absenceState, &expected, 1U, NV_FALSE,
                                    __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
        return NV_ERR_IN_USE;
    status = s540FirstTxnOptionalNvlinkActive(nv, &confirmed);
    if (status != NV_OK) return status;
    if (!generation || generation != confirmed) return NV_ERR_INVALID_STATE;
    if (!absence.generation) {
        absence.format = 1U;
        absence.bytes = sizeof(absence);
        absence.generation = generation;
    } else if (absence.generation != generation) {
        return NV_ERR_INVALID_STATE;
    }
    /* Only the same actual ordinary original-call master can update this
     * bounded record. Repeated capability probes are idempotent for this
     * exact generation; a failed reservation stays retained in state 1. */
    if (query == S540_OPTIONAL_ACPI_DSM_SUPPORT) {
        const NvU32 bit = 1U << function;
        if (!(absence.dsmAbsentMask & bit)) {
            if (absence.dsmQueries >= S540_OPTIONAL_ACPI_DSM_FUNCTIONS)
                return NV_ERR_IN_USE;
            absence.dsmAbsentMask |= bit;
            ++absence.dsmQueries;
        }
    } else {
        absence.dodQueries = 1U;
    }
    __atomic_store_n(&absenceState, 2U, __ATOMIC_RELEASE);
    return NV_OK;
}

NV_STATUS s540OptionalAcpiRead(const void *nv, S540OptionalAcpiAbsence *out)
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
