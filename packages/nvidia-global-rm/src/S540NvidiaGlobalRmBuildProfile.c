// SPDX-License-Identifier: MIT
// These are original compile-profile predicates, not inferred GPU features.
// The same original build flags and namespace are applied to this facade.
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGlobalRm.h"
NvBool NV_API_CALL os_is_grid_supported(void)
{
    s540GlobalRmRecordServiceName(__func__);
#if defined(NV_GRID_BUILD)
    return NV_TRUE;
#else
    return NV_FALSE;
#endif
}
NvU32 NV_API_CALL os_get_grid_csp_support(void)
{
    s540GlobalRmRecordServiceName(__func__);
#if defined(NV_GRID_BUILD_CSP)
    return NV_GRID_BUILD_CSP;
#else
    return 0;
#endif
}
