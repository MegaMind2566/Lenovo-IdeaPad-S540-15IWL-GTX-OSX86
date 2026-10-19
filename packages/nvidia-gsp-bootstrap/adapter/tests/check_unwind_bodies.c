/* SPDX-License-Identifier: MIT */
/* Fault control for exact extracted prospective original adapter bodies.
 * All GPU, locks, runtime and resource owners below are explicit models.
 * This checks changed control flow; it does not execute a GPU or a kernel.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t NvU32;
typedef uint64_t NvU64;
typedef int NvBool;
typedef int NV_STATUS;
#define NV_TRUE 1
#define NV_FALSE 0
#define NV_OK 0
#define NV_ERR_INVALID_STATE 100
#define NV_ERR_NOT_SUPPORTED 101
#define NV_ERR_NO_MEMORY 102
#define NV_ERR_STATE_IN_USE 103
#define NV_ERR_NOT_READY 104
#define NV_U32_MAX UINT32_MAX
#define NV_API_CALL
#define NVCPU_IS_X86_64 1
#define GPUS_LOCK_FLAGS_NONE 0
#define RM_LOCK_MODULES_DESTROY 0
#define RM_LOCK_MODULES_INIT 1
#define API_LOCK_FLAGS_NONE 0
#define RMAPI_GPU_LOCK_INTERNAL 0
#define GPU_STATE_DEFAULT 0
#define THREAD_STATE_FLAGS_NONE 0
#define INTERRUPT_TYPE_DISABLED 0
#define NV_IOVA_DOMAIN_NONE 0
#define IO_VASPACE_A 0
#define LEVEL_ERROR 0
#define LEVEL_INFO 0
#define NV_PRINTF(...) ((void)0)
#define NV_ASSERT(x) assert(x)
#define NVBIT(x) (1U << (x))
enum { NV_INIT_FLAG_GPUMGR_ATTACH=1U, NV_INIT_FLAG_CORE_LOGIC=2U,
 NV_INIT_FLAG_SCALABILITY=4U,NV_INIT_FLAG_FIFO_WATCHDOG=8U,
 NV_INIT_FLAG_GPU_STATE_LOAD=16U,NV_INIT_FLAG_GPU_STATE=32U,
 NV_INIT_FLAG_DMA=64U, NV_INIT_FLAG_HAL=128U };
enum { NV_FLAG_IN_RECOVERY=1U,NV_FLAG_PERSISTENT_SW_STATE=2U,NV_FLAG_SOC_DISPLAY=4U };
enum { PDB_PROP_GPU_CLKS_IN_TEGRA_SOC=1,
 PDB_PROP_GPU_IN_SECONDARY_BUS_RESET=2,PDB_PROP_GPU_IN_FULLCHIP_RESET=3,
 PDB_PROP_GPU_IN_TIMEOUT_RECOVERY=4 };
typedef struct OBJGPU OBJGPU;
struct OBJGPU { NvU32 gpuInstance; NvBool (*getProperty)(OBJGPU *,int);
 void (*setProperty)(OBJGPU *,int,NvBool); };
typedef struct { OBJGPU *pGpu; NvU32 flags; } nv_priv_t;
typedef struct { void *map; NvU64 cpu_address,size; } registers_t;
typedef struct { nv_priv_t *priv; struct { NvU32 hClient,hDevice,hSubDevice,hI2C,hDisp; } rmapi;
 struct { uintptr_t cpu_address; size_t size; } ud;
 NvBool is_external_gpu,client_managed_console,sysmem_mapped_console;
 NvU32 flags; NvU32 iovaspace_id; void *queue; registers_t *regs,*fb;
 registers_t bars[1];NvU32 disp_sw_soc_chip_id,cpu_numa_node_id;
 struct { NvBool iso_iommu_present,niso_iommu_present; } iommus;
 NvBool request_fw_client_rm;struct { NvU32 domain,bus,slot; } pci_info;
 } nv_state_t;
typedef int OBJCL; typedef int OBJOS; typedef int OBJSYS;
typedef int OBJVMM; typedef int OBJVASPACE;
typedef int Intr; typedef int nvidia_stack_t; typedef int THREAD_STATE_NODE;
#define NV_GET_NV_PRIV(nv) ((nv)->priv)
#define NV_GET_NV_PRIV_PGPU(nv) ((nv)->priv->pGpu)
#define SYS_GET_INSTANCE() (&systemFixture)
#define SYS_GET_CL(sys) ((void)(sys), hasCoreClass ? &coreFixture : NULL)
#define SYS_GET_OS(sys) ((void)(sys), &osFixture)
#define SYS_GET_VMM(sys) ((void)(sys), &vmmFixture)
#define GPU_GET_OS(gpu) ((void)(gpu), &osFixture)
#define GPU_GET_INTR(gpu) ((void)(gpu), &intrFixture)
#define GPU_GET_KERNEL_WATCHDOG(gpu) ((void)(gpu), &watchdogFixture)
#define GPU_GET_KERNEL_RC(gpu) ((void)(gpu), NULL)
#define GPU_GET_DCECLIENTRM(gpu) ((void)(gpu), NULL)
#define IS_DCE_CLIENT(gpu) ((void)(gpu), isDce)
#define IS_GSP_CLIENT(gpu) ((void)(gpu), NV_TRUE)
#define GPU_GET_KERNEL_GSP(gpu) ((void)(gpu), NULL)
#define NV_IS_SOC_DISPLAY_DEVICE(nv) (((nv)->flags&NV_FLAG_SOC_DISPLAY)!=0)
#define NV_GPU_BAR_INDEX_IMEM 0
typedef int GPUHWREG;
typedef struct {
 struct { NvBool specified;NvU32 socChipId0,iovaspaceId; } socDeviceArgs;
 NvU64 fbPhysAddr,devPhysAddr,instPhysAddr,regLength,fbLength,instLength;
 GPUHWREG *fbBaseAddr,*regBaseAddr,*instBaseAddr;
 NvU32 intLine,iovaspaceId,cpuNumaNodeId,nvDomainBusDeviceFunc;
 NvBool bRequestFwClientRm;void *pOsAttachArg;
} GPUATTACHARG;
typedef struct { int initStatus;NV_STATUS rmStatus;int line; } UNIX_STATUS;
#define RM_SET_ERROR(status,error) do { (status).initStatus=(error);(status).line=__LINE__; } while(0)
enum { RM_INIT_GPU_GPUMGR_ALLOC_GPU_FAILED=1001,RM_INIT_GPU_GPUMGR_CREATE_DEV_FAILED,
 RM_INIT_GPU_GPUMGR_ATTACH_GPU_FAILED,RM_INIT_FIRMWARE_INIT_FAILED };
typedef struct { NvU32 deviceId; } NV0080_ALLOC_PARAMETERS;
typedef struct { NvU32 subDeviceId; } NV2080_ALLOC_PARAMETERS;
enum { NV01_NULL_OBJECT,NV01_ROOT,NV01_DEVICE_0,NV20_SUBDEVICE_0,NV40_I2C,NV04_DISPLAY_COMMON };
#define NV_ENTER_RM_RUNTIME(sp,fp) do { (void)(sp); (fp)=NULL; ++runtimeDepth; } while(0)
#define NV_EXIT_RM_RUNTIME(sp,fp) do { (void)(sp); (void)(fp); --runtimeDepth; } while(0)
enum Fault { NONE,VISIBILITY,RM_GPU_LOCK,RM_API_FREE,CLIENT_LOCK,GPU_LOCK,
 CORE,SCALABILITY,UNLOAD,DESTROY,DCE,DETACH,DEVICE_DESTROY,DMA_LOOKUP,REGISTERS,
 FIRST_FLUSH,API_LOCK,LAST_FLUSH,CLEANUP,
 MAP_ID,MAP_LOCK,MAP_CREATE,MAP_ARGUMENT,MAP_ATTACH,
 ALLOC_ROOT,ALLOC_DEVICE,ALLOC_SUBDEVICE,ALLOC_I2C,ALLOC_DISPLAY,GSP_INIT };
static enum Fault failAt;
static int systemFixture,coreFixture,osFixture,intrFixture,watchdogFixture;
static int vmmFixture,vaspaceFixture;
static NvBool hasCoreClass,isDce;
static int gpuLockDepth,apiLockDepth,clientDepth,visibilityDepth,runtimeDepth,threadDepth;
static NvU32 gpuLockCalls,flushCalls,detachCalls,deviceDestroyCalls,dmaCalls,
 registerCalls,clearCalls,gpuLockFreeCalls,coreCalls,scalabilityCalls,unloadCalls,
 destroyCalls,apiFreeCalls,disableIntrCalls,cleanupCalls;
static NvU32 mapCreates,mapArguments,mapAttaches,mapLockAllocs,apiAllocCalls;
static NvU32 gspInitCalls;
static NvBool failPendingDestroy,modelGpuLockOwned;
static NvU32 currentInstance;
static NvBool modelDeviceAlive,modelGpuAttached,modelVaspaceAlive;
static NV_STATUS fault(enum Fault f)
 { return failAt==f||(f==DEVICE_DESTROY&&failPendingDestroy) ? 200+(int)f : NV_OK; }
static NV_STATUS gpumgrThreadEnableExpandedGpuVisibility(void)
 { NV_STATUS s=fault(VISIBILITY); if(!s)++visibilityDepth; return s; }
static void gpumgrThreadDisableExpandedGpuVisibility(void) { assert(visibilityDepth==1);--visibilityDepth; }
static NV_STATUS rmGpuLocksAcquire(int a,int b)
 { (void)a;(void)b;++gpuLockCalls;NV_STATUS s=fault(gpuLockCalls==1?RM_GPU_LOCK:GPU_LOCK);
   if(!s)++gpuLockDepth;return s; }
static void rmGpuLocksRelease(int a,void *b) { (void)a;(void)b;assert(gpuLockDepth==1);--gpuLockDepth; }
typedef struct RM_API { NV_STATUS (*Free)(struct RM_API *,NvU32,NvU32);
 NV_STATUS (*AllocWithHandle)(struct RM_API *,NvU32,NvU32,NvU32,NvU32,void *,NvU32);
 NV_STATUS (*Alloc)(struct RM_API *,NvU32,NvU32,NvU32 *,NvU32,void *,NvU32);
} RM_API;
static NV_STATUS apiFree(RM_API *api,NvU32 a,NvU32 b)
 { (void)api;(void)a;(void)b;++apiFreeCalls;return fault(RM_API_FREE); }
static NV_STATUS apiAllocRoot(RM_API *a,NvU32 b,NvU32 c,NvU32 d,NvU32 e,void *out,NvU32 bytes)
 { (void)a;(void)b;(void)c;(void)d;(void)e;assert(bytes==sizeof(NvU32));++apiAllocCalls;
   NV_STATUS s=fault(ALLOC_ROOT);if(!s)*(NvU32 *)out=7;return s; }
static NV_STATUS apiAlloc(RM_API *a,NvU32 b,NvU32 c,NvU32 *out,NvU32 type,void *p,NvU32 bytes)
 { (void)a;(void)b;(void)c;(void)p;(void)bytes;++apiAllocCalls;
   enum Fault point=type==NV01_DEVICE_0?ALLOC_DEVICE:type==NV20_SUBDEVICE_0?ALLOC_SUBDEVICE:
     type==NV40_I2C?ALLOC_I2C:ALLOC_DISPLAY;
   NV_STATUS s=fault(point);if(!s)*out=10+apiAllocCalls;return s; }
static RM_API *rmapiGetInterface(int type)
 { (void)type;static RM_API api={apiFree,apiAllocRoot,apiAlloc};return &api; }
static void portMemSet(void *p,int c,size_t bytes) { memset(p,c,bytes); }
static NvU32 gpuGetInstance(OBJGPU *g) { return g->gpuInstance; }
static NvU32 gpuGetDeviceInstance(OBJGPU *g) { (void)g;return 4; }
static NV_STATUS serverLockAllClients(void *s)
 { (void)s;NV_STATUS v=fault(CLIENT_LOCK);if(!v)++clientDepth;return v; }
static void serverUnlockAllClients(void *s) { (void)s;assert(clientDepth==1);--clientDepth; }
static int g_resServ;
static void RmDestroyPowerManagement(nv_state_t *n) { (void)n; }
static void freeNbsiTable(OBJGPU *g) { (void)g; }
static NV_STATUS teardownCoreLogic(OBJOS *o,OBJGPU *g)
 { (void)o;(void)g;++coreCalls;return fault(CORE); }
static NV_STATUS osTeardownScalability(OBJGPU *g) { (void)g;++scalabilityCalls;return fault(SCALABILITY); }
static void krcWatchdogShutdown(OBJGPU *g,void *rc,int *wd) { (void)g;(void)rc;(void)wd; }
static void rmapiSetDelPendingClientResourcesFromGpuMask(NvU32 m) { (void)m; }
static void rmapiDelPendingDevices(NvU32 m) { (void)m; }
static NV_STATUS gpuStateUnload(OBJGPU *g,int state) { (void)g;(void)state;++unloadCalls;return fault(UNLOAD); }
static NV_STATUS gpuStateDestroy(OBJGPU *g) { (void)g;++destroyCalls;return fault(DESTROY); }
static NV_STATUS dceclientDceRmInit(OBJGPU *g,void *d,NvBool enabled)
 { (void)g;(void)d;(void)enabled;return fault(DCE); }
static void RmDisableDeviceClks(nv_state_t *n) { (void)n; }
static void RmFreeX86EmuState(OBJGPU *g) { (void)g; }
static NV_STATUS gpumgrDetachGpu(NvU32 id)
 { (void)id;++detachCalls;NV_STATUS s=fault(DETACH);if(!s)modelGpuAttached=NV_FALSE;return s; }
static NV_STATUS gpumgrDestroyDevice(NvU32 id)
 { (void)id;++deviceDestroyCalls;NV_STATUS s=fault(DEVICE_DESTROY);if(!s)modelDeviceAlive=NV_FALSE;return s; }
static NV_STATUS vmmGetVaspaceFromId(OBJVMM *v,NvU32 id,int type,OBJVASPACE **out)
 { (void)v;(void)id;(void)type;++dmaCalls;NV_STATUS s=fault(DMA_LOOKUP);
   if(!s)*out=&vaspaceFixture;return s; }
static void vmmDestroyVaspace(OBJVMM *v,OBJVASPACE *vaspace)
 { (void)v;assert(vaspace==&vaspaceFixture);assert(modelVaspaceAlive);modelVaspaceAlive=NV_FALSE; }
static void RmClearPrivateState(nv_state_t *n) { ++clearCalls;n->priv->pGpu=NULL;n->priv->flags=0; }
static void RmUnInitAcpiMethods(OBJSYS *s) { (void)s; }
static void rmGpuLockFree(NvU32 id)
 { (void)id;assert(modelGpuLockOwned);modelGpuLockOwned=NV_FALSE;++gpuLockFreeCalls; }
static NV_STATUS RmTeardownRegisters(nv_state_t *n)
 { ++registerCalls;NV_STATUS s=fault(REGISTERS);if(!s)n->regs->map=NULL;return s; }
static void gpumgrSetCurrentGpuInstance(NvU32 id) { currentInstance=id; }
static void intrSetIntrEn(Intr *i,int state) { (void)i;(void)state;++disableIntrCalls; }
static NvU32 gpumgrGetGpuMask(OBJGPU *g) { return NVBIT(g->gpuInstance); }
static void nv_stop_rc_timer(nv_state_t *n) { (void)n; }
static void threadStateInit(THREAD_STATE_NODE *n,int flags) { (void)n;(void)flags;++threadDepth; }
static void threadStateFree(THREAD_STATE_NODE *n,int flags) { (void)n;(void)flags;--threadDepth; }
static NV_STATUS os_flush_work_queue(void *q,NvBool wait)
 { (void)q;(void)wait;++flushCalls;return fault(flushCalls==1?FIRST_FLUSH:LAST_FLUSH); }
static NV_STATUS s540GspCancellationBeginCleanupState(const void *n)
 { (void)n;++cleanupCalls;return fault(CLEANUP); }
static void os_disable_console_access(void) { assert(!"console fixture must never be active"); }
static void os_enable_console_access(void) { assert(!"console fixture must never be active"); }
static NV_STATUS rmapiLockAcquire(int flags,int module)
 { (void)flags;(void)module;NV_STATUS s=fault(API_LOCK);if(!s)++apiLockDepth;return s; }
static void rmapiLockRelease(void) { assert(apiLockDepth==1);--apiLockDepth; }
static NV_STATUS gpumgrAllocGpuInstance(NvU32 *id) { *id=2;return fault(MAP_ID); }
static NV_STATUS rmGpuLockAlloc(NvU32 id)
 { (void)id;++mapLockAllocs;NV_STATUS s=fault(MAP_LOCK);if(!s)modelGpuLockOwned=NV_TRUE;return s; }
static NV_STATUS gpumgrCreateDevice(NvU32 *id,NvU32 mask,void *ordinal)
 { (void)mask;(void)ordinal;++mapCreates;*id=4;NV_STATUS s=fault(MAP_CREATE);
   if(!s)modelDeviceAlive=NV_TRUE;return s; }
static void *portMemAllocNonPaged(size_t bytes)
 { static GPUATTACHARG argument;assert(bytes==sizeof(argument));++mapArguments;
   return failAt==MAP_ARGUMENT?NULL:&argument; }
static void portMemFree(void *p) { assert(p); }
static void RmSetSocDispDeviceMappings(GPUATTACHARG *a,nv_state_t *s) { (void)a;(void)s; }
static void RmSetSocDpauxDeviceMappings(GPUATTACHARG *a,nv_state_t *s) { (void)a;(void)s; }
static void RmSetSocHdacodecDeviceMappings(GPUATTACHARG *a,nv_state_t *s) { (void)a;(void)s; }
static void RmSetSocMipiCalDeviceMappings(GPUATTACHARG *a,nv_state_t *s) { (void)a;(void)s; }
static NvU32 nv_encode_pci_info(void *p) { (void)p;return 0x100; }
static NV_STATUS gpumgrAttachGpu(NvU32 id,GPUATTACHARG *a)
 { (void)id;++mapAttaches;NV_STATUS s=fault(MAP_ATTACH);if(!s) {
    nv_state_t *nv=a->pOsAttachArg;nv->priv->pGpu=(OBJGPU *)nv->ud.cpu_address;
    modelGpuAttached=NV_TRUE;}return s; }
static nv_state_t *s540RmGspAttemptOwner;
static NV_STATUS kgspInitRm(OBJGPU *g,void *kgsp,int *firmware)
 { (void)kgsp;(void)firmware;++gspInitCalls;
   assert(s540RmGspAttemptOwner&&s540RmGspAttemptOwner->priv->pGpu==g);return fault(GSP_INIT); }
#include "exact-prospective-bodies.inc"
static OBJGPU gpu;
static nv_priv_t priv;
static registers_t regs;
static nv_state_t state;
static NvBool property(OBJGPU *g,int prop) { (void)g;(void)prop;return NV_FALSE; }
static void setProperty(OBJGPU *g,int prop,NvBool value) { (void)g;(void)prop;(void)value; }
static void reset(enum Fault point)
{
 failAt=point;gpu=(OBJGPU){2,property,setProperty};
 priv=(nv_priv_t){&gpu,NV_INIT_FLAG_GPUMGR_ATTACH|NV_INIT_FLAG_CORE_LOGIC|
  NV_INIT_FLAG_GPU_STATE_LOAD|NV_INIT_FLAG_GPU_STATE|NV_INIT_FLAG_DMA|NV_INIT_FLAG_HAL};
 regs.map=&regs;state=(nv_state_t){0};state.priv=&priv;state.regs=&regs;
 state.fb=&regs;
 state.iovaspace_id=1;
 state.rmapi.hClient=7;state.is_external_gpu=NV_TRUE;
 hasCoreClass=NV_TRUE;isDce=NV_TRUE;modelDeviceAlive=modelGpuAttached=modelVaspaceAlive=NV_TRUE;
 modelGpuLockOwned=NV_TRUE;failPendingDestroy=NV_FALSE;
 gpuLockDepth=apiLockDepth=clientDepth=visibilityDepth=runtimeDepth=threadDepth=0;
 gpuLockCalls=flushCalls=detachCalls=deviceDestroyCalls=dmaCalls=registerCalls=
 clearCalls=gpuLockFreeCalls=coreCalls=scalabilityCalls=unloadCalls=destroyCalls=
 apiFreeCalls=disableIntrCalls=cleanupCalls=0;currentInstance=NV_U32_MAX;
 mapCreates=mapArguments=mapAttaches=mapLockAllocs=apiAllocCalls=0;
 memset(&s540RmPendingDevice,0,sizeof(s540RmPendingDevice));
 s540RmGspAttemptOwner=NULL;gspInitCalls=0;
}
int main(void)
{
 NvU32 checks=0;
#define EXPECT(c) do { ++checks; if(!(c)) { fprintf(stderr,"unwind check line %d point %d\n",__LINE__,failAt);return 1; } } while(0)
#define BALANCED() do { EXPECT(gpuLockDepth==0);EXPECT(apiLockDepth==0);EXPECT(clientDepth==0);EXPECT(visibilityDepth==0);EXPECT(runtimeDepth==0);EXPECT(threadDepth==0); } while(0)
 reset(NONE);
 EXPECT(RmShutdownAdapterChecked(&state)==NV_OK);
 EXPECT(!s540RmAdapterHasResources(&state));EXPECT(!modelGpuAttached&&!modelDeviceAlive&&!modelVaspaceAlive);
 EXPECT(dmaCalls==1&&registerCalls==1&&clearCalls==1&&gpuLockFreeCalls==1);BALANCED();
 for(enum Fault f=VISIBILITY;f<=REGISTERS;f++) {
  reset(f);if(f==SCALABILITY)priv.flags=(priv.flags&~NV_INIT_FLAG_CORE_LOGIC)|NV_INIT_FLAG_SCALABILITY;
  EXPECT(RmShutdownAdapterChecked(&state)==200+(int)f);
  EXPECT(s540RmAdapterHasResources(&state));BALANCED();
  if(f<DEVICE_DESTROY) { EXPECT(priv.pGpu==&gpu);EXPECT(modelDeviceAlive); }
  if(f<REGISTERS) { EXPECT(registerCalls==0);EXPECT(regs.map==&regs); }
  if(f<DEVICE_DESTROY) EXPECT(dmaCalls==0);
  if(f==UNLOAD) EXPECT((priv.flags&NV_INIT_FLAG_GPU_STATE_LOAD)!=0);
  if(f==DESTROY) { EXPECT(!(priv.flags&NV_INIT_FLAG_GPU_STATE_LOAD));EXPECT(priv.flags&NV_INIT_FLAG_GPU_STATE); }
  if(f==DETACH) EXPECT(priv.flags&NV_INIT_FLAG_GPUMGR_ATTACH);
  if(f==DEVICE_DESTROY) { EXPECT(priv.pGpu==NULL);EXPECT(!(priv.flags&NV_INIT_FLAG_GPUMGR_ATTACH));EXPECT(modelDeviceAlive&&!modelGpuAttached); }
  if(f==DMA_LOOKUP) { EXPECT(priv.flags&NV_INIT_FLAG_DMA);EXPECT(modelVaspaceAlive);EXPECT(clearCalls==0); }
 }
 reset(NONE);priv.pGpu=NULL;priv.flags=NV_INIT_FLAG_DMA;state.rmapi.hClient=0;
 EXPECT(RmShutdownAdapterChecked(&state)==NV_OK);EXPECT(dmaCalls==1);EXPECT(!s540RmAdapterHasResources(&state));BALANCED();
 reset(DMA_LOOKUP);priv.pGpu=NULL;priv.flags=NV_INIT_FLAG_DMA;state.rmapi.hClient=0;
 EXPECT(RmShutdownAdapterChecked(&state)==200+DMA_LOOKUP);EXPECT(priv.flags&NV_INIT_FLAG_DMA);
 EXPECT(registerCalls==0&&clearCalls==0&&modelVaspaceAlive);EXPECT(s540RmAdapterHasResources(&state));BALANCED();
 for(NvU32 flag=NV_INIT_FLAG_CORE_LOGIC;flag<=NV_INIT_FLAG_HAL;flag<<=1) {
  if(flag==NV_INIT_FLAG_DMA)continue;
  reset(NONE);priv.pGpu=NULL;priv.flags=flag;state.rmapi.hClient=0;
  EXPECT(RmShutdownAdapterChecked(&state)==NV_ERR_INVALID_STATE);
  EXPECT(priv.flags==flag&&clearCalls==0&&registerCalls==0);EXPECT(s540RmAdapterHasResources(&state));BALANCED();
 }
 reset(NONE);priv.pGpu=NULL;priv.flags=NV_INIT_FLAG_GPU_STATE;state.rmapi.hClient=0;
 EXPECT(RmShutdownAdapterChecked(&state)==NV_ERR_INVALID_STATE);EXPECT(registerCalls==0&&clearCalls==0);EXPECT(s540RmAdapterHasResources(&state));BALANCED();
 /* Disable has one GPUs-lock acquire rather than shutdown's earlier RMAPI one. */
 for(enum Fault f=NONE;f<=UNLOAD;f++) {
  if(f!=NONE&&f!=CLIENT_LOCK&&f!=RM_GPU_LOCK&&f!=CORE&&f!=UNLOAD)continue;
  reset(f);EXPECT(RmDisableAdapterChecked(&state)==(f==NONE?NV_OK:200+(int)f));
  EXPECT(priv.pGpu==&gpu&&modelDeviceAlive&&modelGpuAttached);EXPECT(dmaCalls==0&&registerCalls==0);
  if(f==UNLOAD)EXPECT(priv.flags&NV_INIT_FLAG_GPU_STATE_LOAD);
  if(f==NONE)EXPECT(!(priv.flags&NV_INIT_FLAG_GPU_STATE_LOAD));
  EXPECT(currentInstance==NV_U32_MAX);BALANCED();
 }
 for(enum Fault f=NONE;f<=CLEANUP;f++) {
  if(f!=NONE&&f!=FIRST_FLUSH&&f!=API_LOCK&&f!=LAST_FLUSH&&f!=CLEANUP)continue;
  reset(f);EXPECT(s540RmDisableAdapterChecked(NULL,&state)==(f==NONE?NV_OK:200+(int)f));BALANCED();
  if(f==FIRST_FLUSH||f==CLEANUP)EXPECT(disableIntrCalls==0);
  if(f==API_LOCK)EXPECT(unloadCalls==0);
 }
 reset(UNLOAD);EXPECT(s540RmDisableAdapterChecked(NULL,&state)==200+UNLOAD);
 EXPECT(flushCalls==1);EXPECT(priv.flags&NV_INIT_FLAG_GPU_STATE_LOAD);BALANCED();
 reset(API_LOCK);EXPECT(s540RmShutdownAdapterChecked(NULL,&state)==200+API_LOCK);
 EXPECT(detachCalls==0&&registerCalls==0);BALANCED();
 reset(CLEANUP);EXPECT(s540RmShutdownAdapterChecked(NULL,&state)==200+CLEANUP);
 EXPECT(detachCalls==0&&registerCalls==0);BALANCED();
 reset(NONE);state.flags|=NV_FLAG_PERSISTENT_SW_STATE;
 EXPECT(s540RmDisableAdapterChecked(NULL,&state)==NV_ERR_NOT_SUPPORTED);
 EXPECT(disableIntrCalls==0&&flushCalls==1);BALANCED();
 /* Every changed pre-attach exit: actual source prefix, modeled GPUMGR. */
 const enum Fault mappingPoints[]={NONE,MAP_ID,MAP_LOCK,MAP_CREATE,MAP_ARGUMENT,MAP_ATTACH};
 for(NvU32 i=0;i<sizeof(mappingPoints)/sizeof(mappingPoints[0]);++i) {
  enum Fault f=mappingPoints[i];reset(f);priv.pGpu=NULL;priv.flags=NV_INIT_FLAG_DMA;
  state.rmapi.hClient=0;state.ud.cpu_address=(uintptr_t)&gpu;
  modelDeviceAlive=modelGpuAttached=modelGpuLockOwned=NV_FALSE;
  NvU32 reference=NV_U32_MAX;UNIX_STATUS status={0};
  osInitNvMapping(&state,&reference,&status);
  EXPECT(s540RmPendingDevice.owner==NULL);
  if(f==NONE) {
   EXPECT(status.initStatus==0&&status.rmStatus==NV_OK);
   EXPECT(priv.flags&NV_INIT_FLAG_GPUMGR_ATTACH);
   EXPECT(priv.pGpu==&gpu&&modelDeviceAlive&&modelGpuAttached&&modelGpuLockOwned);
  } else {
   EXPECT(status.initStatus!=0);EXPECT(!modelDeviceAlive&&!modelGpuAttached&&!modelGpuLockOwned);
   EXPECT(!(priv.flags&NV_INIT_FLAG_GPUMGR_ATTACH));
   if(f==MAP_ARGUMENT)EXPECT(status.rmStatus==NV_ERR_NO_MEMORY);
   else EXPECT(status.rmStatus==200+(int)f);
  }
  NvU32 destroyedBefore=deviceDestroyCalls;
  EXPECT(RmShutdownAdapterChecked(&state)==NV_OK);
  EXPECT(!s540RmAdapterHasResources(&state));
  if(f!=NONE)EXPECT(deviceDestroyCalls==destroyedBefore);
  BALANCED();
 }
 for(enum Fault f=MAP_ARGUMENT;f<=MAP_ATTACH;++f) {
  reset(f);priv.pGpu=NULL;priv.flags=NV_INIT_FLAG_DMA;state.rmapi.hClient=0;
  state.ud.cpu_address=(uintptr_t)&gpu;modelDeviceAlive=modelGpuAttached=modelGpuLockOwned=NV_FALSE;
  failPendingDestroy=NV_TRUE;NvU32 reference=NV_U32_MAX;UNIX_STATUS status={0};
  osInitNvMapping(&state,&reference,&status);
  EXPECT(status.rmStatus==200+DEVICE_DESTROY);EXPECT(s540RmPendingDevice.owner==&state);
  EXPECT(modelDeviceAlive&&modelGpuLockOwned&&!modelGpuAttached);
  EXPECT(deviceDestroyCalls==1&&gpuLockFreeCalls==0);EXPECT(s540RmAdapterHasResources(&state));
  EXPECT(RmShutdownAdapterChecked(&state)==NV_ERR_INVALID_STATE);
  EXPECT(deviceDestroyCalls==1&&gpuLockFreeCalls==0&&registerCalls==0&&dmaCalls==0);
  nv_state_t foreign=state;UNIX_STATUS foreignStatus={0};NvU32 foreignReference=NV_U32_MAX;
  osInitNvMapping(&foreign,&foreignReference,&foreignStatus);
  EXPECT(foreignStatus.rmStatus==NV_ERR_STATE_IN_USE);
  EXPECT(s540RmPendingDevice.owner==&state&&mapCreates==1);BALANCED();
 }
 /* The boolean allocator never reports a lock error as success and performs
  * no hidden Free; the sole caller owns one later checked shutdown. */
 const enum Fault allocationPoints[]={NONE,RM_GPU_LOCK,ALLOC_ROOT,ALLOC_DEVICE,
  ALLOC_SUBDEVICE,ALLOC_I2C,ALLOC_DISPLAY};
 for(NvU32 i=0;i<sizeof(allocationPoints)/sizeof(allocationPoints[0]);++i) {
  enum Fault f=allocationPoints[i];reset(f);
  NvBool result=RmUnixAllocRmApi(&state,4);
  EXPECT(result==(f==NONE||f==ALLOC_I2C||f==ALLOC_DISPLAY?NV_TRUE:NV_FALSE));
  EXPECT(apiFreeCalls==0);EXPECT(gpuLockDepth==0);
  NvBool hadClient=state.rmapi.hClient!=0;
  if(f==ALLOC_I2C)EXPECT(state.rmapi.hI2C==0);
  if(f==ALLOC_DISPLAY)EXPECT(state.rmapi.hDisp==0);
  EXPECT(RmShutdownAdapterChecked(&state)==NV_OK);
  EXPECT(apiFreeCalls==(hadClient?1U:0U));EXPECT(!s540RmAdapterHasResources(&state));BALANCED();
 }
 /* The actual GSP call branch records ownership before the modeled call.
  * Partial initialization cannot run destructors lacking a completed state. */
 reset(GSP_INIT);priv.flags&=~NV_INIT_FLAG_GPU_STATE;
 EXPECT(s540TestExactGspInitBranch(&state)==200+GSP_INIT);
 EXPECT(gspInitCalls==1&&s540RmGspAttemptOwner==&state);
 EXPECT(RmShutdownAdapterChecked(&state)==NV_ERR_NOT_READY);
 EXPECT(RmDisableAdapterChecked(&state)==NV_ERR_NOT_READY);
 EXPECT(disableIntrCalls==0);
 EXPECT(s540RmAdapterHasResources(&state));
 EXPECT(apiFreeCalls==0&&coreCalls==0&&unloadCalls==0&&destroyCalls==0);
 EXPECT(detachCalls==0&&deviceDestroyCalls==0&&dmaCalls==0&&registerCalls==0);BALANCED();
 nv_state_t foreign=state;
 EXPECT(s540TestExactGspInitBranch(&foreign)==NV_ERR_STATE_IN_USE);
 EXPECT(gspInitCalls==1&&s540RmGspAttemptOwner==&state);
 EXPECT(s540TestExactGspInitBranch(&state)==NV_ERR_STATE_IN_USE);
 EXPECT(gspInitCalls==1&&s540RmGspAttemptOwner==&state);
 reset(NONE);EXPECT(s540TestExactGspInitBranch(&state)==NV_OK);
 EXPECT(s540RmGspAttemptOwner==&state&&gspInitCalls==1);
 EXPECT(RmShutdownAdapterChecked(&state)==NV_OK);
 EXPECT(s540RmGspAttemptOwner==NULL&&!s540RmAdapterHasResources(&state));BALANCED();
 reset(UNLOAD);s540RmGspAttemptOwner=&state;
 EXPECT(RmShutdownAdapterChecked(&state)==200+UNLOAD);
 EXPECT(s540RmGspAttemptOwner==&state&&s540RmAdapterHasResources(&state));BALANCED();
 reset(REGISTERS);s540RmGspAttemptOwner=&state;
 EXPECT(RmShutdownAdapterChecked(&state)==200+REGISTERS);
 EXPECT(s540RmGspAttemptOwner==&state&&s540RmAdapterHasResources(&state));
 EXPECT(RmShutdownAdapterChecked(&state)==NV_ERR_NOT_READY);EXPECT(registerCalls==1);BALANCED();
 printf("{\"format\":1,\"component\":\"nvidia-prospective-adapter-unwind-bodies\",\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"actual_changed_bodies\":true,\"modeled_dependencies\":true,\"kernel_execution\":false,\"gpu_access\":false}\n",checks);
 return 0;
}
