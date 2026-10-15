// SPDX-License-Identifier: MIT
// Application adapter for NVIDIA's actual RS_STANDALONE library. This finite
// kernel-parameter profile deliberately provides no GPU classes/user pointers.
#include "resserv/resserv.h"
#include "resserv/rs_server.h"
#include "resserv/rs_client.h"
#include "resserv/rs_resource.h"
#include "resource_desc.h"
#include "S540NvidiaResourceExercise.h"
_Static_assert(sizeof(PORT_MEM_ALLOCATOR) == 40, "Existing NVPort allocator ABI");
_Static_assert(sizeof(NvLength) == 8 && sizeof(NvP64) == 8, "Intel NVPort scalar ABI");
#define S540_RESOURCE_CLASS 0x54000001U

struct API_STATE { RS_RES_ALLOC_PARAMS *params; };
static RS_RESOURCE_DESC s540Descriptors[2];

static void initDescriptors(void)
{
    portMemSet(s540Descriptors, 0, sizeof(s540Descriptors));
    s540Descriptors[0].externalClassId = NV01_ROOT;
    s540Descriptors[0].internalClassId = classId(RsClientResource);
    s540Descriptors[0].pClassInfo = classInfo(RsClientResource);
    s540Descriptors[0].bMultiInstance = NV_TRUE;
    s540Descriptors[0].bAnyParent = NV_TRUE;
    s540Descriptors[1].externalClassId = S540_RESOURCE_CLASS;
    s540Descriptors[1].internalClassId = classId(RsResource);
    s540Descriptors[1].pClassInfo = classInfo(RsResource);
    s540Descriptors[1].bMultiInstance = NV_TRUE;
    s540Descriptors[1].bAnyParent = NV_TRUE;
}

RS_RESOURCE_DESC *RsResInfoByExternalClassId(NvU32 id)
{
    if (id == NV01_ROOT) return &s540Descriptors[0];
    if (id == S540_RESOURCE_CLASS) return &s540Descriptors[1];
    return NULL;
}
NvU32 RsResInfoGetInternalClassId(const RS_RESOURCE_DESC *desc)
{ return desc == NULL ? 0 : desc->internalClassId; }

NV_STATUS resservClientFactory(PORT_MEM_ALLOCATOR *allocator,
    RS_RES_ALLOC_PARAMS *params, RsClient **out)
{
    if (allocator == NULL || params == NULL || out == NULL ||
        params->externalClassId != NV01_ROOT || params->pSecInfo == NULL ||
        params->pSecInfo->paramLocation != PARAM_LOCATION_KERNEL)
        return NV_ERR_INVALID_ARGUMENT;
    *out = NULL;
    return __nvoc_objCreate_RsClient(out, NULL, 0, allocator, params);
}

NV_STATUS resservResourceFactory(PORT_MEM_ALLOCATOR *allocator,
    CALL_CONTEXT *context, RS_RES_ALLOC_PARAMS *params, RsResource **out)
{
    (void)allocator; // NVOC owns its real object allocation and destructor path.
    if (context == NULL || params == NULL || out == NULL ||
        context->pResourceRef == NULL)
        return NV_ERR_INVALID_ARGUMENT;
    *out = NULL;
    if (params->externalClassId == NV01_ROOT)
    {
        RsClientResource *proxy = NULL;
        NV_STATUS status = __nvoc_objCreate_RsClientResource(&proxy, NULL, 0, context, params);
        if (status == NV_OK) *out = staticCast(proxy, RsResource);
        return status;
    }
    if (params->externalClassId == S540_RESOURCE_CLASS)
        return __nvoc_objCreate_RsResource(out, NULL, 0, context, params);
    return NV_ERR_INVALID_CLASS;
}

NV_STATUS serverAllocApiCopyIn(RsServer *server, RS_RES_ALLOC_PARAMS *params,
                              API_STATE **out)
{
    API_STATE *state;
    (void)server;
    if (out == NULL) return NV_ERR_INVALID_ARGUMENT;
    *out = NULL;
    // Only the actual parameterless base classes are exposed. An unknown class,
    // user pointer, mixed pointer, or nonzero payload is explicitly rejected.
    if (params == NULL || params->pSecInfo == NULL || params->pLockInfo == NULL ||
        params->pSecInfo->paramLocation != PARAM_LOCATION_KERNEL ||
        params->pAllocParams != NULL || params->paramsSize != 0)
        return NV_ERR_INVALID_ARGUMENT;
    if (RsResInfoByExternalClassId(params->externalClassId) == NULL)
        return NV_ERR_INVALID_CLASS;
    state = portMemAllocNonPaged(sizeof(*state));
    if (state == NULL) return NV_ERR_NO_MEMORY;
    state->params = params;
    *out = state;
    return NV_OK;
}
NV_STATUS serverAllocApiCopyOut(RsServer *server, NV_STATUS status, API_STATE *state)
{
    (void)server;
    if (state == NULL) return NV_ERR_INVALID_STATE;
    if (state->params == NULL && status == NV_OK) status = NV_ERR_INVALID_STATE;
    state->params = NULL;
    portMemFree(state);
    return status;
}

static void expect(S540_RESOURCE_RESULT *result, NvBool *group, NvBool condition)
{
    ++result->checks;
    if (!condition) { ++result->failures; *group = NV_FALSE; portDbgPrintf("ResourceServer checkpoint %u failed\n", result->checks); }
}
static NV_STATUS allocate(RsServer *server, API_SECURITY_INFO *security,
    NvHandle client, NvHandle parent, NvHandle requested, NvU32 classId,
    NvHandle *handle, RsClient **clientOut)
{
    RS_LOCK_INFO locks = {0};
    RS_RES_ALLOC_PARAMS params = {0};
    params.hClient = client; params.hParent = parent;
    params.hResource = requested; params.externalClassId = classId;
    params.pLockInfo = &locks; params.pSecInfo = security;
    NV_STATUS status = serverAllocResource(server, &params);
    if (handle) *handle = params.hResource;
    if (clientOut) *clientOut = params.pClient;
    return status;
}
static NV_STATUS release(RsServer *server, API_SECURITY_INFO *security,
                        NvHandle client, NvHandle handle)
{
    RS_LOCK_INFO locks = {0};
    RS_RES_FREE_PARAMS params = {0};
    params.hClient = client; params.hResource = handle;
    params.pLockInfo = &locks; params.pSecInfo = security;
    return serverFreeResourceTree(server, &params);
}

NvBool s540ResourceConstructorProbe(void)
{
    RsServer server = {0};
    initDescriptors();
    NV_STATUS status = serverConstruct(&server, RS_PRIV_LEVEL_KERNEL, 0);
    if (status != NV_OK)
        return !server.bConstructed && server.pAllocator == NULL &&
               server.pClientSortedList == NULL && server.pClientListLock == NULL &&
               server.pShareMapLock == NULL && server.pDisabledClientListLock == NULL &&
               server.pTopLock == NULL && server.pResLock == NULL;
    return serverDestruct(&server) == NV_OK && !server.bConstructed;
}

void s540ResourceExercise(S540_RESOURCE_RESULT *result)
{
    RsServer server = {0};
    API_SECURITY_INFO security = {0};
    NvHandle a = 0, b = 0, parent = 0, child = 0, other = 0;
    RsClient *clientA = NULL, *clientB = NULL;
    RsResourceRef *ref = NULL;
    NV_STATUS status;
    portMemSet(result, 0, sizeof(*result));
    result->server = result->clients = result->resources = result->sharing =
        result->control = result->cleanup = NV_TRUE;
    initDescriptors();
    security.privLevel = RS_PRIV_LEVEL_KERNEL;
    security.paramLocation = PARAM_LOCATION_KERNEL;
    status = serverConstruct(&server, RS_PRIV_LEVEL_KERNEL, 0);
    expect(result, &result->server, status == NV_OK && server.bConstructed);
    if (status != NV_OK) goto done;
    expect(result, &result->server, server.activeClientCount == 0 &&
        server.activeResourceCount == 0 && serverGetClientCount(&server) == 0);
    expect(result, &result->server,
        serverConstruct(&server, RS_PRIV_LEVEL_KERNEL, 0) == NV_ERR_INVALID_STATE);
    expect(result, &result->server, listCount(&server.defaultInheritedSharePolicyList) == 1 &&
        listCount(&server.globalInternalSharePolicyList) == 2);
    status = allocate(&server, &security, 0, 0, 0, NV01_ROOT, &a, NULL);
    expect(result, &result->clients, status == NV_OK && a != 0);
    if (status != NV_OK) goto destruct;
    expect(result, &result->clients, serverGetClientUnderLock(&server, a, &clientA) == NV_OK &&
        clientA != NULL && objDynamicCastById(staticCast(clientA, Dynamic), classId(RsClient)) != NULL);
    status = allocate(&server, &security, 0, 0, 0, NV01_ROOT, &b, NULL);
    expect(result, &result->clients, status == NV_OK && b != 0 && a != b);
    if (status != NV_OK) goto destruct;
    expect(result, &result->clients, serverGetClientUnderLock(&server, b, &clientB) == NV_OK &&
        clientB != NULL && clientA != clientB && server.activeClientCount == 2 &&
        serverGetClientCount(&server) == 2 && server.activeResourceCount == 2);
    expect(result, &result->clients, clientGetResourceRef(clientA, a, &ref) == NV_OK &&
        ref->pResource != NULL && dynamicCast(ref->pResource, RsClientResource) != NULL);
    expect(result, &result->clients,
        clientGetResourceRef(clientB, a, &ref) == NV_ERR_OBJECT_NOT_FOUND);
    status = allocate(&server, &security, a, a, 0, S540_RESOURCE_CLASS, &parent, NULL);
    expect(result, &result->resources, status == NV_OK && parent != 0 && parent != a);
    if (status != NV_OK) goto destruct;
    status = allocate(&server, &security, a, parent, 0, S540_RESOURCE_CLASS, &child, NULL);
    expect(result, &result->resources, status == NV_OK && child != 0 && child != parent);
    if (status != NV_OK) goto destruct;
    expect(result, &result->resources, clientGetResourceRef(clientA, child, &ref) == NV_OK &&
        ref->pParentRef != NULL && ref->pParentRef->hResource == parent && ref->depth == 2 &&
        ref->pResource != NULL && ref->internalClassId == classId(RsResource));
    expect(result, &result->resources, server.activeResourceCount == 4 &&
        mapCount(&clientA->resourceMap) == 3 && mapCount(&clientB->resourceMap) == 1);
    expect(result, &result->resources,
        allocate(&server, &security, a, a, child, S540_RESOURCE_CLASS, &other, NULL) != NV_OK &&
        server.activeResourceCount == 4);
    expect(result, &result->resources,
        allocate(&server, &security, b, a, 0, S540_RESOURCE_CLASS, &other, NULL) != NV_OK &&
        server.activeResourceCount == 4);
    expect(result, &result->resources,
        allocate(&server, &security, a, a, 0, 0x5400ffffU, &other, NULL) == NV_ERR_INVALID_CLASS &&
        server.activeResourceCount == 4);
    {
        RS_LOCK_INFO locks = {0};
        RS_SHARE_POLICY policy = {0};
        RS_RES_SHARE_PARAMS params = {0};
        policy.type = RS_SHARE_TYPE_ALL;
        RS_ACCESS_MASK_ADD(&policy.accessMask, RS_ACCESS_DUP_OBJECT);
        params.hClient = a; params.hResource = parent;
        params.pSharePolicy = &policy; params.pSecInfo = &security; params.pLockInfo = &locks;
        expect(result, &result->sharing, serverShareResourceAccess(&server, &params) == NV_OK && locks.state == 0);
        expect(result, &result->sharing, clientGetResourceRef(clientA, parent, &ref) == NV_OK &&
            ref->bSharePolicyListModified && listCount(&ref->sharePolicyList) == 1);
        policy.action = RS_SHARE_ACTION_FLAG_REVOKE;
        expect(result, &result->sharing, serverShareResourceAccess(&server, &params) == NV_OK &&
            listCount(&ref->sharePolicyList) == 0 && locks.state == 0);
        policy.type = RS_SHARE_TYPE_MAX;
        expect(result, &result->sharing, serverShareResourceAccess(&server, &params) == NV_ERR_INVALID_ARGUMENT);
    }
    {
        RS_LOCK_INFO locks = {0};
        RS_RES_DUP_PARAMS params = {0};
        params.hClientSrc = a; params.hResourceSrc = parent;
        params.hClientDst = b; params.hParentDst = b;
        params.pSecInfo = &security; params.pLockInfo = &locks;
        expect(result, &result->sharing, serverCopyResource(&server, &params) == NV_ERR_INVALID_ARGUMENT &&
            params.hResourceDst == 0 && locks.state == 0 && server.activeResourceCount == 4);
        expect(result, &result->sharing, clientGetResourceRef(clientA, parent, &ref) == NV_OK &&
            resCanCopy(ref->pResource) == NV_FALSE);
        NvBool duplicate = NV_FALSE;
        expect(result, &result->sharing,
            resIsDuplicate(ref->pResource, child, &duplicate) == NV_ERR_NOT_SUPPORTED);
    }
    {
        RS_LOCK_INFO locks = {0};
        RS_RES_CONTROL_PARAMS params = {0};
        params.hClient = a; params.hObject = parent; params.cmd = 0x54000000U;
        params.secInfo = security; params.pLockInfo = &locks;
        expect(result, &result->control, serverControl(&server, &params) == NV_ERR_NOT_SUPPORTED &&
            locks.state == 0 && server.activeResourceCount == 4);
        params.hClient = b;
        expect(result, &result->control, serverControl(&server, &params) != NV_OK && locks.state == 0);
    }
    expect(result, &result->resources, release(&server, &security, a, parent) == NV_OK &&
        server.activeResourceCount == 2 && mapCount(&clientA->resourceMap) == 1);
    expect(result, &result->resources, clientGetResourceRef(clientA, child, &ref) != NV_OK &&
        clientGetResourceRef(clientA, parent, &ref) != NV_OK);
    expect(result, &result->resources, release(&server, &security, a, parent) == NV_OK &&
        server.activeResourceCount == 2);
    expect(result, &result->clients, release(&server, &security, a, a) == NV_OK &&
        server.activeClientCount == 1 && server.activeResourceCount == 1);
    expect(result, &result->clients, release(&server, &security, b, b) == NV_OK &&
        server.activeClientCount == 0 && server.activeResourceCount == 0);
    // Destruction also owns recursive cleanup when clients are still present.
    expect(result, &result->cleanup,
        allocate(&server, &security, 0, 0, 0, NV01_ROOT, &a, NULL) == NV_OK);
    expect(result, &result->cleanup,
        allocate(&server, &security, a, a, 0, S540_RESOURCE_CLASS, &parent, NULL) == NV_OK);
destruct:
    expect(result, &result->cleanup, serverDestruct(&server) == NV_OK && !server.bConstructed);
    expect(result, &result->cleanup, serverDestruct(&server) == NV_ERR_INVALID_OBJECT);
done:
    return;
}
