/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_FIRMWARE_ASSETS_C_H
#define S540_NVIDIA_FIRMWARE_ASSETS_C_H
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
typedef enum S540NvidiaFirmwareAssetReason {
    S540_NVIDIA_ASSETS_VERIFIED = 0,
    S540_NVIDIA_ASSETS_INVALID_ARGUMENT,
    S540_NVIDIA_ASSETS_MISSING,
    S540_NVIDIA_ASSETS_UNSAFE_FILE,
    S540_NVIDIA_ASSETS_SIZE_MISMATCH,
    S540_NVIDIA_ASSETS_READ_FAILED,
    S540_NVIDIA_ASSETS_ALLOCATION_FAILED,
    S540_NVIDIA_ASSETS_HASH_MISMATCH,
    S540_NVIDIA_ASSETS_CONTAINER_INVALID,
    S540_NVIDIA_ASSETS_UCODES_INVALID,
    S540_NVIDIA_ASSETS_LAYOUT_INVALID,
    S540_NVIDIA_ASSETS_CLEANUP_FAILED
} S540NvidiaFirmwareAssetReason;

typedef struct S540NvidiaFirmwareAssetResult {
    uint32_t format;
    bool present;
    bool hashesVerified;
    bool containerParsed;
    bool ucodesParsed;
    bool pairReady;
    bool cleanup;
    uint64_t gspSize;
    uint64_t ucodesSize;
    uint64_t imageSize;
    uint64_t signatureSize;
    uint32_t sectionCount;
    uint32_t ucodesEntryCount;
    uint32_t ucodesPresentCount;
    uint32_t checks;
    S540NvidiaFirmwareAssetReason reason;
} S540NvidiaFirmwareAssetResult;

/* Userspace only. Reads three exact regular files, verifies actual bytes, then
 * frees/closes all resources. Never uploads or executes firmware or accesses GPU.
 * Returns 1 only for a fully verified pair plus the complete matching notice.
 * Result is initialized on every call; a null result returns 0. */
int s540_nvidia_firmware_assets_check(const char *directory, S540NvidiaFirmwareAssetResult *result);
/* Fixed vocabulary, never an untrusted path or file content. */
const char *s540_nvidia_firmware_assets_reason(uint32_t reason);
#ifdef __cplusplus
}
#endif
#endif
