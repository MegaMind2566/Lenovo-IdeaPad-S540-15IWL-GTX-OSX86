// SPDX-License-Identifier: MIT
#include "MockIOKit.hpp"
#include "S540NvidiaDeviceTransport.hpp"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaIrqClosure.h"
#include "S540NvidiaPublicCallout.hpp"
#include <cstdio>
#include <cstdlib>

using namespace S540NvidiaDeviceTransport;
using IOInterruptState=bool;
using IOSimpleLock=std::mutex;
class IOService:public OSObject {};
class IOMemoryMap:public OSObject {};
class IOMapper:public OSObject {};
class IOPlatformExpert:public OSObject {};
class IODMACommand:public OSObject {};
class IOPCIDevice:public IOService {
public:
    bool attached=false,enabled=false,failEnable=false,failDisable=false,failUnregister=false;
    IOReturn getInterruptType(int,int *out){*out=1;return kIOReturnSuccess;}
    IOReturn registerInterrupt(int,IOService *,void (*)(OSObject *,void *,IOService *,int),void *){
        attached=true;return kIOReturnSuccess;
    }
    IOReturn enableInterrupt(int){enabled=true;return failEnable?kIOReturnError:kIOReturnSuccess;}
    IOReturn disableInterrupt(int){if(failDisable)return kIOReturnError;enabled=false;return kIOReturnSuccess;}
    IOReturn unregisterInterrupt(int){if(failUnregister)return kIOReturnError;attached=false;return kIOReturnSuccess;}
};
static bool ml_at_interrupt_context(){return mock::interrupt;}
static bool ordinary(void *){return !mock::interrupt;}
static bool live(void *){return true;}
static IOSimpleLock *IOSimpleLockAlloc(){return new std::mutex;}
static void IOSimpleLockFree(IOSimpleLock *lock){delete lock;}
static IOInterruptState IOSimpleLockLockDisableInterrupt(IOSimpleLock *lock){
    bool prior=mock::interrupt;lock->lock();++mock::guardDepth;return prior;
}
static void IOSimpleLockUnlockEnableInterrupt(IOSimpleLock *lock,IOInterruptState prior){
    --mock::guardDepth;lock->unlock();mock::interrupt=prior;
}
static void IOSleep(unsigned ms){std::this_thread::sleep_for(std::chrono::milliseconds(ms));}
extern "C" NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out){
    *out=std::hash<std::thread::id>{}(std::this_thread::get_id());return NV_OK;
}
static bool epoch=false;
static int exactNv,actualOwner;
static std::atomic<unsigned> enters[2],leaves[2],refusals{0};
static std::atomic<bool> rejectBottom{false};
extern "C" NV_STATUS s540FirstTxnBackendBegin(S540FirstTxnHostIdentity *identity,NvU64 *permit){
    identity->owner=epoch?&actualOwner:nullptr;identity->generation=epoch?7:0;*permit=1;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnBackendEnd(NvU64){return NV_OK;}
extern "C" NV_STATUS s540FirstTxnBackendBeginRelease(const S540FirstTxnHostIdentity *,NvU64 *permit){
    *permit=epoch?0:1;return epoch?NV_ERR_NOT_SUPPORTED:NV_OK;
}
extern "C" NV_STATUS s540FirstTxnIrqBind(const void *nv,const void *,NvU64 *generation){
    if(nv!=&exactNv)return NV_ERR_INVALID_ARGUMENT;
    *generation=7;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnIrqCheckArm(const void *){return NV_OK;}
extern "C" NV_STATUS s540FirstTxnIrqEnter(const void *backend,NvU32 role){
    S540FirstTxnIrqContext observed{};
    if(s540FirstTxnIrqReadContext(backend,role,&observed)!=NV_OK||observed.stage!=role||
       observed.nv!=&exactNv||observed.generation!=7||!observed.thread)return NV_ERR_INVALID_STATE;
    if(role==2&&rejectBottom)return NV_ERR_NOT_READY;
    ++enters[role-1];return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnIrqLeave(const void *,NvU32 role){++leaves[role-1];return NV_OK;}
extern "C" NvU32 s540FirstTxnIrqOrigin(const void *){return 2;}
extern "C" void s540FirstTxnObserveServiceRefusal(NvU32,NvU32,NV_STATUS){++refusals;}
#include "actual-platform.inc"
#include "actual-backend-lifetime.inc"
#include "actual-irq-bodies.inc"
#include "actual-arm.inc"
#include "actual-irq-query.inc"

static unsigned checks;
static std::atomic<unsigned> tops{0},locked{0},unlocked{0},masks{0};
static std::atomic<bool> pauseReturn{false},returnPaused{false},releaseReturn{false},failMask{false};
static std::thread::id lastBottomThread,stopThread;
static void require(bool value){++checks;if(!value)std::abort();}
template<class Predicate>static void until(Predicate predicate){
    for(unsigned i=0;!predicate()&&i<1000;++i)IOSleep(1);
    require(predicate());
}
static bool top(void *,bool &l,bool &u){++tops;l=true;u=true;return true;}
static void lockedAction(void *){
    lastBottomThread=std::this_thread::get_id();++locked;
    if(pauseReturn){returnPaused=true;while(!releaseReturn)std::this_thread::yield();}
}
static void unlockedAction(void *){++unlocked;}
static NV_STATUS mask(void *){
    S540FirstTxnIrqContext observed{};
    if(s540FirstTxnIrqReadContext(registeredIrqBackend,0,&observed)!=NV_OK||
       observed.accepting||observed.controllerAttached||observed.callbacks||
       observed.pending||observed.topStage||observed.bottomStage||!observed.drained)
        std::abort();
    ++masks;return failMask?NV_ERR_NOT_SUPPORTED:NV_OK;
}
static bool ready(void *){return true;}
static void deliver(Platform &p){mock::interrupt=true;interrupt(nullptr,&p,nullptr,0);mock::interrupt=false;}
int main(){
    IOPCIDevice provider;IOService owner;Platform p{};p.provider=&provider;p.owner=&owner;
    InterruptContract contract{&actualOwner,top,lockedAction,unlockedAction,mask,ready,&exactNv};
    require(installInterrupt(&p,contract)==NV_OK);
    epoch=true;
    require(armInterrupt(&p)==NV_OK&&provider.enabled);
    auto *source=p.bottomHalf.source;
    {std::lock_guard<std::recursive_mutex> gate(p.bottomHalf.loop->gate);
        for(unsigned i=0;i<6;++i)deliver(p);
        require(tops==6&&p.pending==(1U|2U|(2U<<2)));
    }
    until([&]{return locked==1&&unlocked==1;});
    require(enters[0]==6&&leaves[0]==6&&enters[1]==1&&leaves[1]==1);
    require(lastBottomThread!=std::this_thread::get_id()&&mock::gateUnderGuard==0);
    // A queued callback remains on the workloop when Stop times out. Stop may
    // not manufacture its return by dispatching original work on this thread.
    source->pauseAfterDequeue(true);deliver(p);
    until([&]{return source->hasDequeued();});
    require(stopInterrupt(&p)==NV_ERR_BUSY_RETRY);
    require(locked==1&&p.pending&&p.bottomHalf.source==source&&p.isrLock);
    require(masks==0&&p.hardwareMaskRequired);
    source->pauseAfterDequeue(false);
    until([&]{return locked==2&&unlocked==2;});
    failMask=true;
    require(stopInterrupt(&p)==NV_ERR_NOT_SUPPORTED);
    require(p.drained&&p.hardwareMaskRequired&&p.bottomHalf.source==source&&p.isrLock);
    failMask=false;
    require(stopInterrupt(&p)==NV_ERR_NOT_SUPPORTED);
    require(p.drained&&p.irqRegistered&&!p.controllerAttached&&!p.accepting&&p.permanentRetention);
    require(masks==2&&!p.hardwareMaskRequired&&p.bottomHalf.source==source&&p.isrLock);
    require(retainedIrqBackends==&p&&p.retainedNext==nullptr);
    require(stopInterrupt(&p)==NV_ERR_NOT_SUPPORTED&&retainedIrqBackends==&p&&p.retainedNext==nullptr);
    // Fixture-only release policy reset reclaims test resources. Production
    // has no reset or release permit for an epoch-associated backend.
    epoch=false;
    require(stopInterrupt(&p)==NV_ERR_NOT_SUPPORTED&&p.bottomHalf.source==source);
    retainedIrqBackends=nullptr;p.permanentRetention=0;
    require(stopInterrupt(&p)==NV_OK&&!p.irqRegistered&&!p.bottomHalf.source&&!p.isrLock);

    // Join the complete action return, including after pending becomes zero.
    Platform q{};q.provider=&provider;q.owner=&owner;
    require(installInterrupt(&q,contract)==NV_OK&&armInterrupt(&q)==NV_OK);
    pauseReturn=true;deliver(q);until([&]{return returnPaused.load();});
    std::atomic<bool> stopped{false};NV_STATUS stoppedStatus=NV_ERR_GENERIC;
    std::thread stopping([&]{stopThread=std::this_thread::get_id();stoppedStatus=stopInterrupt(&q);stopped=true;});
    IOSleep(10);require(!stopped&&q.bottomStage==S540_FIRST_IRQ_BOTTOM);
    releaseReturn=true;stopping.join();require(stoppedStatus==NV_OK&&stopped);
    require(lastBottomThread!=stopThread&&enters[1]==leaves[1]);
    require(refusals==0&&mock::gateUnderGuard==0);
    require(mock::live==2); // only the two explicit stack fixture OSObjects
    std::printf("{\"status\":\"passed\",\"checks\":%u,\"actual_transformed_irq_bodies\":true,\"strong_record_policy\":\"explicit fixture\"}\n",checks);
}
