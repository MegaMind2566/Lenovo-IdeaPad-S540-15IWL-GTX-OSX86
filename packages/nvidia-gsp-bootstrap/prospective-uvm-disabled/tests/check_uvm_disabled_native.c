/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "gpu/gpu.h"
#include "core/gmcapi_impl.h"
#include <stdio.h>
/* Fixture byte comparisons use native libc, not an original RM memory facade. */
#undef memset
#undef memcpy
#undef memcmp
#include <string.h>

void original_disabled_nv_schedule_uvm_isr(nv_state_t *);
NV_STATUS original_disabled_nv_schedule_uvm_drain_p2p(NvU8 *);
void original_disabled_nv_schedule_uvm_resume_p2p(NvU8 *);
void prospective_osQueueMMUFaultHandler(OBJGPU *);
NV_STATUS prospective_osQueueDrainP2PHandler(NvU8 *);
void prospective_osQueueResumeP2PHandler(NvU8 *);
NV_STATUS prospective_gmcapiMmuFaultQueued(GMCAPI_CONTEXT *);

_Static_assert(__builtin_types_compatible_p(__typeof__(&nv_schedule_uvm_isr),
    void (NV_API_CALL *)(nv_state_t *)), "Exact original ISR ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&nv_schedule_uvm_drain_p2p),
    NV_STATUS (NV_API_CALL *)(NvU8 *)), "Exact original drain ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&nv_schedule_uvm_resume_p2p),
    void (NV_API_CALL *)(NvU8 *)), "Exact original resume ABI");

static nv_state_t state, before;
static OBJGPU gpu;
static GMCAPI_CONTEXT context = {.pGpu = &gpu};
int main(void)
{
    NvU32 checks = 0;
    NvU8 uuid[16], old[16];
#define EXPECT(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "UVM disabled check failed line%d\n", __LINE__); return 1; } } while (0)
    memset(&state, 0xa5, sizeof(state)); before = state;
    memset(uuid, 0x5a, sizeof(uuid)); memcpy(old, uuid, sizeof(uuid));
    nv_schedule_uvm_isr(NULL);
    nv_schedule_uvm_isr(&state);
    EXPECT(memcmp(&state, &before, sizeof(state)) == 0);
    nv_schedule_uvm_resume_p2p(NULL);
    nv_schedule_uvm_resume_p2p(uuid);
    EXPECT(memcmp(uuid, old, sizeof(uuid)) == 0);
    EXPECT(nv_schedule_uvm_drain_p2p(NULL) == NV_ERR_NOT_SUPPORTED);
    EXPECT(nv_schedule_uvm_drain_p2p(uuid) == NV_ERR_NOT_SUPPORTED);
    EXPECT(memcmp(uuid, old, sizeof(uuid)) == 0);

    original_disabled_nv_schedule_uvm_isr(NULL);
    original_disabled_nv_schedule_uvm_isr(&state);
    EXPECT(memcmp(&state, &before, sizeof(state)) == 0);
    original_disabled_nv_schedule_uvm_resume_p2p(NULL);
    original_disabled_nv_schedule_uvm_resume_p2p(uuid);
    EXPECT(memcmp(uuid, old, sizeof(uuid)) == 0);
    EXPECT(original_disabled_nv_schedule_uvm_drain_p2p(NULL) ==
        nv_schedule_uvm_drain_p2p(NULL));
    EXPECT(original_disabled_nv_schedule_uvm_drain_p2p(uuid) ==
        nv_schedule_uvm_drain_p2p(uuid));

    gpu.pOsGpuInfo = &state;
    prospective_osQueueMMUFaultHandler(&gpu);
    EXPECT(memcmp(&state, &before, sizeof(state)) == 0);
    EXPECT(prospective_osQueueDrainP2PHandler(uuid) == NV_ERR_NOT_SUPPORTED);
    prospective_osQueueResumeP2PHandler(uuid);
    EXPECT(memcmp(uuid, old, sizeof(uuid)) == 0);
    EXPECT(prospective_gmcapiMmuFaultQueued(&context) == NV_OK);
    EXPECT(memcmp(&state, &before, sizeof(state)) == 0);
    EXPECT(memcmp(uuid, old, sizeof(uuid)) == 0);
    printf("{\"format\":1,\"component\":\"nvidia-prospective-disabled-uvm\","
        "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"actual_original_forwarding_bodies\":4,"
        "\"actual_original_disabled_bodies\":3,\"uvm_interrupt_delivered\":false,"
        "\"p2p_drain_implemented\":false,\"original_entry_admission\":false}\n", checks);
    return 0;
}
