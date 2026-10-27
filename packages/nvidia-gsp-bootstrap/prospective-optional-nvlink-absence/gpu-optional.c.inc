/* This optional child is omitted before allocation and publication, only for
 * the actual disabled-library policy. An initialized core keeps the original
 * constructor path, including every real constructor error and retained child.
 * "NvLinkDisable" is the exact NV_REG_NVLINK_DISABLE spelling, hash-bound to
 * the selected original nv-reg.h and checked global registry profile. */
#if !defined(INCLUDE_NVLINK_LIB)
#error The optional-absence profile requires the actual compiled NVLink library
#endif
static NV_STATUS
s540GpuOptionalNvlinkAbsent(OBJGPU *pGpu, Dynamic **ppChildPtr, NvBool *absent)
{
    NvU64 generation = 0;
    NvU32 disabled = ~0U;
    NV_STATUS status;
    if (!absent) return NV_ERR_INVALID_ARGUMENT;
    *absent = NV_FALSE;
    if (RMCFG_FEATURE_PLATFORM_WINDOWS) return NV_OK;
    if (!pGpu || !ppChildPtr || *ppChildPtr != NULL) return NV_ERR_INVALID_STATE;
    status = s540FirstTxnOptionalNvlinkActive(pGpu->pOsGpuInfo, &generation);
    if (status != NV_OK) return status;
    if (nvlink_lib_is_initialized()) return NV_OK;
    status = osReadRegistryDwordBase(NULL, "NvLinkDisable", &disabled);
    if (status != NV_OK) return status;
    if (disabled != 1U) return NV_ERR_INVALID_STATE;
    status = s540OptionalNvlinkCommitAbsent(pGpu->pOsGpuInfo);
    if (status != NV_OK) return status;
    *absent = NV_TRUE;
    return NV_OK;
}
