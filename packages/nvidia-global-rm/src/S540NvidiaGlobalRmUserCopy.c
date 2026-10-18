// SPDX-License-Identifier: MIT
// Exact original declarations and the private RM namespace precede this unit.
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
NV_STATUS NV_API_CALL os_memcpy_from_user(void *to, const void *from, NvU32 bytes)
{
    s540GlobalRmRecordServiceName(__func__);
    return s540Darwin_os_memcpy_from_user(to, from, bytes);
}
NV_STATUS NV_API_CALL os_memcpy_to_user(void *to, const void *from, NvU32 bytes)
{
    s540GlobalRmRecordServiceName(__func__);
    return s540Darwin_os_memcpy_to_user(to, from, bytes);
}
