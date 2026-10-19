/* SPDX-License-Identifier: MIT */
/* Real record, retained Host, queues and Darwin timer backend. Actual pinned
 * RC wrapper/metadata and immutable production descriptor rows are included.
 * GPU lookup, sanity, 1Hz action and RM-lock observation are explicit fixtures.
 * This does not establish the transitive 1Hz callback policy or GPU execution. */
#include "nv.h"
#include "nv-priv.h"
#include "gpu/gpu.h"
#include "gpu/timer/objtmr.h"
#include "nvoc/rtti.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaGspFirstTransactionOriginal.h"
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
#include <pthread.h>
static nv_state_t nv;
static OBJGPU gpu;
static OBJTMR tmr;
static int retainedOwner;
static struct os_work_queue *deviceQueue,*globalQueue;
static S540GspCancellationToken cancelToken;
static NvU32 checks, failures, callbacks, blockCallback, releaseCallback;
static NvU64 generation, masterThread;
static __thread NvU32 runtimeDepth;
extern void s540RcControlFailNextAllocation(void);
static void require(NvBool value){if(!value)abort();}
static void expect(NvBool value,const char *why){++checks;if(!value){++failures;fprintf(stderr,"RC: %s\n",why);}}
static OBJGPU *fixturePrivate(nv_state_t *state){require(state==&nv);return &gpu;}
static OBJGPU *fixtureGpu(NvU32 instance){require(instance==0);return &gpu;}
static OBJTMR *fixtureTimer(OBJGPU *g){require(g==&gpu);return &tmr;}
static NvBool fixture1Hz(OBJGPU *g){
    require(g==&gpu&&runtimeDepth==1&&s540GspCancellationCurrentScopeActive());
    __atomic_fetch_add(&callbacks,1U,__ATOMIC_RELEASE);
    if(blockCallback)for(unsigned n=0;n!=3000&&!__atomic_load_n(&releaseCallback,__ATOMIC_ACQUIRE);++n)usleep(1000);
    require(!blockCallback||__atomic_load_n(&releaseCallback,__ATOMIC_ACQUIRE));return NV_TRUE;
}
static NV_STATUS fixtureTimerService(OBJGPU *g,OBJTMR *t,TMR_EVENT *event){(void)g;(void)t;(void)event;abort();}
#undef NV_GET_NV_PRIV_PGPU
#define NV_GET_NV_PRIV_PGPU fixturePrivate
#undef FULL_GPU_SANITY_CHECK
#define FULL_GPU_SANITY_CHECK(g) ((g)==&gpu)
#undef NV_ENTER_RM_RUNTIME
#define NV_ENTER_RM_RUNTIME(sp,fp) do{require((sp)!=NULL&&!runtimeDepth);runtimeDepth=1;(fp)=NULL;}while(0)
#undef NV_EXIT_RM_RUNTIME
#define NV_EXIT_RM_RUNTIME(sp,fp) do{(void)(sp);(void)(fp);require(runtimeDepth==1);runtimeDepth=0;}while(0)
#undef osRun1HzCallbacksNow
#define osRun1HzCallbacksNow fixture1Hz
#undef gpumgrGetGpu
#define gpumgrGetGpu fixtureGpu
#undef GPU_GET_TIMER
#define GPU_GET_TIMER fixtureTimer
#undef tmrEventServiceTimer
#define tmrEventServiceTimer fixtureTimerService
#undef NV_PRINTF
#define NV_PRINTF(...) ((void)0)
#include "actual-rc-bodies.inc"
#include "actual-metadata.inc"
#include "actual-policy.inc"
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *state){
    NvU64 thread=0;
    return state==&nv&&s540Darwin_os_get_current_thread(&thread)==NV_OK&&thread==masterThread&&!runtimeDepth?NV_OK:NV_ERR_INVALID_LOCK_STATE;
}
NV_STATUS s540FirstTxnOriginalReadServiceCounters(const void *state,S540FirstTxnServiceCounters *out){
    S540NvidiaGlobalRmHostSnapshot host={0};S540NvidiaGlobalCryptoSnapshot crypto={0};S540DeviceMemoryStatistics memory;
    require(state==&nv&&out);s540GlobalRmHostSnapshot(&host);s540Global_crypto_snapshot(&crypto);memory=s540DeviceMemoryStatistics();
    *out=(S540FirstTxnServiceCounters){0};out->hostInitialized=host.initialized;out->hostUnavailable=host.unavailableCalls;out->hostInvalidFrees=host.invalidFrees;
    out->memoryUnavailableEver=memory.unavailableOperationsEver;out->memoryViolationsEver=memory.lifetimeViolationsEver;
    out->cryptoUnavailable=crypto.unavailable_calls;out->cryptoMaskLow=crypto.unavailable_symbol_mask;out->cryptoMaskHigh=crypto.unavailable_symbol_mask_high;out->cryptoOverflow=crypto.counter_overflow!=0;
    return NV_OK;
}
void *NV_API_CALL os_mem_set(void *out,NvU8 value,NvU32 bytes){NvU8 *p=out;while(bytes--)*p++=value;return out;}
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *stack,nv_state_t *state,void *event){(void)stack;(void)state;(void)event;abort();}
static void action(void *context,void *data){(void)context;(void)data;abort();}
static S540FirstTxnSnapshot snapshot(void){S540FirstTxnSnapshot s={0};require(s540FirstTxnGetSnapshot(&nv,&s)==NV_OK);return s;}
static void setup(void){
    S540NvidiaGlobalRmPlatformFacts facts={0};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;facts.osVersion=facts.osDate="rc-cpu-fixture";
    require(s540GlobalRmHostInitialize(&facts)==NV_OK);require(s540Darwin_os_get_current_thread(&masterThread)==NV_OK);
    require(s540FirstTxnBeginOwner(&retainedOwner)==NV_OK);require(s540GspCancellationBind(&nv,&cancelToken)==NV_OK&&s540GspCancellationBegin(cancelToken)==NV_OK);
    require(s540FirstTxnBind(&nv,cancelToken)==NV_OK);generation=snapshot().generation;
    require(s540GspTimersBind(&nv)==NV_OK);require(s540DarwinWorkQueueCreate(action,&nv,&deviceQueue)==NV_OK&&s540DarwinWorkQueueCreate(action,&nv,&globalQueue)==NV_OK);
    require(s540DarwinBindGlobalWorkQueue(globalQueue)==NV_OK);nv.queue=deviceQueue;
    require(s540FirstTxnServicesBind(&nv,generation,deviceQueue,globalQueue)==NV_OK);require(s540FirstTxnOriginalEnter(&nv)==NV_OK);
}
static void exitRoot(void){require(s540FirstTxnOriginalExitReady(&nv,NV_OK)==NV_OK&&s540FirstTxnOriginalWrapperReturned(&nv)==NV_OK);}
static void waitReturned(void){for(unsigned n=0;n!=3000;++n){if(snapshot().directActionReturned)return;usleep(1000);}abort();}
static void pending(void){
    setup();expect(nv_start_rc_timer(&nv)==0,"real RC arm is admitted before backend publication");
    S540FirstTxnSnapshot s=snapshot();expect(s.directAccepted==1&&s.liveDirect==1&&!s.directOriginalReturned&&!callbacks,"pending original RC has a genuine direct lease");
    expect(nv_stop_rc_timer(&nv)==0,"successful synchronous cancellation retires pending RC arm");s=snapshot();
    expect(!s.firstStatus&&!s.liveDirect&&!s.directOriginalReturned&&!callbacks,"cancellation cannot fabricate an executed RC wrapper");exitRoot();
    expect(s540FirstTxnBeginClosing(&nv)==NV_OK&&s540FirstTxnSeal(&nv)==NV_OK,"real queues and RC can seal with no invented event owners");
    expect(snapshot().ownerCount==0&&snapshot().eventCount==0,"RC does not pretend nv is TMR_EVENT or NVOC");
    expect(s540GspTimersUnbind(&nv)==NV_ERR_IN_USE,"callback text owner still requires final hardware release contract");
}
static void fired(void){
    setup();expect(nv_start_rc_timer(&nv)==0,"actual RC start accepts reviewed wrapper address");exitRoot();waitReturned();
    S540FirstTxnSnapshot s=snapshot();expect(callbacks==1&&s.directOriginalReturned==1&&s.directActionReturned==1,"actual original wrapper and actual later action return are distinct");
    expect(s.directAccepted==2&&s.liveDirect==1&&!s.firstStatus,"RC rearm owns a new generation while old action return retires its own lease");
    expect(nv_stop_rc_timer(&nv)==0&&snapshot().liveDirect==0,"new pending arm is cancelled without reusing previous return evidence");
    expect(s540FirstTxnBeginClosing(&nv)==NV_OK&&s540FirstTxnSeal(&nv)==NV_OK,"one real RC callback plus rearm can be fully software-drained");
}
static void *releaseLater(void *unused){(void)unused;usleep(50000);__atomic_store_n(&releaseCallback,1U,__ATOMIC_RELEASE);return NULL;}
static void running(void){
    setup();blockCallback=1;require(nv_start_rc_timer(&nv)==0);exitRoot();
    for(unsigned n=0;n!=3000&&!__atomic_load_n(&callbacks,__ATOMIC_ACQUIRE);++n)usleep(1000);require(callbacks==1);
    S540FirstTxnSnapshot before=snapshot();expect(before.liveDirect==1&&!before.directActionReturned,"in-flight RC cannot be treated as returned");
    pthread_t helper;require(pthread_create(&helper,NULL,releaseLater,NULL)==0);
    expect(s540GspTimersStop(&nv)==NV_OK,"actual synchronous stop waits for running RC and final backend return hook");require(pthread_join(helper,NULL)==0);
    S540FirstTxnSnapshot after=snapshot();expect(after.directAccepted==1&&after.directActionReturned==1&&!after.liveDirect&&!after.firstStatus,"stopping prevents callback rearm and preserves exact completion");
    expect(s540FirstTxnTimersValidateStopped(&nv,generation)==NV_OK,"guarded service state confirms RC retirement");
}
static void forged(void){
    setup();NvU64 ticket=99;expect(s540FirstTxnRcAdmit(&nv,&tmr,1,&ticket)!=NV_OK&&!ticket,"ordinary caller cannot forge actual guarded timer ADMIT stage");
    expect(snapshot().phase==S540_FIRST_RETAINED&&snapshot().firstStatus,"forged producer attempt becomes sticky before any teardown");
}
static void allocationFailure(void){
    setup();s540RcControlFailNextAllocation();require(nv_start_rc_timer(&nv)==0);exitRoot();
    for(unsigned n=0;n!=3000&&!snapshot().firstStatus;++n)usleep(1000);
    S540FirstTxnSnapshot s=snapshot();
    expect(s.firstStatus==NV_ERR_NO_MEMORY&&s.phase==S540_FIRST_RETAINED,"actual Host stack-allocation failure is sticky before any false completion");
    expect(!callbacks&&!s.directOriginalReturned&&!s.directActionReturned&&s.liveDirect==1,"uncalled original wrapper never becomes original-return evidence");
    S540GspTimersSnapshot timers={0};
    for(unsigned n=0;n!=3000;++n){s540GspTimersGetSnapshot(&timers);if(timers.callbackFailures)break;usleep(1000);}
    expect(timers.quarantined&&timers.callbackFailures==1,"failed active participant retains real timer and callback owners");
    expect(s540GspTimersStop(&nv)!=NV_OK&&s540GspTimersUnbind(&nv)!=NV_OK,"allocation failure cannot authorize successful final timer release");
}
int main(void){
    unsigned total=0;
    for(unsigned test=0;test!=5;++test){int pipefd[2];require(pipe(pipefd)==0);pid_t child=fork();require(child>=0);
        if(!child){close(pipefd[0]);if(test==0)pending();else if(test==1)fired();else if(test==2)running();else if(test==3)forged();else allocationFailure();unsigned out[2]={checks,failures};require(write(pipefd[1],out,sizeof(out))==sizeof(out));_Exit(failures?1:0);}
        close(pipefd[1]);unsigned out[2]={0};require(read(pipefd[0],out,sizeof(out))==sizeof(out));close(pipefd[0]);int result;require(waitpid(child,&result,0)==child);total+=out[0];failures+=out[1];if(!WIFEXITED(result)||WEXITSTATUS(result))++failures;
    }
    printf("{\"checks\":%u,\"failures\":%u,\"actual_original_rc_wrapper\":true,\"real_record_and_timer\":true,\"event_owner_rows_added\":0,\"hardware_admission\":false}\n",total,failures);return failures?1:0;
}
