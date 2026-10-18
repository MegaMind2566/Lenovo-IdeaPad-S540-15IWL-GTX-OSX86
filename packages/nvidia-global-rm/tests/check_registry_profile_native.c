/* SPDX-License-Identifier: MIT */
/* Fault-control fixture for the original registry ABI. The complete global
 * lifecycle separately uses the real original registry implementation.
 */
#include "nv.h"
#include "os/os.h"
#include "os-interface.h"
#include "../src/S540NvidiaGlobalRmProfile.h"
#undef memset
#include <stdio.h>
#include <string.h>

typedef struct Entry { const char *name; NvU32 value; } Entry;
static Entry entries[8];
static NvU32 count, operations, writes, reads, packages, destroys, unavailable;
static NvU32 failOperation, mismatchOperation, failPackage;
static NvBool failDestroy, partialWrite, retainAfterDestroy;

static void reset(void)
{
    memset(entries, 0, sizeof(entries));
    count = operations = writes = reads = packages = destroys = unavailable = 0;
    failOperation = mismatchOperation = failPackage = 0;
    failDestroy = partialWrite = retainAfterDestroy = NV_FALSE;
}

static NvU32 find(const char *name)
{
    NvU32 i;
    for (i = 0; i != count; ++i) if (!strcmp(entries[i].name, name)) return i;
    return count;
}

NV_STATUS RmWriteRegistryDword(nv_state_t *state, const char *name, NvU32 value)
{
    NvU32 slot;
    (void)state;
    ++writes;
    ++operations;
    if (operations == failOperation && !partialWrite) return NV_ERR_GENERIC;
    slot = find(name);
    if (slot == count) ++count;
    entries[slot].name = name;
    entries[slot].value = value;
    return operations == failOperation ? NV_ERR_GENERIC : NV_OK;
}

NV_STATUS RmReadRegistryDword(nv_state_t *state, const char *name, NvU32 *value)
{
    NvU32 slot;
    (void)state;
    ++reads;
    ++operations;
    if (operations == failOperation) return NV_ERR_GENERIC;
    slot = find(name);
    if (slot == count) return NV_ERR_GENERIC;
    *value = entries[slot].value ^ (operations == mismatchOperation ? 1U : 0U);
    return NV_OK;
}

NV_STATUS RmPackageRegistry(nv_state_t *state, PACKED_REGISTRY_TABLE *table,
                            NvU32 *bytes)
{
    (void)state;
    (void)table;
    if (++packages == failPackage) return NV_ERR_GENERIC;
    *bytes = NV_OFFSETOF(PACKED_REGISTRY_TABLE, entries) + count * 64;
    return NV_OK;
}

NV_STATUS RmDestroyRegistry(nv_state_t *state)
{
    (void)state;
    ++destroys;
    if (failDestroy) return NV_ERR_GENERIC;
    if (!retainAfterDestroy) count = 0;
    return NV_OK;
}

void s540GlobalRmRecordUnavailable(NvU32 service) { (void)service; ++unavailable; }
void s540GlobalRmRecordService(NvU32 service) { (void)service; }
void s540GlobalRmRecordServiceName(const char *name) { (void)name; }

int main(void)
{
    NvU32 checks = 0, stage;
#define EXPECT(value) do { ++checks; if (!(value)) { \
    fprintf(stderr, "Registry profile check failed at line %d\n", __LINE__); return 1; \
    } } while (0)
    reset();
    EXPECT(os_registry_init() == NV_OK);
    EXPECT(count == 4 && writes == 4 && reads == 4 && packages == 1);
    EXPECT(!strcmp(entries[0].name, "DynamicPowerManagement") && entries[0].value == 0);
    EXPECT(!strcmp(entries[1].name, "EnableS0ixPowerManagement") && entries[1].value == 0);
    EXPECT(!strcmp(entries[2].name, "NvLinkDisable") && entries[2].value == 1);
    EXPECT(!strcmp(entries[3].name, "S540DarwinGlobalRmProfile") && entries[3].value == 2);
    EXPECT(s540GlobalRmCheckRegistryProfile() == NV_OK && reads == 8);
    EXPECT(os_registry_init() == NV_ERR_STATE_IN_USE);
    EXPECT(count == 4 && writes == 4 && destroys == 0 && unavailable == 0);
    entries[1].value = 1;
    EXPECT(s540GlobalRmCheckRegistryProfile() == NV_ERR_INVALID_STATE);

    reset();
    entries[count++] = (Entry){"foreign-owned-entry", 99};
    EXPECT(os_registry_init() == NV_ERR_STATE_IN_USE);
    EXPECT(writes == 0 && destroys == 0 && count == 1 && entries[0].value == 99);
    reset();
    failPackage = 1;
    EXPECT(os_registry_init() == NV_ERR_GENERIC);
    EXPECT(writes == 0 && destroys == 0 && unavailable == 0);

    /* Fail every write and readback, including writes with side effects. */
    for (stage = 1; stage <= 8; ++stage) {
        reset();
        failOperation = stage;
        partialWrite = NV_TRUE;
        EXPECT(os_registry_init() == NV_ERR_GENERIC);
        EXPECT(count == 0 && destroys == 1 && packages == 2 && unavailable == 0);
        failOperation = 0;
        EXPECT(os_registry_init() == NV_OK);
        EXPECT(s540GlobalRmCheckRegistryProfile() == NV_OK && count == 4);
    }
    for (stage = 2; stage <= 8; stage += 2) {
        reset();
        mismatchOperation = stage;
        EXPECT(os_registry_init() == NV_ERR_INVALID_STATE);
        EXPECT(count == 0 && destroys == 1 && unavailable == 0);
    }
    reset();
    failOperation = 3;
    failDestroy = NV_TRUE;
    EXPECT(os_registry_init() == NV_ERR_INVALID_STATE);
    EXPECT(unavailable == 1 && count != 0 && destroys == 1);
    reset();
    failOperation = 3;
    failPackage = 2;
    EXPECT(os_registry_init() == NV_ERR_INVALID_STATE);
    EXPECT(unavailable == 1 && count == 0 && destroys == 1);
    reset();
    failOperation = 3;
    retainAfterDestroy = NV_TRUE;
    EXPECT(os_registry_init() == NV_ERR_INVALID_STATE);
    EXPECT(unavailable == 1 && count != 0 && destroys == 1);
    reset();
    EXPECT(s540GlobalRmCheckRegistryProfile() == NV_ERR_GENERIC);
    EXPECT(count == 0 && writes == 0 && destroys == 0);

    printf("{\"format\":1,\"component\":\"nvidia-registry-profile\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"original_registry_abi_fixture\":true,\"failure_stages\":8,"
           "\"rollback_refusals\":3,\"execution\":\"native-user-space\","
           "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
#undef EXPECT
}
