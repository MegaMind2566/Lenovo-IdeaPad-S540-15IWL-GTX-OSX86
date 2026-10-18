// SPDX-License-Identifier: MIT
// Host services used by original NVLink library code, even when no physical
// NVLink link is present. This unit adds no discovery or device-success facts.
#include "nv.h"
#include "os-interface.h"
#include "nvlink_os.h"
#include "S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

void *nvlink_malloc(NvLength bytes)
{
    s540GlobalRmRecordServiceName(__func__);
    // Like kmalloc(0), a zero-size request has a non-NULL freeable identity.
    return s540GlobalRmHostAllocateOriginal(bytes ? bytes : 1);
}
void nvlink_free(void *pointer)
{
    s540GlobalRmRecordServiceName(__func__);
    s540GlobalRmHostFreeOriginal(pointer);
}
void *nvlink_memset(void *destination, int value, NvLength bytes)
{
    NvU8 *output = destination;
    s540GlobalRmRecordServiceName(__func__);
    while (bytes--) *output++ = (NvU8)value;
    return destination;
}
void *nvlink_memcpy(void *destination, const void *source, NvLength bytes)
{
    NvU8 *output = destination;
    const NvU8 *input = source;
    s540GlobalRmRecordServiceName(__func__);
    while (bytes--) *output++ = *input++;
    return destination;
}
void nvlink_sleep(unsigned int milliseconds)
{
    s540GlobalRmRecordServiceName(__func__);
    // The original void service cannot return an unsupported-context status.
    // A failed real scheduler operation is fatal, not a successful no-op.
    if (s540Darwin_os_delay(milliseconds) != NV_OK)
        os_bug_check(0, "NVLink sleep requires ordinary thread context");
}
void nvlink_assert(int condition)
{
    s540GlobalRmRecordServiceName(__func__);
    // This port's assertion policy stops the session instead of continuing
    // after Linux WARN_ON/dbg_breakpoint. The diagnostic backend actually
    // terminates; the failed assertion cannot masquerade as supported work.
    if (!condition) os_bug_check(0, "NVLink assertion failed");
}
