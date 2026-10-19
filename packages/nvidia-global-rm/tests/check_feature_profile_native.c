/* SPDX-License-Identifier: MIT */
/* Actual original ABI and real host/data facade; all platform/device values
 * below are explicit fixtures. No GPU or kernel execution is established.
 */
#include "nv.h"
#include "os-interface.h"
#include "../src/S540NvidiaGlobalRm.h"
#include "../src/S540NvidiaGlobalRmFeatureProfile.h"
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>

static nv_state_t selected;
static void seedState(void)
{
    selected = (nv_state_t){0};
    selected.pci_info.vendor_id = 0x10de;
    selected.pci_info.device_id = 0x1f91;
    selected.subsystem_vendor = 0x17aa;
    selected.subsystem_id = 0x3806;
    selected.pci_cfg_space[0] = 0x1f9110de;
    selected.pci_cfg_space[2] = 0xa1;
    selected.pci_cfg_space[11] = 0x380617aa;
}
static NvBool aborted(NvU32 which)
{
    pid_t pid = fork();
    if (pid < 0) return NV_FALSE;
    if (!pid) {
        if (which == 0) nv_get_current_irq_type(NULL);
        else if (which == 1) { selected.num_soc_irqs = 1; nv_control_soc_irqs(&selected, NV_TRUE); }
        else if (which == 2) os_nv_cap_close_fd(5);
        else os_nv_cap_destroy_entry(NULL);
        _exit(0);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) != pid) return NV_FALSE;
    return WIFSIGNALED(status) && (WTERMSIG(status) == SIGABRT || WTERMSIG(status) == SIGILL);
}
int main(void)
{
    NvU32 checks = 0, value = 0x12345678U, second = 0x76543210U, handle = 0xabcdef01U;
    NvU64 physical = 0x1111222233334444ULL, limit = 0x5555666677778888ULL;
    NvU8 message[4] = {1, 2, 3, 4};
    S540NvidiaGlobalRmPlatformFacts facts = {0};
    S540NvidiaGlobalRmHostSnapshot host;
#define EXPECT(condition) do { ++checks; if (!(condition)) { \
    fprintf(stderr, "Feature profile check failed at line %d\n", __LINE__); return 1; } } while (0)
    seedState();
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_NOT_READY);
    facts.format = 1; facts.known = S540_GLOBAL_FACT_ALL;
    facts.cpuCount = 1; facts.cpuFrequencyHz = 2000000000ULL;
    facts.osMajor = 25; facts.osVersion = facts.osDate = "native-feature-fixture";
    EXPECT(s540GlobalRmHostInitialize(&facts) == NV_OK);
    EXPECT(s540GlobalRmFeatureProfileVersion() == 1);
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_OK);
    EXPECT(s540GlobalRmFeatureProfilePreflight(NULL) == NV_ERR_NOT_SUPPORTED);
    selected.pci_cfg_space[2] = 0xa2;
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_NOT_SUPPORTED);
    seedState(); selected.flags = NV_FLAG_SOC_DISPLAY;
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_NOT_SUPPORTED);
    seedState(); selected.flags = NV_FLAG_PASSTHRU;
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_NOT_SUPPORTED);
    seedState(); selected.num_soc_irqs = 1;
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_NOT_SUPPORTED);
    seedState(); selected.is_tegra_pci_igpu = NV_TRUE;
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_NOT_SUPPORTED);
    seedState(); os_imex_channel_is_supported = NV_TRUE;
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_NOT_SUPPORTED);
    os_imex_channel_is_supported = NV_FALSE;
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_OK);
    EXPECT(nv_get_max_freq(&selected, 0, &value) == NV_ERR_NOT_SUPPORTED);
    EXPECT(value == 0x12345678U);
    nv_disable_clk(&selected, 0);
    EXPECT(nv_tegra_get_rm_interface_type(0) == NV_ERR_NOT_SUPPORTED);
    EXPECT(nv_imp_get_import_data(NULL) == NV_ERR_NOT_SUPPORTED);
    EXPECT(nv_imp_get_uefi_data(&selected, &value, &second) == NV_ERR_NOT_SUPPORTED);
    EXPECT(value == 0 && second == 0);
    EXPECT(nv_get_syncpoint_aperture(0, &physical, &limit, &handle) == NV_ERR_NOT_SUPPORTED);
    EXPECT(physical == 0x1111222233334444ULL && limit == 0x5555666677778888ULL && handle == 0xabcdef01U);
    nv_control_soc_irqs(&selected, NV_TRUE);
    nv_control_soc_irqs(&selected, NV_FALSE);
    EXPECT(nv_get_current_irq_type(&selected) == NV_SOC_IRQ_INVALID_TYPE);
    EXPECT(os_call_vgpu_vfio(message, 2) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_call_vgpu_vfio(message, 3) == NV_ERR_NOT_SUPPORTED);
    EXPECT(message[0] == 1 && message[3] == 4);
    EXPECT(os_device_vm_present() == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_cgroup_for_pid(1, NULL, 0) == NULL);
    EXPECT(nv_i2c_add_adapter(&selected, 0) == NULL);
    os_add_record_for_crashLog(message, sizeof(message));
    os_delete_record_for_crashLog(message);
    EXPECT(message[0] == 1 && message[3] == 4);
    EXPECT(os_imex_channel_count() == 0);
    EXPECT(os_imex_channel_get(0x1234) == -1);
    EXPECT(os_nv_cap_validate_and_dup_fd(NULL, 5) == -1);
    os_nv_cap_close_fd(-1);
    int descriptor = 99;
    EXPECT(nv_acquire_fabric_mgmt_cap(5, &descriptor) == NV_ERR_INSUFFICIENT_PERMISSIONS);
    EXPECT(descriptor == -1);
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.unavailableCalls == 0 && host.invalidFrees == 0);
    for (NvU32 i = 0; i < 4; ++i) EXPECT(aborted(i));
    EXPECT(nv_enable_clk(&selected, 0) == NV_ERR_NOT_SUPPORTED);
    EXPECT(nv_set_freq(&selected, 0, 50) == NV_ERR_NOT_SUPPORTED);
    EXPECT(nv_tegra_dce_register_ipc_client(0, NULL, NULL, &handle) == NV_ERR_NOT_SUPPORTED);
    EXPECT(handle == 0xabcdef01U);
    EXPECT(nv_tegra_dce_client_ipc_send_recv(0, message, sizeof(message)) == NV_ERR_NOT_SUPPORTED);
    EXPECT(message[0] == 1 && message[3] == 4);
    EXPECT(nv_tegra_dce_unregister_ipc_client(0) == NV_ERR_NOT_SUPPORTED);
    EXPECT(nv_imp_icc_set_bw(&selected, 1, 2) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_call_vgpu_vfio(message, 1) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_inject_vgx_msi(1, 2, 3) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_tegra_igpu_perf_boost(NULL, NV_TRUE, 1, 0) == NV_ERR_NOT_SUPPORTED);
    EXPECT(os_nv_cap_create_dir_entry(NULL, "x", 0) == NULL);
    EXPECT(os_nv_cap_create_file_entry(NULL, "x", 0) == NULL);
    s540GlobalRmHostSnapshot(&host);
    EXPECT(host.unavailableCalls == 11 && host.invalidFrees == 0);
    EXPECT(s540GlobalRmFeatureProfilePreflight(&selected) == NV_ERR_INVALID_STATE);
    EXPECT(host.liveAllocations == 0 && host.liveBytes == 0);
    EXPECT(s540GlobalRmHostShutdown());
    printf("{\"format\":1,\"component\":\"nvidia-feature-profile\",\"status\":\"passed\","
           "\"checks\":%u,\"failures\":0,\"execution\":\"native-user-space\","
           "\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
           "\"exact_original_headers\":true,\"platform_device_fixture\":true,"
           "\"official_disabled_queries\":true,\"unavailable_operations\":11,"
           "\"fatal_ownership_tripwires\":4,\"cleanup\":true}\n", checks);
    return 0;
#undef EXPECT
}
