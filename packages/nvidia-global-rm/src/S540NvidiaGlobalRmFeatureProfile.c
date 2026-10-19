/* SPDX-License-Identifier: MIT */
/* Selected x86-64 TU117 physical backend; actual original callback headers. */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmFeatureProfile.h"

#if !defined(NV_X86_64) || !defined(NV_UNIX) || NV_ARCH_BITS != 64
#error "This feature profile requires the reviewed x86-64 original Unix ABI"
#endif
#if defined(NV_VGX_HYPER) || defined(NV_VGPU_KVM_BUILD) || defined(NV_DEVICE_VM_BUILD) || \
    defined(NV_GRID_BUILD) || defined(NV_GRID_BUILD_CSP)
#error "The physical TU117 profile cannot provide vGPU/DeviceVM/GRID services"
#endif
#if defined(CONFIG_COMMON_CLK) || defined(NV_LINUX_PLATFORM_TEGRA_DCE_DCE_CLIENT_IPC_H_PRESENT) || \
    defined(NV_LINUX_NVHOST_H_PRESENT) || defined(NV_LINUX_HOST1X_NEXT_H_PRESENT) || \
    defined(CONFIG_I2C) || defined(CONFIG_I2C_MODULE) || \
    defined(NV_DMEM_CGROUP_PRESENT) || defined(NV_MISC_CGROUP_PRESENT) || \
    defined(NV_SOC_TEGRA_TEGRA_BPMP_H_PRESENT) || defined(CONFIG_TEGRA_BPMP) || \
    defined(NV_LINUX_PLATFORM_TEGRA_MC_UTILS_H_PRESENT) || \
    defined(NV_DT_BINDINGS_INTERCONNECT_TEGRA_ICC_ID_H_PRESENT) || \
    defined(CONFIG_PM_DEVFREQ) || defined(NV_UPDATE_DEVFREQ_PRESENT)
#error "A Linux feature was enabled outside this immutable Darwin backend profile"
#endif
#if defined(IMP_SUPPORT_FUNCTIONS_PRESENT) && IMP_SUPPORT_FUNCTIONS_PRESENT
#error "Tegra IMP support requires a different implemented backend"
#endif
#if defined(ICC_SUPPORT_FUNCTIONS_PRESENT) && ICC_SUPPORT_FUNCTIONS_PRESENT
#error "Tegra ICC support requires a different implemented backend"
#endif
#if defined(NV_FILESYSTEM_ACCESS_AVAILABLE) && NV_FILESYSTEM_ACCESS_AVAILABLE
#error "Linux capability/IMEX filesystem ownership requires a different backend"
#endif
#if (defined(NV_SUPPORTS_PLATFORM_DEVICE) && NV_SUPPORTS_PLATFORM_DEVICE) || \
    (defined(NV_SUPPORTS_PLATFORM_DISPLAY_DEVICE) && NV_SUPPORTS_PLATFORM_DISPLAY_DEVICE)
#error "Tegra platform device/display services require a different backend"
#endif
#if S540_GLOBAL_RM_IMEX_CHANNEL_COUNT != 0
#error "This backend owns no IMEX channels or Linux capability descriptors"
#endif

/* Original nv-hypervisor.h command constants. They are repeated here because
 * that kernel-open header is outside the selected original RM include tree;
 * the source-bound contract verifies its exact bytes and these values.
 */
enum { VFIO_WAKE_REMOVE_GPU = 1, VGPU_VFIO_PRESENT = 2, VFIO_PCI_CORE_PRESENT = 3 };
#define MARK() s540GlobalRmRecordServiceName(__func__)
static void unavailable(void) { s540GlobalRmRecordUnavailable(510); }
static __attribute__((noreturn)) void violation(const char *reason)
{
    unavailable();
    os_bug_check(0, reason);
    __builtin_trap(); /* A broken diagnostic backend must not return a guess. */
}
static NvBool selectedState(const nv_state_t *nv)
{
    return nv && nv->pci_info.vendor_id == 0x10de && nv->pci_info.device_id == 0x1f91 &&
        nv->subsystem_vendor == 0x17aa && nv->subsystem_id == 0x3806 &&
        (nv->pci_cfg_space[0] & 0xffffU) == 0x10deU &&
        (nv->pci_cfg_space[0] >> 16) == 0x1f91U &&
        (nv->pci_cfg_space[2] & 0xffU) == 0xa1U &&
        (nv->pci_cfg_space[11] & 0xffffU) == 0x17aaU &&
        (nv->pci_cfg_space[11] >> 16) == 0x3806U &&
        !(nv->flags & (NV_FLAG_SOC_DISPLAY | NV_FLAG_PASSTHRU | NV_FLAG_CONTROL)) &&
        !nv->is_tegra_pci_igpu && nv->num_soc_irqs == 0 &&
        !nv->dma_buf_supported && nv->coherent_gpu_mem_mode == NV_COHERENT_GPU_MEM_MODE_NONE;
}
NvU32 s540GlobalRmFeatureProfileVersion(void)
{
    return S540_GLOBAL_RM_FEATURE_PROFILE_VERSION;
}
NV_STATUS s540GlobalRmFeatureProfilePreflight(const void *originalState)
{
    const S540NvidiaGlobalRmPlatformFacts *facts = s540GlobalRmPlatformFacts();
    S540NvidiaGlobalRmHostSnapshot host;
    s540GlobalRmHostSnapshot(&host);
    if (!facts || facts->format != 1 || facts->known != S540_GLOBAL_FACT_ALL)
        return NV_ERR_NOT_READY;
    if (!host.initialized || host.unavailableCalls || host.invalidFrees)
        return NV_ERR_INVALID_STATE;
    if (facts->vgpuHypervisor || os_imex_channel_is_supported || os_dma_buf_enabled ||
        os_cc_enabled || os_cc_sev_snp_enabled || os_cc_sme_enabled ||
        os_cc_snp_vtom_enabled || os_cc_tdx_enabled || nvidia_caps_root ||
        !selectedState(originalState))
        return NV_ERR_NOT_SUPPORTED;
    return NV_OK;
}

/* Official !CONFIG_COMMON_CLK implementation: no acquired clock handles. */
NV_STATUS NV_API_CALL nv_enable_clk(nv_state_t *nv, TEGRASOC_WHICH_CLK clock)
{
    (void)nv; (void)clock; MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}
void NV_API_CALL nv_disable_clk(nv_state_t *nv, TEGRASOC_WHICH_CLK clock)
{
    (void)nv; (void)clock; MARK();
}
NV_STATUS NV_API_CALL nv_get_max_freq(nv_state_t *nv, TEGRASOC_WHICH_CLK clock, NvU32 *frequency)
{
    (void)nv; (void)clock; (void)frequency; MARK(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_set_freq(nv_state_t *nv, TEGRASOC_WHICH_CLK clock, NvU32 frequency)
{
    (void)nv; (void)clock; (void)frequency; MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}

/* The original disabled-DCE query returns an NV error code in the NvU32 ABI. */
NvU32 NV_API_CALL nv_tegra_get_rm_interface_type(NvU32 type)
{
    (void)type; MARK(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_tegra_dce_register_ipc_client(NvU32 type, void *owner,
    nvTegraDceClientIpcCallback callback, NvU32 *handle)
{
    (void)type; (void)owner; (void)callback; (void)handle;
    MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_tegra_dce_client_ipc_send_recv(NvU32 handle, void *message, NvU32 bytes)
{
    (void)handle; (void)message; (void)bytes; MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_tegra_dce_unregister_ipc_client(NvU32 handle)
{
    (void)handle; MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_imp_get_import_data(TEGRA_IMP_IMPORT_DATA *data)
{
    (void)data; MARK(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_imp_get_uefi_data(nv_state_t *nv, NvU32 *iso, NvU32 *floor)
{
    (void)nv; MARK();
    if (!iso || !floor) return NV_ERR_INVALID_ARGUMENT;
    /* The pinned disabled branch initializes both values before its #if. */
    *iso = 0; *floor = 0;
    return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_imp_icc_set_bw(nv_state_t *nv, NvU32 average, NvU32 floor)
{
    (void)nv; (void)average; (void)floor; MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_get_syncpoint_aperture(NvU32 id, NvU64 *physical, NvU64 *limit, NvU32 *offset)
{
    (void)id; (void)physical; (void)limit; (void)offset; MARK(); return NV_ERR_NOT_SUPPORTED;
}

/* Exact zero-length original SoC IRQ loops, admitted only for this verified
 * original state. Unknown/SoC contexts cannot receive a fabricated answer.
 */
void NV_API_CALL nv_control_soc_irqs(nv_state_t *nv, NvBool enable)
{
    (void)enable; MARK();
    if (!selectedState(nv)) violation("SoC IRQ control requires the selected zero-IRQ PCI state");
}
nv_soc_irq_type_t NV_API_CALL nv_get_current_irq_type(nv_state_t *nv)
{
    MARK();
    if (!selectedState(nv)) violation("SoC IRQ query requires the selected zero-IRQ PCI state");
    return NV_SOC_IRQ_INVALID_TYPE;
}

NV_STATUS NV_API_CALL os_call_vgpu_vfio(void *information, NvU32 command)
{
    (void)information; MARK();
    if (command != VGPU_VFIO_PRESENT && command != VFIO_PCI_CORE_PRESENT)
        unavailable();
    return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL os_device_vm_present(void)
{
    MARK(); return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL os_inject_vgx_msi(NvU16 guest, NvU64 address, NvU32 data)
{
    (void)guest; (void)address; (void)data; MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}
void *NV_API_CALL os_cgroup_for_pid(int pid, void *pidInfo, int implementation)
{
    (void)pid; (void)pidInfo; (void)implementation; MARK(); return NULL;
}
void *NV_API_CALL nv_i2c_add_adapter(nv_state_t *nv, NvU32 port)
{
    (void)nv; (void)port; MARK(); return NULL;
}
void NV_API_CALL os_add_record_for_crashLog(void *buffer, NvU32 bytes)
{
    (void)buffer; (void)bytes; MARK();
}
void NV_API_CALL os_delete_record_for_crashLog(void *buffer)
{
    (void)buffer; MARK();
}
NvS32 NV_API_CALL os_imex_channel_count(void)
{
    MARK(); return S540_GLOBAL_RM_IMEX_CHANNEL_COUNT;
}
NvS32 NV_API_CALL os_imex_channel_get(NvU64 descriptor)
{
    (void)descriptor; MARK(); return -1;
}
int NV_API_CALL os_nv_cap_validate_and_dup_fd(const nv_cap_t *cap, int descriptor)
{
    (void)cap; (void)descriptor; MARK(); return -1;
}
void NV_API_CALL os_nv_cap_close_fd(int descriptor)
{
    MARK();
    /* No descriptor can be acquired in this backend. The original -1 sentinel
     * owns nothing; an arbitrary Darwin fd must never be silently consumed.
     */
    if (descriptor != -1) violation("No Linux capability descriptor is owned by this backend");
}
NV_STATUS NV_API_CALL nv_acquire_fabric_mgmt_cap(int descriptor, int *duplicate)
{
    (void)descriptor; MARK();
    if (!duplicate) return NV_ERR_INVALID_ARGUMENT;
    *duplicate = -1;
    return NV_ERR_INSUFFICIENT_PERMISSIONS;
}
NV_STATUS NV_API_CALL os_tegra_igpu_perf_boost(void *handle, NvBool enable,
    NvU32 duration, int type)
{
    (void)handle; (void)enable; (void)duration; (void)type;
    MARK(); unavailable(); return NV_ERR_NOT_SUPPORTED;
}
/* This backend implements no Linux capability directory/file creation. A
 * status/pointer refusal is observable; it is not an operational capability.
 */
nv_cap_t *NV_API_CALL os_nv_cap_create_dir_entry(nv_cap_t *parent, const char *name, int mode)
{
    (void)parent; (void)name; (void)mode; MARK(); unavailable(); return NULL;
}
nv_cap_t *NV_API_CALL os_nv_cap_create_file_entry(nv_cap_t *parent, const char *name, int mode)
{
    (void)parent; (void)name; (void)mode; MARK(); unavailable(); return NULL;
}
void NV_API_CALL os_nv_cap_destroy_entry(nv_cap_t *cap)
{
    (void)cap; MARK(); violation("No Linux capability entry is owned by this backend");
}
#undef MARK
