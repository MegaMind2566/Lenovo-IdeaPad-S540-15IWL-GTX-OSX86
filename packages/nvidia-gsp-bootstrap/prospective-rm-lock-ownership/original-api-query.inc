/* SPDX-License-Identifier: MIT */
/* Appended only to sealed original rmapi.c. No new ready flag or TLS slot. */
#include "S540ProspectiveRmLockOwnership.h"
NV_STATUS s540ProspectiveOriginalApiOwnership(NvBool *owned)
{
    if (owned == NULL) return NV_ERR_INVALID_ARGUMENT;
    if (!g_bResServInit || g_RmApiLock.pLock == NULL ||
        g_RmApiLock.tlsEntryId == 0 || g_RmApiLock.tlsEntryId == (NvU64)TLS_ERROR_VAL)
        return NV_ERR_NOT_READY;
    *owned = rmapiLockIsOwner();
    return NV_OK;
}
