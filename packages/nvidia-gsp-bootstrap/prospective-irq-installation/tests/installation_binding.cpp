// SPDX-License-Identifier: MIT
// The actual Binding header and transformed Session declarations are compiled
// unchanged. Session/Lease APIs, cancellation, Context, record and mask endpoints
// are explicit fixtures; no real controller registration or hardware occurs.
#include "S540NvidiaGspIrqInstallation.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
using S540NvidiaGspIrq::Binding;
using S540NvidiaDeviceTransport::Session;
using S540NvidiaDeviceTransport::InterruptContract;
using S540NvidiaGspPower::Lease;

namespace {
int contextToken,foreignContextToken,nvToken,pciToken,guardToken,ownerToken,foreignToken;
int stacks[4],privateToken;
S540GspContext *const actualContext=reinterpret_cast<S540GspContext *>(&contextToken);
S540GspContext *const foreignContext=reinterpret_cast<S540GspContext *>(&foreignContextToken);
constexpr NvU64 ownerThread=0x1234,token=0x5678,epoch=0x9abc,dmaEpoch=0xdef0;
S540GspIrqIdentity identity{};
S540GspContextSnapshot contextState{};
S540FirstTxnGlobalSnapshot master{};
S540GspCancellationSnapshot cancellation{};
InterruptContract savedContract{};
NvU64 currentThread,currentDmaGeneration;
NV_STATUS threadStatus,masterStatus,cancelSnapshotStatus,cancelStateStatus,powerStatus;
NV_STATUS identityStatus,modeStatus,installStatus,armStatus,softwareStopStatus,maskStatus;
bool ordinary,matching,sessionActive,sessionAccessible,dmaHeld,installedBit,armedBit;
bool revokeOnRegister,revokeOnEnable,softwareDrained,hardwareMasked;
void *pciHandle;
NvU32 checks,failures,installCalls,registerCalls,armCalls,enableCalls,stopCalls,maskCalls;
NvU32 topCalls,lockedCalls,unlockedCalls,modeCalls,masterReads,softwareReads,fullReads;
void require(bool value) { if(!value)std::abort(); }
void expect(bool value,const char *message) {
    ++checks;if(!value){++failures;std::fprintf(stderr,"installation binding: %s\n",message);}
}
void revoke() { cancellation.revoked=NV_TRUE;powerStatus=NV_ERR_OPERATION_ABORTED; }
void reset() {
    S540NvidiaGspIrq::Detail::installed=nullptr;
    identity={};identity.context=actualContext;identity.nv=&nvToken;identity.privateState=&privateToken;
    identity.pciHandle=&pciToken;identity.isrGuard=&guardToken;identity.ownerThread=ownerThread;
    identity.generation=epoch;identity.mainStack=&stacks[0];identity.isrStack=&stacks[1];
    identity.lockedStack=&stacks[2];identity.unlockedStack=&stacks[3];
    contextState={};contextState.created=contextState.eventLocks=contextState.privateState=NV_TRUE;
    master={};master.owner=&ownerToken;master.nv=identity.nv;master.generation=epoch;
    master.masterThread=ownerThread;master.validated=NV_TRUE;master.state=S540_FIRST_GLOBAL_READY;
    cancellation={};cancellation.bound=NV_TRUE;cancellation.generation=token;
    cancellation.ownerThread=ownerThread;cancellation.phase=S540_GSP_CANCEL_OPERATION;
    savedContract={};currentThread=ownerThread;currentDmaGeneration=dmaEpoch;
    threadStatus=masterStatus=cancelSnapshotStatus=cancelStateStatus=powerStatus=NV_OK;
    identityStatus=modeStatus=installStatus=armStatus=softwareStopStatus=maskStatus=NV_OK;
    ordinary=matching=sessionActive=sessionAccessible=dmaHeld=true;
    installedBit=armedBit=revokeOnRegister=revokeOnEnable=softwareDrained=hardwareMasked=false;
    pciHandle=&pciToken;installCalls=registerCalls=armCalls=enableCalls=stopCalls=maskCalls=0;
    topCalls=lockedCalls=unlockedCalls=modeCalls=masterReads=softwareReads=fullReads=0;
}
NV_STATUS install(Binding &binding,Session &session,Lease &power) {
    return binding.install(actualContext,&session,&power,&ownerToken,ownerThread,token);
}
}

extern "C" NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) { return ordinary; }
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *thread) {
    require(thread);if(threadStatus==NV_OK)*thread=currentThread;return threadStatus;
}
extern "C" NV_STATUS s540FirstTxnGlobalReadMaster(S540FirstTxnGlobalSnapshot *out) {
    require(out);++masterReads;if(masterStatus==NV_OK)*out=master;return masterStatus;
}
extern "C" NV_STATUS s540GspCancellationGetSnapshot(S540GspCancellationToken selected,S540GspCancellationSnapshot *out) {
    require(selected==token && out);if(cancelSnapshotStatus==NV_OK)*out=cancellation;return cancelSnapshotStatus;
}
extern "C" NV_STATUS s540GspCancellationCheckState(const void *nv) { require(nv==identity.nv);return cancelStateStatus; }
extern "C" NV_STATUS s540GspContextReadIrqIdentity(S540GspContext *context,S540GspIrqIdentity *out) {
    require(context==actualContext && out);if(identityStatus==NV_OK)*out=identity;return identityStatus;
}
extern "C" NvBool s540GspContextMatchIrqIdentity(S540GspContext *context,const S540GspIrqIdentity *id) {
    return matching && context==actualContext && id && !std::memcmp(id,&identity,sizeof(identity));
}
extern "C" void s540GspContextSnapshot(S540GspContext *context,S540GspContextSnapshot *out) {
    require(context==actualContext && out);*out=contextState;
}
extern "C" NV_STATUS s540GspContextSelectMessageInterrupt(S540GspContext *context,const S540GspIrqIdentity *id) {
    require(context==actualContext && id && s540GspContextMatchIrqIdentity(context,id));++modeCalls;return modeStatus;
}
extern "C" NvBool s540GspContextInterruptTop(S540GspContext *context,NvBool *locked,NvBool *unlocked) {
    require(context==actualContext && locked && unlocked);++topCalls;*locked=NV_TRUE;*unlocked=NV_FALSE;return NV_TRUE;
}
extern "C" void s540GspContextLockedBottomHalf(S540GspContext *context) { require(context==actualContext);++lockedCalls; }
extern "C" void s540GspContextUnlockedBottomHalf(S540GspContext *context) { require(context==actualContext);++unlockedCalls; }
extern "C" NV_STATUS s540FirstTxnIrqMaskHardware(nvidia_stack_s *stack,nv_state_t *nv) {
    require(static_cast<void *>(stack)==identity.mainStack && static_cast<void *>(nv)==identity.nv);
    require(softwareDrained);++maskCalls;if(maskStatus==NV_OK)hardwareMasked=true;return maskStatus;
}
extern "C" NV_STATUS s540FirstTxnIrqValidateSoftwareDrained(void) {
    ++softwareReads;return softwareDrained?NV_OK:NV_ERR_NOT_READY;
}
extern "C" NV_STATUS s540FirstTxnIrqValidateDrained(void) {
    ++fullReads;return softwareDrained&&hardwareMasked?NV_OK:NV_ERR_NOT_READY;
}
namespace S540NvidiaDeviceTransport {
Session::Session() {}
Session::~Session() {}
bool Session::active() const { return sessionActive; }
bool Session::accessible() { return sessionAccessible; }
bool Session::hardwareDmaLifetimeHeld() const { return dmaHeld; }
NvU64 Session::hardwareDmaGeneration() const { return currentDmaGeneration; }
void *Session::pciHandle() const { return ::pciHandle; }
bool Session::interruptInstalled() const { return installedBit; }
bool Session::interruptArmed() const { return armedBit; }
NV_STATUS Session::installInterrupt(const InterruptContract &contract) {
    ++installCalls;savedContract=contract;
    // Publication precedes the first OS/controller operation.
    require(static_cast<void *>(S540NvidiaGspIrq::Detail::installed)==contract.context);
    require(contract.originalState==identity.nv && contract.validateBinding && contract.selectMode);
    NV_STATUS status=contract.validateBinding(contract.context);if(status!=NV_OK)return status;
    status=contract.selectMode(contract.context);if(status!=NV_OK)return status;
    ++registerCalls;if(revokeOnRegister)revoke();
    if(installStatus==NV_OK)installedBit=true;return installStatus;
}
NV_STATUS Session::armInterrupt() {
    ++armCalls;require(savedContract.readyToArm);
    if(!savedContract.readyToArm(savedContract.context))return NV_ERR_NOT_READY;
    ++enableCalls;if(revokeOnEnable)revoke();
    if(armStatus==NV_OK)armedBit=true;return armStatus;
}
NV_STATUS Session::stopInterrupt() {
    ++stopCalls;if(softwareStopStatus!=NV_OK)return softwareStopStatus;
    softwareDrained=true;
    NV_STATUS status=savedContract.maskHardware(savedContract.context);
    // Real Session public booleans clear only on complete successful stop.
    if(status==NV_OK)installedBit=armedBit=false;
    return status;
}
}
namespace S540NvidiaGspPower {
Lease::Lease():impl_(nullptr),final_{} {}
Lease::~Lease() {}
NV_STATUS Lease::status() const { return powerStatus; }
}

#define REFUSE(change,status,message) do { reset();Session s;Lease p;Binding b;change;expect(install(b,s,p)==status&&!installCalls&&!registerCalls&&!enableCalls,message); } while(0)
int main() {
    reset();expect(Binding::checkInstalled(actualContext)==NV_ERR_NOT_READY,"unpublished Binding cannot authorize original entry");
    {Session s;Lease p;Binding b;auto before=b.snapshot();
        expect(before.installStatus==NV_ERR_NOT_READY && before.armStatus==NV_ERR_NOT_READY && !before.stopAttempts,
            "initial diagnostic status grants no installation");
        expect(install(b,s,p)==NV_OK && registerCalls==1 && enableCalls==1 && modeCalls==1,
            "normal installation selects original mode registers and arms exactly once");
        expect(savedContract.context==&b && savedContract.originalState==identity.nv &&
            savedContract.validateBinding(savedContract.context)==NV_OK,
            "actual contract holds permanent Binding and exact original nv identity");
        bool locked=false,unlocked=true;
        expect(savedContract.top(savedContract.context,locked,unlocked) && locked && !unlocked && topCalls==1,
            "top callback reaches exact retained Context and returns genuine endpoint outputs");
        savedContract.lockedBottomHalf(savedContract.context);savedContract.unlockedBottomHalf(savedContract.context);
        expect(lockedCalls==1 && unlockedCalls==1,"each bottom-half callback reaches exact retained Context");
        expect(Binding::checkInstalled(actualContext)==NV_OK && b.checkBeforeOriginalEntry(foreignContext)==NV_ERR_NOT_READY,
            "installed bound Context passes local gate and foreign Context refuses");
        auto snapshot=b.snapshot();
        expect(snapshot.generation==epoch && snapshot.hardwareDmaGeneration==dmaEpoch && snapshot.modeSelected &&
            snapshot.installationAttempted && snapshot.sessionInstalled && snapshot.sessionArmed,
            "snapshot observes exact record/DMA epochs and Session state");
        matching=false;expect(savedContract.validateBinding(savedContract.context)==NV_ERR_INVALID_STATE &&
            b.checkBeforeOriginalEntry(actualContext)==NV_ERR_INVALID_STATE,"changed original identity refuses callbacks and entry");matching=true;
        currentThread++;expect(b.quiesce()==NV_ERR_INVALID_STATE && !stopCalls,"wrong-thread quiesce performs no stop or mask");
        currentThread=ownerThread;ordinary=false;
        expect(b.quiesce()==NV_ERR_INVALID_STATE && !stopCalls,"nonordinary quiesce performs no stop or mask");ordinary=true;
        expect(b.quiesce()==NV_OK && stopCalls==1 && maskCalls==1 && softwareReads==1 && fullReads==1,
            "owner quiesce observes software exclusion before original mask and both independent drains");
        snapshot=b.snapshot();expect(snapshot.stopAttempts==1 && snapshot.softwareDrainStatus==NV_OK && snapshot.fullDrainStatus==NV_OK &&
            !snapshot.sessionInstalled && !snapshot.sessionArmed && b.checkBeforeOriginalEntry(actualContext)==NV_ERR_NOT_READY,
            "a completed stop permanently denies original entry for this Binding");
        expect(install(b,s,p)==NV_ERR_INVALID_STATE,"installation is one-shot and cannot recycle retained Binding");
    }
    REFUSE(identityStatus=NV_ERR_TIMEOUT,NV_ERR_TIMEOUT,"Context identity refusal precedes all registration");
    REFUSE(contextState.adapterAttempted=NV_TRUE,NV_ERR_INVALID_STATE,"previous original adapter attempt refuses installation");
    REFUSE(contextState.adapterInitialized=NV_TRUE,NV_ERR_INVALID_STATE,"already initialized original adapter refuses installation");
    REFUSE(contextState.quarantined=NV_TRUE,NV_ERR_INVALID_STATE,"quarantined original Context refuses installation");
    REFUSE(ordinary=false,NV_ERR_INVALID_STATE,"nonordinary owner refuses installation");
    REFUSE(currentThread++,NV_ERR_INVALID_STATE,"foreign owner thread refuses installation");
    REFUSE(masterStatus=NV_ERR_TIMEOUT,NV_ERR_TIMEOUT,"strong-master read refusal propagates");
    REFUSE(master.owner=&foreignToken,NV_ERR_INVALID_STATE,"foreign strong owner refuses installation");
    REFUSE(master.nv=&foreignToken,NV_ERR_INVALID_STATE,"foreign strong original nv refuses installation");
    REFUSE(master.generation++,NV_ERR_INVALID_STATE,"foreign strong epoch refuses installation");
    REFUSE(master.masterThread++,NV_ERR_INVALID_STATE,"foreign strong master thread refuses installation");
    REFUSE(master.validated=NV_FALSE,NV_ERR_INVALID_STATE,"unvalidated strong epoch refuses installation");
    REFUSE(master.state=S540_FIRST_GLOBAL_RETAINED,NV_ERR_INVALID_STATE,"retained strong epoch refuses operation installation");
    REFUSE(matching=false,NV_ERR_INVALID_STATE,"changed immutable Context binding refuses installation");
    REFUSE(cancelSnapshotStatus=NV_ERR_TIMEOUT,NV_ERR_TIMEOUT,"cancellation snapshot refusal propagates");
    REFUSE(cancellation.bound=NV_FALSE,NV_ERR_OPERATION_ABORTED,"unbound cancellation refuses installation");
    REFUSE(cancellation.generation++,NV_ERR_OPERATION_ABORTED,"foreign cancellation epoch refuses installation");
    REFUSE(cancellation.ownerThread++,NV_ERR_OPERATION_ABORTED,"foreign cancellation owner refuses installation");
    REFUSE(cancellation.phase=S540_GSP_CANCEL_CLEANUP,NV_ERR_OPERATION_ABORTED,"cleanup-only authority cannot install");
    REFUSE(cancellation.revoked=NV_TRUE,NV_ERR_OPERATION_ABORTED,"revocation before installation permits no controller operation");
    REFUSE(cancellation.publicationInFlight=NV_TRUE,NV_ERR_OPERATION_ABORTED,"revocation publication blocks installation");
    REFUSE(cancelStateStatus=NV_ERR_OPERATION_ABORTED,NV_ERR_OPERATION_ABORTED,"actual bound-state cancellation check refuses installation");
    REFUSE(powerStatus=NV_ERR_OPERATION_ABORTED,NV_ERR_OPERATION_ABORTED,"actual PM lease refusal blocks installation");
    REFUSE(sessionActive=false,NV_ERR_INVALID_STATE,"inactive Session refuses installation");
    REFUSE(sessionAccessible=false,NV_ERR_INVALID_STATE,"actual Session inaccessible state refuses installation");
    REFUSE(dmaHeld=false,NV_ERR_INVALID_STATE,"missing hardware-DMA lifetime hold refuses installation");
    REFUSE(currentDmaGeneration=0,NV_ERR_INVALID_STATE,"zero hardware-DMA epoch refuses installation");
    REFUSE(pciHandle=&foreignToken,NV_ERR_INVALID_STATE,"foreign actual PCI handle refuses installation");
    REFUSE(installedBit=true,NV_ERR_IN_USE,"prior Session interrupt registration refuses installation");
    REFUSE(armedBit=true,NV_ERR_IN_USE,"prior Session interrupt arm refuses installation");
    {reset();Session s;Lease p;Binding b;revokeOnRegister=true;
        expect(install(b,s,p)==NV_ERR_OPERATION_ABORTED && registerCalls==1 && !enableCalls && stopCalls==1,
            "revocation after registration drains before any arm attempt");
        expect(b.snapshot().stopAttempts==1 && b.checkBeforeOriginalEntry(actualContext)==NV_ERR_NOT_READY,
            "registered-then-revoked installation cannot authorize original entry");}
    {reset();Session s;Lease p;Binding b;revokeOnEnable=true;
        expect(install(b,s,p)==NV_ERR_OPERATION_ABORTED && registerCalls==1 && enableCalls==1 && stopCalls==1 && maskCalls==1,
            "revocation during real enable attempt drains and cannot report installation success");
        expect(!b.snapshot().sessionArmed && b.checkBeforeOriginalEntry(actualContext)==NV_ERR_NOT_READY,
            "post-enable revocation leaves no local original-entry permission");}
    {reset();Session s;Lease p;Binding b;modeStatus=NV_ERR_NOT_SUPPORTED;
        expect(install(b,s,p)==NV_ERR_NOT_SUPPORTED && modeCalls==1 && !registerCalls && !armCalls && !b.snapshot().modeSelected,
            "original mode selection refusal cannot reach registration or arming");}
    {reset();Session s;Lease p;Binding b;installStatus=NV_ERR_TIMEOUT;
        expect(install(b,s,p)==NV_ERR_TIMEOUT && registerCalls==1 && !armCalls &&
            b.checkBeforeOriginalEntry(actualContext)==NV_ERR_NOT_READY,"partial registration failure never authorizes original entry");
        expect(b.quiesce()==NV_OK && stopCalls==1,"published partial installation remains available to owner quiesce");}
    {reset();Session s;Lease p;Binding b;armStatus=NV_ERR_TIMEOUT;
        expect(install(b,s,p)==NV_ERR_TIMEOUT && enableCalls==1 && stopCalls==1 && maskCalls==1 &&
            b.checkBeforeOriginalEntry(actualContext)==NV_ERR_NOT_READY,"partial enable failure drains and refuses original entry");}
    {reset();Session s;Lease p;Binding b;require(install(b,s,p)==NV_OK);maskStatus=NV_ERR_NOT_SUPPORTED;
        expect(b.quiesce()==NV_ERR_NOT_SUPPORTED && softwareDrained && !hardwareMasked,
            "pre-GPU full-mask refusal preserves separate successful software exclusion");
        auto snapshot=b.snapshot();expect(snapshot.sessionInstalled && snapshot.sessionArmed && snapshot.stopAttempts==1 &&
            snapshot.softwareDrainStatus==NV_OK && snapshot.fullDrainStatus!=NV_OK,
            "failed full mask preserves actual retained Session bits and incomplete full drain");
        expect(b.checkBeforeOriginalEntry(actualContext)==NV_ERR_NOT_READY && !savedContract.readyToArm(savedContract.context),
            "retained Session bits cannot rearm or authorize original entry after any stop attempt");
        maskStatus=NV_OK;expect(b.quiesce()==NV_OK && b.snapshot().stopAttempts==2 && !b.snapshot().sessionArmed,
            "same retained owner may retry actual mask without resetting installation history");}
    {reset();Session s;Lease p;Binding b;require(install(b,s,p)==NV_OK);softwareStopStatus=NV_ERR_TIMEOUT;
        expect(b.quiesce()==NV_ERR_TIMEOUT && !maskCalls && b.snapshot().softwareDrainStatus!=NV_OK &&
            b.snapshot().fullDrainStatus!=NV_OK && b.checkBeforeOriginalEntry(actualContext)==NV_ERR_NOT_READY,
            "failed software exclusion performs no mask and still permanently refuses original entry");}
    {reset();Session s;Lease p;Binding b;require(install(b,s,p)==NV_OK);revoke();cancellation.phase=S540_GSP_CANCEL_CLEANUP;
        masterStatus=NV_ERR_INVALID_STATE;
        expect(b.quiesce()==NV_OK && maskCalls==1,"ordinary retained owner can quiesce after operation revocation; mask authority remains separate");}
    {reset();Session s;Lease p;Binding b;require(install(b,s,p)==NV_OK);currentDmaGeneration++;
        expect(b.checkBeforeOriginalEntry(actualContext)==NV_ERR_INVALID_STATE,"changed hardware-DMA epoch refuses later original entry");}
    {reset();Session s;Lease p;Binding b;require(install(b,s,p)==NV_OK);sessionAccessible=false;
        expect(b.checkBeforeOriginalEntry(actualContext)==NV_ERR_INVALID_STATE,"actual Session loss of accessibility refuses later original entry");}
    std::printf("{\"checks\":%u,\"failures\":%u,\"hardware_execution\":false}\n",checks,failures);
    return failures?1:0;
}
