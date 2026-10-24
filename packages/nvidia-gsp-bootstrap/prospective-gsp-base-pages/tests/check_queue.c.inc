/* SPDX-License-Identifier: MIT
 * Explicit CPU-only resource endpoints around extracted actual original C
 * bodies. These endpoints are neither IOKit nor DMA/GPU implementations.
 */
#define _POSIX_C_SOURCE 200112L
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
@HEADERS@
@CONSTANTS@

static unsigned checks, cases;
static void expect(int ok, const char *message) {
    ++checks;
    if (!ok) { fprintf(stderr, "FAILED: %s\n", message); abort(); }
}
#define NV_PRINTF(...) ((void)0)
#define NV_ASSERT(ok) expect(!!(ok), "actual original assertion")
#define NV_ASSERT_OR_RETURN(ok,status) do { if (!(ok)) return (status); } while (0)
#define NV_ASSERT_OK_OR_GOTO(status,expression,label) do { \
    (status)=(expression); if ((status)!=NV_OK) goto label; } while (0)
#define NV_ASSERT_TRUE_OR_GOTO(status,ok,error,label) do { \
    if (!(ok)) { (status)=(error); goto label; } } while (0)
#define ct_assert(ok) _Static_assert((ok), "actual queue header invariant")
#ifndef NV_ABI_STABLE
#define NV_ABI_STABLE
#endif

typedef NvU64 RmPhysAddr;
typedef struct ADDRESS_TRANSLATION_ *ADDRESS_TRANSLATION;
typedef NvU32 NV_ADDRESS_SPACE;
typedef struct OBJGPU OBJGPU;
typedef struct MEMORY_DESCRIPTOR MEMORY_DESCRIPTOR;
typedef MEMORY_DESCRIPTOR *PMEMORY_DESCRIPTOR;
typedef struct rpc_message_header_v rpc_message_header_v;
typedef void *msgqHandle;
@QUEUE_STRUCTS@

/* Endpoint-only properties are named selectors, not an asserted NVOC ABI. */
enum { PDB_PROP_SYS_INITIALIZE_SYSTEM_MEMORY_ALLOCATIONS=1,
       PDB_PROP_GPU_TEGRA_SOC_NVDISPLAY=2 };
struct OBJGPU { NvBool (*getProperty)(OBJGPU *,int); };
typedef struct OBJSYS { NvBool (*getProperty)(struct OBJSYS *,int); } OBJSYS;
typedef struct nv_state_t { NvBool force_dma32_alloc; } nv_state_t;
struct MEMORY_DESCRIPTOR {
    OBJGPU *pGpu;
    NvU64 Size, ActualSize, _pageSize, _flags, pageArraySize;
    NvU64 PageCount, pageArrayGranularity;
    RmPhysAddr *pages;
    void *memData;
    NvP64 kernelMapping, kernelPrivate;
    NvU32 allocTag, cache;
    NvBool dynGran, carveout;
};
static OBJSYS sys;
static OBJGPU gpu;
static nv_state_t fixtureNv;
static NvU64 os_page_size=RM_PAGE_SIZE;
#define SYS_GET_INSTANCE() (&sys)
#define NV_GET_NV_STATE(p) ((p)?&fixtureNv:NULL)
#define NV_SOC_IS_ISO_IOMMU_PRESENT(p) 0
#define NV_SOC_IS_NISO_IOMMU_PRESENT(p) 0
#define IS_DISCONTIG_AND_DYNGRAN_ENABLED(p) ((p)->dynGran)
#define IS_VIRTUAL(p) 0
#define IS_SILICON(p) (fixture.silicon)

enum { NORMAL, COLLECTION_FAIL, CREATE_FAIL, ALLOC_FAIL, MAP_FAIL, MAP_NULL,
       QUEUE_FAIL, SHORT_PAGE_ARRAY, BASELINE_HUGE_OOM };
static struct {
    int mode, silicon, override;
    NvU32 overrideKb;
    NvBool forceUnprotected, ccEnabled, hostAllowsUnprotected;
    NV_STATUS allocationStatus;
    unsigned collectionAllocations, collectionFrees, creates, destroys;
    unsigned allocations, nvAllocations, maps, unmaps, frees, queueInits;
    unsigned cleanupCalls, physCalls, deflates, inflates;
    NvU64 requestedPage[4], descriptorPage[4], requestedPages[4];
    NvBool unencrypted[4];
    NvU64 createSize, createFlags, pageArrayCount, physStride;
    void *buffer;
    NvU64 expectedCommand, expectedStatus, expectedShared, expectedPtes;
} fixture;

static NvBool gpuProperty(OBJGPU *object,int property) {
    expect(object==&gpu && property==PDB_PROP_GPU_TEGRA_SOC_NVDISPLAY,
           "actual allocation asks the selected GPU property");
    return NV_FALSE;
}
static NvBool sysProperty(OBJSYS *object,int property) {
    expect(object==&sys && property==PDB_PROP_SYS_INITIALIZE_SYSTEM_MEMORY_ALLOCATIONS,
           "actual allocation asks the selected host initialization property");
    return NV_TRUE;
}
static NvU64 osGetPageSize(void) { return os_page_size; }
static NvBool gpuIsCCFeatureEnabled(OBJGPU *object) {
    expect(object==&gpu, "actual queue uses the exact GPU"); return fixture.ccEnabled;
}
static NvBool confComputeForceUnprotAlloc(OBJGPU *object) {
    expect(object==&gpu, "actual queue forwards the unprotected policy");
    return fixture.forceUnprotected;
}
static NV_STATUS osReadRegistryDword(OBJGPU *object,const char *name,NvU32 *value) {
    expect(object==&gpu && !strcmp(name,"RmGspStatusQueueSize"),
           "actual status queue registry selector");
    if (!fixture.override) return NV_ERR_OBJECT_NOT_FOUND;
    *value=fixture.overrideKb;return NV_OK;
}
static void *portMemAllocNonPaged(size_t bytes) {
    ++fixture.collectionAllocations;
    if (fixture.mode==COLLECTION_FAIL) return NULL;
    return calloc(1,bytes);
}
static void portMemFree(void *pointer) {
    if (pointer) { ++fixture.collectionFrees;free(pointer); }
}
static void portMemSet(void *pointer,int value,size_t bytes) {
    memset(pointer,value,bytes);
}
static NvBool memdescHasSubDeviceMemDescs(PMEMORY_DESCRIPTOR descriptor) {
    expect(descriptor!=NULL,"actual descriptor exists");return NV_FALSE;
}
static NvS32 memdescGetNumaNode(PMEMORY_DESCRIPTOR descriptor) {
    expect(descriptor!=NULL,"NUMA endpoint descriptor");return -1;
}
static NV_ADDRESS_SPACE memdescGetAddressSpace(PMEMORY_DESCRIPTOR descriptor) {
    expect(descriptor!=NULL,"aperture endpoint descriptor");return ADDR_SYSMEM;
}
static NvU32 memdescGetCpuCacheAttrib(PMEMORY_DESCRIPTOR descriptor) { return descriptor->cache; }
static void memdescSetMemData(PMEMORY_DESCRIPTOR descriptor,void *data,void *privateData) {
    expect(privateData==NULL,"actual descriptor private-data contract");descriptor->memData=data;
}
static NvBool memdescIsCarveoutMemory(PMEMORY_DESCRIPTOR descriptor) { return descriptor->carveout; }
static NvBool memdescGetFlag(PMEMORY_DESCRIPTOR descriptor,NvU64 flag) { return !!(descriptor->_flags&flag); }
static void memdescSetFlag(PMEMORY_DESCRIPTOR descriptor,NvU64 flag,NvBool enabled) {
    if (enabled) descriptor->_flags|=flag; else descriptor->_flags&=~flag;
}
static void memdescSetContiguity(PMEMORY_DESCRIPTOR descriptor,ADDRESS_TRANSLATION translation,NvBool contiguous) {
    expect(translation==AT_CPU,"actual contiguity selector");
    memdescSetFlag(descriptor,MEMDESC_FLAGS_PHYSICALLY_CONTIGUOUS,contiguous);
}
static NvU32 memdescGetGuestId(PMEMORY_DESCRIPTOR descriptor) { (void)descriptor;return 0; }
static RmPhysAddr *memdescGetPteArray(PMEMORY_DESCRIPTOR descriptor,ADDRESS_TRANSLATION translation) {
    expect(translation==AT_CPU,"actual page-array selector");return descriptor->pages;
}
static void RmDeflateRmToOsPageArray(RmPhysAddr *pages,NvU64 count) {
    (void)pages;(void)count;++fixture.deflates;
}
static void RmInflateOsToRmPageArray(RmPhysAddr *pages,NvU64 count) {
    (void)pages;(void)count;++fixture.inflates;
}
static NV_STATUS vgpuUpdateGuestSysmemPfnBitMap(OBJGPU *object,PMEMORY_DESCRIPTOR descriptor,NvBool enabled) {
    (void)object;(void)descriptor;(void)enabled;abort();
}
static NV_STATUS memdescSetAllocSizeFields(PMEMORY_DESCRIPTOR descriptor,NvU64 bytes,NvU64 granularity) {
    descriptor->ActualSize=bytes;descriptor->PageCount=bytes/granularity;
    descriptor->pageArrayGranularity=granularity;return NV_OK;
}
static NV_STATUS NV_API_CALL nv_alias_pages(nv_state_t *state,NvU32 count,NvU64 pageBytes,
    NvU32 contiguous,NvU32 cache,NvU64 guest,RmPhysAddr *pages,NvBool carveout,void **data) {
    (void)state;(void)count;(void)pageBytes;(void)contiguous;(void)cache;
    (void)guest;(void)pages;(void)carveout;(void)data;abort();
}
static NV_STATUS NV_API_CALL nv_alloc_pages(nv_state_t *state,NvU32 count,NvU64 pageBytes,
    NvBool contiguous,NvU32 cache,NvBool initialize,NvBool unencrypted,NvS32 node,
    RmPhysAddr *pages,void **data) {
    unsigned call=fixture.nvAllocations++;
    expect(call<4,"bounded fixture allocation calls");
    fixture.requestedPage[call]=pageBytes;fixture.requestedPages[call]=count;
    fixture.unencrypted[call]=unencrypted;
    expect(state==&fixtureNv && !contiguous && cache==NV_MEMORY_CACHED && initialize && node==-1,
           "actual original OS allocation parameters preserved");
    if (fixture.mode==BASELINE_HUGE_OOM && pageBytes==RM_PAGE_SIZE_HUGE)
        return NV_ERR_NO_MEMORY;
    /* Explicit CPU model of the selected backend: genuine base pages only.
     * Admission of unencrypted=1 is separately modeled, not implemented here. */
    if (pageBytes!=RM_PAGE_SIZE || (unencrypted&&!fixture.hostAllowsUnprotected))
        return NV_ERR_NOT_SUPPORTED;
    if (fixture.mode==ALLOC_FAIL) return fixture.allocationStatus;
    expect(posix_memalign(&fixture.buffer,RM_PAGE_SIZE,(size_t)(count*RM_PAGE_SIZE))==0,
           "CPU fixture backing allocation");
    memset(fixture.buffer,0xa5,(size_t)(count*RM_PAGE_SIZE));
    for (NvU64 i=0;i<count;++i) pages[i]=0x10000000ULL+i*2*RM_PAGE_SIZE;
    *data=fixture.buffer;return NV_OK;
}
@ABI_ASSERTIONS@
@MEMDESC_BODIES@
@OS_BODIES@

static NV_STATUS memdescCreate(PMEMORY_DESCRIPTOR *out,OBJGPU *object,NvU64 bytes,
    NvU64 align,NvBool contiguous,NV_ADDRESS_SPACE aperture,NvU32 cache,NvU64 flags) {
    ++fixture.creates;fixture.createSize=bytes;fixture.createFlags=flags;
    expect(object==&gpu && align==RM_PAGE_SIZE && contiguous==NV_MEMORY_NONCONTIGUOUS &&
        aperture==ADDR_SYSMEM && cache==NV_MEMORY_CACHED,"actual descriptor creation parameters");
    if (fixture.mode==CREATE_FAIL) return NV_ERR_INVALID_ARGUMENT;
    PMEMORY_DESCRIPTOR descriptor=calloc(1,sizeof(*descriptor));
    expect(descriptor!=NULL,"CPU descriptor fixture allocation");
    descriptor->pGpu=object;descriptor->Size=bytes;descriptor->_flags=flags;descriptor->cache=cache;
    descriptor->pageArraySize=(bytes+RM_PAGE_SIZE-1)/RM_PAGE_SIZE;
    if (fixture.mode==SHORT_PAGE_ARRAY) --descriptor->pageArraySize;
    descriptor->pages=calloc((size_t)(descriptor->pageArraySize+1),sizeof(RmPhysAddr));
    expect(descriptor->pages!=NULL,"CPU page-array fixture allocation");
    *out=descriptor;return NV_OK;
}
static NV_STATUS memdescAlloc(PMEMORY_DESCRIPTOR descriptor) {
    unsigned call=fixture.allocations++;
    expect(call<4,"bounded descriptor allocation calls");
    fixture.descriptorPage[call]=descriptor->_pageSize;
    expect(descriptor->_flags&MEMDESC_FLAGS_KERNEL_MODE,"actual kernel-mode flag remains set");
    expect(!!(descriptor->_flags&MEMDESC_FLAGS_ALLOC_IN_UNPROTECTED_MEMORY)==fixture.forceUnprotected,
           "actual unprotected request flag is preserved");
    expect(descriptor->allocTag==NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_58,
           "actual allocation tag retained");
    expect(descriptor->_pageSize==(BASELINE&&call==0?RM_PAGE_SIZE_HUGE:RM_PAGE_SIZE),
           "explicit requested descriptor page size precedes allocation");
    return osAllocPagesInternal(descriptor);
}
static NV_STATUS memdescMap(PMEMORY_DESCRIPTOR descriptor,NvU64 offset,NvU64 bytes,
    NvBool kernel,NvU32 protection,NvP64 *address,NvP64 *privateData) {
    ++fixture.maps;
    expect(offset==0 && bytes==fixture.expectedShared && kernel &&
        protection==NV_PROTECT_WRITEABLE && descriptor->memData==fixture.buffer &&
        fixture.buffer!=NULL,"actual mapping uses the exact allocated shared buffer");
    if (fixture.mode==MAP_FAIL) return NV_ERR_OPERATING_SYSTEM;
    *address=fixture.mode==MAP_NULL?NULL:fixture.buffer;*privateData=descriptor;return NV_OK;
}
static void memdescSetKernelMapping(PMEMORY_DESCRIPTOR descriptor,NvP64 pointer) { descriptor->kernelMapping=pointer; }
static void memdescSetKernelMappingPriv(PMEMORY_DESCRIPTOR descriptor,NvP64 pointer) { descriptor->kernelPrivate=pointer; }
static NvP64 memdescGetKernelMapping(PMEMORY_DESCRIPTOR descriptor) { return descriptor->kernelMapping; }
static NvP64 memdescGetKernelMappingPriv(PMEMORY_DESCRIPTOR descriptor) { return descriptor->kernelPrivate; }
static void memdescUnmap(PMEMORY_DESCRIPTOR descriptor,NvBool kernel,NvP64 pointer,NvP64 privateData) {
    ++fixture.unmaps;
    expect(kernel && pointer==fixture.buffer && privateData==descriptor,"actual cleanup mapping identity");
}
static void memdescFree(PMEMORY_DESCRIPTOR descriptor) {
    ++fixture.frees;
    if (descriptor->memData) { expect(descriptor->memData==fixture.buffer,"CPU backing identity");free(fixture.buffer);fixture.buffer=NULL; }
    descriptor->memData=NULL;
}
static void memdescDestroy(PMEMORY_DESCRIPTOR descriptor) {
    ++fixture.destroys;free(descriptor->pages);free(descriptor);
}
static void memdescGetPhysAddrs(PMEMORY_DESCRIPTOR descriptor,ADDRESS_TRANSLATION translation,
    NvU64 offset,NvU64 stride,NvU64 count,RmPhysAddr *out) {
    ++fixture.physCalls;fixture.pageArrayCount=count;fixture.physStride=stride;
    expect(translation==AT_GPU && offset==0 && stride==RM_PAGE_SIZE &&
        count==fixture.expectedPtes && count<=descriptor->pageArraySize &&
        (void *)out==fixture.buffer,"actual full shared-memory PTE geometry");
    for (NvU64 i=0;i<count;++i) out[i]=descriptor->pages[i];
}
static NV_STATUS _gspMsgQueueInit(MESSAGE_QUEUE_INFO *queue,OBJGPU *object) {
    ++fixture.queueInits;
    expect(object==&gpu && queue->commandQueueSize==fixture.expectedCommand &&
        queue->statusQueueSize==fixture.expectedStatus,"actual queue sizing reaches initialization endpoint");
    expect((char *)queue->pCommandQueue-(char *)fixture.buffer==RM_PAGE_SIZE &&
        (char *)queue->pStatusQueue-(char *)fixture.buffer==RM_PAGE_SIZE+(ptrdiff_t)fixture.expectedCommand,
        "actual command/status shared offsets");
    expect(queue->queueElementSizeMin==RM_PAGE_SIZE && queue->queueElementSizeMax==16*RM_PAGE_SIZE &&
        queue->queueHeaderAlign==4 && queue->queueElementAlign==RM_PAGE_SHIFT,
        "actual queue alignment and element geometry");
    expect(queue->queueElementHdrSize==(fixture.ccEnabled?GSP_MSG_QUEUE_ELEMENT_SIZE_WITH_ENCRYPTION:
        GSP_MSG_QUEUE_ELEMENT_SIZE_NO_ENCRYPTION),"actual encrypted/plain header size");
    return fixture.mode==QUEUE_FAIL?NV_ERR_GENERIC:NV_OK;
}
@QUEUE_BODIES@

static void resetFixture(int mode,NvBool hostAllowsUnprotected) {
    expect(fixture.buffer==NULL,"CPU fixture cleanup completed before next case");
    memset(&fixture,0,sizeof(fixture));memset(&fixtureNv,0,sizeof(fixtureNv));
    fixture.mode=mode;fixture.silicon=1;fixture.forceUnprotected=1;
    fixture.hostAllowsUnprotected=hostAllowsUnprotected;fixture.allocationStatus=NV_ERR_NO_MEMORY;
    fixture.expectedCommand=262144;fixture.expectedStatus=262144;
    fixture.expectedShared=528384;fixture.expectedPtes=129;
    gpu.getProperty=gpuProperty;sys.getProperty=sysProperty;os_page_size=RM_PAGE_SIZE;
}
static NV_STATUS runQueue(NV_STATUS wanted) {
    MESSAGE_QUEUE_COLLECTION *collection=NULL;
    NV_STATUS status=GspMsgQueuesInit(&gpu,&collection);
    expect(status==wanted,"actual queue status is propagated unchanged");
    if (wanted==NV_OK) {
        expect(collection!=NULL,"successful queue is published");
        expect(collection->pageTableSize==RM_PAGE_SIZE && collection->pageTableEntryCount==fixture.expectedPtes,
               "actual table size and own PTE entry");
        expect(fixture.createSize==fixture.expectedShared && fixture.pageArrayCount==fixture.expectedPtes,
               "actual shared allocation and PTE counts");
        expect(collection->sharedMemPA==0x10000000ULL,"actual shared table physical address");
        RmPhysAddr *table=fixture.buffer;
        for (NvU64 i=0;i<fixture.expectedPtes;++i)
            expect(table[i]==0x10000000ULL+i*2*RM_PAGE_SIZE,"actual PTEs preserve noncontiguous base pages");
        for (size_t i=(size_t)(fixture.expectedPtes*sizeof(RmPhysAddr));i<RM_PAGE_SIZE;++i)
            expect(((unsigned char *)fixture.buffer)[i]==0,"actual page-table padding zeroed");
        GspMsgQueuesCleanup(&collection);
        expect(collection==NULL,"actual cleanup retires the CPU fixture collection");
    } else expect(collection==NULL,"failed queue is never published");
    expect(fixture.buffer==NULL && fixture.deflates==0 && fixture.inflates==0,
           "CPU endpoints cleaned up and target 4K requires no page-array conversion");
    ++cases;return status;
}
int main(void) {
    resetFixture(NORMAL,NV_TRUE);
    if (BASELINE) {
        runQueue(NV_ERR_NOT_SUPPORTED);
        expect(fixture.allocations==1 && fixture.nvAllocations==1 && fixture.requestedPage[0]==RM_PAGE_SIZE_HUGE &&
            fixture.requestedPages[0]==129 && fixture.unencrypted[0]==1 && fixture.maps==0,
            "actual B6 requests unsupported 2M pages without reinterpreting the status");
        resetFixture(BASELINE_HUGE_OOM,NV_TRUE);
        runQueue(NV_OK);
        expect(fixture.allocations==2 && fixture.requestedPage[0]==RM_PAGE_SIZE_HUGE &&
            fixture.requestedPage[1]==RM_PAGE_SIZE,"actual old fallback applies only to injected NO_MEMORY");
        printf("{\"status\":\"passed-B6-baseline-actual-queue-controls\",\"cases\":%u,\"checks\":%u}\n",cases,checks);
        return 0;
    }
    runQueue(NV_OK);
    expect(fixture.allocations==1 && fixture.nvAllocations==1 && fixture.requestedPage[0]==RM_PAGE_SIZE &&
        fixture.requestedPages[0]==129 && fixture.unencrypted[0]==1 && fixture.unmaps==1,
        "actual B7 requests 129 real 4K unprotected pages once");
    resetFixture(NORMAL,NV_FALSE);
    runQueue(NV_ERR_NOT_SUPPORTED);
    expect(fixture.allocations==1 && fixture.nvAllocations==1 && fixture.unencrypted[0]==1 && fixture.maps==0,
        "base-page-only profile does not invent the separately owned host admission");
    resetFixture(NORMAL,NV_FALSE);fixture.forceUnprotected=0;runQueue(NV_OK);
    expect(fixture.unencrypted[0]==0,"ordinary host allocations remain ordinary");
    resetFixture(NORMAL,NV_TRUE);fixture.ccEnabled=1;runQueue(NV_OK);
    resetFixture(NORMAL,NV_TRUE);fixture.silicon=0;
    fixture.expectedCommand=1572864;fixture.expectedShared=1839104;fixture.expectedPtes=449;runQueue(NV_OK);
    resetFixture(NORMAL,NV_TRUE);fixture.override=1;fixture.overrideKb=0;
    fixture.expectedStatus=65536;fixture.expectedShared=331776;fixture.expectedPtes=81;runQueue(NV_OK);
    resetFixture(NORMAL,NV_TRUE);fixture.override=1;fixture.overrideKb=65;
    fixture.expectedStatus=69632;fixture.expectedShared=335872;fixture.expectedPtes=82;runQueue(NV_OK);
    for (int mode=COLLECTION_FAIL;mode<=SHORT_PAGE_ARRAY;++mode) {
        resetFixture(mode,NV_TRUE);
        NV_STATUS wanted=mode==CREATE_FAIL||mode==SHORT_PAGE_ARRAY?NV_ERR_INVALID_ARGUMENT:
            mode==MAP_FAIL?NV_ERR_OPERATING_SYSTEM:mode==QUEUE_FAIL?NV_ERR_GENERIC:NV_ERR_NO_MEMORY;
        runQueue(wanted);
        expect(fixture.allocations<=1,"4K failure is not retried");
        expect(mode==COLLECTION_FAIL?fixture.creates==0:fixture.creates==1,
               "actual descriptor creation follows collection ownership");
    }
    const NV_STATUS failures[]={NV_ERR_NOT_SUPPORTED,NV_ERR_INVALID_STATE,NV_ERR_OPERATION_ABORTED};
    for (size_t i=0;i<sizeof(failures)/sizeof(failures[0]);++i) {
        resetFixture(ALLOC_FAIL,NV_TRUE);fixture.allocationStatus=failures[i];runQueue(failures[i]);
        expect(fixture.allocations==1 && fixture.nvAllocations==1 && fixture.maps==0,
               "base-page refusal/cancellation keeps exact status without retry/map");
    }
    resetFixture(NORMAL,NV_TRUE);
    MESSAGE_QUEUE_COLLECTION dummy={0},*existing=&dummy;
    expect(GspMsgQueuesInit(&gpu,&existing)==NV_ERR_INVALID_STATE && existing==&dummy &&
        fixture.collectionAllocations==0,"existing queue refuses before allocation");++cases;
    MEMORY_DESCRIPTOR direct={0};NvU64 page,count,rm;
    direct.Size=528384;direct.pageArraySize=129;direct._pageSize=RM_PAGE_SIZE_HUGE;
    expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_OK && page==RM_PAGE_SIZE_HUGE && count==129 && rm==129,
           "actual page helper does not silently convert a noncontiguous 2M request");++cases;
    direct._pageSize=0;
    expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_OK && page==RM_PAGE_SIZE &&
        direct._pageSize==RM_PAGE_SIZE,"actual unspecified-page fallback is genuine OS base page");++cases;
    direct._pageSize=RM_PAGE_SIZE_HUGE;direct._flags=MEMDESC_FLAGS_PHYSICALLY_CONTIGUOUS;
    expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_OK && page==RM_PAGE_SIZE,
           "actual contiguous helper uses OS allocation geometry");++cases;
    direct._flags=0;direct.pageArraySize=128;
    expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_ERR_INVALID_ARGUMENT,
           "actual page-array overflow refusal preserved");++cases;
    direct.Size=((NvU64)NV_U32_MAX+1)*RM_PAGE_SIZE;direct.pageArraySize=(NvU64)NV_U32_MAX+1;
    expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_ERR_INVALID_LIMIT,
           "actual OS/RM page-count limit preserved");++cases;
    printf("{\"status\":\"passed-actual-GSP-base-page-queue-controls\",\"cases\":%u,\"checks\":%u}\n",cases,checks);
    return 0;
}
