/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRmFirmwareTables.h"
typedef NV_STATUS (NV_API_CALL *S540RsdpAbi)(NvU32 *);
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_get_acpi_rsdp_from_uefi),
                                           S540RsdpAbi),
               "Original EFI RSDP ABI changed");
NV_STATUS NV_API_CALL os_get_acpi_rsdp_from_uefi(NvU32 *physical)
{
    /* Match the original Linux initializer/error contract, including its
     * specified zero output on a valid failed query. Never truncate a real
     * 64-bit firmware address to satisfy the original 32-bit ABI.
     */
    if (!physical) return NV_ERR_INVALID_STATE;
    *physical = 0;
    return s540GlobalRmReadFirmwareRsdp(physical);
}
