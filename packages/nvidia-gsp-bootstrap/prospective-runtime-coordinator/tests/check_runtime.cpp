// CPU control of the actual coordinator bodies. All hardware/RM boundaries
// below are explicit fixtures, not evidence of target execution.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "../S540ExperimentalRuntime.h"
#include "../../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../src/S540NvidiaGspContext.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaFirstTxnContext.h"
static unsigned checks=0;
static void expect(bool value,const char *message) {
    ++checks;if(!value){std::fprintf(stderr,"control failed: %s\n",message);std::abort();}
}
struct S540GspContext { int identity; } contextStorage{};
static NvU64 currentThread=44;
static bool maySleep=true,revoked=false;
static unsigned failurePoint=0,lastStep=0,posted=0,globalCalls=0,originalCalls=0,revokeAtStep=0;
static void step(unsigned value){lastStep=value;if(revokeAtStep==value)revoked=true;}
static const void *actualOwner=nullptr;
static S540ExperimentalNativeProfile compiledProfile{};
static S540FirstTxnGlobalSnapshot globalEpoch{};
static S540FirstTxnSnapshot firstTxn{};
static S540GspContextSnapshot contextFacts{};
extern "C" NvBool s540Darwin_os_semaphore_may_sleep(void){return maySleep;}
extern "C" NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out){*out=currentThread;return NV_OK;}
namespace S540NvidiaGspPower {
struct Lease { NV_STATUS actualStatus=NV_OK;NV_STATUS status() const{return actualStatus;} };
}
extern "C" NV_STATUS s540RuntimeReadCompiledProfile(S540ExperimentalNativeProfile *out){*out=compiledProfile;return NV_OK;}
extern "C" NV_STATUS s540GspCancellationGetSnapshot(S540GspCancellationToken token,S540GspCancellationSnapshot *out){
    *out={};out->bound=NV_TRUE;out->generation=token;out->ownerThread=44;
    out->phase=lastStep>=2?S540_GSP_CANCEL_OPERATION:S540_GSP_CANCEL_IDLE;out->revoked=revoked;return NV_OK;
}
extern "C" NV_STATUS s540GspCancellationCheckState(const void *state){
    expect(state==&contextStorage,"exact real context state fixture");return revoked?NV_ERR_OPERATION_ABORTED:NV_OK;
}
extern "C" NV_STATUS s540GspCancellationBegin(S540GspCancellationToken token){
    expect(token==7&&lastStep==1,"cancel begins after lifetime and before globals");
    step(2);return revoked?NV_ERR_OPERATION_ABORTED:(failurePoint==2?NV_ERR_NO_MEMORY:NV_OK);
}
extern "C" NV_STATUS s540GspCancellationRevoke(S540GspCancellationToken token){
    expect(token==7,"cancel exact token");revoked=true;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnBeginOwner(const void *owner){
    expect(lastStep==2,"real owner epoch after cancel begins");actualOwner=owner;step(3);
    globalEpoch={};globalEpoch.owner=owner;globalEpoch.generation=19;globalEpoch.masterThread=44;
    return failurePoint==3?NV_ERR_NO_MEMORY:NV_OK;
}
extern "C" NV_STATUS s540FirstTxnMasterIdentity(S540FirstTxnHostIdentity *out){
    out->owner=actualOwner;out->generation=19;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnGlobalReadMaster(S540FirstTxnGlobalSnapshot *out){*out=globalEpoch;return NV_OK;}
extern "C" NV_STATUS s540FirstTxnGlobalGetSnapshot(S540FirstTxnGlobalSnapshot *out){*out=globalEpoch;return NV_OK;}
extern "C" void *s540GspContextState(S540GspContext *context){return context;}
extern "C" NV_STATUS s540GspContextPrepare(S540GspContext *context){
    expect(context==&contextStorage&&lastStep==4,"context after actual globalREADY");step(5);
    return failurePoint==5?NV_ERR_NO_MEMORY:NV_OK;
}
extern "C" NV_STATUS s540GspContextBindFirstTransaction(S540GspContext *context,S540GspCancellationToken token){
    expect(context==&contextStorage&&token==7&&lastStep==5,"real transaction binding order");step(6);
    globalEpoch.nv=context;return failurePoint==6?NV_ERR_NO_MEMORY:NV_OK;
}
extern "C" NV_STATUS s540GspContextInitializeAdapter(S540GspContext *context){
    expect(context==&contextStorage&&lastStep==7,"adapter after actual IRQ arm");step(8);++originalCalls;
    contextFacts.adapterAttempted=NV_TRUE;contextFacts.adapterInitialized=failurePoint!=8;
    firstTxn.originalReturned=firstTxn.originalExitReady=NV_TRUE;
    return failurePoint==8?NV_ERR_NO_MEMORY:NV_OK;
}
extern "C" void s540GspContextSnapshot(S540GspContext *,S540GspContextSnapshot *out){*out=contextFacts;}
extern "C" NV_STATUS s540FirstTxnGetSnapshot(const void *,S540FirstTxnSnapshot *out){*out=firstTxn;return NV_OK;}
namespace S540NvidiaGspBootstrap {
#include "../runtime-entry.cpp.inc"
static NV_STATUS invokeFixture();
enum {ExperimentalInitialize=77,Stop=78};
struct DispatcherFixture {
    NV_STATUS invoke(unsigned command){expect(command==ExperimentalInitialize,"exact experimental dispatcher");return invokeFixture();}
    NV_STATUS post(unsigned command){expect(command==Stop,"actual stop post");++posted;return NV_OK;}
};
class Owner {
public:
    struct Impl;
    Impl *impl_=nullptr;
    NV_STATUS experimentalInitialize(const S540ExperimentalRuntimeRequest &);
    NV_STATUS cancelExperimental();
    S540ExperimentalRuntimeSnapshot runtimeSnapshot() const;
};
struct Owner::Impl {
    DispatcherFixture dispatcher;
    struct Transport {
        bool held=false,installed=false,armed=false;
        bool hardwareDmaLifetimeHeld()const{return held;}
        bool interruptInstalled()const{return installed;}
        bool interruptArmed()const{return armed;}
    } transport;
    S540NvidiaGspPower::Lease power;
    S540GspContext *context=&contextStorage;
    NvU64 thread=44;
    S540GspCancellationToken cancellationToken=7;
    bool diagnosticLifetimeHeld=false,deviceBound=true;
    struct State {
        bool prepared=true,initializationRefused=true,quarantined=false;
        bool globalInitialized=false,adapterInitialized=false;
        NV_STATUS initializationStatus=NV_ERR_NOT_READY;
    } state;
    bool owned()const{return maySleep&&currentThread==thread;}
    NV_STATUS retainDiagnosticLifetime(){
        expect(lastStep==0,"retain is first resource operation");step(1);
        if(failurePoint==1)return NV_ERR_NO_MEMORY;
        diagnosticLifetimeHeld=transport.held=true;return NV_OK;
    }
    NV_STATUS installDiagnosticInterrupts(){
        expect(lastStep==6,"real IRQ install after transaction");step(7);
        if(failurePoint==7)return NV_ERR_NO_MEMORY;
        transport.installed=transport.armed=true;return NV_OK;
    }
#include "../owner-methods.cpp.inc"
};
static Owner::Impl *activeFixture=nullptr;
static NV_STATUS invokeFixture(){return activeFixture->experimentalInitialize();}
#include "../facade-methods.cpp.inc"
}
extern "C" NV_STATUS s540GlobalRmInitialize(S540NvidiaGlobalRmResult *out){
    using namespace S540NvidiaGspBootstrap;
    expect(lastStep==3,"global after realowner epoch");++globalCalls;
    const NV_STATUS permission=runtimeGlobalEntry();
    if(permission!=NV_OK)return permission;
    expect(permission==NV_OK,"actual global pull gate");step(4);
    globalEpoch.originalReturned=NV_TRUE;
    if(failurePoint==4){globalEpoch.originalStatus=NV_ERR_NO_MEMORY;return NV_ERR_NO_MEMORY;}
    globalEpoch.state=S540_FIRST_GLOBAL_READY;globalEpoch.validated=NV_TRUE;
    *out={};out->initialized=NV_TRUE;return NV_OK;
}
extern "C" NvBool s540GlobalRmIsInitialized(void){return lastStep>=4&&failurePoint!=4;}
int main(){
    using namespace S540NvidiaGspBootstrap;
    compiledProfile.format=1;compiledProfile.bytes=sizeof(compiledProfile);
    compiledProfile.workerStackBytes=compiledProfile.irqStackBytes=16384;
    compiledProfile.codeContractSha256[0]=42;std::memcpy(compiledProfile.targetBuild,"25G241",6);
    S540ExperimentalRuntimeRequest request{};request.format=1;request.bytes=sizeof(request);
    request.observedHostStackBytes=16384;request.manualAcknowledgement=S540_EXPERIMENTAL_MANUAL_ACK;
    std::memcpy(request.codeContractSha256,compiledProfile.codeContractSha256,32);
    std::memcpy(request.targetBuild,compiledProfile.targetBuild,16);
    for(unsigned scenario=0;scenario<23;++scenario){
        runtimeAttemptClaim=0;activeRuntimeEntry=nullptr;globalEpoch={};firstTxn={};contextFacts={};
        actualOwner=nullptr;lastStep=posted=globalCalls=originalCalls=0;revoked=false;maySleep=true;currentThread=44;
        failurePoint=scenario<=8?scenario:0;
        revokeAtStep=scenario>=15?scenario-14:0;
        Owner::Impl impl;Owner owner;owner.impl_=&impl;activeFixture=&impl;
        auto candidate=request;
        if(scenario==9)candidate.manualAcknowledgement=0;
        if(scenario==10)candidate.codeContractSha256[0]^=1;
        if(scenario==11)candidate.observedHostStackBytes=16383;
        if(scenario==12)candidate.targetBuild[7]='X';
        if(scenario==13)currentThread=45;
        if(scenario==14)impl.state.prepared=false;
        const NV_STATUS status=owner.experimentalInitialize(candidate);
        const auto view=owner.runtimeSnapshot();
        expect(view.format==1&&view.bytes==sizeof(view)&&view.snapshotStatus==NV_OK,"typed publishedruntime");
        if(!scenario){
            expect(status==NV_OK&&lastStep==8,"inclusive16KiB permits complete realcallsequencefixture");
            expect(view.stage==S540_RUNTIME_RETURNED&&view.originalEntered&&view.originalReturned,"honestpositiveoriginalreturn");
            expect(view.lifetimeRetained&&view.globalInitialized&&view.adapterInitialized,"actualflags fixture");
            expect(owner.experimentalInitialize(candidate)!=NV_OK,"secondattemptrefused");
            const auto preserved=owner.runtimeSnapshot();
            expect(preserved.stage==S540_RUNTIME_RETURNED&&preserved.firstStatus==NV_OK,"repeatpreservesfirstattempt");
            expect(owner.cancelExperimental()==NV_OK&&revoked&&posted==1,"real cancelandStoppost afteroriginal");
        }else{
            expect(status!=NV_OK&&view.firstStatus==status&&view.stage==S540_RUNTIME_FAILED,"preserveactualfirstfailure");
            if(scenario>=9&&scenario<15)expect(lastStep==0&&!globalCalls&&!originalCalls&&!impl.diagnosticLifetimeHeld,"malformedrequest noentry");
            if(scenario>=2&&scenario<=8)expect(impl.diagnosticLifetimeHeld&&impl.transport.held,"failurekeepsactualbacking");
            if(scenario==4)expect(view.originalEntered&&view.globalOriginalReturned&&!originalCalls,"globalfailureobservednotadapter");
            if(scenario<4||(scenario>=9&&scenario<15))expect(!view.originalEntered,"noinventedoriginalentry");
            if(scenario<8||(scenario>=9&&scenario<15))expect(!originalCalls,"failurebeforeadaptercannotcalladapter");
            if(scenario>=15){
                expect(impl.diagnosticLifetimeHeld&&impl.transport.held,"revocationneverreleasesbacking");
                expect(status==NV_ERR_OPERATION_ABORTED,"actualrevocationpreserved");
                expect(originalCalls==(revokeAtStep==8?1U:0U),"revocationexcludeslateradapterentry");
            }
        }
        impl.runtimeSnapshotGuard=1;const auto busy=owner.runtimeSnapshot();
        expect(busy.snapshotStatus==NV_ERR_IN_USE&&!busy.lifetimeRetained,"collidingdiagnosticisbusy notauthority");
        impl.runtimeSnapshotGuard=0;
    }
    // Independent realgate negativecontrols over exactimmutable identity.
    revoked=false;revokeAtStep=0;
    RuntimeEntry entry{};S540NvidiaGspPower::Lease power;
    entry.owner=&entry;entry.nv=&contextStorage;entry.thread=44;entry.cancellation=7;entry.power=&power;
    entry.stage=S540_RUNTIME_GLOBAL;activeRuntimeEntry=&entry;actualOwner=&entry;currentThread=44;lastStep=3;
    globalEpoch={};globalEpoch.owner=&entry;globalEpoch.masterThread=44;globalEpoch.generation=19;
    expect(runtimeGlobalEntry()==NV_OK,"realentryfixturevalid");
    currentThread=45;expect(runtimeGlobalEntry()!=NV_OK,"foreignthreadrefused");currentThread=44;
    revoked=true;expect(runtimeGlobalEntry()!=NV_OK,"revokedOPrefused");revoked=false;
    globalEpoch.state=S540_FIRST_GLOBAL_READY;expect(runtimeGlobalEntry()!=NV_OK,"reentrantglobalrefused");globalEpoch.state=0;
    globalEpoch.owner=nullptr;expect(runtimeGlobalEntry()!=NV_OK,"foreignownerrefused");globalEpoch.owner=&entry;
    power.actualStatus=NV_ERR_NOT_READY;expect(runtimeGlobalEntry()!=NV_OK,"PMrevocationrefused");power.actualStatus=NV_OK;
    entry.stage=S540_RUNTIME_RETURNED;expect(runtimeGlobalEntry()!=NV_OK,"laterphaseclosedglobalgate");
    std::printf("{\"checks\":%u,\"hardware_executed\":false,\"original_rm_executed\":false}\n",checks);
}
