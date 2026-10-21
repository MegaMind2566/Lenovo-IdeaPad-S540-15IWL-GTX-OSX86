/* SPDX-License-Identifier: MIT */
/* CPU source control only. Object layouts, GPU power/existence and POSIX lock
 * adapters below are explicit fixtures. Complete NVIDIA function bodies are
 * extracted unchanged from three independently hash-checked original files. */
#define _POSIX_C_SOURCE 200809L
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint32_t NvU32;
typedef uint64_t NvU64;
typedef int NvBool;
typedef int NV_STATUS;
typedef NvU32 GPU_MASK;
enum { NV_OK=0, NV_ERR_GENERIC=1, NV_ERR_INVALID_REQUEST=2,
    NV_FALSE=0, NV_TRUE=1, NV_OS_1HZ_REPEAT=1, TMR_NUM_CALLBACKS_OS=8,
    GPU_LOCK_GRP_DEVICE=1, GPU_LOCK_FLAGS_COND_ACQUIRE=2,
    RM_LOCK_MODULES_TMR=3, GPUS_LOCK_FLAGS_NONE=0,
    THREAD_STATE_FLAGS_IS_DEFERRED_INT_HANDLER=4,
    PDB_PROP_TMR_USE_PTIMER_FOR_OSTIMER_CALLBACKS=9, TMR_FLAG_RECUR=1 };
#define NV_API_CALL
#define TLS_DPC_HAVE_UNIQUE_ID 1
#define NV_PRINTF(...) ((void)0)
#define NV_ASSERT_OK_OR_RETURN(call) do { NV_STATUS s=(call); if(s!=NV_OK)return s; } while(0)
#define NV_ASSERT_OK(call) require((call)==NV_OK)

typedef struct OBJGPU OBJGPU;
typedef struct OBJTMR OBJTMR;
typedef struct TMR_EVENT { NvU32 unused; } TMR_EVENT;
typedef void (*OS1HZPROC)(OBJGPU *, void *);
typedef struct OS1HZTIMERENTRY {
    OS1HZPROC callback;
    void *data;
    NvU32 flags;
    struct OS1HZTIMERENTRY *next;
} OS1HZTIMERENTRY, *POS1HZTIMERENTRY;
struct OBJTMR {
    OS1HZTIMERENTRY *pOs1HzCallbackList, *pOs1HzCallbackFreeList;
    OS1HZTIMERENTRY os1HzCallbackTable[TMR_NUM_CALLBACKS_OS];
    TMR_EVENT *pOs1HzEvent;
    NvBool (*getProperty)(OBJTMR *, NvU32);
};
struct OBJGPU { OBJTMR *timer; NvU32 gpuInstance, bCallbackQueued; NvU64 lastCallbackTime; };
typedef struct { OBJGPU *gpu; NvU32 rc_timer_enabled; } nv_state_t;
typedef struct { int unused; } nvidia_stack_t;
typedef struct { int unused; } THREAD_STATE_NODE;
typedef struct { void *pSema; } OBJSYS;

static OBJTMR timer;
static OBJGPU gpu;
static nv_state_t nv;
static OBJSYS systemFixture;
static nvidia_stack_t stack;
static pthread_mutex_t gpuMutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t apiMutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_t master;
static _Thread_local NvBool gpuOwned, apiOwned, interruptContext;
static _Thread_local NvU32 runtimeDepth, threadStateDepth;
static NvBool fullPower=NV_TRUE, sane=NV_TRUE, exists=NV_TRUE;
static NvU32 checks, failures, plainCalls, repeatCalls, existenceReads;
static NvU32 originalCalls, gpuTryFailures, apiTryFailures, gpuReleases;
static NvU64 clockValue=100;
static int plainAllocation;
static pthread_t plainActionThread;

static void require(NvBool condition) { if(!condition)abort(); }
static void expect(NvBool condition, const char *message) {
    ++checks;
    if(!condition){++failures;fprintf(stderr,"1Hz: %s\n",message);}
}
static NvBool property(OBJTMR *object, NvU32 key) {
    require(object==&timer && key==PDB_PROP_TMR_USE_PTIMER_FOR_OSTIMER_CALLBACKS);
    return NV_FALSE;
}
#define GPU_GET_TIMER(g) ((g)->timer)
#define NV_GET_NV_PRIV_PGPU(state) ((state)->gpu)
#define SYS_GET_INSTANCE() (&systemFixture)
#define FULL_GPU_SANITY_CHECK(g) ((g)==&gpu && sane)
#define NV_ENTER_RM_RUNTIME(sp,fp) do { require((sp)==&stack && !runtimeDepth); runtimeDepth=1; (fp)=NULL; } while(0)
#define NV_EXIT_RM_RUNTIME(sp,fp) do { (void)(sp); (void)(fp); require(runtimeDepth==1);runtimeDepth=0; } while(0)
static NvBool gpuIsGpuFullPower(OBJGPU *object) { require(object==&gpu);return fullPower; }
static NV_STATUS gpuVerifyExistence_HAL(OBJGPU *object) {
    require(object==&gpu && gpuOwned && apiOwned && runtimeDepth==1);
    ++existenceReads;return exists?NV_OK:NV_ERR_GENERIC;
}
static NvU64 osGetMonotonicTimeNs(void) { return ++clockValue; }
static NvU32 portAtomicSetU32(NvU32 *value, NvU32 update) {
    return __atomic_exchange_n(value,update,__ATOMIC_SEQ_CST);
}
static NvBool portUtilIsInterruptContext(void) { return interruptContext; }
static NvBool rmDeviceGpuLockIsOwner(NvU32 instance) { require(!instance);return gpuOwned; }
static NV_STATUS rmGpuGroupLockAcquire(NvU32 instance, NvU32 group,
    NvU32 flags, NvU32 module, GPU_MASK *out) {
    require(!instance && group==GPU_LOCK_GRP_DEVICE && flags==GPU_LOCK_FLAGS_COND_ACQUIRE &&
        module==RM_LOCK_MODULES_TMR && out && !gpuOwned);
    if(pthread_mutex_trylock(&gpuMutex)!=0){++gpuTryFailures;return NV_ERR_GENERIC;}
    gpuOwned=NV_TRUE;*out=1;return NV_OK;
}
static void rmGpuGroupLockRelease(GPU_MASK mask, NvU32 flags) {
    require(mask==1 && !flags && gpuOwned);gpuOwned=NV_FALSE;++gpuReleases;
    require(pthread_mutex_unlock(&gpuMutex)==0);
}
static NV_STATUS osCondAcquireRmSema(void *sema) {
    require(sema==&apiMutex && !apiOwned);
    if(pthread_mutex_trylock(&apiMutex)!=0){++apiTryFailures;return NV_ERR_GENERIC;}
    apiOwned=NV_TRUE;return NV_OK;
}
static void osReleaseRmSema(void *sema, void *unused) {
    require(sema==&apiMutex && !unused && apiOwned);apiOwned=NV_FALSE;
    require(pthread_mutex_unlock(&apiMutex)==0);
}
static void threadStateInitISRAndDeferredIntHandler(THREAD_STATE_NODE *node,
    OBJGPU *object,NvU32 flags) {
    require(node && object==&gpu && flags==THREAD_STATE_FLAGS_IS_DEFERRED_INT_HANDLER &&
        runtimeDepth==1 && !threadStateDepth);threadStateDepth=1;
}
static void threadStateFreeISRAndDeferredIntHandler(THREAD_STATE_NODE *node,
    OBJGPU *object,NvU32 flags) {
    require(node && object==&gpu && flags==THREAD_STATE_FLAGS_IS_DEFERRED_INT_HANDLER &&
        runtimeDepth==1 && threadStateDepth==1);threadStateDepth=0;
}
static NvBool _os1HzCallbackIsOnList(OBJTMR *, OS1HZPROC, void *, NvU32);
static NV_STATUS _os1HzCallback(OBJGPU *, OBJTMR *, TMR_EVENT *);
static void _kbifCheckIfGpuExists(OBJGPU *, void *);
NvBool osRun1HzCallbacksNow(OBJGPU *);
static NV_STATUS tmrEventCreate(OBJTMR *a,TMR_EVENT **b,
    NV_STATUS(*c)(OBJGPU *,OBJTMR *,TMR_EVENT *),void *d,NvU32 e) {
    (void)a;(void)b;(void)c;(void)d;(void)e;abort();
}
static void tmrEventDestroy(OBJTMR *a,TMR_EVENT *b) {(void)a;(void)b;abort();}
static NV_STATUS tmrEventScheduleRelSec(OBJTMR *a,TMR_EVENT *b,NvU32 c) {
    (void)a;(void)b;(void)c;abort();
}
static void tmrEventCancel(OBJTMR *a,TMR_EVENT *b) {(void)a;(void)b;abort();}

#include "actual-1hz-bodies.inc"

static void plain(OBJGPU *object,void *data) {
    require(object==&gpu && data==&plainAllocation && gpuOwned && apiOwned && runtimeDepth==1);
    ++plainCalls;plainActionThread=pthread_self();
}
static void repeat(OBJGPU *object,void *data) {
    require(object==&gpu && data==NULL && gpuOwned && apiOwned && runtimeDepth==1);++repeatCalls;
}
static void *worker(void *unused) {
    (void)unused;require(rm_run_rc_callback(&stack,&nv)==NV_OK);++originalCalls;
    require(!runtimeDepth && !threadStateDepth && !gpuOwned && !apiOwned);return NULL;
}
static void runWorker(void) {
    pthread_t thread;require(pthread_create(&thread,NULL,worker,NULL)==0);
    require(pthread_join(thread,NULL)==0);
}
static void lockGpu(void) { require(!gpuOwned && pthread_mutex_lock(&gpuMutex)==0);gpuOwned=NV_TRUE; }
static void unlockGpu(void) { require(gpuOwned);gpuOwned=NV_FALSE;require(pthread_mutex_unlock(&gpuMutex)==0); }
static void lockApi(void) { require(!apiOwned && pthread_mutex_lock(&apiMutex)==0);apiOwned=NV_TRUE; }
static void unlockApi(void) { require(apiOwned);apiOwned=NV_FALSE;require(pthread_mutex_unlock(&apiMutex)==0); }
static void drainOnMaster(void) {
    require(pthread_equal(pthread_self(),master) && gpuOwned && apiOwned && !interruptContext && !runtimeDepth);
    runtimeDepth=1;osRunQueued1HzCallbacksUnderLock(&gpu);runtimeDepth=0;
}
int main(void) {
    master=pthread_self();timer.getProperty=property;gpu.timer=&timer;nv.gpu=&gpu;systemFixture.pSema=&apiMutex;
    expect(osInit1HzCallbacks(&timer)==NV_OK && !timer.pOs1HzEvent &&
        timer.pOs1HzCallbackFreeList==timer.os1HzCallbackTable,
        "actual non-PTIMER initialization creates ordinary list entries");
    expect(osSchedule1HzCallback(&gpu,_kbifCheckIfGpuExists,NULL,NV_OS_1HZ_REPEAT)==NV_OK,
        "actual BIF callback registers NULL ordinary data");
    expect(osSchedule1HzCallback(&gpu,plain,&plainAllocation,0)==NV_OK &&
        osSchedule1HzCallback(&gpu,repeat,NULL,NV_OS_1HZ_REPEAT)==NV_OK,
        "plain allocation and NULL data require no event or NVOC owner");
    expect(osSchedule1HzCallback(&gpu,repeat,NULL,NV_OS_1HZ_REPEAT)==NV_ERR_INVALID_REQUEST,
        "real scheduler refuses duplicate repeat entry");
    expect(rm_run_rc_callback(&stack,NULL)==NV_ERR_GENERIC &&
        rm_run_rc_callback(&stack,&nv)==NV_ERR_GENERIC && !plainCalls,
        "real wrapper refuses missing nv or disabled RC");
    nv.rc_timer_enabled=1;sane=NV_FALSE;
    expect(rm_run_rc_callback(&stack,&nv)==NV_ERR_GENERIC && !plainCalls,
        "real wrapper refuses failed hardware-sanity observation");sane=NV_TRUE;
    lockGpu();runWorker();
    expect(gpu.bCallbackQueued && gpuTryFailures==1 && originalCalls==1 && !plainCalls,
        "actual RC returns while conditional GPU failure leaves original pending bit");
    interruptContext=NV_TRUE;osRunQueued1HzCallbacksUnderLock(&gpu);interruptContext=NV_FALSE;
    expect(gpu.bCallbackQueued && !plainCalls,"interrupt-context master cannot drain original pending work");
    unlockGpu();osRunQueued1HzCallbacksUnderLock(&gpu);
    expect(gpu.bCallbackQueued && !plainCalls,"missing device lock preserves original pending bit");
    lockApi();runWorker();
    expect(gpu.bCallbackQueued && apiTryFailures==1 && gpuReleases==1 && !plainCalls,
        "conditional RM semaphore failure releases GPU token and preserves pending work");
    lockGpu();drainOnMaster();
    expect(!gpu.bCallbackQueued && plainCalls==1 && repeatCalls==1 && existenceReads==1 &&
        pthread_equal(plainActionThread,master),"actual pending list drains on master holding real fixture locks");
    expect(!_os1HzCallbackIsOnList(&timer,plain,&plainAllocation,0) &&
        _os1HzCallbackIsOnList(&timer,repeat,NULL,NV_OS_1HZ_REPEAT),
        "real list recycles one-shot entry and preserves repeating entry");
    drainOnMaster();expect(repeatCalls==1,"second empty pending drain fabricates no action");
    unlockGpu();unlockApi();exists=NV_FALSE;runWorker();
    expect(existenceReads==2 && repeatCalls==2 &&
        !_os1HzCallbackIsOnList(&timer,_kbifCheckIfGpuExists,NULL,NV_OS_1HZ_REPEAT),
        "actual BIF existence failure removes its own NULL-data callback");
    expect(!gpuOwned && !apiOwned && !runtimeDepth && !threadStateDepth,
        "original wrapper releases all fixture lock and thread-state scopes");
    fullPower=NV_FALSE;NvU64 priorTime=gpu.lastCallbackTime;runWorker();
    expect(repeatCalls==2 && gpu.lastCallbackTime==priorTime,
        "original low-power branch runs no callback or successful callback timestamp");
    expect(osDestroy1HzCallbacks(&timer)==NV_OK && !timer.pOs1HzCallbackList && !timer.pOs1HzCallbackFreeList,
        "real non-PTIMER destruction clears only ordinary software list owners");
    printf("{\"checks\":%u,\"failures\":%u,\"original_rc_wrapper_calls\":%u,\"real_plain_1hz_body\":true,\"real_bif_callback_body\":true}\n",
        checks,failures,originalCalls);
    return failures?1:0;
}
