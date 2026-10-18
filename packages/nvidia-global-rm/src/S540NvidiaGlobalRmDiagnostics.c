/* SPDX-License-Identifier: MIT */
/* Compile with the original RM profile and forced private namespace. */
#include "nv.h"
#include "nv-dev-printf.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRmDiagnostics.h"

typedef int (NV_API_CALL *S540DeviceLogAbi)(nv_state_t *, NV_LOG_LEVEL,
                                          const char *, va_list);
typedef NV_STATUS (NV_API_CALL *S540ErrorLogAbi)(nv_state_t *, NvU32,
                                               const char *, va_list);
typedef void (NV_API_CALL *S540BugCheckAbi)(NvU32, const char *);
_Static_assert(__builtin_types_compatible_p(__typeof__(&nv_dev_vprintf),
                                           S540DeviceLogAbi),
               "Original device log ABI changed");
_Static_assert(__builtin_types_compatible_p(__typeof__(&nv_log_error),
                                           S540ErrorLogAbi),
               "Original Xid log ABI changed");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_bug_check),
                                           S540BugCheckAbi),
               "Original bug check ABI changed");

int NV_API_CALL nv_dev_vprintf(nv_state_t *nv, NV_LOG_LEVEL level,
                              const char *format, va_list arguments)
{
    /* Linux also emits nothing for an absent device. A present context's
     * original nv_state owns the captured PCI identity until final detach.
     */
    if (!nv) return 0;
    if (!format) return -1;
    return s540GlobalRmDeviceLogV(nv->pci_info.domain, nv->pci_info.bus,
                                  nv->pci_info.slot, nv->pci_info.function,
                                  (NvU32)level, NV_FALSE, 0, format, arguments);
}

NV_STATUS NV_API_CALL nv_log_error(nv_state_t *nv, NvU32 error,
                                  const char *format, va_list arguments)
{
    if (!nv || !format) return NV_ERR_INVALID_ARGUMENT;
    /* Linux reports an Xid to its tracepoint and optional vendor subscriber.
     * This port reports the actual Xid to Darwin's system log; no Linux trace
     * stream or vendor subscriber registration is claimed by this boundary.
     */
    return s540GlobalRmDeviceLogV(nv->pci_info.domain, nv->pci_info.bus,
                                  nv->pci_info.slot, nv->pci_info.function,
                                  (NvU32)NV_LOG_LEVEL_ERROR, NV_TRUE, error,
                                  format, arguments) < 0
        ? NV_ERR_INVALID_ARGUMENT : NV_OK;
}

void NV_API_CALL os_bug_check(NvU32 code, const char *text)
{
    s540GlobalRmBugCheck(code, text);
}
