/* SPDX-License-Identifier: MIT */
/* Original-profile ABI for the explicitly selected no-RM-ACPI-events backend.
 * Equivalent capability semantics are present in the original nv-acpi.c
 * NV_LINUX_ACPI_EVENTS_SUPPORTED-disabled branch. This never claims that the
 * machine lacks ACPI, that a method executed, or that a PM reference exists.
 */
#include "nv.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmProfile.h"

#if S540_GLOBAL_RM_ACPI_EVENTS_ENABLED != 0
#error "No RM ACPI events backend is implemented for an enabled profile"
#endif

static NV_STATUS unavailable(const char *name)
{
    s540GlobalRmRecordServiceName(name);
    s540GlobalRmRecordUnavailable(0);
    return NV_ERR_NOT_SUPPORTED;
}

void NV_API_CALL nv_acpi_methods_init(NvU32 *handles)
{
    s540GlobalRmRecordServiceName(__func__);
    if (!handles) {
        s540GlobalRmRecordUnavailable(0);
        return;
    }
    /* No handles are registered by this selected backend. This is not ACPI
     * namespace discovery and cannot be used as a hardware absence fact.
     */
    *handles = 0;
}

void NV_API_CALL nv_acpi_methods_uninit(void)
{
    s540GlobalRmRecordServiceName(__func__);
    /* The disabled backend owns no handles and has installed no notifier. */
}

NV_STATUS NV_API_CALL nv_acpi_d3cold_dsm_for_upstream_port(
    nv_state_t *nv, NvU8 *guid, NvU32 revision, NvU32 function, NvU32 *data)
{
    (void)nv; (void)guid; (void)revision; (void)function; (void)data;
    return unavailable(__func__);
}

NV_STATUS NV_API_CALL nv_acpi_ddc_method(nv_state_t *nv, void *edid,
                                       NvU32 *size, NvBool multiBlock)
{
    (void)nv; (void)edid; (void)size; (void)multiBlock;
    return unavailable(__func__);
}

NV_STATUS NV_API_CALL nv_acpi_dod_method(nv_state_t *nv, NvU32 *data, NvU32 *size)
{
    (void)nv; (void)data; (void)size;
    return unavailable(__func__);
}

NV_STATUS NV_API_CALL nv_acpi_dsm_method(
    nv_state_t *nv, NvU8 *guid, NvU32 revision, NvBool nvpcf, NvU32 function,
    void *input, NvU16 inputSize, NvU32 *status, void *data, NvU16 *size)
{
    (void)nv; (void)guid; (void)revision; (void)nvpcf; (void)function;
    (void)input; (void)inputSize; (void)status; (void)data; (void)size;
    return unavailable(__func__);
}

NV_STATUS NV_API_CALL nv_acpi_get_powersource(NvU32 *acPlugged)
{
    (void)acPlugged;
    return unavailable(__func__);
}

NV_STATUS NV_API_CALL nv_acpi_mux_method(nv_state_t *nv, NvU32 *inOut,
                                       NvU32 muxId, const char *method)
{
    (void)nv; (void)inOut; (void)muxId; (void)method;
    return unavailable(__func__);
}
