/* SPDX-License-Identifier: MIT */
/* Uses the pinned original declarations, actual selected ACPI facade and real
 * host refusal observer. No AML, notifier or physical device is exercised.
 */
#include "nv.h"
#include "../src/S540NvidiaGlobalRm.h"
#include "../src/S540NvidiaGlobalRmProfile.h"
#include <stdio.h>

typedef void (NV_API_CALL *InitAbi)(NvU32 *);
typedef void (NV_API_CALL *UninitAbi)(void);
typedef NV_STATUS (NV_API_CALL *D3Abi)(nv_state_t *, NvU8 *, NvU32, NvU32, NvU32 *);
typedef NV_STATUS (NV_API_CALL *DdcAbi)(nv_state_t *, void *, NvU32 *, NvBool);
typedef NV_STATUS (NV_API_CALL *DodAbi)(nv_state_t *, NvU32 *, NvU32 *);
typedef NV_STATUS (NV_API_CALL *DsmAbi)(nv_state_t *, NvU8 *, NvU32, NvBool,
                                     NvU32, void *, NvU16, NvU32 *, void *, NvU16 *);
typedef NV_STATUS (NV_API_CALL *PowerAbi)(NvU32 *);
typedef NV_STATUS (NV_API_CALL *MuxAbi)(nv_state_t *, NvU32 *, NvU32, const char *);
#define ABI(name, type) _Static_assert(__builtin_types_compatible_p( \
    __typeof__(&name), type), "Pinned ACPI ABI changed: " #name)
ABI(nv_acpi_methods_init, InitAbi);
ABI(nv_acpi_methods_uninit, UninitAbi);
ABI(nv_acpi_d3cold_dsm_for_upstream_port, D3Abi);
ABI(nv_acpi_ddc_method, DdcAbi);
ABI(nv_acpi_dod_method, DodAbi);
ABI(nv_acpi_dsm_method, DsmAbi);
ABI(nv_acpi_get_powersource, PowerAbi);
ABI(nv_acpi_mux_method, MuxAbi);

int main(void)
{
    NvU32 checks = 0, handles = ~0U, value = 0xDECAFACEU, size = 8;
    NvU32 data[2] = {0x12345678U, 0x98765432U};
    NvU8 guid[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
    NvU32 outputStatus = 0xC0FFEEU;
    NvU16 shortSize = 8;
    S540NvidiaGlobalRmPlatformFacts facts = {0};
    S540NvidiaGlobalRmHostSnapshot snapshot = {0};
#define EXPECT(value) do { ++checks; if (!(value)) { \
    fprintf(stderr, "ACPI profile check failed at line %d\n", __LINE__); return 1; \
    } } while (0)
    facts.format = 1;
    facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1;
    facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25;
    facts.osVersion = "native-platform-fixture";
    facts.osDate = "native-platform-fixture";
    EXPECT(S540_GLOBAL_RM_ACPI_EVENTS_ENABLED == 0);
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    nv_acpi_methods_init(&handles);
    EXPECT(handles == 0);
    nv_acpi_methods_uninit();
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.unavailableCalls == 0 && snapshot.liveAllocations == 0);

    EXPECT(nv_acpi_d3cold_dsm_for_upstream_port(NULL, guid, 1, 2, &value)
           == NV_ERR_NOT_SUPPORTED);
    EXPECT(value == 0xDECAFACEU && guid[0] == 1 && guid[15] == 16);
    EXPECT(nv_acpi_ddc_method(NULL, data, &size, NV_TRUE) == NV_ERR_NOT_SUPPORTED);
    EXPECT(data[0] == 0x12345678U && data[1] == 0x98765432U && size == 8);
    EXPECT(nv_acpi_dod_method(NULL, data, &size) == NV_ERR_NOT_SUPPORTED);
    EXPECT(data[0] == 0x12345678U && data[1] == 0x98765432U && size == 8);
    EXPECT(nv_acpi_dsm_method(NULL, guid, 1, NV_TRUE, 2, data, 8,
                             &outputStatus, data, &shortSize) == NV_ERR_NOT_SUPPORTED);
    EXPECT(outputStatus == 0xC0FFEEU && shortSize == 8 &&
           data[0] == 0x12345678U && data[1] == 0x98765432U);
    EXPECT(nv_acpi_get_powersource(&value) == NV_ERR_NOT_SUPPORTED);
    EXPECT(value == 0xDECAFACEU);
    EXPECT(nv_acpi_mux_method(NULL, data, 0, "_DSM") == NV_ERR_NOT_SUPPORTED);
    EXPECT(data[0] == 0x12345678U && data[1] == 0x98765432U);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.unavailableCalls == 6);
    EXPECT(s540GlobalRmObservedServices() == 8);
    EXPECT(snapshot.liveAllocations == 0 && snapshot.liveBytes == 0);
    nv_acpi_methods_init(NULL);
    s540GlobalRmHostSnapshot(&snapshot);
    EXPECT(snapshot.unavailableCalls == 7);
    EXPECT(s540GlobalRmHostShutdown());

    printf("{\"format\":1,\"component\":\"nvidia-acpi-profile\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"unsupported_methods\":6,\"observed_refusals\":7,"
           "\"real_host_observer\":true,\"rm_acpi_events_enabled\":false,"
           "\"platform_facts_fixture\":true,\"execution\":\"native-user-space\","
           "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
