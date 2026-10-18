/* SPDX-License-Identifier: MIT */
/* The included functions contain exact source-extracted statements from the
 * approved osRmInitRm patch. Registry calls use explicit fault fixtures.
 */
#include "nv.h"
#include "nv-reg.h"
#include "nvrm_registry.h"
#include "os/os.h"
#include <stdio.h>

extern NV_STATUS RmInitRegistry(void);
extern NV_STATUS RmDestroyRegistry(nv_state_t *);
#include "S540RegistryOverlayStages.h"

static NV_STATUS initStatus, writeStatus, readStatus;
static NvU32 disable, derived, writes, reads, destroys;
static NvBool readMismatch;

static void reset(void)
{
    initStatus = writeStatus = readStatus = NV_OK;
    disable = 1;
    derived = writes = reads = destroys = 0;
    readMismatch = NV_FALSE;
}

NV_STATUS RmInitRegistry(void) { return initStatus; }
NV_STATUS RmDestroyRegistry(nv_state_t *nv)
{
    (void)nv;
    ++destroys;
    derived = 0;
    return NV_OK;
}
NV_STATUS osWriteRegistryDword(OBJGPU *gpu, const char *key, NvU32 value)
{
    (void)gpu; (void)key;
    ++writes;
    // Also model a reported write error after a registry side effect.
    derived = value;
    return writeStatus;
}
NV_STATUS osReadRegistryDword(OBJGPU *gpu, const char *key, NvU32 *value)
{
    (void)gpu; (void)key;
    if (++reads == 1) {
        *value = disable;
        return NV_OK;
    }
    if (readStatus != NV_OK) return readStatus;
    *value = derived ^ (readMismatch ? 1U : 0U);
    return NV_OK;
}

int main(void)
{
    NvU32 checks = 0;
#define EXPECT(value) do { ++checks; if (!(value)) { \
    fprintf(stderr, "Registry overlay check failed at line %d\n", __LINE__); return 1; \
    } } while (0)
    reset();
    EXPECT(s540TestRegistryInitStage() == NV_OK);
    initStatus = NV_ERR_NO_MEMORY;
    EXPECT(s540TestRegistryInitStage() == NV_ERR_NO_MEMORY);
    EXPECT(writes == 0 && destroys == 0);
    reset();
    EXPECT(s540TestNvLinkStage() == NV_OK);
    EXPECT(writes == 1 && reads == 2 && derived == 1 && destroys == 0);
    reset();
    writeStatus = NV_ERR_NO_MEMORY;
    EXPECT(s540TestNvLinkStage() == NV_ERR_NO_MEMORY);
    EXPECT(writes == 1 && reads == 1 && derived == 0 && destroys == 1);
    reset();
    readStatus = NV_ERR_GENERIC;
    EXPECT(s540TestNvLinkStage() == NV_ERR_GENERIC);
    EXPECT(writes == 1 && reads == 2 && derived == 0 && destroys == 1);
    reset();
    readMismatch = NV_TRUE;
    EXPECT(s540TestNvLinkStage() == NV_ERR_INVALID_STATE);
    EXPECT(writes == 1 && reads == 2 && derived == 0 && destroys == 1);
    reset();
    disable = 0;
    EXPECT(s540TestNvLinkStage() == NV_OK);
    EXPECT(writes == 0 && reads == 1 && derived == 0 && destroys == 0);
    printf("{\"format\":1,\"component\":\"nvidia-registry-overlay\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"source_extracted_stages\":true,\"registry_abi_fixture\":true,"
           "\"execution\":\"native-user-space\","
           "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
