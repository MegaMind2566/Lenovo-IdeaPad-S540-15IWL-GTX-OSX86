// SPDX-License-Identifier: MIT
#include "MockIOKit.hpp"
#include "S540NvidiaDeviceTransport.hpp"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaIrqClosure.h"
#include "S540NvidiaPublicCallout.hpp"
#include "S540NvidiaGspIrqIdentity.h"
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
constexpr int kIOInterruptTypePCIMessaged=1;
namespace S540NvidiaPci {
struct Inventory { bool valid=true; unsigned msiOffset=0x68,msixOffset=0,msiVectors=1; };
static Inventory current;
class Context { public: bool bind(void *) {return true;} Inventory inventory(){return current;} void unbind(){} };
}
class IOPCIDevice:public IOService {
public:
    bool attached=false,enabled=false,failEnable=false,failDisable=false,failUnregister=false;
    bool typeKnown=true,arbitration=true;int interruptType=1;unsigned registrations=0,types=0;
    bool lockForArbitration(bool){return arbitration;} void unlockForArbitration(){}
    IOReturn getInterruptType(int,int *out){++types;*out=interruptType;return typeKnown?kIOReturnSuccess:kIOReturnError;}
    IOReturn registerInterrupt(int,IOService *,void (*)(OSObject *,void *,IOService *,int),void *){
        ++registrations;attached=true;return kIOReturnSuccess;
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
#include "actual-mode-query.inc"

static unsigned checks;
static std::atomic<unsigned> tops{0},locked{0},unlocked{0},masks{0};
static std::atomic<bool> pauseReturn{false},returnPaused{false},releaseReturn{false},failMask{false};
static std::thread::id lastBottomThread,stopThread;
static void requireAt(bool value,unsigned line){++checks;if(!value){std::fprintf(stderr,"failed backend check line %u\n",line);std::abort();}}
#define require(value) requireAt((value),__LINE__)
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
static bool bindingValid=true;static unsigned selections=0;static IOPCIDevice *modeProvider;
static NV_STATUS validate(void *){return bindingValid?NV_OK:NV_ERR_INVALID_STATE;}
static NV_STATUS selectMode(void *){
    S540GspIrqModeFacts facts{};
    if(s540GspIrqReadBackendMode(&exactNv,&facts)!=NV_OK||facts.nv!=&exactNv||facts.generation!=7||
       !facts.known||!facts.messageSignaled||!facts.msiCapable||facts.msixCapable||facts.msiVectors!=1||
       modeProvider->attached)return NV_ERR_INVALID_STATE;
    ++selections;return NV_OK;
}
static void deliver(Platform &p){mock::interrupt=true;interrupt(nullptr,&p,nullptr,0);mock::interrupt=false;}
int main(){
    IOPCIDevice provider;IOService owner;Platform p{};p.provider=&provider;p.owner=&owner;
    modeProvider=&provider;
    InterruptContract contract{&actualOwner,top,lockedAction,unlockedAction,mask,ready,&exactNv,selectMode,validate};
    // Real mode selection body reads current provider API + bounded capability inventory.
    { Platform rejected{};rejected.provider=&provider;rejected.owner=&owner;
      S540GspIrqModeFacts facts{};facts.generation=99;
      provider.typeKnown=false;require(readOriginalMode(&rejected,facts)==NV_ERR_NOT_SUPPORTED&&facts.generation==99);
      require(installInterrupt(&rejected,contract)==NV_ERR_NOT_SUPPORTED&&provider.registrations==0);provider.typeKnown=true;
      provider.interruptType=0;require(installInterrupt(&rejected,contract)==NV_ERR_NOT_SUPPORTED&&provider.registrations==0);provider.interruptType=1;
      S540NvidiaPci::current.valid=false;require(installInterrupt(&rejected,contract)==NV_ERR_NOT_SUPPORTED);S540NvidiaPci::current.valid=true;
      S540NvidiaPci::current.msiOffset=0;require(installInterrupt(&rejected,contract)==NV_ERR_NOT_SUPPORTED);S540NvidiaPci::current.msiOffset=0x68;
      S540NvidiaPci::current.msixOffset=0x90;require(installInterrupt(&rejected,contract)==NV_ERR_NOT_SUPPORTED);S540NvidiaPci::current.msixOffset=0;
      S540NvidiaPci::current.msiVectors=2;require(installInterrupt(&rejected,contract)==NV_ERR_NOT_SUPPORTED);S540NvidiaPci::current.msiVectors=1;
      provider.arbitration=false;require(installInterrupt(&rejected,contract)==NV_ERR_BUSY_RETRY);provider.arbitration=true;
      require(provider.registrations==0&&selections==0&&!rejected.isrLock);
    }
    require(installInterrupt(&p,contract)==NV_OK);
    require(selections==1&&provider.registrations==1&&provider.types>=7);
    S540GspIrqModeFacts original{};original.generation=55;
    require(s540GspIrqReadBackendMode(&actualOwner,&original)==NV_ERR_INVALID_STATE&&original.generation==55);
    require(s540GspIrqReadBackendMode(&exactNv,&original)==NV_OK&&original.generation==7);
    epoch=true;
    require(armInterrupt(&p)==NV_OK&&provider.enabled);
    auto *source=p.bottomHalf.source;
    bindingValid=false;deliver(p);require(tops==0&&refusals==1);bindingValid=true;
    {std::lock_guard<std::recursive_mutex> gate(p.bottomHalf.loop->gate);
        for(unsigned i=0;i<6;++i)deliver(p);
        require(tops==6&&p.pending==(1U|2U|(2U<<2)));
    }
    until([&]{return locked==1&&unlocked==1;});
    require(enters[0]==7&&leaves[0]==7&&enters[1]==1&&leaves[1]==1);
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
    // Identity refusal after a real top dispatch retains the entire packed
    // coalesced word and never counts an original bottom-half return.
    Platform r{};r.provider=&provider;r.owner=&owner;
    require(installInterrupt(&r,contract)==NV_OK&&armInterrupt(&r)==NV_OK);
    const unsigned beforeLocked=locked,beforeUnlocked=unlocked;
    {std::lock_guard<std::recursive_mutex> gate(r.bottomHalf.loop->gate);
        deliver(r);bindingValid=false;
    }
    until([&]{return refusals==2&&r.bottomStage==0;});
    require(r.pending==(1U|2U|(2U<<2))&&locked==beforeLocked&&unlocked==beforeUnlocked);
    bindingValid=true;require(scheduleBottomHalf(&r));
    until([&]{return locked==beforeLocked+1&&unlocked==beforeUnlocked+1;});
    require(stopInterrupt(&r)==NV_OK&&enters[1]==leaves[1]);
    require(refusals==2&&mock::gateUnderGuard==0);
    require(mock::live==2); // only the two explicit stack fixture OSObjects
    std::printf("{\"status\":\"passed\",\"checks\":%u,\"actual_transformed_irq_bodies\":true,\"strong_record_policy\":\"explicit fixture\"}\n",checks);
}
