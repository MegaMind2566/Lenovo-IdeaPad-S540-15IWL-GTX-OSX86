/* SPDX-License-Identifier: MIT
 * Native CPU control for two complete source-extracted constructor bodies.
 * Public 0x90cd parameters and producer helpers are original NVIDIA code.
 * Private resource types, mapping, descriptor allocation and destruction below
 * are explicit CPU fixtures, not an NVOC ABI or GPU/OS-event implementation.
 */
#include "nvtypes.h"
#include "nvstatus.h"
#include "class/cl90cd.h"
#include "eventbufferproducer.h"
/* Host fixture bookkeeping uses libc, outside the original RM namespace. */
#undef memset
#undef memcpy
#undef memcmp
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef KERNEL
#error "EventBuffer policy fixtures must never enter a kernel image"
#endif

enum { FIXTURE_CLIENT=1, FIXTURE_MEMORY=2, RS_PRIV_LEVEL_KERNEL=2,
    NV01_MEMORY_DEVICELESS=0x90ad, RMAPI_GPU_LOCK_INTERNAL=1,
    PDB_PROP_SYS_INTERNAL_EVENT_BUFFER_ALLOC_ALLOWED=1,
    NV_PROTECT_READ_WRITE=3, NV_PROTECT_READABLE=1,
    MEMDESC_FLAGS_USER_READ_ONLY=1,
    fixtureFlag__ACCESS__READ_ONLY=1, fixtureFlag__ACCESS__READ_WRITE=2,
    fixtureFlag__ALLOW_MAPPING_ON_HCC__YES=4 };
typedef struct Counters {
    unsigned casts, privileges, properties, references, maps, dependencies;
    unsigned allocAttempts, allocations, frees, live, userMaps, destructs, conversions;
    unsigned deviceMaps, unsupportedDeviceServices;
} Counters;
static Counters count;
static unsigned checks, failAllocAt, failUserMapAt;
#define CHECK(x) do { ++checks; assert(x); } while (0)
#define NV_ASSERT_OR_RETURN(x,s) do { if (!(x)) return (s); } while (0)
#define NV_PRINTF(...) ((void)0)
#define FLD_SET_DRF(p,r,f,v,old) ((old) | fixtureFlag_##f##_##v)
#define RMCFG_FEATURE_PLATFORM_GSP 0

typedef struct MEMORY_DESCRIPTOR { void *bytes; NvU64 length; NvU32 flags; } MEMORY_DESCRIPTOR;
typedef struct Memory {
    NvU32 fixtureKind; MEMORY_DESCRIPTOR *pMemDesc; NvU64 Length;
    NvP64 KernelVAddr; NvHandle handle;
} Memory;
typedef struct RmClient { NvU32 fixtureKind; NvHandle hClient; NvU32 privilege; } RmClient;
typedef struct RsResourceRef { NvU32 externalClassId; void *pResource; unsigned dependencies; } RsResourceRef;
typedef struct KernelBus { int unused; } KernelBus;
typedef struct OBJGPU { KernelBus *bus; NvBool isVirtual; } OBJGPU;
typedef struct Subdevice { NvU32 subDeviceInst; OBJGPU *gpu; NvHandle parent; } Subdevice;
typedef struct CALL_CONTEXT { RmClient *pClient; RsResourceRef *pResourceRef; } CALL_CONTEXT;
typedef struct RS_RES_ALLOC_PARAMS_INTERNAL { void *pAllocParams; } RS_RES_ALLOC_PARAMS_INTERNAL;
typedef struct EVENT_BUFFER_MAP_INFO {
    NvP64 headerAddr, headerPriv, recordBuffAddr, recordBuffPriv, vardataBuffAddr, vardataBuffPriv;
} EVENT_BUFFER_MAP_INFO;
typedef struct EventBuffer {
    NvHandle hClient, hSubDevice, hInternalClient, hInternalDevice, hInternalSubdevice;
    NvU32 subDeviceInst;
    EVENT_BUFFER_MAP_INFO kernelMapInfo, clientMapInfo;
    Memory *pHeader, *pRecord, *pVardata;
    MEMORY_DESCRIPTOR *pHeaderDesc, *pRecordBufDesc, *pVardataBufDesc;
    EVENT_BUFFER_PRODUCER_INFO producerInfo;
} EventBuffer;
typedef struct OBJSYS { NvBool (*getProperty)(struct OBJSYS *, unsigned); } OBJSYS;
typedef struct RM_API RM_API;
struct RM_API {
    NV_STATUS (*DupObject)(RM_API *, NvHandle, NvHandle, NvHandle *, NvHandle, NvHandle, NvU32);
    NV_STATUS (*MapToCpu)(RM_API *, NvHandle, NvHandle, NvHandle, NvU64, NvU64, NvP64 *, NvU32);
};
static RsResourceRef resources[3];
static MEMORY_DESCRIPTOR backing[3];
static Memory memory[3];
static OBJGPU gpu;
static Subdevice subdevice;
static void *fixtureCast(void *p, NvU32 kind) {
    ++count.casts;
    return p && *(NvU32 *)p==kind ? p : NULL;
}
#define fixtureKind_RmClient FIXTURE_CLIENT
#define fixtureKind_Memory FIXTURE_MEMORY
#define dynamicCast(p,type) ((type *)fixtureCast((p),fixtureKind_##type))
#define GPU_RES_GET_GPU(p) ((p)->gpu)
#define GPU_GET_KERNEL_BUS(p) ((p)->bus)
#define IS_VIRTUAL_WITHOUT_SRIOV(p) ((p)->isVirtual)
#define RES_GET_PARENT_HANDLE(p) ((p)->parent)
#define RES_GET_HANDLE(p) ((p)->handle)
static NvU32 rmclientGetCachedPrivilege(RmClient *p) { ++count.privileges; return p->privilege; }
static NvBool property(OBJSYS *p, unsigned name) {
    assert(p && name==PDB_PROP_SYS_INTERNAL_EVENT_BUFFER_ALLOC_ALLOWED);
    ++count.properties; return NV_TRUE;
}
static OBJSYS systemObject={property};
#define SYS_GET_INSTANCE() (&systemObject)
static NV_STATUS clientGetResourceRef(RmClient *p, NvHandle h, RsResourceRef **out) {
    assert(p); ++count.references;
    if (h<1 || h>3) return NV_ERR_INVALID_OBJECT_HANDLE;
    *out=&resources[h-1]; return NV_OK;
}
static NV_STATUS subdeviceGetByHandle(RmClient *p, NvHandle h, Subdevice **out) {
    assert(p && out);
    if (h!=10) return NV_ERR_INVALID_OBJECT_HANDLE;
    *out=&subdevice; return NV_OK;
}
static NvBool portSafeMulU32(NvU32 a, NvU32 b, NvU32 *out) {
    NvU64 v=(NvU64)a*b; if (v>0xffffffffULL) return NV_FALSE; *out=(NvU32)v; return NV_TRUE;
}
static NvBool memdescGetFlag(MEMORY_DESCRIPTOR *p, NvU32 flag) { return !!(p->flags&flag); }
static NvBool kbusIsBarAccessBlocked(KernelBus *p) { assert(p); return NV_FALSE; }
static NvBool gpuIsCCDevToolsModeEnabled(OBJGPU *p) { assert(p); return NV_FALSE; }
static void refAddDependant(RsResourceRef *p, RsResourceRef *dependent) {
    assert(p && dependent); ++p->dependencies; ++count.dependencies;
}
static NV_STATUS memCreateKernelMapping(Memory *p, NvU32 protect, NvBool all) {
    assert(p && p->pMemDesc && p->pMemDesc->bytes && protect==NV_PROTECT_READ_WRITE && all);
    ++count.maps; p->KernelVAddr=(NvP64)(NvUPtr)p->pMemDesc->bytes; return NV_OK;
}
static NV_STATUS _eventBufferMapExternalBacking(Memory *p, CALL_CONTEXT *ctx,
    NvHandle mapperClient, NvHandle mapperDevice, NvBool kernel, NvBool staging,
    NvU32 flags, NvP64 *out) {
    assert(p && ctx && kernel && !staging && mapperClient==ctx->pClient->hClient);
    assert(mapperDevice==subdevice.parent && flags==fixtureFlag__ACCESS__READ_WRITE);
    assert(p->pMemDesc && p->pMemDesc->bytes);
    ++count.deviceMaps; ++count.maps; *out=(NvP64)(NvUPtr)p->pMemDesc->bytes; return NV_OK;
}
static NV_STATUS _mapExternalSysmemToKernelOnGsp(Memory *p,NvU32 protect,NvP64 *out) {
    (void)p;(void)protect;(void)out; ++count.unsupportedDeviceServices; return NV_ERR_NOT_SUPPORTED;
}
static RM_API *rmapiGetInterface(unsigned mode) {
    (void)mode; ++count.unsupportedDeviceServices; assert(!"unexpected fixture RM API path"); return NULL;
}
static NV_STATUS rmapiutilAllocClientAndDeviceHandles(RM_API *api, OBJGPU *p,
    NvHandle *a,NvHandle *b,NvHandle *c) {
    (void)api;(void)p;(void)a;(void)b;(void)c;
    ++count.unsupportedDeviceServices; return NV_ERR_NOT_SUPPORTED;
}
static NV_STATUS _allocAndMapMemory(CALL_CONTEXT *ctx, NvP64 address,
    MEMORY_DESCRIPTOR **out, NvU64 bytes, NvP64 *mapped, NvP64 *priv, Subdevice *sub) {
    assert(ctx && !address && out && !*out && bytes && !sub);
    ++count.allocAttempts;
    if (failAllocAt==count.allocAttempts) return NV_ERR_NO_MEMORY;
    MEMORY_DESCRIPTOR *descriptor=calloc(1,sizeof(*descriptor));
    if (!descriptor) return NV_ERR_NO_MEMORY;
    descriptor->bytes=calloc(1,(size_t)bytes);
    if (!descriptor->bytes) { free(descriptor); return NV_ERR_NO_MEMORY; }
    descriptor->length=bytes;
    *out=descriptor; *mapped=(NvP64)(NvUPtr)descriptor->bytes; *priv=(NvP64)(NvUPtr)descriptor;
    ++count.allocations; ++count.live; ++count.maps; return NV_OK;
}
static NV_STATUS _createInternalUserMapping(MEMORY_DESCRIPTOR *p, NvU64 bytes,
    NvBool kernel, NvP64 *returned, NvP64 *address, NvP64 *priv) {
    assert(p && p->bytes && bytes==p->length && returned && address && priv);
    (void)kernel; /* CPU fixture aliases; no user VM mapping is claimed. */
    ++count.userMaps;
    if (failUserMapAt==count.userMaps) return NV_ERR_INSUFFICIENT_RESOURCES;
    *returned=*address=(NvP64)(NvUPtr)p->bytes; *priv=(NvP64)(NvUPtr)p; return NV_OK;
}
static NV_STATUS osUserHandleToKernelPtr(NvHandle h,NvP64 user,NvP64 *out) {
    assert(h && user && out); ++count.conversions;
    /* Actual OS conversion is deliberately unavailable in this CPU fixture. */
    return NV_ERR_NOT_SUPPORTED;
}
static void destroyDescriptor(MEMORY_DESCRIPTOR **slot) {
    if (!*slot) return;
    assert(count.live && (*slot)->bytes);
    free((*slot)->bytes); free(*slot); *slot=NULL;
    ++count.frees; --count.live;
}
static void eventbufferDestruct_IMPL(EventBuffer *p) {
    ++count.destructs;
    destroyDescriptor(&p->pHeaderDesc); destroyDescriptor(&p->pRecordBufDesc);
    destroyDescriptor(&p->pVardataBufDesc);
    for (unsigned i=0;i!=3;++i) resources[i].dependencies=0;
    memset(&p->kernelMapInfo,0,sizeof(p->kernelMapInfo));
    memset(&p->clientMapInfo,0,sizeof(p->clientMapInfo));
}

#include "eventbuffer_policy_bodies.h"

typedef NV_STATUS (*Constructor)(EventBuffer *,CALL_CONTEXT *,RS_RES_ALLOC_PARAMS_INTERNAL *);
static Constructor constructors[2]={baseline_eventbufferConstruct_IMPL,proposed_eventbufferConstruct_IMPL};
static RmClient client;
static RsResourceRef objectRef;
static CALL_CONTEXT context;
static void reset(NvBool kernel) {
    assert(!count.live);
    memset(&count,0,sizeof(count));failAllocAt=failUserMapAt=0;
    client=(RmClient){FIXTURE_CLIENT,0x20,kernel ? RS_PRIV_LEVEL_KERNEL : 0};
    objectRef=(RsResourceRef){0};context=(CALL_CONTEXT){&client,&objectRef};
    gpu=(OBJGPU){0};subdevice=(Subdevice){3,&gpu,0x30};
    for (unsigned i=0;i!=3;++i) {
        backing[i]=(MEMORY_DESCRIPTOR){calloc(1,128),128,MEMDESC_FLAGS_USER_READ_ONLY};
        assert(backing[i].bytes);
        memory[i]=(Memory){FIXTURE_MEMORY,&backing[i],128,0,i+1};
        resources[i]=(RsResourceRef){NV01_MEMORY_DEVICELESS,&memory[i],0};
    }
}
static void finish(void) {
    CHECK(count.live==0 && count.allocations==count.frees);
    for (unsigned i=0;i!=3;++i) { free(backing[i].bytes);backing[i].bytes=NULL; }
}
static NV_EVENT_BUFFER_ALLOC_PARAMETERS params(NvBool external,NvBool vardata) {
    NV_EVENT_BUFFER_ALLOC_PARAMETERS p;
    memset(&p,0,sizeof(p));p.recordSize=16;p.recordCount=4;p.recordsFreeThreshold=1;
    if (external) { p.hBufferHeader=1;p.hRecordBuffer=2; }
    if (vardata) { p.vardataBufferSize=64;p.vardataFreeThreshold=8;if(external)p.hVardataBuffer=3; }
    return p;
}
static void refusal(NvBool kernel,NvBool external) {
    reset(kernel);
    EventBuffer object, saved; memset(&object,0xa5,sizeof(object));saved=object;
    NV_EVENT_BUFFER_ALLOC_PARAMETERS p=params(external,NV_TRUE);
    p.notificationHandle=0x55;p.bufferHeader=(NvP64)(NvUPtr)11;
    p.recordBuffer=(NvP64)(NvUPtr)12;p.vardataBuffer=(NvP64)(NvUPtr)13;
    const NV_EVENT_BUFFER_ALLOC_PARAMETERS original=p;
    Counters before=count;RS_RES_ALLOC_PARAMS_INTERNAL alloc={&p};
    CHECK(proposed_eventbufferConstruct_IMPL(&object,&context,&alloc)==NV_ERR_NOT_SUPPORTED);
    CHECK(memcmp(&p,&original,sizeof(p))==0);
    CHECK(memcmp(&object,&saved,sizeof(object))==0);
    CHECK(memcmp(&count,&before,sizeof(count))==0);
    CHECK(!resources[0].dependencies && !resources[1].dependencies && !resources[2].dependencies);
    finish();
}
static void baselineNonzero(NvBool kernel,NvBool external) {
    reset(kernel);EventBuffer object={0};
    NV_EVENT_BUFFER_ALLOC_PARAMETERS p=params(external,NV_TRUE);
    p.notificationHandle=0x55;RS_RES_ALLOC_PARAMS_INTERNAL alloc={&p};
    NV_STATUS status=baseline_eventbufferConstruct_IMPL(&object,&context,&alloc);
    CHECK(status==(kernel ? NV_OK : NV_ERR_NOT_SUPPORTED));
    CHECK(count.casts && count.privileges);
    CHECK(external ? count.references==3 && count.maps==3 : count.allocations==3);
    CHECK(kernel ? !count.conversions && object.producerInfo.notificationHandle==(NvP64)0x55 : count.conversions==1 && count.destructs==1);
    if(kernel)eventbufferDestruct_IMPL(&object);
    finish();
}
static void positiveExternal(unsigned variant,NvBool kernel,NvBool device,NvBool vardata) {
    reset(kernel);EventBuffer object={0};
    NV_EVENT_BUFFER_ALLOC_PARAMETERS p=params(NV_TRUE,vardata);
    if(device) { assert(kernel && !vardata);p.hSubDevice=10;resources[0].externalClassId=resources[1].externalClassId=0x1234; }
    RS_RES_ALLOC_PARAMS_INTERNAL alloc={&p};
    CHECK(constructors[variant](&object,&context,&alloc)==NV_OK);
    CHECK(count.allocations==0 && count.maps==(vardata ? 3U : 2U));
    CHECK(count.references==(vardata ? 3U : 2U) && count.dependencies==(vardata ? 3U : 2U));
    CHECK(!count.conversions && !count.unsupportedDeviceServices);
    CHECK(!p.bufferHeader && !p.recordBuffer && !p.vardataBuffer);
    CHECK(object.producerInfo.recordBuffer.pHeader==backing[0].bytes && object.producerInfo.recordBuffer.recordBuffAddr==(NvP64)(NvUPtr)backing[1].bytes);
    CHECK(object.producerInfo.recordBuffer.recordSize==16 && object.producerInfo.recordBuffer.totalRecordCount==4 && object.producerInfo.recordBuffer.bufferSize==64);
    CHECK(object.producerInfo.notificationHandle==0 && !object.producerInfo.isEnabled);
    if(vardata)CHECK(object.producerInfo.vardataBuffer.vardataBuffAddr==(NvP64)(NvUPtr)backing[2].bytes && object.producerInfo.vardataBuffer.bufferSize==64);
    if(device)CHECK(count.deviceMaps==2 && object.subDeviceInst==3 && object.hClient==client.hClient);
    eventbufferDestruct_IMPL(&object);finish();
}
static void internal(unsigned variant,unsigned allocFailure,unsigned mapFailure) {
    reset(NV_TRUE);EventBuffer object={0};
    NV_EVENT_BUFFER_ALLOC_PARAMETERS p=params(NV_FALSE,NV_TRUE);
    RS_RES_ALLOC_PARAMS_INTERNAL alloc={&p};failAllocAt=allocFailure;failUserMapAt=mapFailure;
    NV_STATUS status=constructors[variant](&object,&context,&alloc);
    CHECK(status==(allocFailure ? NV_ERR_NO_MEMORY : mapFailure ? NV_ERR_INSUFFICIENT_RESOURCES : NV_OK));
    CHECK(!count.conversions && !count.unsupportedDeviceServices);
    if(!allocFailure && !mapFailure) {
        CHECK(count.allocations==3 && count.live==3 && count.userMaps==3);
        CHECK(p.bufferHeader && p.recordBuffer && p.vardataBuffer);
        CHECK(object.producerInfo.recordBuffer.pHeader==(void *)(NvUPtr)p.bufferHeader && !object.producerInfo.notificationHandle);
        eventbufferDestruct_IMPL(&object);
    } else {
        CHECK(count.destructs==1 && count.live==0);
        CHECK(!object.pHeaderDesc && !object.pRecordBufDesc && !object.pVardataBufDesc);
    }
    finish();
}
int main(void) {
    for(unsigned k=0;k!=2;++k)for(unsigned e=0;e!=2;++e)refusal(k,e);
    for(unsigned k=0;k!=2;++k)for(unsigned e=0;e!=2;++e)baselineNonzero(k,e);
    for(unsigned v=0;v!=2;++v) {
        for(unsigned k=0;k!=2;++k)for(unsigned d=0;d!=2;++d)positiveExternal(v,k,NV_FALSE,d);
        positiveExternal(v,NV_TRUE,NV_TRUE,NV_FALSE);
        internal(v,0,0);
        for(unsigned stage=1;stage!=4;++stage) { internal(v,stage,0);internal(v,0,stage); }
    }
    printf("{\"format\":1,\"component\":\"nvidia-os-event-buffer-policy\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"full_original_constructor_bodies\":2,\"public_0x90cd_parameters\":true,\"original_producer_helpers\":true,\"private_types_and_memory_helpers\":\"explicit-cpu-fixtures\",\"production_candidate_allowed\":false}\n",checks);
    return 0;
}
