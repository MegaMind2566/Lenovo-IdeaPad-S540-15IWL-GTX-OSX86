/* SPDX-License-Identifier: MIT */
/* Compile with the generated full-RM namespace header and pinned nv.h first. */
#include "nv.h"
#include "S540NvidiaGspFirmwareBridge.h"
const void *NV_API_CALL nv_get_firmware(nv_state_t *nv, nv_firmware_type_t type,
    nv_firmware_chip_family_t family, const void **bytes, NvU32 *size)
{
    return s540GspFirmwareAcquire(nv, (NvU32)type, (NvU32)family, bytes, size);
}
void NV_API_CALL nv_put_firmware(const void *handle)
{
    s540GspFirmwareRelease(handle);
}
