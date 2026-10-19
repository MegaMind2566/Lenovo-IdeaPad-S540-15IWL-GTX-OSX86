/* SPDX-License-Identifier: MIT */
/* Explicit manual-start/no-file/no-NVIDIA-console ABI participant. */
#include "nv.h"
#include "os-interface.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"

#if !defined(S540_NVIDIA_LIVE_PLATFORM_CLOSURE) || S540_NVIDIA_LIVE_PLATFORM_CLOSURE != 1 || \
    !defined(S540_NVIDIA_MANUAL_ADAPTER_START) || S540_NVIDIA_MANUAL_ADAPTER_START != 1
#error "Explicit sealed manual-adapter-start platform profile required"
#endif
#if !defined(S540_NVIDIA_NO_FILE_BACKEND) || S540_NVIDIA_NO_FILE_BACKEND != 1 || \
    !defined(S540_NVIDIA_NO_NVIDIA_CONSOLE) || S540_NVIDIA_NO_NVIDIA_CONSOLE != 1
#error "Explicit no-file/no-NVIDIA-console profile required"
#endif
#if !defined(NV_X86_64) || NV_ARCH_BITS != 64 || !defined(NV_UNIX)
#error "Exact original x86-64 Unix callback ABI required"
#endif
#if defined(NV_FILESYSTEM_ACCESS_AVAILABLE) && NV_FILESYSTEM_ACCESS_AVAILABLE
#error "The no-file profile cannot serve enabled filesystem access"
#endif

#define MARK() s540GlobalRmRecordServiceName(__func__)
static void unavailable(void) { s540GlobalRmRecordUnavailable(580); }
static __attribute__((noreturn)) void violation(const char *reason)
{
    unavailable();
    os_bug_check(0, reason);
    __builtin_trap();
}

NvBool NV_API_CALL os_is_bif_reset_supported(void *osInfo)
{
    S540FirstTxnSnapshot snapshot;
    MARK();
    if (!osInfo || s540FirstTxnGetSnapshot(osInfo, &snapshot) != NV_OK || !snapshot.generation)
        violation("BIF init policy requires the exact retained original state");
    /* The original result is !init_on_probe, also negated by
     * osIsInitOnProbeEnabled. Our sealed owner starts original adapter work
     * only after an explicit request, never during provider probe. This is
     * startup-policy identity, not proof that a hardware reset is safe.
     */
    return NV_TRUE;
}

NV_STATUS NV_API_CALL os_allocate_temporary_file(void **file, NvU64 bytes)
{
    (void)file; (void)bytes;
    MARK(); unavailable();
    /* Exact official disabled-filesystem outcome: ERR_PTR(-EOPNOTSUPP)
     * reaches NV_ERR_OPERATING_SYSTEM without publishing *file.
     */
    return NV_ERR_OPERATING_SYSTEM;
}
NV_STATUS NV_API_CALL os_read_file(void *file, NvU8 *buffer, NvU64 bytes, NvU64 offset)
{
    (void)file; (void)buffer; (void)bytes; (void)offset;
    MARK(); unavailable();
    return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS NV_API_CALL os_write_file(void *file, NvU8 *buffer, NvU64 bytes, NvU64 offset)
{
    (void)file; (void)buffer; (void)bytes; (void)offset;
    MARK(); unavailable();
    return NV_ERR_NOT_SUPPORTED;
}
void NV_API_CALL os_close_file(void *file)
{
    MARK();
    /* FBSR cleanup can visit an unsuccessful allocation's NULL sectionHandle.
     * No backend in this profile can publish a non-NULL file identity. Never
     * pretend a foreign handle has been closed or its ownership retired.
     */
    if (file) violation("No-file backend cannot close a live file identity");
}
void NV_API_CALL os_disable_console_access(void)
{
    MARK();
    violation("NVIDIA console exclusion required before original BAR1 setup");
}
void NV_API_CALL os_enable_console_access(void)
{
    MARK();
    violation("No NVIDIA console lock was acquired by this backend");
}
