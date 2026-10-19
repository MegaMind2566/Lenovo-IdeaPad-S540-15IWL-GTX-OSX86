/* SPDX-License-Identifier: MIT */
/* Complete original/proposed constructor bodies, explicit CPU resource fixture.
 * Private structures below are fixtures; separate full-TU compilation verifies
 * the actual original types. No original RM runtime or GPU is emulated.
 */
#include "nvtypes.h"
#include "nvstatus.h"
#include "nvos.h"
#include "class/cl0000.h"
#include "class/cl0005.h"
#undef memset
#undef memcpy
#undef memcmp
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { RS_PRIV_LEVEL_USER_ROOT = 1, RS_PRIV_LEVEL_KERNEL = 3,
    classid_KernelHostVgpuDeviceApi = 1, classid_ContextDma = 2 };
typedef NvU32 RS_PRIV_LEVEL;
typedef struct RsResourceRef { NvU32 externalClassId, internalClassId;
    NvHandle hResource; struct RsResourceRef *pParentRef; } RsResourceRef;
typedef struct RsClient { NvHandle hClient; } RsClient;
typedef struct { RS_PRIV_LEVEL privLevel; } SecInfo;
typedef struct { RsClient *pClient; RsResourceRef *pResourceRef; } CALL_CONTEXT;
typedef struct { void *pAllocParams; SecInfo *pSecInfo; } RS_RES_ALLOC_PARAMS_INTERNAL;
typedef struct OBJGPU { NvU32 unused; } OBJGPU;
typedef struct EVENTNOTIFICATION { NvU32 type; NvP64 data; } EVENTNOTIFICATION;
typedef EVENTNOTIFICATION *PEVENTNOTIFICATION;
typedef struct EventApi { NvHandle hNotifierClient, hNotifierResource;
    void *owned; NvBool userReference; } EventApi;
static struct { NvU32 clientLookups, initCalls, allocations, live, conversions,
    refcount, releases, registrations, destructs, rpcCalls; NV_STATUS conversionStatus;
    NvU32 lastType; NvP64 lastData; NvHandle lastParent; } stats;
static EVENTNOTIFICATION *notification;
static RsResourceRef clientRef;

#define classId(x) classid_##x
#define NV_ASSERT_OK_OR_RETURN(expr) do { NV_STATUS result_ = (expr); \
    if (result_ != NV_OK) return result_; } while (0)
#define IS_FW_CLIENT(gpu) ((void)(gpu), NV_FALSE)
#define IS_VIRTUAL_WITHOUT_SRIOV(gpu) ((void)(gpu), NV_FALSE)
#define IS_VIRTUAL_WITH_SRIOV(gpu) ((void)(gpu), NV_FALSE)
#define NV_RM_RPC_ALLOC_EVENT(gpu, client, notifier, channel, resource, event, type, index, status) \
    do { (void)(channel); ++stats.rpcCalls; } while (0)
#define NV_PRINTF(...) ((void)0)
static NvBool _eventRpcForType(NvHandle client, NvHandle resource)
{ (void)client; (void)resource; return NV_FALSE; }
static NV_STATUS serverutilGetResourceRef(NvHandle client, NvHandle resource, RsResourceRef **out)
{ (void)client; (void)resource; *out = &clientRef; return NV_OK; }
static OBJGPU *CliGetGpuFromContext(RsResourceRef *ref, void *unused)
{ (void)ref; (void)unused; return NULL; }
static NV_STATUS clientGetResourceRef(RsClient *client, NvHandle resource, RsResourceRef **out)
{ (void)client; (void)resource; ++stats.clientLookups; *out = &clientRef; return NV_OK; }
static NV_STATUS eventapiInit(EventApi *event, CALL_CONTEXT *context,
    NvHandle parent, NvHandle source, PEVENTNOTIFICATION **out)
{
    (void)context; (void)source; ++stats.initCalls;
    event->owned = calloc(1, sizeof(EVENTNOTIFICATION));
    if (!event->owned) return NV_ERR_NO_MEMORY;
    ++stats.allocations; ++stats.live; stats.lastParent = parent;
    event->hNotifierClient = parent; event->hNotifierResource = source;
    notification = event->owned; *out = &notification; return NV_OK;
}
static NV_STATUS osUserHandleToKernelPtr(NvHandle client, NvP64 input, NvP64 *out)
{
    (void)client; ++stats.conversions;
    if (stats.conversionStatus != NV_OK) return stats.conversionStatus;
    *out = input; ++stats.refcount; return NV_OK;
}
static NV_STATUS osDereferenceObjectCount(void *value)
{ (void)value; if (!stats.refcount) abort(); --stats.refcount; ++stats.releases; return NV_OK; }
static NV_STATUS registerEventNotification(PEVENTNOTIFICATION *list, RsClient *client,
    NvHandle notifier, NvHandle event, NvU32 index, NvU32 type, NvP64 data, NvBool user)
{
    (void)client; (void)notifier; (void)event; (void)index;
    ++stats.registrations; stats.lastType = type; stats.lastData = data;
    (*list)->type = type; (*list)->data = data;
    /* Fixture owns the allocation; a real successfully converted reference is
     * transferred to the notification until the fixture destructs it. */
    (void)user; return NV_OK;
}
static void eventapiDestruct_IMPL(EventApi *event)
{
    ++stats.destructs;
    if (event->owned) { free(event->owned); event->owned = NULL; --stats.live; }
    if (event->userReference) { osDereferenceObjectCount(NULL); event->userReference = NV_FALSE; }
}
#include "eventapi_policy_bodies.h"

static NvU32 checks;
#define EXPECT(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "EventApi policy check failed line%d\n", __LINE__); return 1; } } while (0)
static void reset(void) { if (stats.live || stats.refcount) abort(); memset(&stats, 0, sizeof(stats)); }
int main(void)
{
    RsClient client = {.hClient = 42};
    RsResourceRef ref = {.externalClassId = NV01_EVENT_OS_EVENT, .hResource = 7};
    CALL_CONTEXT context = {.pClient = &client, .pResourceRef = &ref};
    SecInfo sec = {.privLevel = RS_PRIV_LEVEL_USER_ROOT};
    NV0005_ALLOC_PARAMETERS parameters = {.hParentClient = 0, .hSrcResource = 6,
        .hClass = NV01_EVENT_OS_EVENT, .data = (NvP64)(NvUPtr)0x1234};
    RS_RES_ALLOC_PARAMS_INTERNAL params = {.pAllocParams = &parameters, .pSecInfo = &sec};
    EventApi event = {0}, before;
    NV0005_ALLOC_PARAMETERS saved;
    for (NvU32 privilege = RS_PRIV_LEVEL_USER_ROOT; privilege <= RS_PRIV_LEVEL_KERNEL; privilege += 2) {
        reset(); sec.privLevel = privilege; before = event; saved = parameters;
        EXPECT(proposed_eventapiConstruct_IMPL(&event, &context, &params) == NV_ERR_NOT_SUPPORTED);
        EXPECT(!memcmp(&event, &before, sizeof(event)) && !memcmp(&parameters, &saved, sizeof(saved)));
        EXPECT(!stats.clientLookups && !stats.initCalls && !stats.allocations && !stats.live);
        EXPECT(!stats.conversions && !stats.refcount && !stats.registrations && !stats.destructs && !stats.rpcCalls);
    }
    reset(); sec.privLevel = RS_PRIV_LEVEL_USER_ROOT;
    EXPECT(baseline_eventapiConstruct_IMPL(&event, &context, &params) == NV_OK);
    EXPECT(stats.allocations == 1 && stats.live == 1 && stats.conversions == 1 && stats.refcount == 1);
    EXPECT(stats.registrations == 1 && stats.lastType == NV01_EVENT_OS_EVENT && stats.lastParent == client.hClient);
    event.userReference = NV_TRUE; eventapiDestruct_IMPL(&event);
    EXPECT(!stats.live && !stats.refcount && stats.releases == 1);
    reset(); sec.privLevel = RS_PRIV_LEVEL_KERNEL;
    EXPECT(baseline_eventapiConstruct_IMPL(&event, &context, &params) == NV_OK);
    EXPECT(stats.allocations == 1 && stats.live == 1 && !stats.conversions && !stats.refcount);
    eventapiDestruct_IMPL(&event); EXPECT(!stats.live);
    reset(); sec.privLevel = RS_PRIV_LEVEL_USER_ROOT; stats.conversionStatus = NV_ERR_INVALID_EVENT;
    EXPECT(baseline_eventapiConstruct_IMPL(&event, &context, &params) == NV_ERR_INVALID_EVENT);
    EXPECT(stats.allocations == 1 && stats.destructs == 1 && !stats.live && !stats.refcount);
    EXPECT(stats.conversions == 1 && !stats.registrations && !stats.releases);
    for (NvU32 which = 0; which != 2; ++which) {
        reset(); sec.privLevel = RS_PRIV_LEVEL_KERNEL;
        ref.externalClassId = which ? NV01_EVENT_KERNEL_CALLBACK_EX : NV01_EVENT_KERNEL_CALLBACK;
        parameters.hClass = ref.externalClassId;
        EXPECT(proposed_eventapiConstruct_IMPL(&event, &context, &params) == NV_OK);
        EXPECT(stats.allocations == 1 && stats.live == 1 && stats.registrations == 1);
        EXPECT(stats.lastType == ref.externalClassId && stats.lastData == parameters.data && !stats.conversions);
        eventapiDestruct_IMPL(&event); EXPECT(!stats.live && !stats.refcount);
        reset(); sec.privLevel = RS_PRIV_LEVEL_USER_ROOT; before = event;
        EXPECT(proposed_eventapiConstruct_IMPL(&event, &context, &params) == NV_ERR_ILLEGAL_ACTION);
        EXPECT(!stats.allocations && !stats.registrations && !memcmp(&event, &before, sizeof(event)));
    }
    EXPECT(!stats.rpcCalls && !stats.live && !stats.refcount);
    printf("{\"format\":1,\"component\":\"nvidia-os-event-api-policy\",\"status\":\"passed\","
        "\"checks\":%u,\"failures\":0,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\","
        "\"gpu_access\":false,\"complete_source_bodies\":2,\"private_types_and_resource_helpers\":\"explicit-cpu-fixtures\","
        "\"baseline_os_event_acquisition_observed\":true,\"kernel_callback_allocation_preserved\":true}\n", checks);
    return 0;
}
