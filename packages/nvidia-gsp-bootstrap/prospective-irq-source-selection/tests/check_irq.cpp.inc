// SPDX-License-Identifier: MIT
// Actual generated production bodies below; OS/record endpoints are CPU fixtures.
#include "@TRANSPORT_HEADER@"
#include "@IRQ_HEADER@"
#include "@RECORD_HEADER@"
#include "@COMMIT_HEADER@"
#include "@CLOSURE_HEADER@"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <utility>
using namespace S540NvidiaDeviceTransport;
constexpr int kIOReturnSuccess=0,kIOReturnError=-1,kIOInterruptTypePCIMessaged=0x10000;
using IOReturn=int;
class OSObject {public:virtual ~OSObject()=default;};
class OSArray:public OSObject {public:NvU32 count=0;NvU32 getCount(){return count;}};
#define OSDynamicCast(type,value) dynamic_cast<type *>(value)
class IOService:public OSObject {};
class IOMemoryMap:public OSObject {};
class IOMapper:public OSObject {};
class IOPlatformExpert:public OSObject {};
class IODMACommand:public OSObject {};
using IOInterruptState=bool;
struct IOSimpleLock {};
class S540PublicCallout {
public:bool initialized=false,pending=false;
    bool initialize(void (*)(void *),void *){initialized=true;return true;}
    bool schedule(NvU64){pending=true;return true;}
    bool drain(){pending=false;return true;}
    bool retire(){initialized=false;return true;}
};
namespace S540NvidiaPci {
struct Inventory {bool valid=false;NvU32 msiOffset=0,msixOffset=0,msiVectors=0;};
static Inventory current;
static bool canBind=true;
class Context {public:bool bind(void *){return canBind;}Inventory inventory(){return current;}void unbind(){}};
}
class IOPCIDevice:public IOService {
public:
    OSArray controllers,specifiers;OSObject wrongObject;
    bool controllersPresent=true,specifiersPresent=true,wrongArrays=false;
    bool arbitration=true,inactive=false,failRegister=false,failEnable=false,failDisable=false,failUnregister=false;
    int unknown=-1;unsigned propertyCalls=0,locks=0,unlocks=0;
    std::vector<int> types{0,kIOInterruptTypePCIMessaged};
    std::vector<int> queried;
    std::vector<std::pair<char,int>> actions;
    IOPCIDevice(){controllers.count=specifiers.count=2;}
    bool lockForArbitration(bool){++locks;return arbitration;}
    void unlockForArbitration(){++unlocks;}
    OSObject *getProperty(const char *key){++propertyCalls;
        if(wrongArrays)return &wrongObject;
        if(!std::strcmp(key,"IOInterruptControllers"))return controllersPresent?&controllers:nullptr;
        if(!std::strcmp(key,"IOInterruptSpecifiers"))return specifiersPresent?&specifiers:nullptr;
        return nullptr;
    }
    IOReturn getInterruptType(int source,int *out){queried.push_back(source);
        if(source==unknown||source<0||static_cast<unsigned>(source)>=types.size())return kIOReturnError;
        *out=types[source];return kIOReturnSuccess;
    }
    IOReturn registerInterrupt(int source,IOService *,void (*)(OSObject *,void *,IOService *,int),void *){
        actions.emplace_back('r',source);return failRegister?kIOReturnError:kIOReturnSuccess;
    }
    IOReturn enableInterrupt(int source){actions.emplace_back('e',source);return failEnable?kIOReturnError:kIOReturnSuccess;}
    IOReturn disableInterrupt(int source){actions.emplace_back('d',source);return failDisable?kIOReturnError:kIOReturnSuccess;}
    IOReturn unregisterInterrupt(int source){actions.emplace_back('u',source);return failUnregister?kIOReturnError:kIOReturnSuccess;}
};
static bool ordinaryContext=true,liveProvider=true,inInterrupt=false;
static bool ordinary(void *){return ordinaryContext;}
static bool live(void *){return liveProvider;}
static IOSimpleLock *IOSimpleLockAlloc(){return new IOSimpleLock;}
static void IOSimpleLockFree(IOSimpleLock *value){delete value;}
static IOInterruptState IOSimpleLockLockDisableInterrupt(IOSimpleLock *){return false;}
static void IOSimpleLockUnlockEnableInterrupt(IOSimpleLock *,IOInterruptState){}
static void IOSleep(unsigned){}
static bool ml_at_interrupt_context(){return inInterrupt;}
static void clock_get_uptime(uint64_t *value){*value=1;}
static unsigned tops=0,locked=0,unlocked=0,refusals=0,enters=0,masks=0,checks=0,cases=0;
static int originalState,ownerState;
extern "C" NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out){*out=7;return NV_OK;}
extern "C" NV_STATUS s540FirstTxnBackendBegin(S540FirstTxnHostIdentity *out,NvU64 *permit){*out={};*permit=1;return NV_OK;}
extern "C" NV_STATUS s540FirstTxnBackendEnd(NvU64){return NV_OK;}
extern "C" NV_STATUS s540FirstTxnBackendBeginRelease(const S540FirstTxnHostIdentity *,NvU64 *permit){*permit=1;return NV_OK;}
extern "C" NV_STATUS s540FirstTxnIrqBind(const void *,const void *,NvU64 *generation){*generation=1;return NV_OK;}
extern "C" NV_STATUS s540FirstTxnIrqCheckArm(const void *){return NV_OK;}
extern "C" NV_STATUS s540FirstTxnIrqEnter(const void *,NvU32){++enters;return NV_OK;}
extern "C" NV_STATUS s540FirstTxnIrqLeave(const void *,NvU32){return NV_OK;}
extern "C" NvU32 s540FirstTxnIrqOrigin(const void *){return 2;}
extern "C" void s540FirstTxnObserveServiceRefusal(NvU32,NvU32,NV_STATUS){++refusals;}
extern "C" NV_STATUS s540GspCancellationCommitEnterState(const void *,S540GspCancellationCommitLease *out){*out=1;return NV_OK;}
extern "C" NV_STATUS s540GspCancellationCommitLeaveState(const void *,S540GspCancellationCommitLease){return NV_OK;}
@PLATFORM@
@LIFETIME@
@BODIES@
static bool top(void *,bool &l,bool &u){++tops;l=true;u=true;return true;}
static void lockedAction(void *){++locked;}
static void unlockedAction(void *){++unlocked;}
static NV_STATUS mask(void *){++masks;return NV_OK;}
static bool ready(void *){return true;}
static NV_STATUS select(void *){return NV_OK;}
static NV_STATUS validate(void *){return NV_OK;}
[[maybe_unused]] static InterruptContract contract{&ownerState,top,lockedAction,unlockedAction,mask,ready,&originalState,select,validate};
static void requireAt(bool value,unsigned line){++checks;if(!value){std::fprintf(stderr,"failed actual IRQ body check %u\n",line);std::abort();}}
#define require(value) requireAt((value),__LINE__)
static void defaults(){S540NvidiaPci::current={true,0x68,0,1};S540NvidiaPci::canBind=true;ordinaryContext=true;liveProvider=true;}
static Platform platform(IOPCIDevice &provider,IOService &owner){Platform p{};p.provider=&provider;p.owner=&owner;return p;}
static void expectedRefusal(IOPCIDevice &provider,IOService &owner,NV_STATUS expected=NV_ERR_NOT_SUPPORTED){
    ++cases;auto p=platform(provider,owner);S540GspIrqModeFacts facts{};facts.generation=99;
    require(readOriginalMode(&p,facts)==expected&&facts.generation==99);
    require(p.statistics.sourceProbeAttempted&&p.statistics.sourceProbeReturned&&p.statistics.sourceProbeStatus==expected);
    require(!p.irqSourceValid&&provider.actions.empty()&&!p.isrLock);
    require(provider.unlocks==(provider.arbitration?provider.locks:0));
}
int main(){
    IOService owner;
    defaults();
#if BASELINE
    IOPCIDevice d;auto p=platform(d,owner);S540GspIrqModeFacts facts{};
    require(readOriginalMode(&p,facts)==NV_ERR_NOT_SUPPORTED&&!p.irqSourceValid);
    require((d.queried==std::vector<int>{0})&&d.actions.empty());
    std::printf("{\"status\":\"passed-baseline-refusal\",\"checks\":%u,\"cases\":1,\"source0_legacy_source1_MSI\":true}\n",checks);
#else
    {S540GspIrqModeFacts facts{};require(readOriginalMode(nullptr,facts)==NV_ERR_INVALID_STATE);}
    {IOPCIDevice d;d.controllersPresent=false;expectedRefusal(d,owner);}
    {IOPCIDevice d;d.specifiersPresent=false;expectedRefusal(d,owner);}
    {IOPCIDevice d;d.wrongArrays=true;expectedRefusal(d,owner);}
    {IOPCIDevice d;d.controllers.count=d.specifiers.count=0;expectedRefusal(d,owner);require(d.queried.empty());}
    {IOPCIDevice d;d.controllers.count=d.specifiers.count=33;d.types.assign(33,0);d.types[1]=kIOInterruptTypePCIMessaged;expectedRefusal(d,owner);require(d.queried.empty());}
    {IOPCIDevice d;d.specifiers.count=1;expectedRefusal(d,owner);require(d.queried.empty());}
    {IOPCIDevice d;d.unknown=0;expectedRefusal(d,owner);require(d.queried==std::vector<int>{0});}
    {IOPCIDevice d;d.unknown=1;expectedRefusal(d,owner);require((d.queried==std::vector<int>{0,1}));}
    {IOPCIDevice d;d.types={kIOInterruptTypePCIMessaged,0};d.unknown=1;expectedRefusal(d,owner);}
    {IOPCIDevice d;d.types={0,0};expectedRefusal(d,owner);}
    {IOPCIDevice d;d.types={kIOInterruptTypePCIMessaged,kIOInterruptTypePCIMessaged};expectedRefusal(d,owner);}
    {IOPCIDevice d;S540NvidiaPci::current.valid=false;expectedRefusal(d,owner);defaults();}
    {IOPCIDevice d;S540NvidiaPci::canBind=false;expectedRefusal(d,owner);defaults();}
    {IOPCIDevice d;S540NvidiaPci::current.msiOffset=0;expectedRefusal(d,owner);defaults();}
    {IOPCIDevice d;S540NvidiaPci::current.msixOffset=0x90;expectedRefusal(d,owner);defaults();}
    for(NvU32 vectors: {0U,2U,32U}){IOPCIDevice d;S540NvidiaPci::current.msiVectors=vectors;expectedRefusal(d,owner);defaults();}
    {IOPCIDevice d;d.arbitration=false;expectedRefusal(d,owner,NV_ERR_BUSY_RETRY);require(!d.propertyCalls);}
    {IOPCIDevice d;ordinaryContext=false;expectedRefusal(d,owner,NV_ERR_INVALID_STATE);defaults();require(!d.locks);}
    {IOPCIDevice d;liveProvider=false;expectedRefusal(d,owner,NV_ERR_INVALID_STATE);defaults();require(!d.locks);}
    // Actual kernel regression: source0 legacy, source1 MSI. Every OS lifecycle
    // operation and callback uses the retained1, without changing PCI config.
    {++cases;IOPCIDevice d;auto p=platform(d,owner);
        require(installInterrupt(&p,contract)==NV_OK&&p.irqSourceValid&&p.irqSource==1);
        require((d.actions==std::vector<std::pair<char,int>>{{'r',1}}));
        require(armInterrupt(&p)==NV_OK);
        const unsigned before=tops,priorRefusals=refusals;
        inInterrupt=true;interrupt(nullptr,&p,&d,0);inInterrupt=false;
        require(tops==before&&refusals==priorRefusals+1&&!p.callbacks&&!p.pending);
        IOService foreign;
        inInterrupt=true;interrupt(nullptr,&p,&foreign,1);interrupt(nullptr,&p,&d,-1);inInterrupt=false;
        require(tops==before&&refusals==priorRefusals+3&&!p.callbacks);
        inInterrupt=true;interrupt(nullptr,&p,&d,1);inInterrupt=false;
        require(tops==before+1&&p.pending);
        bottomHalf(&p);require(!p.pending&&locked&&unlocked);
        auto stats=interruptStatistics(&p);
        require(stats.sourceProbeAttempted&&stats.sourceProbeReturned&&stats.sourceProbeStatus==NV_OK);
        require(stats.sourceCount==2&&stats.sourcesObserved==2&&stats.messagedSources==1);
        require(stats.selectedSourceValid&&stats.selectedSource==1&&stats.selectedTypeValid);
        require(stats.inventoryValid&&stats.msiCapable&&!stats.msixCapable&&stats.msiVectors==1);
        require(stopInterrupt(&p)==NV_OK&&p.irqSourceValid&&p.irqSource==1);
        require((d.actions==std::vector<std::pair<char,int>>{{'r',1},{'e',1},{'d',1},{'u',1}}));
    }
    // Valid source0 remains supported; selection follows actual array order.
    for(unsigned selected: {0U,2U,31U}){++cases;IOPCIDevice d;
        d.controllers.count=d.specifiers.count=selected+1;d.types.assign(selected+1,0);d.types[selected]=kIOInterruptTypePCIMessaged;
        auto p=platform(d,owner);require(installInterrupt(&p,contract)==NV_OK&&p.irqSource==selected);
        require(armInterrupt(&p)==NV_OK&&stopInterrupt(&p)==NV_OK);
        for(const auto &action:d.actions)require(static_cast<unsigned>(action.second)==selected);
    }
    // Complete source revalidation refuses count/order/type/unknown changes
    // without enabling a replacement source. The original chosen index stays.
    for(unsigned change=0;change!=5;++change){++cases;IOPCIDevice d;auto p=platform(d,owner);
        require(installInterrupt(&p,contract)==NV_OK&&p.irqSource==1);
        if(change==0)d.types={kIOInterruptTypePCIMessaged,0};
        if(change==1)d.controllers.count=d.specifiers.count=1;
        if(change==2)d.types[1]|=4;
        if(change==3)d.unknown=0;
        if(change==4)d.types[0]=kIOInterruptTypePCIMessaged;
        require(armInterrupt(&p)!=NV_OK&&p.irqSource==1&&p.irqSourceValid);
        require(d.actions.size()==1&&d.actions[0].first=='r');
        require(stopInterrupt(&p)==NV_OK&&p.irqSource==1);
        require(d.actions.back()==std::make_pair('u',1));
    }
    {++cases;IOPCIDevice d;d.failRegister=true;auto p=platform(d,owner);
        require(installInterrupt(&p,contract)==NV_ERR_OPERATING_SYSTEM&&p.irqSource==1&&p.irqSourceValid);
        require(!p.irqRegistered&&!p.controllerAttached&&p.permanentRetention);
        require(p.bottomHalf.retire());IOSimpleLockFree(p.isrLock);p.isrLock=nullptr;
        retainedIrqBackends=nullptr;
    }
    {++cases;IOPCIDevice d;d.failEnable=true;auto p=platform(d,owner);
        require(installInterrupt(&p,contract)==NV_OK&&armInterrupt(&p)==NV_ERR_OPERATING_SYSTEM);
        require(p.irqSource==1&&p.irqSourceValid&&stopInterrupt(&p)==NV_OK);
        require((d.actions==std::vector<std::pair<char,int>>{{'r',1},{'e',1},{'d',1},{'u',1}}));
    }
    for(bool disableFailure: {true,false}){++cases;IOPCIDevice d;auto p=platform(d,owner);
        require(installInterrupt(&p,contract)==NV_OK&&armInterrupt(&p)==NV_OK);
        d.failDisable=disableFailure;d.failUnregister=!disableFailure;
        require(stopInterrupt(&p)==NV_ERR_OPERATING_SYSTEM&&p.irqSource==1&&p.isrLock);
        d.failDisable=d.failUnregister=false;
        require(stopInterrupt(&p)==NV_OK&&p.irqSource==1);
        for(const auto &action:d.actions)require(action.second==1);
    }
    std::printf("{\"status\":\"passed\",\"checks\":%u,\"cases\":%u,\"actual_production_bodies\":true,\"CPU_fixture_OS_and_record\":true}\n",checks,cases);
#endif
}
