// Host fixture around extracted production lifecycle bodies. No hardware.
#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <new>
#include <thread>
#include <chrono>
#include "S540ExperimentalTargetState.h"
#include "S540ExperimentalRuntime.h"
#include "S540NvidiaRetainedStop.h"
#include "S540PreparationObservation.h"
static unsigned checks=0,failures=0;
static void expect(bool value,const char *message) {
    ++checks;if(!value){++failures;std::fprintf(stderr,"FAILED:%s\n",message);}
}
typedef NvU32 IOReturn;
static constexpr IOReturn kIOReturnSuccess=0;
static constexpr int THREAD_UNINT=0;
struct IOLock { std::mutex mutex;std::condition_variable wake; };
static IOLock lockStorage,*guard=&lockStorage;
static thread_local bool lockHeld=false;
static S540ExperimentalState state{};
static NvU32 cancellationPublishers=0;
static bool busy=false,cancellationReady=false;
static std::atomic<bool> joinWaiting{false},cancelEntered{false},releaseCancel{false},initializeEntered{false},runFinished{false};
static std::atomic<unsigned> sequence{0},cancelExitSequence{0},stopSequence{0};
static unsigned mode=0,ownerPublications=0;
static bool failAllocation=false;
static void IOLockLock(IOLock *lock){lock->mutex.lock();lockHeld=true;}
static void IOLockUnlock(IOLock *lock){lockHeld=false;lock->mutex.unlock();}
static void IOLockWakeup(IOLock *lock,void *,bool){lock->wake.notify_all();}
static void IOLockSleep(IOLock *lock,void *,int){
    std::unique_lock<std::mutex> held(lock->mutex,std::adopt_lock);
    lockHeld=false;joinWaiting.store(true,std::memory_order_release);
    lock->wake.wait(held,[]{return cancellationPublishers==0;});
    held.release();lockHeld=true;
}
static void *IOMalloc(std::size_t bytes){return failAllocation?nullptr:std::malloc(bytes);}
struct IOPCIDevice {};
struct S540ExperimentalPlacement {void *address;};
void *operator new(std::size_t,S540ExperimentalPlacement placement) noexcept{return placement.address;}
class S540ExperimentalTargetControl;
static S540ExperimentalTargetControl *fixtureControl=nullptr;
namespace S540NvidiaGspBootstrap {
struct Images {const void *gsp,*ucodes;NvU64 gspBytes,ucodesBytes;};
struct Snapshot {NvU32 globalInitialized=0,adapterInitialized=0,firmwareLoaded=0,interruptInstalled=0,
    interruptArmed=0,powerRevoked=0,cancellationRevoked=0,powerAcknowledged=0;
    S540PreparationObservation preparation{};};
class Owner {
public:
    unsigned prepares=0,initializations=0,originalCalls=0,stops=0,cancels=0;
    S540PreparationObservation preparation{};
    bool privateImplPresent=false;
    std::atomic<bool> revoked{false};
    NV_STATUS prepare(IOPCIDevice *,S540ExperimentalTargetControl *,const Images &);
    NV_STATUS experimentalInitialize(const S540ExperimentalRuntimeRequest &);
    NV_STATUS cancelExperimental();
    NV_STATUS stop(){
        IOLockLock(guard);expect(cancellationPublishers==0,"noOwnerstopbeforepublisherjoin");IOLockUnlock(guard);
        ++stops;stopSequence.store(++sequence,std::memory_order_release);return NV_ERR_IN_USE;
    }
    Snapshot snapshot()const{
        Snapshot value{};value.preparation=preparation;return value;
    }
    S540ExperimentalRuntimeSnapshot runtimeSnapshot()const{
        S540ExperimentalRuntimeSnapshot value{};value.snapshotStatus=NV_OK;value.originalEntered=originalCalls!=0;return value;
    }
    S540RetainedStopSnapshot retainedStopSnapshot()const{
        S540RetainedStopSnapshot value{};value.format=1;value.bytes=sizeof(value);value.snapshotStatus=NV_OK;return value;
    }
};
}
// Instrument only the facade field representation. The extracted production
// assignment and surrounding lock calls are unchanged. This detects a real
// pointer publication moved outside its guard without reimplementing it.
struct TrackedOwner {
    S540NvidiaGspBootstrap::Owner *value=nullptr;
    TrackedOwner &operator=(S540NvidiaGspBootstrap::Owner *created){
        expect(lockHeld,"actualOwnerpublicationunderguard");++ownerPublications;value=created;return *this;
    }
    operator bool()const{return value!=nullptr;}
    S540NvidiaGspBootstrap::Owner *operator->()const{return value;}
};
class S540ExperimentalTargetControl {
public:
    TrackedOwner owner;
    IOPCIDevice *retainedProvider=nullptr;
    bool permanentPin=false;
    NvBool fixtureRequestOwned=NV_FALSE;
    unsigned retainCount=0;
    void retain(){++retainCount;}
    void publishOwnerObservation();
    NV_STATUS runOnce(const S540ExperimentalRequest &,NvBool *);
    NV_STATUS runOnce(const S540ExperimentalRequest &request){return runOnce(request,&fixtureRequestOwned);}
    NV_STATUS requestStop();
};
class S540ExperimentalTargetClient {
public:
    S540ExperimentalTargetControl *control=nullptr;
    NvBool requestOwned=NV_FALSE;
    bool terminated=false;
    void terminate(){terminated=true;}
    IOReturn clientClose();
};
static const S540ExperimentalBuildIdentity *s540FixtureIdentity(){
    static const S540ExperimentalBuildIdentity value={1,80,{1},{2},16384};return &value;
}
extern "C" const S540ExperimentalBuildIdentity *s540ExperimentalGetBuildIdentity(){return s540FixtureIdentity();}
extern "C" NV_STATUS s540RuntimeReadCompiledProfile(S540ExperimentalNativeProfile *out){
    *out={};out->format=1;out->bytes=104;out->codeContractSha256[0]=3;
    out->workerStackBytes=out->irqStackBytes=16384;
    std::memcpy(out->targetBuild,"25G241",7);return NV_OK;
}
extern "C" NV_STATUS s540RuntimeEmbeddedFirmware(const void **gsp,NvU64 *gspBytes,const void **ucodes,NvU64 *ucodesBytes){
    static const char bytes=0;*gsp=*ucodes=&bytes;*gspBytes=*ucodesBytes=1;return NV_OK;
}
static IOPCIDevice *copyTarget(){static IOPCIDevice device;return &device;}

@ACTUAL_BODIES@

static S540PreparationObservation failedPreparation(unsigned selected){
    S540PreparationObservation value{};
    if(selected==7)return value; // An absent observation remains unavailable.
    value.format=1;value.bytes=sizeof(value);
    value.observedMask=S540_PREP_OBS_STAGE|S540_PREP_OBS_STATUS|S540_PREP_OBS_FIRST_FAILURE;
    value.firstFailureStatus=value.lastStatus=NV_ERR_NOT_SUPPORTED;
    if(selected==5){
        value.stage=value.firstFailureStage=S540_PREP_POWER_START;
        value.lastCompleted=S540_PREP_DISPATCH_PREPARE;
        value.observedMask|=S540_PREP_OBS_POWER;
        auto &power=value.power;power.format=1;power.bytes=sizeof(power);
        power.stage=power.firstFailureStage=S540_PREP_POWER_JOIN_REGISTER_DRIVER;
        power.lastCompleted=S540_PREP_POWER_JOIN_PM_INIT;
        power.firstFailureStatus=NV_ERR_NOT_SUPPORTED;
        power.rawIOReturn=power.firstFailureRawIOReturn=0xe00002c7U;
        power.rawIOReturnValid=power.firstFailureRawIOReturnValid=1;
        power.observedMask=S540_PREP_PM_OBS_RAW_IOR;
    }else{
        value.observedMask|=S540_PREP_OBS_HOST_FACTS;
        value.hostKnown=selected==4?(S540_PREP_HOST_ALL&~S540_PREP_HOST_BATTERY):S540_PREP_HOST_ALL;
        value.hostMissing=selected==4?S540_PREP_HOST_BATTERY:0;
        if(selected==4){
            value.stage=value.firstFailureStage=S540_PREP_HOST_FACTS;
            value.lastCompleted=S540_PREP_PLATFORM_INITIALIZE;
        }else{
            value.stage=value.firstFailureStage=S540_PREP_DEVICE_FACTS;
            value.lastCompleted=S540_PREP_HOST_FACTS;
            value.observedMask|=S540_PREP_OBS_DEVICE_FACTS;
            value.deviceObserved=S540_PREP_DEVICE_ALL;
            value.devicePredicates=S540_PREP_DEVICE_ALL&~S540_PREP_DEVICE_D0;
        }
    }
    return value;
}
NV_STATUS S540NvidiaGspBootstrap::Owner::prepare(IOPCIDevice *,S540ExperimentalTargetControl *,const Images &){
    ++prepares;
    privateImplPresent=true;
    if(mode>=4){
        preparation=failedPreparation(mode);
        // Explicit fake endpoint: the real frontend must use the facade's
        // preserved record after the private owner state has been released.
        privateImplPresent=false;return NV_ERR_NOT_SUPPORTED;
    }
    if(mode==1)expect(fixtureControl->requestStop()==NV_ERR_BUSY_RETRY,"STOPduringpreparepublished");
    return NV_OK;
}
NV_STATUS S540NvidiaGspBootstrap::Owner::experimentalInitialize(const S540ExperimentalRuntimeRequest &){
    ++initializations;initializeEntered.store(true,std::memory_order_release);
    if(mode==2)expect(fixtureControl->requestStop()==NV_ERR_BUSY_RETRY,"preparedtokenSTOPpublished");
    if(mode==3)while(!cancelEntered.load(std::memory_order_acquire))std::this_thread::yield();
    if(revoked.load(std::memory_order_acquire))return NV_ERR_OPERATION_ABORTED;
    ++originalCalls;return NV_OK;
}
NV_STATUS S540NvidiaGspBootstrap::Owner::cancelExperimental(){
    ++cancels;revoked.store(true,std::memory_order_release);cancelEntered.store(true,std::memory_order_release);
    if(mode==3)while(!releaseCancel.load(std::memory_order_acquire))std::this_thread::yield();
    cancelExitSequence.store(++sequence,std::memory_order_release);return NV_OK;
}
static S540ExperimentalRequest request(){
    S540ExperimentalRequest value{};value.format=1;value.bytes=sizeof(value);value.generation=7;
    value.observedKernelStackBytes=16384;value.manualAcknowledgement=S540_EXPERIMENTAL_MANUAL_ACK;
    value.sourceSha256[0]=1;value.policySha256[0]=2;value.nativeCodeContractSha256[0]=3;
    std::memcpy(value.targetBuild,"25G241",7);return value;
}
static void reset(unsigned selected){
    mode=selected;state={};busy=false;cancellationReady=false;cancellationPublishers=0;ownerPublications=0;
    failAllocation=false;joinWaiting=false;cancelEntered=false;releaseCancel=false;initializeEntered=false;runFinished=false;
    sequence=0;cancelExitSequence=0;stopSequence=0;
    expect(s540ExperimentalModuleEnter(&state)==NV_OK,"modulefixture");
    expect(s540ExperimentalServiceStart(&state,7)==NV_OK,"servicefixture");
}
static void finish(S540ExperimentalTargetControl &control){
    // These fake owners have no hardware or persistent backing. Fixture-only
    // destruction after every real test thread joined is not driver cleanup.
    if(control.owner.value){control.owner.value->~Owner();std::free(control.owner.value);control.owner.value=nullptr;}
}
int main(){
    {
        reset(0);S540ExperimentalTargetControl control;fixtureControl=&control;
        S540ExperimentalTargetClient client;client.control=&control;
        expect(client.clientClose()==kIOReturnSuccess&&client.terminated,"readonlyclientclose");
        expect(!state.snapshot.stopRequested&&!state.snapshot.requestConsumed,"readonlyclosedoesnotclosefirstattemptadmission");
        expect(control.runOnce(request(),&client.requestOwned)==NV_OK&&client.requestOwned,"firstrunafterreadonlycloseclaimsownclient");
        expect(control.owner.value&&control.owner->originalCalls==1&&ownerPublications==1,"oneactualOwnerpublicationandentry");
        expect(control.retainCount==1&&control.permanentPin,"realretainbeforeOwnerallocation");
        expect(control.runOnce(request())==NV_ERR_STATE_IN_USE&&ownerPublications==1,"secondrequestcannotreplaceOwner");
        expect(client.clientClose()==kIOReturnSuccess&&state.snapshot.stopRequested&&control.owner->stops==1,"consumedclientcloseattemptsrealstop");
        finish(control);
    }
    {
        reset(1);S540ExperimentalTargetControl control;fixtureControl=&control;
        expect(control.runOnce(request())!=NV_OK,"STOPduringprepareabortsentry");
        expect(control.owner->prepares==1&&control.owner->initializations==0&&control.owner->originalCalls==0,"prepareSTOPpreventsoriginal");
        expect(control.owner->stops==1&&state.snapshot.stopAttempted&&state.snapshot.stopReturned,"pendingSTOPactuallyrunsafterprepare");
        finish(control);
    }
    {
        reset(2);S540ExperimentalTargetControl control;fixtureControl=&control;
        expect(control.runOnce(request())==NV_ERR_OPERATION_ABORTED,"STOPbeforeoperationadmissionaborts");
        expect(control.owner->cancels==1&&control.owner->originalCalls==0&&control.owner->stops==1,"preparedtokenrevokedthenstopattempted");
        expect(cancelExitSequence.load()<stopSequence.load(),"cancelpublishercompletedbeforestop");
        finish(control);
    }
    {
        reset(3);S540ExperimentalTargetControl control;fixtureControl=&control;
        NV_STATUS status=NV_ERR_NOT_READY,stopped=NV_ERR_NOT_READY;
        std::thread run([&]{status=control.runOnce(request());runFinished.store(true,std::memory_order_release);});
        while(!initializeEntered.load(std::memory_order_acquire))std::this_thread::yield();
        S540ExperimentalTargetClient reader;reader.control=&control;
        expect(reader.clientClose()==kIOReturnSuccess&&!state.snapshot.stopRequested,
            "readonlyclientclosedoesnotstopanotherclientsinflightrequest");
        std::thread cancel([&]{stopped=control.requestStop();});
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
        while(!joinWaiting.load(std::memory_order_acquire)&&!runFinished.load(std::memory_order_acquire)&&
              std::chrono::steady_clock::now()<deadline)std::this_thread::yield();
        expect(joinWaiting.load(std::memory_order_acquire),"actualpublicationclosurewaitsforrealpublisher");
        releaseCancel.store(true,std::memory_order_release);cancel.join();run.join();
        expect(status==NV_ERR_OPERATION_ABORTED&&stopped==NV_ERR_BUSY_RETRY,"concurrentSTOPstatusesremaintruthful");
        expect(control.owner->stops==1&&cancellationPublishers==0&&!cancellationReady,"publisherjoinedbeforeownerstop");
        expect(cancelExitSequence.load()<stopSequence.load(),"blockingcancelcompletedbeforeordinaryOwnerstop");
        finish(control);
    }
    {
        reset(0);S540ExperimentalTargetControl control;fixtureControl=&control;failAllocation=true;
        expect(control.runOnce(request())==NV_ERR_NO_MEMORY&&!control.owner,"realallocationfailurebranch");
        expect(state.snapshot.requestConsumed&&state.snapshot.retainedUntilReboot&&control.permanentPin,"allocationfailuredoesnotinventunloadauthority");
        expect(!state.snapshot.preparationAttempted&&!state.snapshot.preparation.observedMask,
            "allocationfailuredoesnotinventpreparationobservation");
    }
    for(unsigned failureMode=4;failureMode<=7;++failureMode){
        reset(failureMode);S540ExperimentalTargetControl control;fixtureControl=&control;
        const auto expected=failedPreparation(failureMode);
        expect(control.runOnce(request())==NV_ERR_NOT_SUPPORTED,"actualrunretainsfailedpreparationstatus");
        expect(control.owner->prepares==1&&!control.owner->privateImplPresent&&
            control.owner->initializations==0&&control.owner->originalCalls==0,"failedpreparecleanuphasnoinitialization");
        expect(state.snapshot.preparationAttempted&&state.snapshot.preparationReturned&&
            state.snapshot.preparationStatus==NV_ERR_NOT_SUPPORTED,"failedpreparationwiremilestonesremainseparate");
        expect(!std::memcmp(&state.snapshot.preparation,&expected,sizeof(expected)),
            "actualpublicationcopiesallpreparationfieldsafterprivatecleanup");
        if(failureMode==7){
            expect(!state.snapshot.preparation.observedMask&&state.snapshot.preparationStatus!=NV_OK,
                "zeroedobservationisnotpreparationsuccess");
        }else{
            expect(state.snapshot.preparation.firstFailureStage==expected.firstFailureStage&&
                state.snapshot.preparation.firstFailureStatus==NV_ERR_NOT_SUPPORTED,
                "specificfirstfailurestageandstatuspublished");
        }
        const S540PreparationObservation cached=state.snapshot.preparation;
        expect(control.requestStop()==NV_ERR_IN_USE,"failedpreparestillusesactualstopprotocol");
        expect(state.snapshot.stopReturned&&state.snapshot.stopStatus==NV_ERR_IN_USE&&
            state.snapshot.preparationStatus==NV_ERR_NOT_SUPPORTED,
            "stopstatusdoesnotoverwritepreparationfailure");
        expect(!std::memcmp(&state.snapshot.preparation,&cached,sizeof(cached)),
            "preparationobservationpreservedthroughpostcleanupstoppublication");
        expect(state.snapshot.retainedUntilReboot&&control.permanentPin&&
            !state.snapshot.wholeDmaStopProven&&!state.snapshot.pmAcknowledgementAuthorized,
            "diagnosticfailuredoesnotgrantunloadorcleanupauthority");
        finish(control);
    }
    std::printf("{\"status\":\"%s\",\"checks\":%u,\"failures\":%u,\"actual_lifecycle_bodies\":true,\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n",failures?"failed":"passed",checks,failures);
    return failures?1:0;
}
