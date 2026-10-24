// SPDX-License-Identifier: MIT
// Actual old/new kernel PM bodies with explicit PM/provider endpoint fixtures.
#include "S540NvidiaGspPower.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>
using namespace S540NvidiaGspPower;
using IOReturn = unsigned;
using UInt32 = unsigned;
using uint64_t = unsigned long;
static unsigned checks, failStage, waitCalls, domainCalls, activeCalls, freeCalls;
static bool makeReady, domainKnown, providerActive;
static std::vector<std::string> calls;
static void expect(bool value, const char *text) { ++checks; if (!value) {std::fprintf(stderr,"PM observation: %s\n",text);std::abort();} }
constexpr IOReturn kIOReturnSuccess = 0;
constexpr unsigned kIOPMPowerOn = 1, kIOPMDeviceUsable = 2, kIOPMPreventIdleSleep = 4;
constexpr unsigned kOnWaitMs = 5000, kMillisecondScale = 1000;
constexpr int THREAD_UNINT = 0, THREAD_TIMED_OUT = 4;
struct IOPMPowerState { unsigned version=0, capabilityFlags=0, inputPowerRequirement=0; };
static IOReturn rawResult(unsigned stage) { return failStage == stage ? 0xe0000000U + stage : 0; }
static void IOLockLock(std::mutex *guard) {guard->lock();}
static void IOLockUnlock(std::mutex *guard) {guard->unlock();}
static void clock_interval_to_deadline(unsigned,unsigned,uint64_t *out) {*out=123;}
static int IOLockSleepDeadline(std::mutex *,void *,uint64_t,int) {++waitCalls;calls.push_back("sleep");return THREAD_TIMED_OUT;}
class S540NvidiaGspPowerService;
static S540NvidiaGspPowerService *currentService;
class IOPCIDevice {
public:
    void retain(){calls.push_back("retain");}
    IOReturn addPowerChild(S540NvidiaGspPowerService *){calls.push_back("child");return rawResult(6);}
    bool isInactive(){++activeCalls;calls.push_back("inactive");return !providerActive;}
};
class IOService {
public:
    bool start(IOPCIDevice *){calls.push_back("start");return failStage!=2;}
};
class S540NvidiaGspPowerService : public IOService {
public:
    mutable std::mutex mutex;
    std::mutex *guard=&mutex;
    IOPCIDevice *endpoint=nullptr;
    Revocation revocation{};
    Detail::Protocol protocol;
    NvU32 revocationHooksInFlight=0;
    bool attached=false,pmInitialized=false,closing=false;
    bool attach(IOPCIDevice *) {calls.push_back("attach");return failStage!=1;}
    void setName(const char *){calls.push_back("name");}
    void PMinit(){calls.push_back("PMinit");}
    IOReturn registerPowerDriver(S540NvidiaGspPowerService *,IOPMPowerState *,unsigned){calls.push_back("register");return rawResult(4);}
    IOReturn changePowerStateTo(unsigned n){expect(n==0,"same initial off request");calls.push_back("off");return rawResult(5);}
    IOReturn changePowerStateToPriv(unsigned n){
        expect(n==1,"same original privileged on request");calls.push_back("on");
        const auto result=rawResult(7);
        if (!result && makeReady){IOLockLock(guard);protocol.setState(true);protocol.completed();IOLockUnlock(guard);}
        return result;
    }
    bool exactDomain() const{++domainCalls;calls.push_back("domain");return domainKnown;}
    Snapshot snapshot() const;
    bool join(IOPCIDevice *,const Revocation &);
    bool originalJoin(IOPCIDevice *,const Revocation &);
    NV_STATUS waitOn();
    NV_STATUS originalWaitOn();
    NV_STATUS finish(){IOLockLock(guard);protocol.stopped();IOLockUnlock(guard);calls.push_back("finish");return NV_OK;}
    void release(){calls.push_back("release");}
};
static NvU64 ordinaryThread(){return 44;}
static void IOFree(void *,decltype(sizeof(0))){++freeCalls;calls.push_back("free");}
class TestLease {
public:
    struct Impl {S540NvidiaGspPowerService *service;NvU64 ownerThread;};
    Impl *impl_;
    Snapshot final_{};
    S540PreparationPowerObservation preparationFinal_{};
    NV_STATUS status() const;
    NV_STATUS originalStatus() const;
    NV_STATUS stop();
    S540PreparationPowerObservation preparationObservation() const;
};
#include "actual-power-kernel.inc"
#define KERNEL 1
#include "actual-power-lease.inc"
#undef KERNEL
static void reset(){calls.clear();waitCalls=domainCalls=activeCalls=freeCalls=0;}
static S540PreparationPowerObservation observed(S540NvidiaGspPowerService &service){
    IOLockLock(service.guard);const auto value=service.protocol.preparationObservation();IOLockUnlock(service.guard);return value;
}
static NV_STATUS hook(void *) {return NV_OK;}
int main(){
    IOPCIDevice provider;
    for (unsigned failure : {0U,1U,2U,4U,5U,6U,7U}) {
        failStage=failure;makeReady=domainKnown=providerActive=true;
        S540NvidiaGspPowerService original,actual;
        reset();currentService=&original;const bool a=original.originalJoin(&provider,{&original,hook});const auto originalCalls=calls;
        reset();currentService=&actual;const bool b=actual.join(&provider,{&actual,hook});
        expect(a==b && calls==originalCalls,"actual join returns and all original PM calls/order unchanged");
        const auto value=observed(actual);
        expect(value.format==1 && value.bytes==56,"typed 56-byte actual guarded PM observation");
        if (failure) {
            expect(!b && value.stage==failure && value.firstFailureStage==failure && value.firstFailureStatus==NV_ERR_NOT_READY,
                "each original false join decision identifies its exact first substage");
            const bool raw=failure>=4;
            expect(bool(value.firstFailureRawIOReturnValid)==raw && bool(value.rawIOReturnValid)==raw,
                "BOOL failures never fabricate IOReturn validity");
            if (raw) expect(value.firstFailureRawIOReturn==rawResult(failure),"actual raw IOReturn preserved");
        } else expect(b && value.lastCompleted==S540_PREP_POWER_JOIN_MARK_REQUESTED && !value.firstFailureStage,
            "all real join endpoints completed before readiness wait");
    }
    for (unsigned kind=0;kind<4;++kind) {
        failStage=0;makeReady=kind!=1;domainKnown=kind!=2;providerActive=kind!=3;
        S540NvidiaGspPowerService original,actual;
        original.originalJoin(&provider,{&original,hook});actual.join(&provider,{&actual,hook});
        reset();const auto a=original.originalWaitOn();const auto trace=calls;const auto sleeps=waitCalls,domains=domainCalls,active=activeCalls;
        reset();const auto b=actual.waitOn();
        expect(a==b && calls==trace && waitCalls==sleeps && domainCalls==domains && activeCalls==active,
            "actual wait boolean short circuit, original sleeps/domain/provider call counts unchanged");
        const auto value=observed(actual);
        expect(bool(value.observedMask&S540_PREP_PM_OBS_READY),"readiness actually observed");
        expect(bool(value.observedMask&S540_PREP_PM_OBS_DOMAIN)==(kind!=1),"domain is unobserved if original readiness short-circuited");
        expect(bool(value.observedMask&S540_PREP_PM_OBS_ACTIVE)==(kind==0||kind==3),"provider active is unobserved when original prefix refused");
        if (!kind) expect(b==NV_OK && value.stage==S540_PREP_POWER_COMPLETE && value.lastCompleted==12 && !value.firstFailureStage,"successful PM start truthfully completed");
        else expect(b==NV_ERR_NOT_READY && value.firstFailureStage==8+kind && value.firstFailureStatus==NV_ERR_NOT_READY,
            "85 disambiguates wait readiness, actual domain, and provider active predicates");
        if(kind==1)expect(value.waitResultValid && value.waitResult==THREAD_TIMED_OUT,"real sleep timeout result retained");
        TestLease::Impl data{&actual,44};TestLease lease;lease.impl_=&data;
        const auto beforeDomain=domainCalls,beforeActive=activeCalls;const auto captured=lease.preparationObservation();
        expect(domainCalls==beforeDomain && activeCalls==beforeActive,"metadata getter does not repeat any registry/provider query");
        expect(!std::memcmp(&captured,&value,sizeof(value)),"getter returns exact guarded fields");
        expect(lease.stop()==NV_OK,"actual original stop result remains successful");
        const auto after=lease.preparationObservation();
        expect(!std::memcmp(&captured,&after,sizeof(after)) && !lease.impl_ && freeCalls==1,
            "observations survive actual Impl destruction without cleanup overwriting first failure");
    }
    for(unsigned kind=0;kind<4;++kind){
        failStage=0;makeReady=kind!=1;domainKnown=kind!=2;providerActive=kind!=3;
        S540NvidiaGspPowerService original,actual;original.originalJoin(&provider,{&original,hook});actual.join(&provider,{&actual,hook});
        TestLease::Impl aData{&original,44},bData{&actual,44};TestLease aLease,bLease;aLease.impl_=&aData;bLease.impl_=&bData;
        reset();const auto a=aLease.originalStatus();const auto trace=calls;
        reset();const auto b=bLease.status();expect(a==b&&calls==trace,"final status original snapshot/provider short-circuit preserved");
        const auto value=bLease.preparationObservation();expect(value.stage==13,"final status distinct from initial wait");
        expect((value.observedMask&(S540_PREP_PM_OBS_READY|S540_PREP_PM_OBS_DOMAIN))==3,
            "status reuses actual existing snapshot domain query even if readiness was false");
        expect(bool(value.observedMask&S540_PREP_PM_OBS_ACTIVE)==(kind==0||kind==3),"status does not invent skipped isInactive observation");
        if(kind)expect(value.firstFailureStage==13&&value.firstFailureStatus==NV_ERR_NOT_READY,"actual final status refusal captured");
    }
    std::printf("{\"status\":\"passed\",\"checks\":%u,\"kernel_execution\":\"not_tested\",\"extra_hardware_queries\":0}\n",checks);
}
