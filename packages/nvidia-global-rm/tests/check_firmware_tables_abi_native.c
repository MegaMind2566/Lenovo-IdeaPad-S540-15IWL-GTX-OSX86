/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
int s540RsdpOriginalAbiControl(void)
{
    NvU32 physical = 0x12345678;
    if (os_get_acpi_rsdp_from_uefi(NULL) != NV_ERR_INVALID_STATE) return -1;
    if (os_get_acpi_rsdp_from_uefi(&physical) != NV_ERR_NOT_SUPPORTED) return -2;
    if (physical != 0) return -3;
    return 3;
}
