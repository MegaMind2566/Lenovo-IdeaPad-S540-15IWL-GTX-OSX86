/* Exact transformed original os_timer.c surrounds these endpoint fixtures.
 * Registration/removal/list traversal, original lock/TLS cleanup and the
 * cancellation record are real. GPU power, locks, timer backend, monotonic
 * clock and first-record observation/physical-release boundary are fixtures. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gpu/gpu.h"
#undef memcpy
#undef memset
#define memcpy(...) __builtin_memcpy(__VA_ARGS__)
#define memset(...) __builtin_memset(__VA_ARGS__)
static OBJGPU actualGpu;
static OBJTMR actualTimer;
static OBJSYS actualSystem;
static TMR_EVENT actualEvent;
static nv_state_t exactNv, foreignNv;
static S540GspCancellationToken token;
static NvU64 nowNs = 1000000000ULL, eventNs = 1000000000ULL, thread = 71;
static NvU32 checks, calls[64], arms, cancels, destroys, creates, acquired,
    released, stateInit, stateFree, semAcquired, semReleased, mode;
static NvBool fullPower = NV_TRUE, interruptContext = NV_FALSE,
    ownsDevice = NV_TRUE, lockFails, semFails, recordBound;
static NV_STATUS armStatus, observedFailure;
static TIMEPROC timerCallback;
static void expect(NvBool value, const char *why)
{
    ++checks;
    if (!value) { fprintf(stderr, "RC check failed: %s\n", why); exit(1); }
}
NvBool s540Darwin_os_semaphore_may_sleep(void) { return NV_TRUE; }
NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out) { *out=thread; return NV_OK; }
NvU64 s540Darwin_os_get_monotonic_time_ns(void) { return nowNs; }
NV_STATUS s540Darwin_os_schedule(void) { return NV_OK; }
NV_STATUS s540Darwin_os_delay(NvU32 n) { (void)n; return NV_OK; }
void s540FirstTxnObserveServiceRefusal(NvU32 domain, NvU32 site, NV_STATUS status)
{ (void)domain; (void)site; if (recordBound && !observedFailure) observedFailure=status; }
NV_STATUS s540FirstTxnGetSnapshot(const void *nv, S540FirstTxnSnapshot *out)
{
    if (!recordBound || nv != &exactNv) return NV_ERR_INVALID_ARGUMENT;
    memset(out,0,sizeof(*out)); out->firstStatus=observedFailure; return NV_OK;
}
NV_STATUS s540FirstTxnBackendBeginRelease(const S540FirstTxnHostIdentity *birth, NvU64 *permit)
{
    expect(birth && !birth->owner && !birth->generation,"release boundary uses empty, never retagged birth");
    *permit=recordBound?0:91; return recordBound?NV_ERR_NOT_SUPPORTED:NV_OK;
}
NV_STATUS s540FirstTxnBackendEnd(NvU64 permit)
{ expect(permit==91,"only actual preepoch release permit is completed"); return NV_OK; }
static NV_STATUS fixtureCreate(OBJTMR *tmr,TMR_EVENT **event,TIMEPROC callback,void *data,NvU32 flags)
{ (void)tmr;(void)data;(void)flags;++creates;*event=&actualEvent;timerCallback=callback;return NV_OK; }
static NV_STATUS fixtureArm(OBJTMR *tmr,TMR_EVENT *event,NvU64 delay)
{
    expect(tmr==&actualTimer && event==&actualEvent && delay==1000000000ULL,"original one-second timer arm arguments");
    ++arms;
    if(mode==13) expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"revoke inside actual arm endpoint");
    return armStatus;
}
static void fixtureCancel(OBJTMR *tmr,TMR_EVENT *event)
{ (void)tmr;(void)event;++cancels; }
static void fixtureDestroy(OBJTMR *tmr,TMR_EVENT *event)
{ (void)tmr;(void)event;++destroys; }
static NV_STATUS fixtureGpuAcquire(NvU32 gpu,GPU_LOCK_GRP_ID group,NvU32 flags,NvU32 module,GPU_MASK *mask)
{ (void)gpu;(void)group;(void)flags;(void)module;if(lockFails)return NV_ERR_BUSY_RETRY;++acquired;*mask=1;return NV_OK; }
static void fixtureGpuRelease(GPU_MASK mask,NvU32 flags)
{ (void)flags;expect(mask==1,"original release mask");++released; }
static NV_STATUS fixtureSemAcquire(void *sema)
{ (void)sema;if(semFails)return NV_ERR_BUSY_RETRY;++semAcquired;return NV_OK; }
static void fixtureSemRelease(void *sema,void *threadState)
{ (void)sema;(void)threadState;++semReleased; }
static void fixtureStateInit(THREAD_STATE_NODE *node,OBJGPU *gpu,NvU32 flags)
{ (void)node;(void)gpu;(void)flags;++stateInit; }
static void fixtureStateFree(THREAD_STATE_NODE *node,OBJGPU *gpu,NvU32 flags)
{ (void)node;(void)gpu;(void)flags;++stateFree; }
#undef GPU_GET_TIMER
#define GPU_GET_TIMER(gpu) (&actualTimer)
#undef SYS_GET_INSTANCE
#define SYS_GET_INSTANCE() (&actualSystem)
#undef gpuIsGpuFullPower
#define gpuIsGpuFullPower(gpu) (fullPower)
#undef tmrEventCreate
#define tmrEventCreate fixtureCreate
#undef tmrEventScheduleRel
#define tmrEventScheduleRel fixtureArm
#undef tmrEventCancel
#define tmrEventCancel fixtureCancel
#undef tmrEventDestroy
#define tmrEventDestroy fixtureDestroy
#undef rmGpuGroupLockAcquire
#define rmGpuGroupLockAcquire fixtureGpuAcquire
#undef rmGpuGroupLockRelease
#define rmGpuGroupLockRelease fixtureGpuRelease
#undef rmDeviceGpuLockIsOwner
#define rmDeviceGpuLockIsOwner(gpu) (ownsDevice)
#undef osCondAcquireRmSema
#define osCondAcquireRmSema fixtureSemAcquire
#undef osReleaseRmSema
#define osReleaseRmSema fixtureSemRelease
#undef threadStateInitISRAndDeferredIntHandler
#define threadStateInitISRAndDeferredIntHandler fixtureStateInit
#undef threadStateFreeISRAndDeferredIntHandler
#define threadStateFreeISRAndDeferredIntHandler fixtureStateFree
#undef portUtilIsInterruptContext
#define portUtilIsInterruptContext() (interruptContext)
#undef osGetMonotonicTimeNs
#define osGetMonotonicTimeNs() (nowNs)
#undef NV_PRINTF
#define NV_PRINTF(...) do {} while(0)

/* EXACT_TRANSFORMED_ORIGINAL_BODY */

static void replacement(OBJGPU *gpu,void *data) { (void)gpu; ++calls[(NvUPtr)data]; }
static void callback(OBJGPU *gpu,void *data)
{
    NvU32 id=(NvU32)(NvUPtr)data;
    ++calls[id];
    if (mode==2 || mode==3 || mode==19) expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"real cancellation inside genuine original callback");
    if (mode==4 || mode==5) {
        osRemove1HzCallback(gpu,callback,data);
        if(mode==5) expect(osSchedule1HzCallback(gpu,replacement,(void *)7,NV_OS_1HZ_REPEAT)==NV_OK,"same actual slot reused for a different callback");
    }
    if(mode==6) expect(osSchedule1HzCallback(gpu,replacement,(void *)7,NV_OS_1HZ_REPEAT)==NV_OK,"callback genuinely inserts another registration");
    if(mode==12) nowNs=eventNs+30000000000ULL;
}
static void setup(NvBool bind,NvBool cleanup)
{
    actualGpu.pOsGpuInfo=&exactNv;
    actualTimer.PDB_PROP_TMR_USE_PTIMER_FOR_OSTIMER_CALLBACKS=NV_TRUE;
    expect(osInit1HzCallbacks(&actualTimer)==NV_OK && creates==1 && timerCallback,"original constructor creates real callback target and table");
    if(bind){
        expect(s540GspCancellationBind(&exactNv,&token)==NV_OK && token,"genuine cancellation binding");
        expect(s540GspCancellationBegin(token)==NV_OK,"genuine owner operation");
        if(cleanup){
            expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"real PM callback before cleanup");
            expect(s540GspCancellationBeginCleanupState(&exactNv)==NV_OK,"genuine explicit cleanup scope");
            nowNs=eventNs+30000000000ULL-1;
        }
    }
}
static void add(NvU32 id,NvU32 flags)
{ expect(osSchedule1HzCallback(&actualGpu,callback,(void *)(NvUPtr)id,flags)==NV_OK,"actual original registration accepted"); }
static NV_STATUS drain(void)
{ actualGpu.bCallbackQueued=NV_TRUE;return s540Global_s540OsRunQueued1HzCallbacksUnderLockStatus(&actualGpu); }
static NvU32 entries(OS1HZTIMERENTRY *entry)
{ NvU32 n=0;while(entry && n<64){++n;entry=entry->next;}return n; }
int main(int argc,char **argv)
{
    expect(argc==2,"scenario argument required");mode=(NvU32)atoi(argv[1]);
    setup(mode==1 || mode==2 || mode==3 || mode==11 || mode==12 || mode==13 || mode==17 || mode==19,
        mode==11 || mode==12);
    if(mode==0){
        add(1,NV_OS_1HZ_REPEAT);add(2,NV_OS_1HZ_ONESHOT);
        expect(drain()==NV_OK && calls[1]==1 && calls[2]==1 && !actualGpu.bCallbackQueued,"ordinary repeat and oneshot genuine completion");
        expect(entries(actualTimer.pOs1HzCallbackList)==1 && entries(actualTimer.pOs1HzCallbackFreeList)==35,"original oneshot is retired exactly once");
        expect(drain()==NV_OK && calls[1]==2 && calls[2]==1,"later tick repeats only live callback");
    }else if(mode==1){
        add(1,NV_OS_1HZ_REPEAT);expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"pre-dispatch revoke");
        expect(drain()==NV_ERR_OPERATION_ABORTED && !calls[1] && actualGpu.bCallbackQueued && entries(actualTimer.pOs1HzCallbackList)==1,"cancel before callback preserves actual queued registration");
        osRunQueued1HzCallbacksUnderLock(&actualGpu);
        expect(!calls[1] && actualGpu.bCallbackQueued,"void legacy wrapper cannot erase retained obligation");
    }else if(mode==2 || mode==3){
        add(1,NV_OS_1HZ_REPEAT);add(2,mode==3?NV_OS_1HZ_ONESHOT:NV_OS_1HZ_REPEAT);
        expect(drain()==NV_ERR_OPERATION_ABORTED && calls[2]==1 && !calls[1] && actualGpu.bCallbackQueued,"cancel after returned callback prevents next callback");
        expect(entries(actualTimer.pOs1HzCallbackList)==(mode==3?1:2),"returned oneshot retired but unvisited registration remains");
        expect(drain()==NV_ERR_OPERATION_ABORTED && calls[2]==1,"retained cancellation never reruns returned callback");
    }else if(mode>=4 && mode<=6){
        add(1,NV_OS_1HZ_REPEAT);add(2,NV_OS_1HZ_REPEAT);
        OS1HZTIMERENTRY *slot=actualTimer.pOs1HzCallbackList;
        expect(drain()==NV_ERR_BUSY_RETRY && calls[2]==1 && !calls[1] && !calls[7] && actualGpu.bCallbackQueued,"actual mutation stops without walking freed or replacement slot");
        expect(entries(actualTimer.pOs1HzCallbackList)==(mode==4?1:mode==5?2:3),"all actual unvisited or replacement registrations retained");
        if(mode==5)expect(actualTimer.pOs1HzCallbackList==slot && slot->callback==replacement,"same-slot ABA exists in genuine original registration path");
        expect(drain()==NV_ERR_BUSY_RETRY && !calls[1] && !calls[7],"sticky lifecycle refusal prevents false replay after void callback mutation");
    }else if(mode==7){
        armStatus=NV_ERR_TIMEOUT;
        expect(osSchedule1HzCallback(&actualGpu,callback,(void *)1,NV_OS_1HZ_REPEAT)==NV_ERR_TIMEOUT,"actual first-arm failure propagated");
        expect(arms==1 && !actualTimer.pOs1HzCallbackList && entries(actualTimer.pOs1HzCallbackFreeList)==36,"failed arm never consumes a registration or claims publication");
    }else if(mode==8){
        for(NvU32 i=1;i<=36;++i)add(i,NV_OS_1HZ_REPEAT);
        expect(drain()==NV_OK,"full real table completes one bounded bookkeeping pass");
        for(NvU32 i=1;i<=36;++i)expect(calls[i]==1,"each real registration called once");
        expect(osSchedule1HzCallback(&actualGpu,callback,(void *)37,NV_OS_1HZ_REPEAT)==NV_ERR_INVALID_REQUEST,"actual fixed table capacity preserved");
    }else if(mode==9){
        add(1,NV_OS_1HZ_REPEAT);actualTimer.pOs1HzCallbackList->next=actualTimer.pOs1HzCallbackList;
        expect(drain()==NV_ERR_INVALID_STATE && calls[1]==1 && actualGpu.bCallbackQueued,"cycle detected before a second execution, without dropping cycle metadata");
    }else if(mode==10){
        add(1,NV_OS_1HZ_REPEAT);fullPower=NV_FALSE;
        expect(drain()==NV_ERR_NOT_READY && !calls[1] && actualGpu.bCallbackQueued,"low power is retained work, not software completion");
        fullPower=NV_TRUE;ownsDevice=NV_FALSE;
        expect(drain()==NV_ERR_INVALID_LOCK_STATE && !calls[1] && actualGpu.bCallbackQueued,"device-lock refusal retains queued callback");
        ownsDevice=NV_TRUE;interruptContext=NV_TRUE;
        expect(drain()==NV_ERR_INVALID_STATE && !calls[1] && actualGpu.bCallbackQueued,"interrupt-context refusal retains queued callback");
    }else if(mode==11 || mode==12){
        add(1,NV_OS_1HZ_REPEAT);add(2,NV_OS_1HZ_ONESHOT);
        expect(drain()==(mode==12?NV_ERR_TIMEOUT:NV_OK),"real cleanup uses unchanged fixed deadline");
        expect(calls[2]==1 && calls[1]==(mode==11) && entries(actualTimer.pOs1HzCallbackList)==1,"cleanup expiration retires completed oneshot while retaining unvisited entry");
        S540GspCancellationSnapshot snapshot={0};expect(s540GspCancellationGetSnapshot(token,&snapshot)==NV_OK && snapshot.deadlineNs==eventNs+30000000000ULL,"actual thirty-second timestamp is unchanged");
    }else if(mode==13){
        add(1,NV_OS_1HZ_REPEAT);
        expect(arms==1 && entries(actualTimer.pOs1HzCallbackList)==1,"accepted arm completes actual registration despite concurrent revoke");
        expect(drain()==NV_ERR_OPERATION_ABORTED && !calls[1] && actualGpu.bCallbackQueued,"subsequent observed cancellation retains accepted obligation");
    }else if(mode==14){
        add(1,NV_OS_1HZ_REPEAT);recordBound=NV_TRUE;
        OS1HZTIMERENTRY *list=actualTimer.pOs1HzCallbackList,*freeList=actualTimer.pOs1HzCallbackFreeList;
        expect(osDestroy1HzCallbacks(&actualTimer)==NV_ERR_NOT_SUPPORTED && !destroys && actualTimer.pOs1HzEvent==&actualEvent && actualTimer.pOs1HzCallbackList==list && actualTimer.pOs1HzCallbackFreeList==freeList,"release-boundary refusal precedes destroy and all metadata clearing");
    }else if(mode==15){
        add(1,NV_OS_1HZ_REPEAT);
        expect(osDestroy1HzCallbacks(&actualTimer)==NV_OK && destroys==1 && !actualTimer.pOs1HzEvent && !actualTimer.pOs1HzCallbackList,"pre-epoch genuine cleanup retains original behavior");
    }else if(mode==16){
        add(1,NV_OS_1HZ_REPEAT);lockFails=NV_TRUE;
        expect(s540Global_s540OsRun1HzCallbacksNowStatus(&actualGpu)==NV_ERR_BUSY_RETRY && !calls[1] && !released && !stateFree && actualGpu.bCallbackQueued,"GPU-lock failure retains work without releasing unacquired ownership");
        lockFails=NV_FALSE;semFails=NV_TRUE;
        expect(s540Global_s540OsRun1HzCallbacksNowStatus(&actualGpu)==NV_ERR_BUSY_RETRY && acquired==1 && released==1 && !semReleased && !stateFree,"semaphore failure releases only actual acquired GPU lock");
        semFails=NV_FALSE;
        expect(osRun1HzCallbacksNow(&actualGpu) && calls[1]==1 && acquired==2 && released==2 && stateInit==1 && stateFree==1 && semAcquired==1 && semReleased==1 && !actualGpu.bCallbackQueued,"legacy ABI wrapper preserves full original cleanup and genuine completion");
    }else if(mode==17){
        add(1,NV_OS_1HZ_REPEAT);expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"revoke exact nv");actualGpu.pOsGpuInfo=&foreignNv;
        expect(drain()==NV_OK && calls[1]==1,"foreign nv cannot borrow exact cancellation authority");
    }else if(mode==18){
        add(1,NV_OS_1HZ_REPEAT);expect(timerCallback(&actualGpu,&actualTimer,&actualEvent)==NV_OK && arms==2 && calls[1]==1,"actual PTIMER callback rearms after genuine completion");
        armStatus=NV_ERR_TIMEOUT;
        expect(timerCallback(&actualGpu,&actualTimer,&actualEvent)==NV_ERR_TIMEOUT && calls[1]==2 && actualGpu.bCallbackQueued,"real rearm failure preserves pending callback state");
        expect(timerCallback(&actualGpu,&actualTimer,&actualEvent)==NV_ERR_TIMEOUT && calls[1]==2 && arms==3,"failed rearm cannot silently restart original callbacks");
    }else if(mode==19){
        add(1,NV_OS_1HZ_REPEAT);
        expect(timerCallback(&actualGpu,&actualTimer,&actualEvent)==NV_ERR_OPERATION_ABORTED && calls[1]==1 && arms==1 && actualGpu.bCallbackQueued,"actual PTIMER callback cancellation retains registration and never rearms");
        expect(acquired==1 && released==1 && semAcquired==1 && semReleased==1 && stateInit==1 && stateFree==1,"original PTIMER lock/thread-state cleanup runs after cancellation");
        expect(timerCallback(&actualGpu,&actualTimer,&actualEvent)==NV_ERR_OPERATION_ABORTED && calls[1]==1 && arms==1 && actualGpu.bCallbackQueued,"later entry cannot replay canceled callback or fake timer drain");
    }else return 2;
    if(token){expect(s540GspCancellationFinish(token)==NV_OK,"actual cancellation operation returned");expect(s540GspCancellationUnbind(token)==NV_OK,"actual completed cancellation generation unbound");}
    printf("{\"status\":\"passed\",\"scenario\":%u,\"checks\":%u,\"failures\":0,\"pm_30_second_shutdown_bound_proven\":false}\n",mode,checks);
    return 0;
}
