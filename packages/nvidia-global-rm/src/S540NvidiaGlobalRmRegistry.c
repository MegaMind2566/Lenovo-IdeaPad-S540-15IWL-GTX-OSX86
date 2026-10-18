/* SPDX-License-Identifier: MIT */
/* Original-profile C bridge, compiled with the private RM namespace. */
#include "nv.h"
#include "nv-reg.h"
#include "os/os.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmProfile.h"

extern NV_STATUS RmWriteRegistryDword(nv_state_t *, const char *, NvU32);
extern NV_STATUS RmReadRegistryDword(nv_state_t *, const char *, NvU32 *);
extern NV_STATUS RmPackageRegistry(nv_state_t *, PACKED_REGISTRY_TABLE *, NvU32 *);
extern NV_STATUS RmDestroyRegistry(nv_state_t *);

typedef struct S540ProfileRegistryEntry {
    const char *name;
    NvU32 value;
} S540ProfileRegistryEntry;

/* The original keys and values retain their original meanings. The marker is
 * written last and is never treated as evidence for kernel runtime admission.
 */
static const S540ProfileRegistryEntry profile[] = {
    { NV_REG_DYNAMIC_POWER_MANAGEMENT, NV_REG_DYNAMIC_POWER_MANAGEMENT_NEVER },
    { NV_REG_ENABLE_S0IX_POWER_MANAGEMENT, 0 },
    { NV_REG_NVLINK_DISABLE, 1 },
    { "S540DarwinGlobalRmProfile", S540_GLOBAL_RM_PROFILE_VERSION }
};

NV_STATUS s540GlobalRmCheckRegistryCold(void)
{
    NvU32 bytes = 0;
    NV_STATUS status = RmPackageRegistry(NULL, NULL, &bytes);
    if (status != NV_OK) return status;
    return bytes == NV_OFFSETOF(PACKED_REGISTRY_TABLE, entries)
        ? NV_OK : NV_ERR_STATE_IN_USE;
}

NV_STATUS s540GlobalRmCheckRegistryProfile(void)
{
    NvU32 index;
    for (index = 0; index != sizeof(profile) / sizeof(profile[0]); ++index) {
        NvU32 actual = ~0U;
        NV_STATUS status = RmReadRegistryDword(NULL, profile[index].name, &actual);
        if (status != NV_OK) return status;
        if (actual != profile[index].value) return NV_ERR_INVALID_STATE;
    }
    return NV_OK;
}

NV_STATUS s540GlobalRmInitializeRegistryProfile(void)
{
    const NvU32 emptySize = NV_OFFSETOF(PACKED_REGISTRY_TABLE, entries);
    NvU32 bytes = 0;
    NvU32 index;
    NV_STATUS status = s540GlobalRmCheckRegistryCold();
    /* The original API has no single-key deletion operation. Only claim
     * rollback ownership when the actual global registry is initially empty.
     * Never discard an unknown caller's preexisting registry entries.
     */
    if (status != NV_OK) return status;

    for (index = 0; index != sizeof(profile) / sizeof(profile[0]); ++index) {
        NvU32 actual = ~0U;
        status = RmWriteRegistryDword(NULL, profile[index].name, profile[index].value);
        if (status != NV_OK) goto failed;
        status = RmReadRegistryDword(NULL, profile[index].name, &actual);
        if (status != NV_OK) goto failed;
        if (actual != profile[index].value) {
            status = NV_ERR_INVALID_STATE;
            goto failed;
        }
    }
    return NV_OK;

failed:
    /* Also covers a write that performed a side effect before reporting an
     * error. This function owns the entire initially empty registry epoch.
     */
    if (RmDestroyRegistry(NULL) != NV_OK ||
        RmPackageRegistry(NULL, NULL, &bytes) != NV_OK || bytes != emptySize) {
        s540GlobalRmRecordUnavailable(0);
        return NV_ERR_INVALID_STATE;
    }
    return status;
}
