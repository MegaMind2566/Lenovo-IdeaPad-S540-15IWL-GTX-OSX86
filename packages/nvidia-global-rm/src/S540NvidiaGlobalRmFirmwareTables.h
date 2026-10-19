/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GLOBAL_RM_FIRMWARE_TABLES_H
#define S540_NVIDIA_GLOBAL_RM_FIRMWARE_TABLES_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS s540GlobalRmReadFirmwareRsdp(NvU32 *physical);
#ifdef __cplusplus
}
namespace S540NvidiaFirmwareTables {
/* Explicit native byte-reader boundary. Production supplies its fixed public
 * IOKit physical descriptor implementation; no caller supplies readiness.
 */
struct Reader {
    void *context;
    NV_STATUS (*read)(void *, NvU64 address, NvU8 *bytes, NvU32 length);
};
NV_STATUS decodeTableAddress(const NvU8 *bytes, NvU32 length, NvU64 &result);
NV_STATUS validateRsdp(const Reader &, NvU64 physical, NvU32 &result);
}
#endif
#endif
