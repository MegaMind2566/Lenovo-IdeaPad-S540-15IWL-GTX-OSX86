/* SPDX-License-Identifier: MIT */
/* Seven exact original callbacks; no display, runtime PM or NVSwitch backend. */
#include "nv.h"
#include "os-interface.h"
#include "nvlink_os.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

#if !defined(S540_NVIDIA_DARWIN_PLATFORM_CLOSURE) || S540_NVIDIA_DARWIN_PLATFORM_CLOSURE != 1
#error "Explicit selected Darwin platform closure required"
#endif
#if !defined(NV_X86_64) || !defined(NV_UNIX) || NV_ARCH_BITS != 64
#error "Platform closure requires exact x86-64 original Unix ABI"
#endif
#if defined(NV_PM_RUNTIME_AVAILABLE)
#error "Platform closure cannot serve an enabled runtime-PM backend"
#endif
#if (defined(NV_SUPPORTS_PLATFORM_DEVICE) && NV_SUPPORTS_PLATFORM_DEVICE) || \
    (defined(NV_SUPPORTS_PLATFORM_DISPLAY_DEVICE) && NV_SUPPORTS_PLATFORM_DISPLAY_DEVICE)
#error "Platform closure cannot serve a Tegra platform backend"
#endif

#define MARK() s540GlobalRmRecordServiceName(__func__)

/* The selected source is the real NVIDIA open RM. This is identity support,
 * matching the official x86-64 branch, not simulated device initialization.
 */
NV_STATUS NV_API_CALL os_get_is_openrm(NvBool *open)
{
    MARK();
    if (!open) {
        s540GlobalRmRecordUnavailable(570);
        return NV_ERR_INVALID_ARGUMENT;
    }
    *open = NV_TRUE;
    return NV_OK;
}

/* Official !NV_PM_RUNTIME_AVAILABLE capability branch. This does not claim
 * D0 ownership, PM-tree readiness, suspension or successful PM operations.
 */
NvBool NV_API_CALL nv_dynamic_power_available(nv_state_t *nv)
{
    (void)nv;
    MARK();
    return NV_FALSE;
}

/* Official non-platform query. The original caller handles NOT_SUPPORTED by
 * choosing silicon/hardware simulation mode. It must not consume this output.
 */
NV_STATUS NV_API_CALL os_get_tegra_platform(NvU32 *mode)
{
    (void)mode;
    MARK();
    return NV_ERR_NOT_SUPPORTED;
}

/* Real utilities: original nvlink_os.h uses NvLength, not NvU32 lengths. */
char *nvlink_strcpy(char *destination, const char *source)
{
    char *begin = destination;
    MARK();
    do { *destination++ = *source; } while (*source++);
    return begin;
}
NvLength nvlink_strlen(const char *text)
{
    NvLength length = 0;
    MARK();
    while (text[length]) ++length;
    return length;
}
int nvlink_strcmp(const char *left, const char *right)
{
    const unsigned char *a = (const unsigned char *)left;
    const unsigned char *b = (const unsigned char *)right;
    MARK();
    while (*a && *a == *b) { ++a; ++b; }
    return (int)*a - (int)*b;
}
NvU64 nvlink_get_platform_time(void)
{
    MARK();
    /* Linux uses raw monotonic ns, not epoch. The existing Darwin provider
     * converts clock_get_uptime ticks with the actual kernel timebase.
     */
    return s540Darwin_os_get_monotonic_time_ns_hr();
}
