/* SPDX-License-Identifier: MIT */
/* Full-header typed port + strong record + actual Host/crypto/memory/queues/
 * timer backend. ONLY metadata rows/readers and original callback bodies are
 * explicit TEST controls. They do not authorize real NVIDIA event policies. */
#include "nv.h"
#include "os-interface.h"
#include "S540NvidiaGspTimers.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaFirstTxnServices.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaGlobalCrypto.h"
#include "nv_unsupported_memory.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>

typedef struct FixtureOwner { const void *classIdentity; } FixtureOwner;
typedef struct FixtureEvent { FixtureOwner *owner; void (*callback)(void); } FixtureEvent;
typedef struct FixtureWork { void (*callback)(void *); void *parameter; NvU32 flags; } FixtureWork;
static unsigned checks, failures;
static int fixtureClass, retainedOwner;
static nv_state_t nv;
static FixtureOwner *object;
static FixtureEvent *event;
static FixtureWork *pendingWork;
static struct os_work_queue *deviceQueue, *globalQueue;
static nv_nano_timer_t *handle;
static S540GspCancellationToken cancelToken;
static NvU64 generation, masterThread;
static NvU32 mode, holdWork, arrived, released, workCalls, queuedByTimer,
    cryptoFailedBeforeNote, eventReadableAfterRetire;
static void require(NvBool v) { if (!v) abort(); }
static void expect(NvBool v, const char *why) {
    ++checks; if (!v) { ++failures; fprintf(stderr, "strong joint: %s\n", why); }
}
static NvBool waitFor(NvU32 *value) {
    for (unsigned n = 0; n != 3000 && !__atomic_load_n(value, __ATOMIC_ACQUIRE); ++n) usleep(1000);
    return __atomic_load_n(value, __ATOMIC_ACQUIRE) != 0;
}
static void eventCallback(void) {}
static void workCallback(void *parameter) {
    require(parameter == event && event->owner == object);
    __atomic_store_n(&arrived, 1U, __ATOMIC_RELEASE);
    if (holdWork) require(waitFor(&released));
    if (mode == 4) {
        NvU8 output[4] = {0x5a,0x5a,0x5a,0x5a};
        require(!s540Global_libspdm_random_bytes(output, sizeof(output)) && output[0] == 0x5a);
        /* Actual refusal has already published sticky. This real internal
         * Host free precedes the outer original-return note. */
        s540GlobalRmHostFreeOriginal(event);
        S540GlobalRmHostAllocationSnapshot retained = {0};
        cryptoFailedBeforeNote = s540GlobalRmHostRetentionInspect(event, &retained) == NV_OK && retained.retired;
        eventReadableAfterRetire = event->owner->classIdentity == &fixtureClass;
    }
    __atomic_fetch_add(&workCalls, 1U, __ATOMIC_RELEASE);
}
const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[] = {
    {S540_FIRST_DESC_OWNER,S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,0,0,0,(NvUPtr)&fixtureClass,NV_FALSE},
    {S540_FIRST_DESC_EVENT,S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,0,0,(NvUPtr)&eventCallback,(NvUPtr)&fixtureClass,NV_FALSE},
    {S540_FIRST_DESC_WORK,S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,~0U,1,(NvUPtr)&workCallback,0,NV_TRUE}
};
const NvU32 s540FirstTxnOriginalDescriptorCount = sizeof(s540FirstTxnOriginalDescriptors)/sizeof(s540FirstTxnOriginalDescriptors[0]);
NV_STATUS s540FirstTxnInspectOriginalOwner(const void *p, NvUPtr *out) {
    if (!p || !out) return NV_ERR_INVALID_ARGUMENT;
    *out = (NvUPtr)((const FixtureOwner *)p)->classIdentity; return NV_OK;
}
NV_STATUS s540FirstTxnInspectOriginalEvent(const void *p, S540FirstTxnOriginalEvent *out) {
    if (!p || !out) return NV_ERR_INVALID_ARGUMENT;
    const FixtureEvent *e = p; out->callback = (NvUPtr)e->callback; out->owner = e->owner; return NV_OK;
}
NV_STATUS s540FirstTxnInspectOriginalWork(const void *p, S540FirstTxnOriginalWork *out) {
    if (!p || !out) return NV_ERR_INVALID_ARGUMENT;
    const FixtureWork *w = p; out->callback = (NvUPtr)w->callback; out->parameter = w->parameter; out->flags = w->flags; return NV_OK;
}
/* A TEST control, never the production OriginalLocksReleased implementation.
 * Actual API/GPU source tokens and blocked RM-sema proof have a separate test. */
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *state) {
    NvU64 thread = 0;
    return state == &nv && s540Darwin_os_get_current_thread(&thread) == NV_OK && thread == masterThread
        ? NV_OK : NV_ERR_INVALID_LOCK_STATE;
}
NV_STATUS s540FirstTxnOriginalReadServiceCounters(const void *state, S540FirstTxnServiceCounters *out) {
    S540NvidiaGlobalRmHostSnapshot host = {0}; S540NvidiaGlobalCryptoSnapshot crypto = {0};
    S540DeviceMemoryStatistics memory;
    if (state != &nv || !out) return NV_ERR_INVALID_ARGUMENT;
    s540GlobalRmHostSnapshot(&host); s540Global_crypto_snapshot(&crypto); memory = s540DeviceMemoryStatistics();
    out->hostInitialized=host.initialized;out->hostUnavailable=host.unavailableCalls;out->hostInvalidFrees=host.invalidFrees;
    out->memoryUnavailableEver=memory.unavailableOperationsEver;out->memoryViolationsEver=memory.lifetimeViolationsEver;
    out->cryptoUnavailable=crypto.unavailable_calls;out->cryptoMaskLow=crypto.unavailable_symbol_mask;
    out->cryptoMaskHigh=crypto.unavailable_symbol_mask_high;out->cryptoOverflow=crypto.counter_overflow;return NV_OK;
}
void *NV_API_CALL os_mem_set(void *out, NvU8 byte, NvU32 bytes) {
    NvU8 *p = out; while (bytes--) *p++ = byte; return out;
}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *stack, nv_state_t *state) {
    (void)stack; (void)state; abort();
}
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *stack, nv_state_t *state, void *parameter) {
    require(stack && ((NvUPtr)stack & 15) == 0 && state == &nv && parameter == event);
    require(s540GspCancellationCurrentScopeActive());
    NV_STATUS status = s540Darwin_os_queue_work_item(deviceQueue, pendingWork);
    if (status == NV_OK) __atomic_store_n(&queuedByTimer,1U,__ATOMIC_RELEASE);
    return status;
}
static void action(void *context, void *data) {
    require(context == &nv);
    FixtureWork *work = data;
    work->callback(work->parameter);
    s540GlobalRmHostFreeOriginal(work);
    require(s540FirstTxnWorkOriginalReturned(&nv, NV_OK) == NV_OK);
}
static FixtureWork *newWork(void) {
    FixtureWork *w = s540GlobalRmHostAllocateOriginal(sizeof(*w)); require(w != NULL);
    w->callback = workCallback; w->parameter = event; w->flags = 1; return w;
}
static void setup(void) {
    S540NvidiaGlobalRmPlatformFacts facts = {0}; S540FirstTxnSnapshot snapshot = {0};
    facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;
    facts.osMajor=25;facts.osVersion=facts.osDate="strong-joint-test-control";
    require(s540GlobalRmHostInitialize(&facts) == NV_OK);
    require(s540Darwin_os_get_current_thread(&masterThread) == NV_OK && masterThread);
    require(s540FirstTxnBeginOwner(&retainedOwner) == NV_OK);
    require(s540GspCancellationBind(&nv, &cancelToken) == NV_OK);
    require(s540GspCancellationBegin(cancelToken) == NV_OK);
    require(s540FirstTxnBind(&nv, cancelToken) == NV_OK);
    require(s540FirstTxnGetSnapshot(&nv,&snapshot) == NV_OK); generation=snapshot.generation;
    require(s540GspTimersBind(&nv) == NV_OK);
    require(s540DarwinWorkQueueCreate(action,&nv,&deviceQueue) == NV_OK);
    require(s540DarwinWorkQueueCreate(action,&nv,&globalQueue) == NV_OK);
    require(s540DarwinBindGlobalWorkQueue(globalQueue) == NV_OK);nv.queue=deviceQueue;
    require(s540FirstTxnServicesBind(&nv,generation,deviceQueue,globalQueue) == NV_OK);
    object=s540GlobalRmHostAllocateOriginal(sizeof(*object));event=s540GlobalRmHostAllocateOriginal(sizeof(*event));
    require(object != NULL && event != NULL);object->classIdentity=&fixtureClass;event->owner=object;event->callback=eventCallback;
    require(s540FirstTxnRegisterOwner(&nv,object) == NV_OK);
    nv_create_nano_timer(&nv,event,&handle);require(handle != NULL);
    require(s540FirstTxnOriginalEnter(&nv) == NV_OK);
}
static S540FirstTxnSnapshot snapshot(void) {
    S540FirstTxnSnapshot s = {0}; require(s540FirstTxnGetSnapshot(&nv,&s) == NV_OK);return s;
}
static void waitDirectReturn(void) {
    for(unsigned n=0;n!=3000;++n){S540FirstTxnSnapshot s=snapshot();if(s.directActionReturned==1)return;usleep(1000);}abort();
}
static void directWork(NvU32 testMode) {
    mode=testMode;setup();pendingWork=newWork();holdWork=1;
    nv_start_nano_timer(&nv,handle,0);require(waitFor(&arrived));waitDirectReturn();
    S540FirstTxnSnapshot s=snapshot();
    expect(queuedByTimer && s.directAccepted==1 && s.directOriginalReturned==1 && s.directActionReturned==1 && !s.liveDirect,
        "actual direct callback entry, original wrapper return and later action return settle its genuine strong ticket");
    expect(s.workAccepted==1 && s.liveWork==1 && s.eventBorrowers==1,
        "actual accepted queue borrower survives completed direct callback");
    if(testMode==2){
        expect(s540GspTimersDestroyNano(&nv,handle)!=NV_OK,
            "actual checked delete cannot retire an event while accepted work is borrowing it");
        s540GlobalRmHostFreeOriginal(event);
        S540GlobalRmHostAllocationSnapshot kept={0};
        expect(s540GlobalRmHostRetentionInspect(event,&kept)==NV_OK && kept.retired && event->owner==object,
            "first strong refusal precedes caller rollback free and actual Host preserves readable event backing");
    }
    __atomic_store_n(&released,1U,__ATOMIC_RELEASE);
    require(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)==NV_OK);s=snapshot();
    expect(s.workOriginalReturned==1 && s.workActionReturned==1 && !s.liveWork && !s.eventBorrowers && workCalls==1,
        "actual original/action returns settle the consumed queue ticket and event borrow truthfully");
    if(testMode==1){
        require(s540FirstTxnOriginalExitReady(&nv,NV_OK)==NV_OK);
        require(s540FirstTxnOriginalWrapperReturned(&nv)==NV_OK);
        expect(s540FirstTxnBeginClosing(&nv)==NV_OK && s540FirstTxnSeal(&nv)==NV_OK &&
            s540FirstTxnBeginDestructive(&nv)==NV_OK,
            "strong state machine invokes actual timer and both queue drains outside fixture RM tokens");
        NV_STATUS deleted=s540GspTimersDestroyNano(&nv,handle);
        NV_STATUS before=s540FirstTxnCheckBeforeDestroy(&nv);
        if(deleted!=NV_OK || before!=NV_OK){S540FirstTxnSnapshot why=snapshot();fprintf(stderr,"delete=%x before=%x first=%x site=%u phase=%u\n",deleted,before,why.firstStatus,why.firstSite,why.phase);}
        expect(deleted==NV_OK && before==NV_OK,
            "sealed exact event generation allows actual checked timer destruction without recursive registry locking");
        s540GlobalRmHostFreeOriginal(event);s540GlobalRmHostFreeOriginal(object);
        S540NvidiaGlobalRmHostSnapshot heap={0};s540GlobalRmHostSnapshot(&heap);
        expect(!heap.originalLiveAllocations && !heap.originalLiveBytes,
            "healthy fixture transaction actually frees its own original heap metadata");
    }else{
        expect(s.phase==S540_FIRST_RETAINED && s.firstStatus && s540FirstTxnBeginClosing(&nv)!=NV_OK,
            "sticky failed transaction stays retained even after real callbacks have all returned");
        if(testMode==4)expect(cryptoFailedBeforeNote && eventReadableAfterRetire,
            "actual crypto refusal freezes real Host free inside callback before outer return note");
    }
    expect(s540GspTimersUnbind(&nv)==NV_ERR_IN_USE && s540DarwinUnbindGlobalWorkQueue(globalQueue)==NV_ERR_IN_USE &&
        s540GspCancellationFinish(cancelToken)==NV_ERR_IN_USE && !s540GlobalRmHostShutdown(),
        "absent final hardware/text receipt retains actual timer, queue, cancellation and Host owners");
}
static void revokedQueued(void) {
    mode=3;setup();holdWork=1;FixtureWork *first=newWork(),*second=newWork();
    require(s540Darwin_os_queue_work_item(deviceQueue,first)==NV_OK);require(waitFor(&arrived));
    require(s540Darwin_os_queue_work_item(deviceQueue,second)==NV_OK);
    require(s540GspCancellationRevoke(cancelToken)==NV_OK);__atomic_store_n(&released,1U,__ATOMIC_RELEASE);
    expect(s540DarwinWorkQueueStop(deviceQueue)==NV_ERR_OPERATION_ABORTED,
        "revoked queued essential work is retained rather than invoked/dropped or falsely drained");
    S540FirstTxnSnapshot s=snapshot();
    expect(s.phase==S540_FIRST_RETAINED && s.workAccepted==2 && s.workActionReturned==1 && s.liveWork==1 && s.eventBorrowers==1 && workCalls==1,
        "real second admitted ticket and borrow remain owned after operation cancellation");
    S540GlobalRmHostAllocationSnapshot kept={0};
    expect(s540GlobalRmHostRetentionInspect(second,&kept)==NV_OK && !kept.retired && kept.bytes==sizeof(*second),
        "unconsumed original work allocation remains genuinely live");
    expect(s540FirstTxnServicesValidateRetired(&nv,generation)!=NV_OK,
        "actual software service retirement refuses the retained accepted item");
}
int main(void) {
    unsigned total=0;
    for(unsigned test=1;test!=5;++test){int pipefd[2];require(pipe(pipefd)==0);pid_t child=fork();require(child>=0);
        if(!child){close(pipefd[0]);checks=failures=0;if(test==3)revokedQueued();else directWork(test);unsigned r[2]={checks,failures};
            require(write(pipefd[1],r,sizeof(r))==sizeof(r));close(pipefd[1]);_Exit(failures?1:0);}
        close(pipefd[1]);unsigned r[2]={0};require(read(pipefd[0],r,sizeof(r))==sizeof(r));close(pipefd[0]);int status=0;
        require(waitpid(child,&status,0)==child);total+=r[0];failures+=r[1];if(!WIFEXITED(status)||WEXITSTATUS(status))++failures;}
    printf("{\"checks\":%u,\"failures\":%u,\"component\":\"strong-record-real-services-joint\","
        "\"actual_strong_record\":true,\"actual_host_crypto_memory\":true,\"actual_queue_timer_backends\":true,"
        "\"original_metadata_and_callback_policy\":\"explicit-typed-test-controls\",\"production_policy_admitted\":false,"
        "\"hardware_admission\":false}\n",total,failures);return failures?1:0;
}
