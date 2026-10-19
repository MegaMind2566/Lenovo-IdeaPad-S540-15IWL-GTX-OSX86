/* SPDX-License-Identifier: MIT
 * CPU controls: complete pinned bodies + full original nv.h ABI + real service
 * queues/timers/strong record/Host. Immutable EXTRA policy rows below exist
 * only in this executable; they do not authorize production callback policy.
 * RM token, runtime-stack, NVOC cast, empty-list and hardware-time endpoints are
 * explicit fixtures. The NVIDIA callback body itself is never substituted. */
#include "nv.h"
#include "nv-priv.h"
#include "gpu/gpu.h"
#include "gpu/timer/objtmr.h"
#include "gpu/timed_sema.h"
#include "core/thread_state.h"
#include "nvoc/rtti.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "../original/S540NvidiaGspFirstTransactionOriginal.h"
#include "S540NvidiaFirstTxnServices.h"
#include "S540NvidiaGspTimers.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaGlobalCrypto.h"
#include "nv_unsupported_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
static nv_state_t nv;
static OBJGPU gpu;
static OBJTMR timer;
static TimedSemaSwObject owner;
static TMR_EVENT_PVT event;
static const struct NVOC_CLASS_DEF fixtureClass={0};
static const struct NVOC_RTTI fixtureRtti={.pClassDef=&fixtureClass};
static S540GspCancellationToken cancelToken;
static struct os_work_queue *deviceQueue,*globalQueue;
static NvU32 checks,failures,callbackCalls,lockAcquires,lockReleases,workFrees;
static NvU32 heldAction,actionOriginalReturned,releaseAction;
static NvU64 masterThread,workThread;
static __thread NvU32 lockDepth,runtimeDepth;
static void require(NvBool v){if(!v)abort();}
static void expect(NvBool v,const char *why){++checks;if(!v){++failures;fprintf(stderr,"actual bodies: %s\n",why);}}
static NvBool waitFor(NvU32 *v){for(NvU32 n=0;n<3000&&!__atomic_load_n(v,__ATOMIC_ACQUIRE);++n)usleep(1000);return __atomic_load_n(v,__ATOMIC_ACQUIRE)!=0;}
static OBJGPU *fixtureGpu(NvU32 instance){require(instance==0);return &gpu;}
static nv_state_t *fixtureNv(OBJGPU *g){require(g==&gpu);return &nv;}
static OBJTMR *fixtureTimer(OBJGPU *g){require(g==&gpu);return &timer;}
static OBJGPU *fixturePrivate(nv_state_t *n){require(n==&nv);return &gpu;}
static NvU32 fixtureInstance(OBJGPU *g){require(g==&gpu);return 0;}
static NvU32 fixtureSetInstance(NvU32 v){require(v==0);return 0;}
static NV_STATUS fixtureLocksAcquire(NvU32 instance,OsQueueWorkItemFlags flags,OsQueueWorkItemFlags *out,NvU32 *mask){
 require(instance==0&&flags.bRequiresGpu&&flags.bLockGpuGroupDevice&&!lockDepth);*out=flags;*mask=1;++lockDepth;__atomic_add_fetch(&lockAcquires,1U,__ATOMIC_RELAXED);return NV_OK;
}
static void fixtureLocksRelease(OsQueueWorkItemFlags flags,NvU32 mask){require(flags.bLockGpuGroupDevice&&mask==1&&lockDepth==1);--lockDepth;__atomic_add_fetch(&lockReleases,1U,__ATOMIC_RELAXED);}
static void fixtureThreadInit(THREAD_STATE_NODE *n,NvU32 f){(void)n;(void)f;require(runtimeDepth==1);}
static void fixtureThreadFree(THREAD_STATE_NODE *n,NvU32 f){(void)n;(void)f;require(runtimeDepth==1);}
static void fixtureDeferredInit(THREAD_STATE_NODE *n,OBJGPU *g,NvU32 f){(void)n;(void)f;require(g==&gpu&&runtimeDepth==1);}
static void fixtureDeferredFree(THREAD_STATE_NODE *n,OBJGPU *g,NvU32 f){fixtureDeferredInit(n,g,f);}
static void fixtureFree(void *p){if(p){__atomic_add_fetch(&workFrees,1U,__ATOMIC_RELAXED);s540GlobalRmHostFreeOriginal(p);}}
static void *fixtureAllocate(NvU64 bytes){return s540GlobalRmHostAllocateOriginal(bytes);}
static void fixtureLog(int level,const char *format,...){(void)level;(void)format;}
static TimedSemaSwObject *fixtureCast(ChannelDescendant *base){require(base==&owner.__nvoc_base_ChannelDescendant);return &owner;}
static PGF100_TIMED_SEM_ENTRY fixtureEmptyList(const void *list){require(list==&owner.entryList);return NULL;}
static void fixtureTime(OBJTMR *t,NvU64 *out){require(t==&timer&&lockDepth==1);*out=s540Darwin_os_get_monotonic_time_ns();__atomic_add_fetch(&callbackCalls,1U,__ATOMIC_RELAXED);}
static void impossible(void){abort();}
#undef dynamicCast
#define dynamicCast(o,t) fixtureCast(o)
#undef GPU_RES_GET_DEVICE
#define GPU_RES_GET_DEVICE(o) ((Device *)NULL)
#undef listHead
#define listHead(l) fixtureEmptyList(l)
#undef listNext
#define listNext(l,p) ((PGF100_TIMED_SEM_ENTRY)NULL)
#undef listRemove
#define listRemove(l,p) impossible()
#define _9074TimedSemReleaseNow(a,b,c,d) ((void)(a),(void)(b),(void)(c),(void)(d),impossible(),NV_FALSE)
#define _9074TimedSemRelease(...) (impossible(),NV_ERR_INVALID_STATE)
#undef tmrGetCurrentTime
#define tmrGetCurrentTime fixtureTime
#undef tmrEventScheduleAbs
#define tmrEventScheduleAbs(...) impossible()
#undef tmrEventOnList
#define tmrEventOnList tmrEventOnList_IMPL
#undef tmrEventServiceOSTimerCallback_HAL
#define tmrEventServiceOSTimerCallback_HAL tmrEventServiceOSTimerCallback_OSTIMER
#undef tmrEventServiceTimer
#define tmrEventServiceTimer tmrEventServiceTimer_IMPL
#undef gpumgrGetGpu
#define gpumgrGetGpu fixtureGpu
#undef gpuGetInstance
#define gpuGetInstance fixtureInstance
#undef GPU_GET_TIMER
#define GPU_GET_TIMER fixtureTimer
#undef NV_GET_NV_STATE
#define NV_GET_NV_STATE fixtureNv
#undef NV_GET_NV_PRIV_PGPU
#define NV_GET_NV_PRIV_PGPU fixturePrivate
#undef FULL_GPU_SANITY_FOR_PM_RESUME
#define FULL_GPU_SANITY_FOR_PM_RESUME(g) ((g)==&gpu)
#undef gpumgrSetCurrentGpuInstance
#define gpumgrSetCurrentGpuInstance fixtureSetInstance
#undef workItemLocksAcquire
#define workItemLocksAcquire fixtureLocksAcquire
#undef workItemLocksRelease
#define workItemLocksRelease fixtureLocksRelease
#undef portMemAllocNonPaged
#define portMemAllocNonPaged fixtureAllocate
#undef portMemFree
#define portMemFree fixtureFree
#undef os_queue_work_item
#define os_queue_work_item s540Darwin_os_queue_work_item
#undef os_is_queue_flush_ongoing
#define os_is_queue_flush_ongoing s540Darwin_os_is_queue_flush_ongoing
#undef threadStateInit
#define threadStateInit fixtureThreadInit
#undef threadStateFree
#define threadStateFree fixtureThreadFree
#undef threadStateInitISRAndDeferredIntHandler
#define threadStateInitISRAndDeferredIntHandler fixtureDeferredInit
#undef threadStateFreeISRAndDeferredIntHandler
#define threadStateFreeISRAndDeferredIntHandler fixtureDeferredFree
#undef NV_ENTER_RM_RUNTIME
#define NV_ENTER_RM_RUNTIME(sp,fp) do{require((sp)!=NULL&&!runtimeDepth);runtimeDepth=1;(fp)=NULL;}while(0)
#undef NV_EXIT_RM_RUNTIME
#define NV_EXIT_RM_RUNTIME(sp,fp) do{(void)(sp);(void)(fp);require(runtimeDepth==1);runtimeDepth=0;}while(0)
#undef NV_PRINTF
#define NV_PRINTF(...) fixtureLog(__VA_ARGS__)
#undef NV_ASSERT
#define NV_ASSERT(x) require(!!(x))
#undef NV_ASSERT_OR_GOTO
#define NV_ASSERT_OR_GOTO(x,label) do{if(!(x))goto label;}while(0)
#include "actual-original-bodies.inc"
#include "actual-original-metadata.inc"
const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[]={
 {S540_FIRST_DESC_WORK,S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,S540_FIRST_WORK_ALL_KNOWN,S540_FIRST_WORK_DONT_FREE|S540_FIRST_WORK_REQUIRES_GPU|S540_FIRST_WORK_GROUP_DEVICE,(NvUPtr)_tmrEventServiceTimerWorkItem,0,NV_TRUE},
 {S540_FIRST_DESC_OWNER,S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,0,0,0,(NvUPtr)&fixtureClass,NV_FALSE},
 {S540_FIRST_DESC_EVENT,S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,0,0,(NvUPtr)_class9074TimerCallback,(NvUPtr)&fixtureClass,NV_FALSE}
};
const NvU32 s540FirstTxnOriginalDescriptorCount=3;
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *n){return n==&nv&&!lockDepth&&!runtimeDepth?NV_OK:NV_ERR_INVALID_LOCK_STATE;}
NV_STATUS s540FirstTxnOriginalReadServiceCounters(const void *n,S540FirstTxnServiceCounters *out){
 S540NvidiaGlobalRmHostSnapshot host;require(n==&nv&&out&&!lockDepth&&!runtimeDepth);s540GlobalRmHostSnapshot(&host);
 *out=(S540FirstTxnServiceCounters){0};out->hostInitialized=host.initialized;out->hostUnavailable=host.unavailableCalls;out->hostInvalidFrees=host.invalidFrees;
 S540DeviceMemoryStatistics memory=s540DeviceMemoryStatistics();S540NvidiaGlobalCryptoSnapshot crypto={0};s540Global_crypto_snapshot(&crypto);
 out->memoryUnavailableEver=memory.unavailableOperationsEver;out->memoryViolationsEver=memory.lifetimeViolationsEver;
 out->cryptoUnavailable=crypto.unavailable_calls;out->cryptoMaskLow=crypto.unavailable_symbol_mask;out->cryptoMaskHigh=crypto.unavailable_symbol_mask_high;out->cryptoOverflow=crypto.counter_overflow!=0;
 return NV_OK;
}
void *NV_API_CALL os_mem_set(void *p,NvU8 byte,NvU32 size){NvU8 *v=p;while(size--)*v++=byte;return p;}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *s,nv_state_t *n){(void)s;(void)n;abort();}
static void actualWorkAction(void *context,void *data){
 nvidia_stack_t stack __attribute__((aligned(16)));require(context==&nv);
 require(s540Darwin_os_get_current_thread(&workThread)==NV_OK);rm_execute_work_item(&stack,data);
 require(!lockDepth&&!runtimeDepth);require(s540FirstTxnWorkOriginalReturned(&nv,NV_OK)==NV_OK);
 __atomic_store_n(&actionOriginalReturned,1U,__ATOMIC_RELEASE);
 if(heldAction)require(waitFor(&releaseAction));
}
static void setup(void){
 S540NvidiaGlobalRmPlatformFacts facts={0};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;facts.osVersion=facts.osDate="actual-original-cpu-fixture";
 require(s540GlobalRmHostInitialize(&facts)==NV_OK);require(s540FirstTxnBeginOwner(&owner)==NV_OK);
 require(s540GspCancellationBind(&nv,&cancelToken)==NV_OK&&s540GspCancellationBegin(cancelToken)==NV_OK);
 require(s540FirstTxnBind(&nv,cancelToken)==NV_OK);require(s540Darwin_os_get_current_thread(&masterThread)==NV_OK);
 require(s540DarwinWorkQueueCreate(actualWorkAction,&nv,&deviceQueue)==NV_OK&&s540DarwinWorkQueueCreate(actualWorkAction,&nv,&globalQueue)==NV_OK);
 nv.queue=deviceQueue;gpu.gpuInstance=0;timer.PDB_PROP_TMR_USE_OS_TIMER_FOR_CALLBACKS=NV_FALSE;owner.__nvoc_rtti=&fixtureRtti;
 owner.__nvoc_base_ChannelDescendant.__nvoc_rtti=&fixtureRtti;
 event.super.pTimeProc=_class9074TimerCallback;event.super.pUserData=&owner.__nvoc_base_ChannelDescendant;
 event.super.flags=TMR_FLAG_USE_OS_TIMER|TMR_FLAG_OS_TIMER_QUEUED;event.bInUse=NV_TRUE;timer.pRmActiveOSTimerEventList=&event;
 require(s540GspTimersBind(&nv)==NV_OK);S540FirstTxnSnapshot s={0};require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 require(s540FirstTxnServicesBind(&nv,s.generation,deviceQueue,globalQueue)==NV_OK&&s540DarwinBindGlobalWorkQueue(globalQueue)==NV_OK);
 require(s540FirstTxnRegisterOwner(&nv,&owner.__nvoc_base_ChannelDescendant)==NV_OK);
 require(s540FirstTxnOriginalEnter(&nv)==NV_OK);
}
static void healthy(void){
 nv_nano_timer_t *handle=NULL;S540FirstTxnSnapshot s={0};setup();heldAction=1;
 nv_create_nano_timer(&nv,&event.super,&handle);require(handle!=NULL);nv_start_nano_timer(&nv,handle,0);require(waitFor(&actionOriginalReturned));
 require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(s.workAccepted==1&&s.workOriginalReturned==1&&s.workActionReturned==0&&s.liveWork==1,"actual original wrapper returned while real queue action retains its ticket");
 expect(s.eventBorrowers>=1&&s.eventCount==1,"accepted original nano work retains actual event until action return");
 expect(callbackCalls==1&&workThread!=masterThread&&lockAcquires==1&&lockReleases==1,"real worker executes actual typed timer callback and original lock-release body once");
 expect(workFrees==1&&!(event.super.flags&TMR_FLAG_OS_TIMER_QUEUED)&&!event.bInUse&&!timer.pRmActiveOSTimerEventList,"actual done frees work once and actual timer service clears completion metadata after callback");
 __atomic_store_n(&releaseAction,1U,__ATOMIC_RELEASE);require(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)==NV_OK);
 for(NvU32 i=0;i<3000;++i){require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);if(s.directActionReturned==1)break;usleep(1000);}
 expect(s.workActionReturned==1&&s.directActionReturned==1&&!s.liveWork&&!s.liveDirect&&!s.eventBorrowers,"genuine service action returns release both real direct and accepted-work borrowers");
 require(s540FirstTxnOriginalExitReady(&nv,NV_OK)==NV_OK);require(s540FirstTxnOriginalWrapperReturned(&nv)==NV_OK);require(s540FirstTxnBeginClosing(&nv)==NV_OK);
 expect(s540FirstTxnSeal(&nv)==NV_OK&&s540FirstTxnBeginDestructive(&nv)==NV_OK,"real timer stop and both actual queues drain before record seal and destructive boundary");
 expect(s540GspTimersDestroyNano(&nv,handle)==NV_OK,"sealed zero-borrow event destroys through actual service callback-stage probe without guard recursion");
 require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);expect(s.phase==S540_FIRST_DESTRUCTIVE&&!s.firstStatus&&s.sealSerial==s.generation,"software seal records exact generation only; no hardware receipt issued");
}
static void stickyReturned(void){
 nv_nano_timer_t *handle=NULL;S540FirstTxnSnapshot s={0};setup();heldAction=1;
 nv_create_nano_timer(&nv,&event.super,&handle);require(handle!=NULL);nv_start_nano_timer(&nv,handle,0);require(waitFor(&actionOriginalReturned));
 s540FirstTxnObserveServiceRefusal(777,11,NV_ERR_NOT_SUPPORTED);__atomic_store_n(&releaseAction,1U,__ATOMIC_RELEASE);
 require(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)==NV_OK);
 for(NvU32 i=0;i<3000;++i){require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);if(s.directActionReturned==1)break;usleep(1000);}
 expect(s.phase==S540_FIRST_RETAINED&&s.firstStatus==NV_ERR_NOT_SUPPORTED,"actual producer refusal remains first sticky status");
 expect(s.workActionReturned==1&&!s.liveWork&&!s.eventBorrowers,"consumed original work settles after sticky without treating freed pointer as live");
 expect(s540FirstTxnCheckBeforeDestroy(&nv)==NV_ERR_NOT_SUPPORTED,"sticky record blocks first original destructor");
 expect(s540FirstTxnOriginalExitReady(&nv,NV_OK)==NV_ERR_NOT_SUPPORTED,"successful original return cannot erase earlier sticky failure after actual unlock proof");
 require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(s.originalExitReady&&s.originalInFlight&&!s.originalReturned&&s.phase==S540_FIRST_RETAINED,"unlocked failed wrapper marks exit-ready without claiming outer return");
 NV_STATUS wrapped=s540FirstTxnOriginalWrapperReturned(&nv);require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(wrapped==NV_ERR_NOT_SUPPORTED&&s.originalReturned&&!s.originalInFlight&&s.firstStatus==NV_ERR_NOT_SUPPORTED,"actual outer wrapper return settles call reference while preserving first failure");
}
static void unknownEvent(void){
 nv_nano_timer_t *handle=NULL;S540FirstTxnSnapshot s={0};setup();event.super.pTimeProc=NULL;
 nv_create_nano_timer(&nv,&event.super,&handle);require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(!handle&&s.phase==S540_FIRST_RETAINED&&s.firstStatus==NV_ERR_NOT_SUPPORTED,"unknown actual event metadata refuses before publication; no default drop");
 S540GspTimersSnapshot timers;s540GspTimersGetSnapshot(&timers);expect(timers.liveNanoTimers==1&&timers.quarantined,"unpublished real timer owner remains retained on unknown policy");
}
static void pendingCancelledSticky(void){
 nv_nano_timer_t *handle=NULL;S540FirstTxnSnapshot s={0};setup();
 nv_create_nano_timer(&nv,&event.super,&handle);require(handle!=NULL);nv_start_nano_timer(&nv,handle,60000000000ULL);
 s540FirstTxnObserveServiceRefusal(888,12,NV_ERR_NOT_SUPPORTED);
 expect(s540GspTimersCancelNano(&nv,handle)==NV_OK,"actual pending-arm cancellation settles under registry spin guard despite transaction sticky");
 expect(s540GspTimersCancelNano(&nv,handle)==NV_OK,"actual second cancellation cannot consume the same arm ticket twice");
 require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);
 expect(s.directAccepted==1&&!s.liveDirect&&!s.eventBorrowers&&!s.directActionReturned&&!callbackCalls,"genuine cancelled pending arm releases borrower without inventing action return");
 expect(s.phase==S540_FIRST_RETAINED&&s.firstStatus==NV_ERR_NOT_SUPPORTED&&s540FirstTxnCheckBeforeDestroy(&nv)!=NV_OK,"actual service cancellation success cannot erase original sticky refusal");
}
int main(void){
 unsigned total=0,totalFailures=0;
 for(unsigned t=0;t<4;++t){int pipefd[2];require(pipe(pipefd)==0);pid_t child=fork();require(child>=0);
  if(!child){close(pipefd[0]);if(t==0)healthy();else if(t==1)stickyReturned();else if(t==2)unknownEvent();else pendingCancelledSticky();unsigned result[2]={checks,failures};require(write(pipefd[1],result,sizeof(result))==sizeof(result));close(pipefd[1]);_Exit(failures?1:0);}
  close(pipefd[1]);unsigned result[2]={0};ssize_t count=read(pipefd[0],result,sizeof(result));close(pipefd[0]);int status=0;require(waitpid(child,&status,0)==child);
  total+=result[0];totalFailures+=result[1];if(count!=sizeof(result)||!WIFEXITED(status)||WEXITSTATUS(status)){++totalFailures;fprintf(stderr,"actual bodies child %u failed status %d\n",t,status);}
 }
 printf("{\"format\":1,\"status\":\"%s\",\"checks\":%u,\"failures\":%u,\"actual_original_bodies\":12,\"actual_strong_record\":true,\"actual_queues_and_timers\":true,\"descriptor_policy\":\"explicit-test-only-typed-rows\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"hardware_admission\":false}\n",totalFailures?"failed":"passed",total,totalFailures);return totalFailures?1:0;
}
