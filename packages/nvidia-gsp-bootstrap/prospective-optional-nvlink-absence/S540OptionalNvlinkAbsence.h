/* SPDX-License-Identifier: MIT */
#ifndef S540_OPTIONAL_NVLINK_ABSENCE_H
#define S540_OPTIONAL_NVLINK_ABSENCE_H
#include "nvtypes.h"
#include "nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct S540OptionalNvlinkAbsence {
    NvU32 format, bytes;
    NvU64 generation;
    NvU32 absent, classId;
    NvU64 instance;
} S540OptionalNvlinkAbsence;
/* These private scalar observations never authorize cleanup or release. */
NV_STATUS s540OptionalNvlinkCommitAbsent(const void *exactNv);
NV_STATUS s540OptionalNvlinkRead(const void *exactNv, S540OptionalNvlinkAbsence *);
#ifdef __cplusplus
}
#endif
#endif
