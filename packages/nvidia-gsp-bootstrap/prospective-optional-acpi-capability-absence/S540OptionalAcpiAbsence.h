/* SPDX-License-Identifier: MIT */
#ifndef S540_OPTIONAL_ACPI_ABSENCE_H
#define S540_OPTIONAL_ACPI_ABSENCE_H
#include "nvtypes.h"
#include "nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
enum {
    S540_OPTIONAL_ACPI_DSM_SUPPORT = 1U,
    S540_OPTIONAL_ACPI_DOD = 2U,
    S540_OPTIONAL_ACPI_DSM_FUNCTIONS = 12U
};
typedef struct S540OptionalAcpiAbsence {
    NvU32 format, bytes;
    NvU64 generation;
    NvU32 dsmAbsentMask, dsmQueries, dodQueries, reserved;
} S540OptionalAcpiAbsence;
/* NV_OK here records selected backend capability absence. The original
 * operation still receives NV_ERR_NOT_SUPPORTED; no ACPI method ran. */
NV_STATUS s540OptionalAcpiCommitAbsent(const void *exactNv, NvU32 query, NvU32 function);
NV_STATUS s540OptionalAcpiRead(const void *exactNv, S540OptionalAcpiAbsence *);
#ifdef __cplusplus
}
#endif
#endif
