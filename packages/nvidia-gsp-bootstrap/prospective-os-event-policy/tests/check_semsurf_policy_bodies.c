/* SPDX-License-Identifier: MIT */
/* Full source controls with explicit CPU waiter/refcount fixtures. */
#include "nvtypes.h"
#include "nvstatus.h"
#include "ctrl/ctrl00da.h"
#undef memset
#undef memcpy
#undef memcmp
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum { PARAM_LOCATION_KERNEL = 1 };
typedef struct RsClient { NvHandle hClient; } RsClient;
typedef struct { struct { NvU32 paramLocation; } secInfo; RsClient *pClient; } CALL_CONTEXT;
typedef struct { NvU64 bytes; } Shared;
typedef struct { Shared *pShared; RsClient *client; NvHandle handle; } SemaphoreSurface;
static CALL_CONTEXT context;
static struct { NvU32 validations, conversions, refcount, releases, allocations,
    live, adds, deletes; NvBool validIndex; NV_STATUS conversionStatus, addStatus;
    void *waiter; NvBool waiterOwnsOsRef; NvP64 lastNotification; NvBool lastKernel; } stats;
#define NV_CHECK_OR_RETURN(level, condition, status) do { if (!(condition)) return status; } while (0)
#define NV_PRINTF(...) ((void)0)
#define staticCast(pointer, type) ((type *)(pointer))
#define RES_GET_CLIENT(surface) ((surface)->client)
#define RES_GET_HANDLE(surface) ((surface)->handle)
static CALL_CONTEXT *resservGetTlsCallContext(void) { return &context; }
static NvBool _semsurfValidateIndex(Shared *shared, NvU64 index)
{ (void)shared; (void)index; ++stats.validations; return stats.validIndex; }
static NV_STATUS osUserHandleToKernelPtr(NvHandle client, NvP64 input, NvP64 *out)
{
    (void)client; ++stats.conversions;
    if (stats.conversionStatus != NV_OK) return stats.conversionStatus;
    *out = input; ++stats.refcount; return NV_OK;
}
static NV_STATUS osDereferenceObjectCount(void *event)
{ (void)event; if (!stats.refcount) abort(); --stats.refcount; ++stats.releases; return NV_OK; }
static NV_STATUS _semsurfAddWaiter(SemaphoreSurface *surface, RsClient *client,
    NvHandle handle, NvU64 index, NvU64 wait, NvU64 next, NvP64 notification, NvBool kernel)
{
    (void)surface; (void)client; (void)handle; (void)index; (void)wait; (void)next;
    ++stats.adds; stats.lastNotification = notification; stats.lastKernel = kernel;
    if (stats.addStatus != NV_OK) return stats.addStatus;
    if (stats.waiter) abort(); stats.waiter = malloc(32);
    if (!stats.waiter) return NV_ERR_NO_MEMORY;
    ++stats.allocations; ++stats.live; stats.waiterOwnsOsRef = !kernel && notification != 0;
    return NV_OK;
}
static NV_STATUS _semsurfDelWaiter(SemaphoreSurface *surface, NvU64 index,
    NvU64 wait, NvP64 notification, NvBool kernel)
{
    (void)surface; (void)index; (void)wait; ++stats.deletes;
    stats.lastNotification = notification; stats.lastKernel = kernel;
    if (!stats.waiter) return NV_ERR_OBJECT_NOT_FOUND;
    free(stats.waiter); stats.waiter = NULL; --stats.live;
    if (stats.waiterOwnsOsRef) osDereferenceObjectCount(NULL);
    stats.waiterOwnsOsRef = NV_FALSE; return NV_OK;
}
#include "semsurf_policy_bodies.h"
static NvU32 checks;
#define EXPECT(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "Semaphore policy check failed line%d\n", __LINE__); return 1; } } while (0)
static void reset(void)
{ if (stats.live || stats.refcount || stats.waiter) abort(); memset(&stats, 0, sizeof(stats)); stats.validIndex = NV_TRUE; }
int main(void)
{
    RsClient client = {.hClient = 42}; Shared shared = {.bytes = 8};
    SemaphoreSurface surface = {.pShared = &shared, .client = &client, .handle = 7};
    NV_SEMAPHORE_SURFACE_CTRL_REGISTER_WAITER_PARAMS reg = {
        .index = 1, .waitValue = 4, .newValue = 8, .notificationHandle = 0x1234};
    NV_SEMAPHORE_SURFACE_CTRL_UNREGISTER_WAITER_PARAMS unreg = {
        .index = 1, .waitValue = 4, .notificationHandle = 0x1234};
    NV_SEMAPHORE_SURFACE_CTRL_REGISTER_WAITER_PARAMS oldReg = reg;
    NV_SEMAPHORE_SURFACE_CTRL_UNREGISTER_WAITER_PARAMS oldUnreg = unreg;
    context.pClient = &client; context.secInfo.paramLocation = 0;
    reset();
    EXPECT(proposed_semsurfCtrlCmdRegisterWaiter_IMPL(&surface, &reg) == NV_ERR_NOT_SUPPORTED);
    EXPECT(stats.validations == 1 && !stats.conversions && !stats.adds && !stats.allocations && !stats.refcount);
    EXPECT(!memcmp(&reg, &oldReg, sizeof(reg)) && shared.bytes == 8);
    EXPECT(proposed_semsurfCtrlCmdUnregisterWaiter_IMPL(&surface, &unreg) == NV_ERR_NOT_SUPPORTED);
    EXPECT(stats.validations == 2 && !stats.conversions && !stats.deletes && !stats.releases && !stats.live);
    EXPECT(!memcmp(&unreg, &oldUnreg, sizeof(unreg)) && shared.bytes == 8);
    reset(); stats.validIndex = NV_FALSE;
    EXPECT(proposed_semsurfCtrlCmdRegisterWaiter_IMPL(&surface, &reg) == NV_ERR_INVALID_INDEX);
    EXPECT(proposed_semsurfCtrlCmdUnregisterWaiter_IMPL(&surface, &unreg) == NV_ERR_INVALID_INDEX);
    EXPECT(!stats.conversions && !stats.adds && !stats.deletes && !stats.allocations);
    reset();
    EXPECT(baseline_semsurfCtrlCmdRegisterWaiter_IMPL(&surface, &reg) == NV_OK);
    EXPECT(stats.conversions == 1 && stats.adds == 1 && stats.allocations == 1 && stats.live == 1 && stats.refcount == 1);
    EXPECT(stats.waiterOwnsOsRef && !stats.lastKernel && stats.lastNotification == (NvP64)reg.notificationHandle);
    EXPECT(baseline_semsurfCtrlCmdUnregisterWaiter_IMPL(&surface, &unreg) == NV_OK);
    EXPECT(stats.conversions == 2 && stats.deletes == 1 && !stats.live && !stats.refcount && stats.releases == 2);
    reset(); stats.addStatus = NV_ERR_NO_MEMORY;
    EXPECT(baseline_semsurfCtrlCmdRegisterWaiter_IMPL(&surface, &reg) == NV_ERR_NO_MEMORY);
    EXPECT(stats.conversions == 1 && stats.adds == 1 && stats.releases == 1 && !stats.live && !stats.refcount);
    reset(); stats.conversionStatus = NV_ERR_INVALID_EVENT;
    EXPECT(baseline_semsurfCtrlCmdRegisterWaiter_IMPL(&surface, &reg) == NV_ERR_INVALID_EVENT);
    EXPECT(!stats.adds && !stats.allocations && !stats.refcount && !stats.releases);
    reset(); context.secInfo.paramLocation = PARAM_LOCATION_KERNEL;
    EXPECT(proposed_semsurfCtrlCmdRegisterWaiter_IMPL(&surface, &reg) == NV_OK);
    EXPECT(stats.lastKernel && stats.lastNotification == (NvP64)reg.notificationHandle && !stats.conversions);
    EXPECT(stats.live == 1 && stats.allocations == 1 && !stats.refcount);
    EXPECT(proposed_semsurfCtrlCmdUnregisterWaiter_IMPL(&surface, &unreg) == NV_OK);
    EXPECT(!stats.live && !stats.refcount && !stats.conversions && stats.deletes == 1);
    reset(); context.secInfo.paramLocation = 0; reg.notificationHandle = unreg.notificationHandle = 0;
    EXPECT(proposed_semsurfCtrlCmdRegisterWaiter_IMPL(&surface, &reg) == NV_OK);
    EXPECT(!stats.lastKernel && !stats.lastNotification && !stats.conversions && stats.live == 1);
    EXPECT(proposed_semsurfCtrlCmdUnregisterWaiter_IMPL(&surface, &unreg) == NV_OK);
    EXPECT(!stats.live && !stats.refcount && !stats.conversions && !stats.releases);
    EXPECT(shared.bytes == 8);
    printf("{\"format\":1,\"component\":\"nvidia-os-event-semsurf-policy\",\"status\":\"passed\","
        "\"checks\":%u,\"failures\":0,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"complete_source_bodies\":4,\"private_types_and_resource_helpers\":\"explicit-cpu-fixtures\","
        "\"baseline_os_event_acquisition_observed\":true,\"kernel_waiters_preserved\":true}\n", checks);
    return 0;
}
