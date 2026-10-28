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
@PROJECT_HEADERS@
typedef struct KernelGsp { NvU32 bootAttempts; } KernelGsp;

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
       QUEUE_FAIL, SHORT_PAGE_ARRAY, BASELINE_HUGE_OOM, FIRST_OOM };
static struct {
    int mode, silicon, override;
    NvU32 overrideKb;
    NvBool forceUnprotected, ccEnabled, hostAllowsUnprotected;
    NV_STATUS allocationStatus, firstAllocationFailure;
    NvBool retainAllocationFailure;
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
    if (fixture.retainAllocationFailure && fixture.firstAllocationFailure!=NV_OK) return fixture.firstAllocationFailure;
    if (fixture.mode==FIRST_OOM && call==0) {
        if(fixture.retainAllocationFailure)fixture.firstAllocationFailure=NV_ERR_NO_MEMORY;
        return NV_ERR_NO_MEMORY;
    }
    expect(posix_memalign(&fixture.buffer,RM_PAGE_SIZE,(size_t)(count*RM_PAGE_SIZE))==0,
           "CPU fixture backing allocation");
    memset(fixture.buffer,0xa5,(size_t)(count*RM_PAGE_SIZE));
    for (NvU64 i=0;i<count;++i) pages[i]=0x123400000ULL+i*2*RM_PAGE_SIZE;
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
    expect(descriptor->allocTag==NV_FB_ALLOC_RM_INTERNAL_OWNER_UNNAMED_TAG_17,
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
    expect(translation==AT_GPU && stride==RM_PAGE_SIZE && offset%RM_PAGE_SIZE==0 &&
        offset/RM_PAGE_SIZE+count<=descriptor->pageArraySize,
        "actual Radix3 descriptor PTE geometry stays within backing");
    for (NvU64 i=0;i<count;++i) out[i]=descriptor->pages[offset/RM_PAGE_SIZE+i];
}

#ifndef NV_ARRAY_ELEMENTS
#define NV_ARRAY_ELEMENTS(a) (sizeof(a)/sizeof((a)[0]))
#endif
#define NV_ASSERT_OR_ELSE_STR(ok,message,action) do { if (!(ok)) { action; } } while (0)
#define NV_ASSERT_OK_OR_RETURN(expression) do { NV_STATUS _s=(expression); if (_s!=NV_OK) return _s; } while (0)
#ifndef KERNEL_POINTER_FROM_NvP64
#define KERNEL_POINTER_FROM_NvP64(type,value) ((type)(value))
#endif
static NvU64 memdescGetSize(PMEMORY_DESCRIPTOR p) { return p->Size; }
static void portMemCopy(void *to,size_t capacity,const void *from,size_t bytes) {
    expect(bytes<=capacity,"actual bounded data copy capacity"); memcpy(to,from,bytes);
}
static NV_STATUS s540FirstTxnRequestDeferredCleanupGpu(OBJGPU *p,NV_STATUS status) {
    expect(p==&gpu && status!=NV_OK,"retained cleanup preserves failed operation");
    ++fixture.cleanupCalls;return status;
}
@RADIX_BODY@

/* Actual cancellation GPU forwarding and actual timeout-reset wrapper are
 * executed; state admission, current-thread lookup/time initialization and
 * hardware boot are explicitly typed endpoints, not a full RM/GSP execution. */
typedef struct THREAD_STATE_NODE { NvU32 flags; } THREAD_STATE_NODE;
static struct { NvU32 setupFlags; } threadStateDatabase;
static THREAD_STATE_NODE timeoutNode;
static struct {
    unsigned polls, boots, currentCalls, initCalls, prints;
    NV_STATUS cancel[8], boot[8], currentStatus, initStatus;
    NvBool retry[8], apiOwner;
    NvU32 lockMask;
} retryFixture;
NV_STATUS s540GspCancellationCheckState(const void *state) {
    expect(state==&fixtureNv,"actual CheckGpu forwards exact NV identity");
    unsigned n=retryFixture.polls++;
    expect(n<8,"bounded cancellation endpoint polling");return retryFixture.cancel[n];
}
@CANCEL_BODY@
static NV_STATUS threadStateGetCurrent(THREAD_STATE_NODE **out,OBJGPU *p) {
    expect(p==&gpu,"actual timeout reset uses exact GPU");++retryFixture.currentCalls;
    *out=retryFixture.currentStatus==NV_OK?&timeoutNode:NULL;
    return retryFixture.currentStatus;
}
static NV_STATUS _threadNodeInitTime(THREAD_STATE_NODE *p) {
    expect(p==&timeoutNode,"actual timeout reset uses current thread node");
    ++retryFixture.initCalls;return retryFixture.initStatus;
}
static void _threadStatePrintInfo(THREAD_STATE_NODE *p) {
    expect(p==&timeoutNode,"actual initialized timeout node");++retryFixture.prints;
}
@TIMEOUT_BODY@
static NvBool rmapiLockIsOwner(void) { return retryFixture.apiOwner; }
static NV_STATUS _kgspBootGspRm(OBJGPU *p,KernelGsp *gsp,void *fw,NvU32 *locks,NvBool *again) {
    expect(p==&gpu && fw==&fixtureNv,"actual retry forwards GPU and firmware endpoint identity");
    unsigned n=retryFixture.boots++;
    expect(n<8,"bounded hardware boot endpoint calls");
    *again=NV_FALSE;*locks=retryFixture.lockMask;
    NV_STATUS status=retryFixture.boot[n];
    if (status!=NV_OK && status!=NV_ERR_OPERATION_ABORTED) {
        ++gsp->bootAttempts;*again=retryFixture.retry[n];
    }
    return status;
}
static NV_STATUS actualRetry(OBJGPU *pGpu,KernelGsp *pKernelGsp,NvU32 maxGspBootAttempts,NV_STATUS status) {
    NvU32 gpusLockedMask=1;
    void *pGspFw=&fixtureNv;
@RETRY_BODY@
done:
    return status;
}
static void resetRetry(void) {
    memset(&retryFixture,0,sizeof(retryFixture));memset(&timeoutNode,0,sizeof(timeoutNode));
    retryFixture.apiOwner=NV_TRUE;retryFixture.lockMask=1;
    threadStateDatabase.setupFlags=THREAD_STATE_SETUP_FLAGS_TIMEOUT_ENABLED;
}
static void checkRetry(void) {
    KernelGsp gsp={0};NV_STATUS status;
    expect(NV_REG_STR_RM_GSP_BOOT_RETRY_ATTEMPTS_DEFAULT==4,"real default boot limit is four");
    resetRetry();status=actualRetry(&gpu,&gsp,4,NV_OK);
    expect(status==NV_OK && retryFixture.boots==1 && retryFixture.polls==1 && retryFixture.initCalls==0,
        "default bRetry=false executes one successful boot");++cases;
    resetRetry();gsp.bootAttempts=0;retryFixture.boot[0]=NV_ERR_GENERIC;
    status=actualRetry(&gpu,&gsp,4,NV_OK);
    expect(status==NV_ERR_GENERIC && retryFixture.boots==1 && retryFixture.initCalls==0,
        "failure without eligible retry remains one attempt and exact status");++cases;
    resetRetry();gsp.bootAttempts=0;
    for(unsigned i=0;i<4;++i){retryFixture.boot[i]=NV_ERR_TIMEOUT;retryFixture.retry[i]=NV_TRUE;}
    status=actualRetry(&gpu,&gsp,NV_REG_STR_RM_GSP_BOOT_RETRY_ATTEMPTS_DEFAULT,NV_OK);
    expect(status==NV_ERR_TIMEOUT && retryFixture.boots==4 && retryFixture.polls==4 && gsp.bootAttempts==4,
        "original actual retry eligibility and four-attempt limit");
    expect(retryFixture.initCalls==(BASELINE?0U:3U) && retryFixture.prints==retryFixture.initCalls,
        "healthy polling preserves previous failure for each timeout reset");++cases;
    resetRetry();gsp.bootAttempts=0;retryFixture.boot[0]=NV_ERR_GENERIC;retryFixture.retry[0]=NV_TRUE;
    status=actualRetry(&gpu,&gsp,4,NV_OK);
    expect(status==NV_OK && retryFixture.boots==2 && retryFixture.initCalls==(BASELINE?0U:1U),
        "failure then success resets timeout between attempts");++cases;
    resetRetry();gsp.bootAttempts=0;status=actualRetry(&gpu,&gsp,4,NV_ERR_TIMEOUT);
    expect(status==NV_OK && retryFixture.boots==1 && retryFixture.initCalls==(BASELINE?0U:1U),
        "first healthy poll preserves an already nonzero prior status");++cases;
    const NV_STATUS cancelErrors[]={NV_ERR_OPERATION_ABORTED,NV_ERR_INVALID_STATE,NV_ERR_NOT_SUPPORTED};
    for(unsigned i=0;i<NV_ARRAY_ELEMENTS(cancelErrors);++i){
        resetRetry();gsp.bootAttempts=0;retryFixture.cancel[0]=cancelErrors[i];
        status=actualRetry(&gpu,&gsp,4,NV_ERR_GENERIC);
        expect(status==cancelErrors[i] && retryFixture.boots==0 && retryFixture.initCalls==0,
            "every cancellation error stops before reset/boot with actual status");++cases;
    }
    resetRetry();gsp.bootAttempts=0;retryFixture.boot[0]=NV_ERR_TIMEOUT;retryFixture.retry[0]=NV_TRUE;
    retryFixture.cancel[1]=NV_ERR_OPERATION_ABORTED;
    status=actualRetry(&gpu,&gsp,4,NV_OK);
    expect(status==NV_ERR_OPERATION_ABORTED && retryFixture.boots==1 && retryFixture.polls==2 && retryFixture.initCalls==0,
        "cancellation on later retry stops before timeout reset and next boot");++cases;
    resetRetry();gsp.bootAttempts=0;retryFixture.boot[0]=NV_ERR_OPERATION_ABORTED;retryFixture.retry[0]=NV_TRUE;
    status=actualRetry(&gpu,&gsp,4,NV_OK);
    expect(status==NV_ERR_OPERATION_ABORTED && retryFixture.boots==1,"aborted original boot is not retried");++cases;
    resetRetry();gsp.bootAttempts=0;retryFixture.boot[0]=NV_ERR_TIMEOUT;retryFixture.retry[0]=NV_TRUE;
    status=actualRetry(&gpu,&gsp,1,NV_OK);
    expect(status==NV_ERR_TIMEOUT && retryFixture.boots==1 && retryFixture.initCalls==0,"explicit one-attempt limit retained");++cases;
    resetRetry();gsp.bootAttempts=0;retryFixture.lockMask=0;
    status=actualRetry(&gpu,&gsp,4,NV_OK);
    expect(status==NV_ERR_INVALID_LOCK_STATE && retryFixture.boots==1,"missing original GPU lock refuses immediately");++cases;
    resetRetry();gsp.bootAttempts=0;retryFixture.apiOwner=NV_FALSE;
    status=actualRetry(&gpu,&gsp,4,NV_OK);
    expect(status==NV_ERR_INVALID_LOCK_STATE,"missing original API lock refuses immediately");++cases;
    resetRetry();threadStateDatabase.setupFlags=0;
    expect(threadStateResetTimeout(&gpu)==NV_ERR_INVALID_STATE && retryFixture.currentCalls==0,
        "actual timeout wrapper refuses disabled state");++cases;
    resetRetry();retryFixture.currentStatus=NV_ERR_OBJECT_NOT_FOUND;
    expect(threadStateResetTimeout(&gpu)==NV_ERR_OBJECT_NOT_FOUND && retryFixture.initCalls==0,
        "actual current-thread lookup error preserved");++cases;
    resetRetry();retryFixture.initStatus=NV_ERR_TIMEOUT;
    expect(threadStateResetTimeout(&gpu)==NV_ERR_TIMEOUT && timeoutNode.flags==0 && retryFixture.prints==0,
        "actual timeout initializer failure preserved without success flag");++cases;
    resetRetry();expect(threadStateResetTimeout(&gpu)==NV_OK &&
        (timeoutNode.flags&THREAD_STATE_FLAGS_TIMEOUT_INITED) && retryFixture.prints==1,
        "actual timeout reset publishes initialized flag only after success");++cases;
}
static void resetFixture(int mode) {
    expect(fixture.buffer==NULL,"CPU backing retired by harness teardown");
    memset(&fixture,0,sizeof(fixture));memset(&fixtureNv,0,sizeof(fixtureNv));
    fixture.mode=mode;fixture.forceUnprotected=NV_TRUE;fixture.hostAllowsUnprotected=NV_TRUE;
    fixture.allocationStatus=NV_ERR_NO_MEMORY;gpu.getProperty=gpuProperty;sys.getProperty=sysProperty;
    os_page_size=RM_PAGE_SIZE;
}
static NvU64 dataPages, tablePages;
static void geometry(NvU64 size) {
    dataPages=(size+4095)/4096;
    tablePages=1+((dataPages+511)/512)+(((dataPages+511)/512+511)/512);
    fixture.expectedShared=(tablePages+dataPages)*4096;
}
static void finishDescriptor(MEMORY_DESCRIPTOR *descriptor) {
    if (!descriptor) return;
    if (descriptor->memData) {free(descriptor->memData);fixture.buffer=NULL;}
    free(descriptor->pages);free(descriptor);
}
static NV_STATUS runRadix(NvU64 size,const void *data,NV_STATUS wanted) {
    MEMORY_DESCRIPTOR *descriptor=NULL;KernelGsp gsp={0};geometry(size);
    NV_STATUS status=kgspCreateRadix3_IMPL(&gpu,&gsp,&descriptor,NULL,data,size);
    expect(status==wanted,"actual Radix3 returns exact operation status");
    if(status==NV_OK){
        expect(descriptor && fixture.buffer && fixture.unmaps==1 && fixture.cleanupCalls==0,
            "actual successful Radix3 unmaps and retains descriptor");
        expect(fixture.createSize==fixture.expectedShared && fixture.allocations<=2,
            "actual Radix3 table/data allocation geometry");
        NvU64 l1=1,l2=(dataPages+511)/512;
        const NvU64 off[3]={0,4096,8192};
        const NvU64 next[3]={4096,8192,tablePages*4096};
        const NvU64 count[3]={l1,l2,dataPages};
        for(unsigned level=0;level<3;++level){
            NvU64 *table=(NvU64*)((unsigned char*)fixture.buffer+off[level]);
            for(NvU64 i=0;i<count[level];++i)
                expect(table[i]==0x123400000ULL+(next[level]/4096+i)*8192,
                    "actual PDE/PTE entries preserve discontiguous physical pages above4GiB");
            for(NvU64 i=count[level]*8;i<(level==2?l2*4096:4096);++i)
                expect(((unsigned char*)table)[i]==0,"actual page-table padding zeroed");
        }
        if(data){
            const unsigned char *start=(unsigned char*)fixture.buffer+tablePages*4096;
            expect(memcmp(start,data,(size_t)size)==0,"actual firmware bytes copied at unchanged data offset");
            for(NvU64 i=size;i<dataPages*4096;++i)expect(start[i]==0,"actual last data-page padding zeroed");
        }
    } else {
        expect(fixture.maps==0 || fixture.mode==MAP_FAIL || fixture.mode==MAP_NULL,
            "failed allocation never maps");
        expect(fixture.unmaps==0 && fixture.frees==0 && fixture.destroys==0,
            "actual deferred failure path does not free or authorize reclamation");
        expect(fixture.cleanupCalls==(fixture.creates && fixture.mode!=CREATE_FAIL?1U:0U),
            "actual failure asks only retained deferred cleanup after create");
    }
    finishDescriptor(descriptor);expect(fixture.buffer==NULL,"harness CPU teardown only");++cases;return status;
}
int main(void) {
    unsigned char data[4097];for(unsigned i=0;i<sizeof(data);++i)data[i]=(unsigned char)(i*13U+7U);
    if(BASELINE){
        resetFixture(NORMAL);runRadix(4097,data,NV_ERR_NOT_SUPPORTED);
        expect(fixture.allocations==1 && fixture.requestedPage[0]==RM_PAGE_SIZE_HUGE && fixture.maps==0,
            "pre-profile actual Radix3 reaches typedbackend with unsupported huge pages once");
        resetFixture(BASELINE_HUGE_OOM);runRadix(4097,data,NV_OK);
        expect(fixture.allocations==2 && fixture.requestedPage[0]==RM_PAGE_SIZE_HUGE && fixture.requestedPage[1]==RM_PAGE_SIZE,
            "original no-memory-only fallback remains distinct from unsupported geometry");
    }else{
        const NvU64 sizes[]={1,4096,4097,1025*4096ULL};
        for(unsigned i=0;i<NV_ARRAY_ELEMENTS(sizes);++i){resetFixture(NORMAL);runRadix(sizes[i],sizes[i]<=sizeof(data)?data:NULL,NV_OK);}
        resetFixture(NORMAL);fixture.forceUnprotected=NV_FALSE;runRadix(4097,data,NV_OK);
        expect(fixture.unencrypted[0]==NV_FALSE,"ordinary allocation flag preserved");
        resetFixture(NORMAL);fixture.hostAllowsUnprotected=NV_FALSE;runRadix(4097,data,NV_ERR_NOT_SUPPORTED);
        expect(fixture.allocations==1 && fixture.unencrypted[0]==NV_TRUE,"unprotected request is not erased");
        /* This transient endpoint isolates the unchanged original fallback.
         * It is not the retained backend: the separate sticky81 case below
         * explicitly keeps that production-lifetime refusal. */
        resetFixture(FIRST_OOM);runRadix(4097,data,NV_OK);
        expect(fixture.allocations==2 && fixture.requestedPage[0]==4096 && fixture.requestedPage[1]==4096,
            "typed non-sticky81 endpoint verifies original fallback control flow only");
        resetFixture(FIRST_OOM);fixture.retainAllocationFailure=NV_TRUE;runRadix(4097,data,NV_ERR_NO_MEMORY);
        expect(fixture.allocations==2 && fixture.firstAllocationFailure==NV_ERR_NO_MEMORY && fixture.maps==0,
            "typed retained refusal is not erased by the original no-memory retry");
        const NV_STATUS errors[]={NV_ERR_NOT_SUPPORTED,NV_ERR_NO_MEMORY,NV_ERR_INVALID_STATE,NV_ERR_OPERATION_ABORTED};
        for(unsigned i=0;i<NV_ARRAY_ELEMENTS(errors);++i){
            resetFixture(ALLOC_FAIL);fixture.allocationStatus=errors[i];runRadix(4097,data,errors[i]);
            expect(fixture.allocations==(errors[i]==NV_ERR_NO_MEMORY?2U:1U),"only81 triggers the original fallback");
        }
        resetFixture(CREATE_FAIL);runRadix(4097,data,NV_ERR_INVALID_ARGUMENT);
        resetFixture(MAP_FAIL);runRadix(4097,data,NV_ERR_OPERATING_SYSTEM);
        resetFixture(MAP_NULL);runRadix(4097,data,NV_ERR_NO_MEMORY);
        resetFixture(NORMAL);MEMORY_DESCRIPTOR *p=NULL;KernelGsp gsp={0};
        expect(kgspCreateRadix3_IMPL(&gpu,&gsp,NULL,NULL,NULL,1)==NV_ERR_INVALID_PARAMETER,"null output refuses before work");++cases;
        MEMORY_DESCRIPTOR existing={0};
        expect(kgspCreateRadix3_IMPL(&gpu,&gsp,&p,&existing,data,1)==NV_ERR_INVALID_PARAMETER,"conflicting data sources refused");++cases;
        expect(kgspCreateRadix3_IMPL(&gpu,&gsp,&p,NULL,NULL,0)==NV_ERR_OUT_OF_RANGE,"zero length refused before allocation");++cases;
        MEMORY_DESCRIPTOR direct={0};NvU64 page,count,rm;direct.Size=4097;direct.pageArraySize=2;direct._pageSize=RM_PAGE_SIZE_HUGE;
        expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_OK && page==RM_PAGE_SIZE_HUGE && count==2 && rm==2,"actual page propagation does not relabel2M");++cases;
        direct._pageSize=0;expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_OK && page==RM_PAGE_SIZE && direct._pageSize==RM_PAGE_SIZE,"zero page size uses actual OS base page");++cases;
        direct._pageSize=RM_PAGE_SIZE_HUGE;direct._flags=MEMDESC_FLAGS_PHYSICALLY_CONTIGUOUS;
        expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_OK && page==RM_PAGE_SIZE,"contiguous helper still uses OS page size");++cases;
        direct._flags=0;direct.pageArraySize=1;
        expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_ERR_INVALID_ARGUMENT,"page-array overflow preserved");++cases;
        direct.Size=((NvU64)NV_U32_MAX+1)*RM_PAGE_SIZE;direct.pageArraySize=(NvU64)NV_U32_MAX+1;
        expect(osGetPagesInfo(&direct,&page,&count,&rm)==NV_ERR_INVALID_LIMIT,"actual OS count limit preserved");++cases;
    }
    checkRetry();
    printf("{\"status\":\"passed-actual-GSP-boot-contract-controls\",\"cases\":%u,\"checks\":%u}\n",cases,checks);
    return 0;
}
