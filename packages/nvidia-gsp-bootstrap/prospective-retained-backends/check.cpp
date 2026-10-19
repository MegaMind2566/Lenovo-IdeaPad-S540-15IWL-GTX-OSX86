// SPDX-License-Identifier: MIT
// Actual transformed record and Darwin methods. Host preflight and unused
// original/RC metadata adapters are explicit endpoints, never owner setters.
#include "S540NvidiaDarwinInternal.hpp"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalRmHostRetention.h"
#include <atomic>
#include <thread>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include <unistd.h>
#include <sys/wait.h>
using namespace S540DarwinInternal;
namespace {
unsigned checks;
int owner;
std::atomic<unsigned> pausedPhase{0},arrived{0},released{0},preflightPause{0},callbacks{0},holdAction{0};
void expect(bool result,const char *why){++checks;if(!result){std::fprintf(stderr,"retained backend: %s\n",why);std::abort();}}
bool waitFor(std::atomic<unsigned>&value){
    for(unsigned i=0;i<3000;++i){if(value.load(std::memory_order_acquire))return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));}return false;
}
void resetPause(unsigned phase){arrived=0;released=0;pausedPhase=phase;}
Guard&header(void *object){return *static_cast<Guard *>(object);}
void timerAction(void *){callbacks.fetch_add(1,std::memory_order_release);}
void workAction(void *,void *){
    arrived.store(1,std::memory_order_release);
    if(holdAction.load())expect(waitFor(released),"release held real work action");
    callbacks.fetch_add(1,std::memory_order_release);
}
void begin(){expect(s540FirstTxnBeginOwner(&owner)==NV_OK,"real BeginOwner succeeds");}
void initializeHost(){
    S540NvidiaGlobalRmPlatformFacts facts{};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;
    facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;
    facts.osVersion=facts.osDate="retained-backend-control";
    expect(s540GlobalRmHostInitialize(&facts)==NV_OK,"actual Host initializes without heap allocation");
}
S540FirstTxnHostIdentity actual(){S540FirstTxnHostIdentity out{};NvU64 scope=0;
    expect(s540FirstTxnBackendBegin(&out,&scope)==NV_OK&&scope,"actual record identity captured");
    expect(s540FirstTxnBackendEnd(scope)==NV_OK,"actual record scope completed");return out;}
void usable(void *spin){auto token=s540Darwin_os_acquire_spinlock(spin);s540Darwin_os_release_spinlock(spin,token);}
void preowner(){
    void *spin=nullptr,*mutex=nullptr;
    expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK,"preowner spin allocated");
    expect(s540Darwin_os_alloc_mutex(&mutex)==NV_OK,"preowner mutex allocated");
    auto *sem=s540Darwin_os_alloc_semaphore(1);auto *rw=s540Darwin_os_alloc_rwlock();
    os_wait_queue *wait=nullptr;expect(s540Darwin_os_alloc_wait_queue(&wait)==NV_OK,"preowner waitqueue");
    S540DarwinTimer *timer=nullptr;os_work_queue *queue=nullptr;
    expect(s540DarwinTimerCreate(timerAction,nullptr,&timer)==NV_OK,"preowner timer");
    expect(s540DarwinWorkQueueCreate(workAction,nullptr,&queue)==NV_OK,"preowner queue");
    auto *pid=s540Darwin_os_get_pid_info();NvU32 number=0;
    expect(pid&&s540Darwin_os_find_ns_pid(pid,&number)==NV_OK&&number==NvU32(getpid()),"real PID reference");
    expect(s540DarwinTimerArm(timer,0)==NV_OK&&waitFor(callbacks),"preowner real timer callback");
    expect(s540Darwin_os_queue_work_item(queue,nullptr)==NV_OK&&s540Darwin_os_flush_work_queue(queue,NV_FALSE)==NV_OK,"preowner real queue");
    s540DarwinTimerDestroy(timer);s540DarwinWorkQueueDestroy(queue);
    s540Darwin_os_free_spinlock(spin);s540Darwin_os_free_mutex(mutex);s540Darwin_os_free_semaphore(sem);
    s540Darwin_os_free_rwlock(rw);s540Darwin_os_free_wait_queue(wait);s540Darwin_os_put_pid_info(pid);
    expect(s540DarwinLiveObjects()==0&&backendSnapshot().retainedObjects==0,"preowner physical cleanup completes");
    for(unsigned point: {1U,2U,3U,4U}){
        S540NvidiaDarwinServicesNative::failNext(static_cast<S540NvidiaDarwinServicesNative::Failure>(point));
        timer=reinterpret_cast<S540DarwinTimer *>(1);
        expect(s540DarwinTimerCreate(timerAction,nullptr,&timer)==NV_ERR_NO_MEMORY&&!timer,"preowner failed constructor cleans safely");
        expect(s540DarwinLiveObjects()==0,"preowner partial storage/mutex/condition/worker fully released");
    }
    expect(s540GlobalRmHostShutdown()==NV_TRUE,"actual preowner Host shutdown still releases cold guard");
}
void retained(){
    void *legacy=nullptr;expect(s540Darwin_os_alloc_spinlock(&legacy)==NV_OK,"legacy allocation");begin();
    auto identity=actual();expect(identity.owner==&owner&&identity.generation,"actual strong owner/generation before Bind");
    void *spin=nullptr,*mutex=nullptr;os_wait_queue *wait=nullptr;
    expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK&&s540Darwin_os_alloc_mutex(&mutex)==NV_OK,"owned locks");
    auto *sem=s540Darwin_os_alloc_semaphore(1);auto *rw=s540Darwin_os_alloc_rwlock();
    expect(sem&&rw&&s540Darwin_os_alloc_wait_queue(&wait)==NV_OK,"owned sync backends");
    auto *pid=s540Darwin_os_get_pid_info();expect(pid,"owned PID ref");
    S540DarwinTimer *timer=nullptr;os_work_queue *queue=nullptr;
    expect(s540DarwinTimerCreate(timerAction,nullptr,&timer)==NV_OK&&s540DarwinWorkQueueCreate(workAction,nullptr,&queue)==NV_OK,"owned timer+queue");
    expect(header(spin).backendIdentity.owner==identity.owner&&header(spin).backendIdentity.generation==identity.generation,"backend birth matches record");
    expect(s540Darwin_os_acquire_mutex(mutex)==NV_OK&&s540Darwin_os_acquire_semaphore(sem)==NV_OK&&s540Darwin_os_acquire_rwlock_write(rw)==NV_OK,"hold tokens during finalfree attempt");
    auto token=s540Darwin_os_acquire_spinlock(spin);
    s540Darwin_os_free_spinlock(spin);s540Darwin_os_release_spinlock(spin,token);
    s540Darwin_os_free_mutex(mutex);s540Darwin_os_free_semaphore(sem);s540Darwin_os_free_rwlock(rw);s540Darwin_os_free_wait_queue(wait);
    s540Darwin_os_release_mutex(mutex);expect(s540Darwin_os_release_semaphore(sem)==NV_OK,"retained semaphore token preserved");
    s540Darwin_os_release_rwlock_write(rw);usable(spin);s540Darwin_os_wake_up(wait);s540Darwin_os_wait_uninterruptible(wait);
    s540Darwin_os_put_pid_info(pid);NvU32 number=0;expect(s540Darwin_os_find_ns_pid(pid,&number)==NV_OK,"retained PID reference readable");
    expect(s540DarwinTimerArm(timer,2000000)==NV_OK,"arm actual timer");s540DarwinTimerDestroy(timer);
    expect(waitFor(callbacks)&&s540DarwinTimerArm(timer,0)==NV_OK,"destroy does not cancel or shut down retained timer");
    holdAction=1;arrived=0;released=0;
    expect(s540Darwin_os_queue_work_item(queue,nullptr)==NV_OK&&waitFor(arrived),"actual work callback is in flight");
    s540DarwinWorkQueueDestroy(queue);
    expect(s540Darwin_os_queue_work_item(queue,nullptr)==NV_OK,"destroy returns without stopping queue or waiting callback");
    holdAction=0;released=1;
    expect(s540Darwin_os_flush_work_queue(queue,NV_FALSE)==NV_OK,"preserved work and callback finish");
    s540Darwin_os_free_spinlock(legacy);
    expect(!header(legacy).backendIdentity.owner&&!header(legacy).backendIdentity.generation,"legacy resource is retained without retagging");
    auto snap=backendSnapshot();
    expect(snap.retainedObjects==9&&snap.associatedObjects==8&&snap.legacyObjects==1&&s540DarwinLiveObjects()==9,"all direct storage and guards retained exactly once");
    s540DarwinTimerDestroy(timer);s540DarwinWorkQueueDestroy(queue);
    expect(backendSnapshot().retainedObjects==9,"repeat destruction does not duplicate retained registry");
}
void constructionFailures(){
    begin();
    for(unsigned point:{1U,2U,3U,4U})for(bool work:{false,true}){
        auto before=s540DarwinLiveObjects();
        S540NvidiaDarwinServicesNative::failNext(static_cast<S540NvidiaDarwinServicesNative::Failure>(point));
        S540DarwinTimer *timer=nullptr;os_work_queue *queue=nullptr;
        auto result=work?s540DarwinWorkQueueCreate(workAction,nullptr,&queue):s540DarwinTimerCreate(timerAction,nullptr,&timer);
        expect(result==NV_ERR_NO_MEMORY&&!timer&&!queue,"actual failed constructor publishes no handle");
        expect(s540DarwinLiveObjects()==before+(point==1?0:1),"failed epoch construction retains allocated storage and initialized lock parts");
    }
    auto s=backendSnapshot();expect(s.retainedObjects==6&&s.associatedObjects==6&&s.legacyObjects==0,"partial guard and worker failures are tracked, not freed");
}
void beforeIrqArm(){
    begin();void *isrGuard=nullptr;os_work_queue *device=nullptr,*global=nullptr;
    expect(s540Darwin_os_alloc_spinlock(&isrGuard)==NV_OK&&s540DarwinWorkQueueCreate(workAction,nullptr,&device)==NV_OK,"real startup backends before any IRQ arm/binding");
    S540NvidiaDarwinServicesNative::failNext(S540NvidiaDarwinServicesNative::Failure::Worker);
    expect(s540DarwinWorkQueueCreate(workAction,nullptr,&global)==NV_ERR_NO_MEMORY&&!global,"second queue constructor fails before IRQ arm");
    s540DarwinWorkQueueDestroy(device);s540Darwin_os_free_spinlock(isrGuard);
    expect(backendSnapshot().retainedObjects==3&&s540DarwinLiveObjects()==3,"actual failure cleanup retains first queue, partial second queue, ISR guard without transactionNv");
    usable(isrGuard);expect(s540Darwin_os_queue_work_item(device,nullptr)==NV_OK&&s540Darwin_os_flush_work_queue(device,NV_FALSE)==NV_OK,"pre-IRQ failure did not kill first queue callback");
}
void sticky(){
    begin();void *spin=nullptr;S540DarwinTimer *timer=nullptr;os_work_queue *queue=nullptr;
    expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK&&s540DarwinTimerCreate(timerAction,nullptr,&timer)==NV_OK&&s540DarwinWorkQueueCreate(workAction,nullptr,&queue)==NV_OK,"resources before sticky");
    s540FirstTxnObserveServiceRefusal(7,9,NV_ERR_OPERATING_SYSTEM);
    s540Darwin_os_free_spinlock(spin);s540DarwinTimerDestroy(timer);s540DarwinWorkQueueDestroy(queue);
    expect(backendSnapshot().retainedObjects==3&&s540DarwinLiveObjects()==3,"sticky does not permit destructor unwind");
    usable(spin);expect(s540DarwinTimerArm(timer,0)==NV_OK&&waitFor(callbacks),"callback backing stays usable after sticky");
    void *out=reinterpret_cast<void *>(1);expect(s540Darwin_os_alloc_spinlock(&out)!=NV_OK&&!out&&s540DarwinLiveObjects()==3,"sticky construction refuses before allocation");
}
void foreignAndGeneration(){
    begin();void *spin=nullptr;expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK,"generation resource");
    auto birth=header(spin).backendIdentity;NvU64 permit=91;auto wrong=birth;++wrong.generation;
    expect(s540FirstTxnBackendBeginRelease(&wrong,&permit)==NV_ERR_INVALID_STATE&&!permit,"wrong epoch can never obtain physical permit");
    std::thread other([&]{s540Darwin_os_free_spinlock(spin);void *out=nullptr;expect(s540Darwin_os_alloc_spinlock(&out)!=NV_OK&&!out,"foreign constructor not authorized by owner flag");});other.join();
    usable(spin);expect(header(spin).backendIdentity.owner==birth.owner&&header(spin).backendIdentity.generation==birth.generation&&backendSnapshot().retainedObjects==1,"foreign release preserves actual birth tuple");
}
void allocationRace(){
    resetPause(1);void *spin=nullptr;
    std::thread creator([&]{expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK,"actual allocation completes");});
    expect(waitFor(arrived),"paused inside actual allocator");
    expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_BUSY_RETRY,"owner refuses preowner allocation in progress");
    pausedPhase=0;released=1;creator.join();begin();s540Darwin_os_free_spinlock(spin);
    expect(s540DarwinLiveObjects()==1&&backendSnapshot().legacyObjects==1,"successful retry never retags preowner allocation");
}
void releaseRace(){
    void *spin=nullptr;expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK,"resource for actual physical release");
    resetPause(2);std::thread destroyer([&]{s540Darwin_os_free_spinlock(spin);});
    expect(waitFor(arrived),"paused in actual deallocator after guard disposal");
    expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_BUSY_RETRY,"owner cannot cross a preowner physical release");
    pausedPhase=0;released=1;destroyer.join();expect(s540DarwinLiveObjects()==0,"actual physical release finishes before owner");begin();
}
void reservationRace(){
    void *spin=nullptr;expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK,"resource before owner reservation");
    preflightPause=1;arrived=0;released=0;
    std::thread ownerThread([&]{expect(s540FirstTxnBeginOwner(&owner)==NV_OK,"reserved owner eventually begins");});
    expect(waitFor(arrived),"real BeginOwner paused in preflight after reservation");
    s540Darwin_os_free_spinlock(spin);
    expect(s540DarwinLiveObjects()==1&&backendSnapshot().legacyObjects==1,"reserving window conservatively retains, never frees");
    void *out=nullptr;expect(s540Darwin_os_alloc_spinlock(&out)!=NV_OK&&!out,"reservation refuses new allocation");
    released=1;ownerThread.join();usable(spin);
}
void scopeIntegrity(){
    S540FirstTxnHostIdentity out{};NvU64 permit=0;
    expect(s540FirstTxnBackendBegin(&out,&permit)==NV_OK&&permit&&!out.owner&&!out.generation,"real preowner permit");
    std::thread other([&]{expect(s540FirstTxnBackendEnd(permit)==NV_ERR_INVALID_STATE,"foreign thread cannot consume scope");});other.join();
    expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_BUSY_RETRY,"forged completion cannot open owner admission");
    expect(s540FirstTxnBackendEnd(permit)==NV_OK&&s540FirstTxnBackendEnd(permit)!=NV_OK,"scope consumed exactly once");begin();
}
void stickyReservationRace(){
    BackendConstruction preowner;
    expect(preowner.allowed(),"actual preowner construction scope remains outstanding");
    resetPause(3);NV_STATUS result=NV_OK;
    std::thread ownerThread([&]{result=s540FirstTxnBeginOwner(&owner);});
    expect(waitFor(arrived),"actual reservation paused before backend count read");
    s540FirstTxnObserveServiceRefusal(5,2,NV_ERR_OPERATING_SYSTEM);
    pausedPhase=0;released=1;ownerThread.join();
    expect(result==NV_ERR_OPERATING_SYSTEM,"sticky reservation refuses rather than publishing over outstanding physical scope");
    S540FirstTxnHostIdentity identity{};
    expect(s540FirstTxnHostCaptureAllocation(&identity)==NV_ERR_NOT_READY&&!identity.owner&&!identity.generation,"no actual owner/generation was published across busy sticky reservation");
    expect(s540GlobalRmHostShutdown()==NV_FALSE,"retained reservation also refuses Host shutdown");
}
void hostReleaseRace(){
    resetPause(4);NvBool result=NV_FALSE;
    std::thread shutdown([&]{result=s540GlobalRmHostShutdown();});
    expect(waitFor(arrived),"actual Host shutdown paused before deleting its guard");
    expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_BUSY_RETRY,"owner refuses in-flight zero-allocation Host guard release");
    pausedPhase=0;released=1;shutdown.join();
    expect(result==NV_TRUE,"preowner physical Host release completes");
    initializeHost();begin();
}
void failedReservationRetention(){
    void *spin=nullptr;expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK,"resource before failed reservation");
    // Genuine unavailable counter makes actual Host preflight fail while the
    // still-unbound record remains clean. No synthetic owner/phase setter.
    s540GlobalRmRecordUnavailable(4);
    preflightPause=1;arrived=0;released=0;NV_STATUS result=NV_OK;
    std::thread ownerThread([&]{result=s540FirstTxnBeginOwner(&owner);});
    expect(waitFor(arrived),"failed actual preflight paused after reservation");
    s540Darwin_os_free_spinlock(spin);released=1;ownerThread.join();
    expect(result==NV_ERR_STATE_IN_USE,"actual Host refusal rolls reservation back");
    S540FirstTxnHostIdentity identity{};
    expect(s540FirstTxnHostCaptureAllocation(&identity)==NV_ERR_OBJECT_NOT_FOUND,"failed reservation published no epoch");
    s540Darwin_os_free_spinlock(spin);usable(spin);
    auto s=backendSnapshot();expect(s.retainedObjects==1&&s.legacyObjects==1&&s.releaseRefusals==2&&s540DarwinLiveObjects()==1,
        "retained node stays permanent after rollback; repeat free cannot leave dangling registry");
}
void zeroAllocationHostShutdown(){
    void *spin=nullptr;expect(s540Darwin_os_alloc_spinlock(&spin)==NV_OK,"direct storage outside Host allocator");
    S540NvidiaGlobalRmHostSnapshot before{},after{};s540GlobalRmHostSnapshot(&before);
    expect(before.initialized&&!before.liveAllocations&&!before.liveBytes,"real Host has zero allocations");
    begin();
    expect(s540GlobalRmHostShutdown()==NV_FALSE,"zero heap allocations cannot authorize Host shutdown in permanent epoch");
    s540GlobalRmHostSnapshot(&after);expect(after.initialized&&!after.liveAllocations&&!after.liveBytes,"Host facts and guard remain published");
    s540FirstTxnObserveServiceRefusal(1,1,NV_ERR_OPERATING_SYSTEM);
    expect(s540GlobalRmHostShutdown()==NV_FALSE,"sticky owner also prevents zero-allocation shutdown");
    s540GlobalRmHostSnapshot(&after);expect(after.initialized,"sticky Host facts are not cleared");
    s540Darwin_os_free_spinlock(spin);usable(spin);
    expect(s540DarwinLiveObjects()==1&&backendSnapshot().retainedObjects==1,"Host refusal preserves independent direct guard");
}
}
extern "C" void s540RetainedBackendControlPause(unsigned phase){
    if(pausedPhase.load()!=phase)return;arrived=1;
    if(!waitFor(released))std::abort();
}
void preflightObserver(NvU32 stage,const void *,NvU64,const S540FirstTxnHostIdentity *,S540FirstTxnHostFreePermit){
    if(stage==6&&preflightPause.load()){arrived=1;if(!waitFor(released))std::abort();}
}
// These original/RC adapters are not invoked by an unbound raw queue/timer.
// All are explicit fail-closed fixtures so accidental invocation cannot pass.
extern "C" const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[1]={};
extern "C" const NvU32 s540FirstTxnOriginalDescriptorCount=0;
extern "C" NV_STATUS s540FirstTxnInspectOriginalWork(const void *,S540FirstTxnOriginalWork *){std::abort();}
extern "C" NV_STATUS s540FirstTxnInspectOriginalEvent(const void *,S540FirstTxnOriginalEvent *){std::abort();}
extern "C" NV_STATUS s540FirstTxnInspectOriginalOwner(const void *,NvUPtr *){std::abort();}
extern "C" NV_STATUS s540FirstTxnServicesReadTimerContext(const void *,S540FirstTxnServiceContext *){std::abort();}
extern "C" NV_STATUS s540FirstTxnInspectOriginalRc(const void *,NvUPtr *){std::abort();}
// There is no GSP wrapper binding in these direct backend controls. This is
// exactly the no-binding return behavior, not a settlement of any timer lease.
extern "C" NV_STATUS s540FirstTxnTimerActionReturned(S540DarwinTimer *){return NV_OK;}
int main(){
    using Case=void(*)();const Case cases[]={preowner,retained,constructionFailures,beforeIrqArm,sticky,
        foreignAndGeneration,allocationRace,releaseRace,reservationRace,scopeIntegrity,zeroAllocationHostShutdown,
        stickyReservationRace,hostReleaseRace,failedReservationRetention};
    unsigned total=0;
    for(auto test:cases){int pipefd[2];if(pipe(pipefd))return 1;auto pid=fork();if(pid<0)return 1;
        if(!pid){close(pipefd[0]);checks=0;initializeHost();S540HostRetentionNative::observePhysicalFree(preflightObserver);
            test();if(write(pipefd[1],&checks,sizeof(checks))!=sizeof(checks))_exit(1);_exit(0);}
        close(pipefd[1]);unsigned count=0;auto bytes=read(pipefd[0],&count,sizeof(count));close(pipefd[0]);
        int status=0;if(waitpid(pid,&status,0)!=pid||!WIFEXITED(status)||WEXITSTATUS(status)||bytes!=sizeof(count))return 1;total+=count;}
    std::printf("{\"status\":\"passed\",\"cases\":14,\"checks\":%u,\"failures\":0}\n",total);return 0;
}
