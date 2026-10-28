/* SPDX-License-Identifier: MIT; explicit typed CPU facade boundary only. */
#ifndef S540_HOST_ALLOCATION_CONTROL_NV_H
#define S540_HOST_ALLOCATION_CONTROL_NV_H
#include "S540NvidiaGlobalRm.h"
typedef struct nv_state_t nv_state_t;
#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS NV_API_CALL os_alloc_mem(void **, NvU64);
void NV_API_CALL nv_acpi_methods_init(NvU32 *);
void NV_API_CALL nv_acpi_methods_uninit(void);
NV_STATUS NV_API_CALL nv_acpi_d3cold_dsm_for_upstream_port(
    nv_state_t *, NvU8 *, NvU32, NvU32, NvU32 *);
NV_STATUS NV_API_CALL nv_acpi_ddc_method(nv_state_t *, void *, NvU32 *, NvBool);
NV_STATUS NV_API_CALL nv_acpi_dod_method(nv_state_t *, NvU32 *, NvU32 *);
NV_STATUS NV_API_CALL nv_acpi_dsm_method(nv_state_t *, NvU8 *, NvU32, NvBool,
    NvU32, void *, NvU16, NvU32 *, void *, NvU16 *);
NV_STATUS NV_API_CALL nv_acpi_get_powersource(NvU32 *);
NV_STATUS NV_API_CALL nv_acpi_mux_method(nv_state_t *, NvU32 *, NvU32, const char *);
#ifdef __cplusplus
}
#endif
#endif
