/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRmCentralPolicy.h"
#include "S540NvidiaGlobalRm.h"
#if defined(NV_PM_RUNTIME_AVAILABLE) || defined(NV_PCI_ENABLE_ATOMIC_OPS_TO_ROOT_PRESENT) || \
    defined(PCI_DVSEC_CXL_DEVCAP_CACHE_CAPABLE)
#error "Enabled runtime PM, PCI requester atomics or CXL cache requires an operational backend"
#endif
#if S540_GLOBAL_RM_RUNTIME_PM_BACKEND || S540_GLOBAL_RM_KERNEL_SUSPEND_NOTIFIERS || \
    S540_GLOBAL_RM_PCI_HOT_REMOVE_SERVICE || S540_GLOBAL_RM_PCI_REQUEST_ATOMICS_SERVICE || \
    S540_GLOBAL_RM_CXL_CACHE_SERVICE
#error "The selected central policy has no enabled optional operation backend"
#endif
#define MARK() s540GlobalRmRecordServiceName(__func__)
#define ABI(name,type) _Static_assert(__builtin_types_compatible_p(__typeof__(&name),type), \
                                      "Original central policy ABI mismatch: " #name)
typedef NvBool (NV_API_CALL *BoolQuery)(void);
typedef NV_STATUS (NV_API_CALL *DevicePower)(nv_state_t *);
typedef void (NV_API_CALL *DeviceAction)(nv_state_t *);
typedef void (NV_API_CALL *CxlAction)(nv_state_t *, NvBool);
typedef void (NV_API_CALL *PciRemove)(void *);
typedef NV_STATUS (NV_API_CALL *AtomicRequest)(void *, enum os_pci_req_atomics_type);
ABI(os_supports_kernel_suspend_notifiers,BoolQuery);
ABI(os_pci_remove_supported,BoolQuery);
ABI(os_pci_remove,PciRemove);
ABI(nv_indicate_idle,DevicePower);
ABI(nv_indicate_not_idle,DevicePower);
ABI(nv_audio_dynamic_power,DeviceAction);
ABI(os_enable_pci_req_atomics,AtomicRequest);
ABI(nv_pci_cxl_set_caching,CxlAction);

NvBool NV_API_CALL os_supports_kernel_suspend_notifiers(void)
{
    /* Our IOKit PM child revokes/quiesces this owner. It never registers the
     * Linux suspend notifier or forwards RM S-state/hibernate operations.
     */
    MARK(); return NV_FALSE;
}
NvBool NV_API_CALL os_pci_remove_supported(void)
{
    /* The backend owns no bus-device hot-remove service. This is a capability
     * denial, not an assertion about physical slot/hotplug capability.
     */
    MARK(); return NV_FALSE;
}
void NV_API_CALL os_pci_remove(void *handle)
{
    (void)handle; MARK(); s540GlobalRmRecordUnavailable(509);
    os_bug_check(0,"PCI hot-remove operation was not admitted by this backend");
    __builtin_trap();
}
NV_STATUS NV_API_CALL nv_indicate_idle(nv_state_t *state)
{
    /* Exact original no-runtime-PM status. This does not decrement a platform
     * power reference; an unexpected operation invalidates adapter success.
     */
    (void)state; MARK(); s540GlobalRmRecordUnavailable(509);
    return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL nv_indicate_not_idle(nv_state_t *state)
{
    (void)state; MARK(); s540GlobalRmRecordUnavailable(509);
    return NV_ERR_NOT_SUPPORTED;
}
void NV_API_CALL nv_audio_dynamic_power(nv_state_t *state)
{
    /* Official empty branch without Linux runtime PM/HDA wake infrastructure.
     * No audio power operation or codec wakeup is claimed.
     */
    (void)state; MARK();
}
NV_STATUS NV_API_CALL os_enable_pci_req_atomics(void *handle, enum os_pci_req_atomics_type type)
{
    /* Original unavailable-conftest branch. The aggregate caller preserves a
     * zero capability mask on NOT_SUPPORTED; no config register was changed.
     */
    (void)handle; (void)type; MARK(); return NV_ERR_NOT_SUPPORTED;
}
void NV_API_CALL nv_pci_cxl_set_caching(nv_state_t *state, NvBool enable)
{
    /* Official empty branch without the CXL cache-capability backend. This
     * reports no cache writeback/invalidation completion for a CXL device.
     */
    (void)state; (void)enable; MARK();
}
