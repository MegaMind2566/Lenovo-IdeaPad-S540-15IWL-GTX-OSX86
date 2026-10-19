/* SPDX-License-Identifier: MIT */
/* Native fault control of complete, exact extracted original/candidate bodies.
 * Dependencies and owners are explicit models, not a kernel or GPU execution.
 */
#if defined(KERNEL) || defined(__KERNEL__)
#error Native source-body fixture must not be linked into a kernel image
#endif
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t NvU32;
typedef uint64_t NvU64;
typedef uintptr_t NvP64;
typedef uint64_t RmPhysAddr;
typedef uint32_t NvHandle;
typedef int NvBool;
typedef int NV_STATUS;
#define NV_TRUE 1
#define NV_FALSE 0
enum { NV_OK, NV_ERR_NOT_SUPPORTED=10, NV_ERR_NO_MEMORY, NV_ERR_INVALID_ARGUMENT,
 NV_ERR_INVALID_BASE, NV_ERR_INVALID_OBJECT_HANDLE, NV_ERR_INVALID_STATE,
 NV_ERR_INVALID_FLAGS, NVOS46_FLAGS_P2P_ENABLE_NOSLI=1000 };
enum { ADDR_SYSMEM=1, ADDR_FBMEM, ADDR_FABRIC_MC, ADDR_FABRIC_V2, ADDR_UNKNOWN,
 NV_MEMORY_CACHED, NV_MEMORY_UNCACHED, NV_MEMORY_CONTIGUOUS,
 MEMDESC_FLAGS_NONE=0, MEMDESC_FLAGS_SKIP_IOMMU_MAPPING=1,
 MEMDESC_FLAGS_EXT_PAGE_ARRAY_MEM=2, MEMDESC_FLAGS_MEMORY_TYPE_DISPLAY_NISO=4,
 MEMDESC_FLAGS_ENCRYPTED=8, MEMDESC_FLAGS_MAP_FORCE_COMPRESSED_MAP=16,
 MEMDESC_FLAGS_SET_KIND=32, AT_CPU=0, NV_RM_PAGE_SIZE=4096,
 MEMDESC_FLAGS_SKIP_RESOURCE_COMPUTE=64, AT_GPU=1, RM_PAGE_MASK=4095,
 NV_PROTECT_READ_WRITE=0, FB_IS_KIND_DISALLOW_PLC=0, FB_IS_KIND_SUPPORTED=0,
 RM_DEFAULT_PTE_KIND=0, SLI_LOOP_FLAGS_BC_ONLY=0,
 SLI_LOOP_FLAGS_IGNORE_REENTRANCY=0, LEVEL_ERROR=0, LEVEL_INFO=0 };
enum { FLAG_CONTIG=1, FLAG_SYNCPOINT=2, FLAG_NISO=4, FLAG_KERNEL=8,
 FLAG_KIND_INVALID=16, FLAG_KIND_OVERRIDE=32 };
#define NV_PRINTF(...) ((void)0)
#define NV_ASSERT(x) do { if (!(x)) ++modelErrors; } while (0)
#define NV_ASSERT_OR_RETURN(x,s) do { if (!(x)) return (s); } while (0)
#define NV_ASSERT_OK(x) NV_ASSERT((x)==NV_OK)
#define NV_ASSERT_OK_OR_GOTO(s,x,label) do { (s)=(x); if ((s)!=NV_OK) goto label; } while (0)
#define FLD_TEST_DRF(d,r,f,c,v) field_test(#f,#c,(v))
#define DRF_VAL(d,r,f,v) ((void)(v), field_value(#f))
#define DRF_DEF(d,r,f,c) 0
#define NV_IS_ALIGNED64(x,a) (((x)&((a)-1))==0)
#define NV_ALIGN_UP64(x,a) (((x)+(a)-1)&~((NvU64)(a)-1))
#define NV_RM_PAGES_TO_OS_PAGES(x) (x)
#define IS_DISCONTIG_AND_DYNGRAN_ENABLED(x) ((void)(x),dynamicGranularity)
#define NV_SOC_IS_NISO_IOMMU_PRESENT(x) ((void)(x),hasNisoIommu)
#define SLI_LOOP_START(x)
#define SLI_LOOP_END
#define RMCFG_CLASS_NV50_P2P 1
typedef struct OBJGPU { struct { NvU32 iovaspaceId; } busInfo; } OBJGPU;
typedef struct nv_state_t { int unused; } nv_state_t;
typedef struct MEMORY_DESCRIPTOR {
 OBJGPU *pGpu; NvU64 Size; NvU64 PageCount;
 NvU64 pte[4]; NvU32 flags; void *privateData;
 void (*release)(struct MEMORY_DESCRIPTOR *);
 int alive, registered, iova, addressSpace;
} MEMORY_DESCRIPTOR;
typedef MEMORY_DESCRIPTOR *PMEMORY_DESCRIPTOR;
typedef struct { NvU64 iovaArray[1]; } IOVAMAPPING;
typedef struct { MEMORY_DESCRIPTOR *pMemDesc; NvBool bRpcAlloc; } Memory;
typedef struct { Memory base; NvBool bAllowUnicastMapping; NvHandle hVASpace; } VirtualMemory;
typedef struct { NvHandle hClient; } RsClient;
typedef struct { Memory *pResource; NvHandle hResource; } RsResourceRef;
typedef struct CLI_DMA_MAPPING_INFO {
 MEMORY_DESCRIPTOR *pMemDesc; NvU64 DmaOffset; NvU32 Flags;
 void *KernelVAddr[1]; void *KernelPriv; NvBool bP2P;
} CLI_DMA_MAPPING_INFO;
typedef int MemoryManager;
typedef int VirtMemAllocator;
typedef int OBJVASPACE;
typedef struct {
 OBJGPU *pGpu,*pSrcGpu; RsResourceRef *pMemoryRef;
 NvHandle hBroadcastDevice,hMemoryDevice; NvU32 gpuMask;
 NvU64 offset,length; NvU32 flags,flags2; MEMORY_DESCRIPTOR *pSrcMemDesc;
 NvU64 *pDmaOffset; NvBool bFlaMapping,bSubdeviceHandleProvided; NvU32 kindOverride;
} RS_RES_MAP_TO_PARAMS;
typedef struct {
 OBJVASPACE *pVas; OBJGPU *pPeerGpu; MEMORY_DESCRIPTOR *pPeerMemDesc;
 NvU32 flags; NvU64 offset,length; CLI_DMA_MAPPING_INFO *pDmaMappingInfo;
 MEMORY_DESCRIPTOR *pMemDescOut; NvU32 flagsOut; NvU64 offsetOut;
} DMA_BAR1P2P_MAPPING_PRARAMS;
typedef struct {
 NvHandle hClient,hDevice,hDma,hMemory; NvU64 offset,length,dmaOffset;
 NvU32 flags,kindOverride;
} NVOS46_PARAMETERS;
enum Fault { NONE,CREATE,TEMP_ALLOC,REGISTER,ALLOC_FIELDS,IOVA_MAP,VASPACE,
 INTERMAP_CREATE,BAR_ALLOC,SUBMEM_CREATE,DMA_ALLOC,INTERMAP_REGISTER,KERNEL_MAP,RPC };
static enum Fault failAt;
static int modelErrors,checks,failures,destroyCalls,unregisterCalls,unmapCalls;
static int mapCalls,tempAllocs,tempFrees,descriptorsCreated,registeredMaps;
static NvBool dynamicGranularity,hasNisoIommu,indirectPeer,bar1P2p,splitVas;
static NvU32 fieldP2p;
static const NvU64 os_page_size=4096;
static const NvU32 os_page_shift=12;
static nv_state_t nvFixture;
static RsClient clientFixture={3};
static int unusedFixture;
static MEMORY_DESCRIPTOR descriptors[16];
static CLI_DMA_MAPPING_INFO dmaMapping;
static IOVAMAPPING iovaMapping={{0x10000}};
static NV_STATUS fault(enum Fault f) { return failAt==f ? 100+(int)f : NV_OK; }
static NvBool field_test(const char *field,const char *value,NvU32 flags)
{
 (void)value;
 if (!strcmp(field,"_PHYSICALITY")) return (flags&FLAG_CONTIG)!=0;
 if (!strcmp(field,"_ALLOC_TYPE_SYNCPOINT")) return (flags&FLAG_SYNCPOINT)!=0;
 if (!strcmp(field,"_ALLOC_NISO_DISPLAY")) return (flags&FLAG_NISO)!=0;
 if (!strcmp(field,"_KERNEL_MAPPING")) return (flags&FLAG_KERNEL)!=0;
 if (!strcmp(field,"_PAGE_KIND_OVERRIDE")) return (flags&(FLAG_KIND_INVALID|FLAG_KIND_OVERRIDE))!=0;
 if (!strcmp(field,"_PAGE_KIND")) return (flags&FLAG_KIND_INVALID)!=0;
 return NV_FALSE;
}
static NvU32 field_value(const char *field)
 { return !strcmp(field,"_P2P_ENABLE") ? fieldP2p : 0; }
#define NV_GET_NV_STATE(g) ((void)(g),&nvFixture)
#define staticCast(p,t) ((t *)(p))
#define dynamicCast(p,t) ((t *)(p))
#define RES_GET_CLIENT(p) ((void)(p),&clientFixture)
#define RES_GET_HANDLE(p) ((void)(p),4U)
#define GPU_GET_MEMORY_MANAGER(g) ((void)(g),&unusedFixture)
#define GPU_GET_DMA(g) ((void)(g),&unusedFixture)
#define GPU_GET_KERNEL_BUS(g) ((void)(g),&unusedFixture)
#define IS_VIRTUAL(g) ((void)(g),NV_FALSE)
#define IS_GSP_CLIENT(g) ((void)(g),NV_TRUE)
#define NV_RM_RPC_MAP_MEMORY_DMA(g,p,s) do { (void)(g); (void)(p); (s)=fault(RPC); } while (0)
static void *portMemAllocNonPaged(size_t bytes)
 { if (failAt==TEMP_ALLOC) return NULL; ++tempAllocs; return calloc(1,bytes); }
static void portMemFree(void *p) { if(p){++tempFrees;free(p);} }
static NV_STATUS memdescCreate(MEMORY_DESCRIPTOR **out,OBJGPU *gpu,NvU64 size,
 NvU64 alignment,int contiguous,int addressSpace,NvU32 cache,NvU64 flags)
{
 (void)alignment;(void)contiguous;(void)cache;
 NV_STATUS s=fault(CREATE); if(s)return s;
 MEMORY_DESCRIPTOR *p=&descriptors[descriptorsCreated++]; memset(p,0,sizeof(*p));
 p->alive=1;p->pGpu=gpu;p->Size=size;p->PageCount=size/4096;
 p->flags=(NvU32)flags;p->addressSpace=addressSpace;*out=p;return NV_OK;
}
static void memdescSetMemData(MEMORY_DESCRIPTOR *p,void *priv,void (*release)(MEMORY_DESCRIPTOR *))
 { if(!p||!p->alive){++modelErrors;return;}p->privateData=priv;p->release=release; }
static void memdescSetFlag(MEMORY_DESCRIPTOR *p,NvU32 f,NvBool value)
 { if(value)p->flags|=f;else p->flags&=~f; }
static NvBool memdescGetFlag(MEMORY_DESCRIPTOR *p,NvU32 f) { return (p->flags&f)!=0; }
static NvU64 *memdescGetPteArray(MEMORY_DESCRIPTOR *p,int at) { (void)at;return p->pte; }
static NvU32 memdescGetCpuCacheAttrib(MEMORY_DESCRIPTOR *p) { (void)p;return NV_MEMORY_CACHED; }
static NV_STATUS nv_register_phys_pages(nv_state_t *nv,NvU64 *phys,NvU64 pages,NvU32 cache,void **out)
 { (void)nv;(void)phys;(void)pages;(void)cache;NV_STATUS s=fault(REGISTER);if(s)return s;
   *out=&unusedFixture;return NV_OK; }
static void nv_unregister_phys_pages(nv_state_t *nv,void *p)
 { (void)nv;if(p!=&unusedFixture)++modelErrors;++unregisterCalls; }
static void osDestroyOsDescriptorFromPhysAddr(MEMORY_DESCRIPTOR *p)
 { nv_unregister_phys_pages(&nvFixture,p->privateData);p->privateData=NULL; }
static NV_STATUS memdescSetAllocSizeFields(MEMORY_DESCRIPTOR *p,NvU64 size,NvU64 gran)
 { (void)p;(void)size;(void)gran;return fault(ALLOC_FIELDS); }
static NV_STATUS memdescMapIommu(MEMORY_DESCRIPTOR *p,NvU32 id)
 { (void)id;++mapCalls;NV_STATUS s=fault(IOVA_MAP);if(s)return s;p->iova=1;return NV_OK; }
static void memdescUnmapIommu(MEMORY_DESCRIPTOR *p,NvU32 id)
 { (void)id;++unmapCalls;if(!p||!p->alive||!p->iova){++modelErrors;return;}p->iova=0; }
static void memdescDestroy(MEMORY_DESCRIPTOR *p)
 { if(!p)return;++destroyCalls;if(!p->alive){++modelErrors;return;}
   if(p->iova)memdescUnmapIommu(p,0);if(p->release)p->release(p);p->alive=0; }
static NvBool kbusHasPcieBar1P2PMapping_HAL(OBJGPU *a,int *b,OBJGPU *c,int *d)
 { (void)a;(void)b;(void)c;(void)d;return bar1P2p; }
static NV_STATUS vaspaceGetByHandleOrDeviceDefault(RsClient *c,NvHandle a,NvHandle b,OBJVASPACE **out)
 { (void)c;(void)a;(void)b;*out=&unusedFixture;return fault(VASPACE); }
static NV_STATUS intermapCreateDmaMapping(RsClient *c,VirtualMemory *v,CLI_DMA_MAPPING_INFO **out,NvU32 f,NvU32 f2)
 { (void)c;(void)v;(void)f;(void)f2;NV_STATUS s=fault(INTERMAP_CREATE);if(s)return s;
   memset(&dmaMapping,0,sizeof(dmaMapping));*out=&dmaMapping;return NV_OK; }
static NV_STATUS dmaAllocBar1P2PMapping_HAL(OBJGPU *g,VirtMemAllocator *d,DMA_BAR1P2P_MAPPING_PRARAMS *p)
 { (void)g;(void)d;p->pMemDescOut=p->pPeerMemDesc;p->flagsOut=p->flags;p->offsetOut=p->offset;return fault(BAR_ALLOC); }
static MEMORY_DESCRIPTOR *memdescGetMemDescFromGpu(MEMORY_DESCRIPTOR *p,OBJGPU *g) { (void)g;return p; }
static NvU32 memdescGetAddressSpace(MEMORY_DESCRIPTOR *p) { return (NvU32)p->addressSpace; }
static NvU64 memdescGetSize(MEMORY_DESCRIPTOR *p) { return p->Size; }
static NvU64 memdescGetPhysAddr(MEMORY_DESCRIPTOR *p,int at,NvU64 offset)
 { (void)at;return p->pte[0]+offset; }
static void memdescDescribe(MEMORY_DESCRIPTOR *p,int at,NvU64 base,NvU64 size)
 { p->addressSpace=at;p->pte[0]=base;p->Size=size; }
static IOVAMAPPING *memdescGetIommuMap(MEMORY_DESCRIPTOR *p,NvU32 id)
 { (void)id;return p->iova?&iovaMapping:NULL; }
static NvBool gpumgrCheckIndirectPeer(OBJGPU *g,OBJGPU *s) { (void)g;(void)s;return indirectPeer; }
static NV_STATUS memdescCreateSubMem(MEMORY_DESCRIPTOR **out,MEMORY_DESCRIPTOR *src,OBJGPU *g,NvU64 offset,NvU64 size)
 { (void)offset;NV_STATUS s=fault(SUBMEM_CREATE);if(s)return s;
   return memdescCreate(out,g,size,0,1,src->addressSpace,0,0); }
static NvBool memmgrIsKindCompressible(MemoryManager *m,NvU32 k) { (void)m;(void)k;return NV_FALSE; }
static NvU32 memdescGetPteKind(MEMORY_DESCRIPTOR *p) { (void)p;return 0; }
static NvBool memmgrIsKind_HAL(MemoryManager *m,int t,NvU32 k) { (void)m;(void)t;(void)k;return NV_TRUE; }
static NvU32 memmgrGetCompressedKind_HAL(MemoryManager *m,NvU32 k,int z) { (void)m;(void)z;return k; }
static NvBool memmgrComprSupported(MemoryManager *m,NvU32 at) { (void)m;(void)at;return NV_TRUE; }
static NvU32 memmgrGetHwPteKindFromSwPteKind_HAL(OBJGPU *g,MemoryManager *m,NvU32 k) { (void)g;(void)m;return k; }
static NvU32 memmgrGetUncompressedKind_HAL(OBJGPU *g,MemoryManager *m,NvU32 k,int z) { (void)g;(void)m;(void)z;return k; }
static void memdescSetPteKind(MEMORY_DESCRIPTOR *p,NvU32 k) { (void)p;(void)k; }
static NvBool gpuIsSplitVasManagementServerClientRmEnabled(OBJGPU *g) { (void)g;return splitVas; }
static NV_STATUS dmaAllocMap(OBJGPU *g,VirtMemAllocator *d,OBJVASPACE *v,VirtualMemory *vm,Memory *m,CLI_DMA_MAPPING_INFO *map)
 { (void)g;(void)d;(void)v;(void)vm;(void)m;map->DmaOffset=8192;return fault(DMA_ALLOC); }
static void dmaFreeMap(OBJGPU *g,VirtMemAllocator *d,OBJVASPACE *v,VirtualMemory *vm,CLI_DMA_MAPPING_INFO *m,NvU32 f)
 { (void)g;(void)d;(void)v;(void)vm;(void)m;(void)f; }
static NV_STATUS intermapRegisterDmaMapping(RsClient *c,VirtualMemory *v,CLI_DMA_MAPPING_INFO *m,NvU64 o,NvU32 mask)
 { (void)c;(void)v;(void)m;(void)o;(void)mask;NV_STATUS s=fault(INTERMAP_REGISTER);if(!s)++registeredMaps;return s; }
static NV_STATUS intermapDelDmaMapping(RsClient *c,VirtualMemory *v,NvU64 o,NvU32 mask)
 { (void)c;(void)v;(void)o;(void)mask;if(registeredMaps!=1)++modelErrors;else --registeredMaps;return NV_OK; }
static void intermapFreeDmaMapping(CLI_DMA_MAPPING_INFO *m) { (void)m; }
static NvU32 gpumgrGetSubDeviceInstanceFromGpu(OBJGPU *g) { (void)g;return 0; }
static OBJGPU *gpumgrGetParentGPU(OBJGPU *g) { return g; }
static NV_STATUS memdescMapOld(MEMORY_DESCRIPTOR *p,NvU64 offset,NvU64 size,NvBool kernel,NvU32 protect,void **addr,void **priv)
 { (void)p;(void)offset;(void)size;(void)kernel;(void)protect;NV_STATUS s=fault(KERNEL_MAP);
   if(!s){*addr=&unusedFixture;*priv=&unusedFixture;}return s; }
static void memdescUnmapOld(MEMORY_DESCRIPTOR *p,NvBool k,void *a,void *priv) { (void)p;(void)k;(void)a;(void)priv; }
static NV_STATUS _virtmemAllocKernelMapping(OBJGPU *g,OBJVASPACE *v,CLI_DMA_MAPPING_INFO *m,NvU64 o,NvU64 n,Memory *mem)
 { (void)g;(void)v;(void)m;(void)o;(void)n;(void)mem;return fault(KERNEL_MAP); }
static void _virtmemFreeKernelMapping(OBJGPU *g,CLI_DMA_MAPPING_INFO *m) { (void)g;(void)m; }
static NvBool IsSLIEnabled(OBJGPU *g) { (void)g;return NV_FALSE; }
static void dmaFreeBar1P2PMapping_HAL(VirtMemAllocator *d,CLI_DMA_MAPPING_INFO *m) { (void)d;(void)m; }

#include "exact-memory-unwind-bodies.inc"

static void check(int value,const char *label)
 { ++checks;if(!value){++failures;fprintf(stderr,"check failed: %s\n",label);} }
static void reset(void)
 { failAt=NONE;modelErrors=destroyCalls=unregisterCalls=unmapCalls=mapCalls=0;
   tempAllocs=tempFrees=descriptorsCreated=registeredMaps=0;
   dynamicGranularity=hasNisoIommu=NV_TRUE;indirectPeer=NV_TRUE;
   bar1P2p=splitVas=NV_FALSE;fieldP2p=0;memset(descriptors,0,sizeof(descriptors)); }
static void physical_controls(void)
{
 OBJGPU gpu={{7}};
 for(int gran=0;gran!=2;++gran)
 for(enum Fault f=CREATE;f<=IOVA_MAP;++f)
 {
  reset();dynamicGranularity=gran;failAt=f;
  MEMORY_DESCRIPTOR borrowed={.alive=1};void *borrowedPrivate=&borrowed;
  MEMORY_DESCRIPTOR *out=&borrowed;void *priv=borrowedPrivate;NvU64 limit=8191;
  NV_STATUS s=osCreateOsDescriptorFromPhysAddr(&gpu,8192,3,FLAG_CONTIG,&limit,&out,&priv);
  check(s==(f==TEMP_ALLOC?NV_ERR_NO_MEMORY:100+(int)f),"physical original error preserved");
  check(out==&borrowed&&priv==borrowedPrivate&&borrowed.alive,"physical outputs unpublished on failure");
  check(destroyCalls==(f==CREATE?0:1)&&modelErrors==0,"physical new descriptor destroyed once");
  check(unregisterCalls==(f>REGISTER?1:0),"physical only successful registration released");
  check(tempAllocs==tempFrees,"physical temporary array balanced");
 }
 reset();failAt=REGISTER;MEMORY_DESCRIPTOR *out=NULL;void *priv=NULL;NvU64 limit=8191;
 NV_STATUS s=osCreateOsDescriptorFromPhysAddr(&gpu,8192,3,FLAG_CONTIG,&limit,&out,&priv);
 /* Exact original external-root catch fragment is emitted by the generator. */
 exactExternalRootCatch(&out);
 check(s!=NV_OK&&out==NULL&&destroyCalls==1&&modelErrors==0,"external root catch cannot destroy failed publication twice");
 for(int skip=0;skip!=2;++skip)
 {
  reset();out=NULL;priv=NULL;limit=8191;hasNisoIommu=!skip;
  s=osCreateOsDescriptorFromPhysAddr(&gpu,8192,3,FLAG_CONTIG|(skip?FLAG_SYNCPOINT:0),&limit,&out,&priv);
  check(s==NV_OK&&out&&out->alive&&priv==&unusedFixture,"physical success publishes both outputs");
  check(mapCalls==!skip&&destroyCalls==0&&unregisterCalls==0,"physical success leaves final owner intact");
  memdescDestroy(out);
  check(destroyCalls==1&&unregisterCalls==1&&modelErrors==0,"physical published owner has one release");
 }
}
static void virtual_case(enum Fault f,NvBool isIndirect,NvBool rpc,NvBool kernel,NvBool bar,NvBool invalidKind)
{
 reset();failAt=f;indirectPeer=isIndirect;bar1P2p=bar;fieldP2p=bar;
 OBJGPU gpu={{7}},srcGpu={{8}};
 MEMORY_DESCRIPTOR src={.pGpu=&srcGpu,.Size=8192,.alive=1,.addressSpace=ADDR_FBMEM};
 MEMORY_DESCRIPTOR virtualDesc={.pGpu=&gpu,.Size=8192,.alive=1};
 Memory srcMemory={&src,NV_FALSE};RsResourceRef ref={&srcMemory,9};
 VirtualMemory virtualMemory={{&virtualDesc,rpc},NV_TRUE,5};NvU64 offset=4096;
 RS_RES_MAP_TO_PARAMS params={.pGpu=&gpu,.pSrcGpu=&srcGpu,.pMemoryRef=&ref,
  .hBroadcastDevice=6,.hMemoryDevice=10,.gpuMask=1,.length=4096,
  .flags=(kernel?FLAG_KERNEL:0)|(invalidKind?FLAG_KIND_INVALID:0),
  .pSrcMemDesc=&src,.pDmaOffset=&offset};
 NV_STATUS s=virtmemMapTo_IMPL(&virtualMemory,&params);
 const NvBool beforeMap=f==VASPACE||f==INTERMAP_CREATE||f==BAR_ALLOC||f==SUBMEM_CREATE||invalidKind;
 const NvBool mapped=isIndirect&&!beforeMap&&f!=IOVA_MAP;
 check(s==(invalidKind?NV_ERR_INVALID_ARGUMENT:f==NONE?NV_OK:100+(int)f),"virtual status preserved");
 check(modelErrors==0,"virtual no absent IOVA cleanup or double destroy");
 check(unmapCalls==((s!=NV_OK&&mapped)?1:0),"virtual failure balances only acquired IOVA");
 if(s==NV_OK){check(dmaMapping.pMemDesc&&dmaMapping.pMemDesc->alive,"virtual success retains mapping owner");
  memdescDestroy(dmaMapping.pMemDesc);}
 else check(dmaMapping.pMemDesc==NULL,"virtual failed descriptor not published");
}
static void peer_bar_controls(void)
{
 OBJGPU local={{7}},remote={{8}};
 reset();failAt=CREATE;MEMORY_DESCRIPTOR *out=NULL;
 NvU64 address=kbusSetupPeerBarAccess_IMPL(&local,&remote,8192,4096,&out);
 check(address==~0ULL&&out==NULL&&destroyCalls==0,"peer failed constructor has no owner to destroy");
 reset();failAt=IOVA_MAP;out=NULL;
 address=kbusSetupPeerBarAccess_IMPL(&local,&remote,8192,4096,&out);
 check(address==~0ULL&&out==NULL&&destroyCalls==1&&modelErrors==0,"peer failed new map destroys only new unpublished descriptor");
 for(int oldMapping=0;oldMapping!=2;++oldMapping)
 {
  reset();failAt=IOVA_MAP;
  MEMORY_DESCRIPTOR borrowed={.pGpu=&local,.Size=4096,.pte={8192},.alive=1,
   .iova=oldMapping,.addressSpace=ADDR_SYSMEM};out=&borrowed;
  address=kbusSetupPeerBarAccess_IMPL(&local,&remote,8192,4096,&out);
  check(address==~0ULL&&out==&borrowed&&borrowed.alive,"peer map failure preserves borrowed live descriptor");
  check(destroyCalls==0&&unmapCalls==0&&borrowed.iova==oldMapping,"peer map failure leaves prior mapping owned");
  failAt=NONE;
  address=kbusSetupPeerBarAccess_IMPL(&local,&remote,8192,4096,&out);
  check(address==iovaMapping.iovaArray[0]&&out==&borrowed&&borrowed.alive,"peer borrowed descriptor can retry successfully");
  memdescDestroy(out);
  check(destroyCalls==1&&unmapCalls==1&&modelErrors==0,"peer later owner teardown releases borrowed descriptor once");
 }
 reset();out=NULL;
 address=kbusSetupPeerBarAccess_IMPL(&local,&remote,8192,4096,&out);
 check(address==iovaMapping.iovaArray[0]&&out&&out->alive&&destroyCalls==0,"peer successful new map publishes owner");
 memdescDestroy(out);check(destroyCalls==1&&unmapCalls==1&&modelErrors==0,"peer successful new owner tears down once");
 reset();out=NULL;
 address=kbusSetupPeerBarAccess_IMPL(&local,&local,8192,4096,&out);
 check(address==8192&&out&&out->alive&&mapCalls==0,"peer same GPU identity route acquires no IOVA");
 memdescDestroy(out);check(destroyCalls==1&&unmapCalls==0&&modelErrors==0,"peer identity descriptor owner tears down once");
}
int main(void)
{
 physical_controls();
 virtual_case(VASPACE,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(INTERMAP_CREATE,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(BAR_ALLOC,NV_TRUE,NV_FALSE,NV_FALSE,NV_TRUE,NV_FALSE);
 virtual_case(SUBMEM_CREATE,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(NONE,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE,NV_TRUE);
 virtual_case(IOVA_MAP,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(DMA_ALLOC,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(INTERMAP_REGISTER,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(KERNEL_MAP,NV_TRUE,NV_FALSE,NV_TRUE,NV_FALSE,NV_FALSE);
 virtual_case(RPC,NV_TRUE,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(INTERMAP_REGISTER,NV_TRUE,NV_TRUE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(KERNEL_MAP,NV_TRUE,NV_TRUE,NV_TRUE,NV_FALSE,NV_FALSE);
 virtual_case(DMA_ALLOC,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE,NV_FALSE);
 virtual_case(NONE,NV_TRUE,NV_FALSE,NV_TRUE,NV_FALSE,NV_FALSE);
 peer_bar_controls();
 printf("{\"format\":1,\"status\":\"%s\",\"failures\":%d,\"checks\":%d,"
  "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,"
  "\"actual_complete_function_bodies\":true,\"modeled_dependencies\":true}\n",
  failures?"failed":"passed",failures,checks);
 return failures?1:0;
}
