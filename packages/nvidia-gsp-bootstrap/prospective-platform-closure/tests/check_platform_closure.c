/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
#include "nvlink_os.h"
#include "gpu/gpu.h"
#include <stdio.h>
#include "../../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#undef memset
#undef memcmp
#include <string.h>

NV_STATUS original_os_get_is_openrm(NvBool *);
NV_STATUS original_os_get_tegra_platform(NvU32 *);
NvBool original_nv_dynamic_power_available(nv_state_t *);
NvU32 control_osGetSimulationMode(void);
NV_STATUS control_osGetIsOpenRM(NvBool *);

#define EXACT(name, type) _Static_assert(__builtin_types_compatible_p(__typeof__(&name), type), #name " original ABI")
EXACT(os_get_is_openrm, NV_STATUS (NV_API_CALL *)(NvBool *));
EXACT(os_get_tegra_platform, NV_STATUS (NV_API_CALL *)(NvU32 *));
EXACT(nv_dynamic_power_available, NvBool (NV_API_CALL *)(nv_state_t *));
EXACT(nvlink_strcpy, char *(*)(char *, const char *));
EXACT(nvlink_strlen, NvLength (*)(const char *));
EXACT(nvlink_strcmp, int (*)(const char *, const char *));
EXACT(nvlink_get_platform_time, NvU64 (*)(void));
_Static_assert(sizeof(NvLength) == 8, "Original length is not a truncated NvU32");

static NvU32 checks, unavailable, firstUnavailable, observations;
static nv_state_t state, before;
void s540GlobalRmRecordServiceName(const char *name) { if (name && *name) ++observations; }
void s540GlobalRmRecordUnavailable(NvU32 service) {
    ++unavailable;
    if (!firstUnavailable) firstUnavailable = service;
}
#define EXPECT(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "platform closure line%d\n", __LINE__); return 1; } } while (0)

int main(void)
{
    NvBool open = NV_FALSE, official = NV_FALSE;
    NvU32 mode = 0xfeed1234, officialMode = mode;
    NvU64 first, second;
    char buffer[12];
    char hi[] = {(char)0x80, 0};
    char lo[] = {0x7f, 0};
    memset(&state, 0xa5, sizeof(state)); before = state;

    EXPECT(os_get_is_openrm(&open) == NV_OK && open == NV_TRUE);
    EXPECT(original_os_get_is_openrm(&official) == NV_OK && official == open);
    open = NV_FALSE;
    EXPECT(control_osGetIsOpenRM(&open) == NV_OK && open == NV_TRUE);
    EXPECT(nv_dynamic_power_available(&state) == NV_FALSE);
    EXPECT(nv_dynamic_power_available(NULL) == NV_FALSE);
    EXPECT(original_nv_dynamic_power_available(&state) == NV_FALSE);
    EXPECT(memcmp(&state, &before, sizeof(state)) == 0);
    EXPECT(os_get_tegra_platform(&mode) == NV_ERR_NOT_SUPPORTED);
    EXPECT(mode == 0xfeed1234);
    EXPECT(original_os_get_tegra_platform(&officialMode) == NV_ERR_NOT_SUPPORTED);
    EXPECT(mode == officialMode);
    EXPECT(os_get_tegra_platform(NULL) == NV_ERR_NOT_SUPPORTED);
    EXPECT(control_osGetSimulationMode() == NV_SIM_MODE_HARDWARE);
    EXPECT(unavailable == 0);

    memset(buffer, 0x5a, sizeof(buffer));
    EXPECT(nvlink_strcpy(buffer, "alpha") == buffer);
    EXPECT(memcmp(buffer, "alpha\0", 6) == 0 && buffer[6] == 0x5a);
    EXPECT(nvlink_strlen(buffer) == 5);
    EXPECT(nvlink_strlen("") == 0);
    EXPECT(nvlink_strcmp("alpha", "alpha") == 0);
    EXPECT(nvlink_strcmp("alpha", "alphabet") < 0);
    EXPECT(nvlink_strcmp("alphabet", "alpha") > 0);
    EXPECT(nvlink_strcmp(hi, lo) > 0);
    EXPECT(nvlink_strcmp(lo, hi) < 0);
    first = nvlink_get_platform_time();
    EXPECT(first != 0);
    EXPECT(s540Darwin_os_delay_us(1000) == NV_OK);
    second = nvlink_get_platform_time();
    EXPECT(second >= first + 1000000ULL);
    EXPECT(second <= s540Darwin_os_get_monotonic_time_ns_hr());
    EXPECT(unavailable == 0 && observations != 0);

    EXPECT(os_get_is_openrm(NULL) == NV_ERR_INVALID_ARGUMENT);
    EXPECT(unavailable == 1 && firstUnavailable == 570);
    open = NV_FALSE;
    EXPECT(os_get_is_openrm(&open) == NV_OK && open == NV_TRUE);
    EXPECT(control_osGetSimulationMode() == NV_SIM_MODE_HARDWARE);
    EXPECT(unavailable == 1 && firstUnavailable == 570);
    EXPECT(os_get_is_openrm(NULL) == NV_ERR_INVALID_ARGUMENT);
    EXPECT(unavailable == 2 && firstUnavailable == 570);
    EXPECT(memcmp(&state, &before, sizeof(state)) == 0);
    printf("{\"format\":1,\"component\":\"nvidia-prospective-platform-closure\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"actual_original_query_callers\":3,"
        "\"official_branch_bodies\":3,\"callbacks\":7,"
        "\"real_monotonic_backend\":true,\"host_observer_fixture\":true,"
        "\"original_entry_admission\":false}\n", checks);
    return 0;
}
