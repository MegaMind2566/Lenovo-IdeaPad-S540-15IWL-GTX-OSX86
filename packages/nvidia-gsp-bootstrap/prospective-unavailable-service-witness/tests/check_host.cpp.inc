/* SPDX-License-Identifier: MIT; actual transformed Host.cpp with typed endpoints. */
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
#include "actual-host.cpp"
namespace fixture {
int nv, foreign, owner;
bool ordinary = true, retainDiagnostic = false;
NvU64 thread = 73;
NV_STATUS snapshotStatus = NV_OK, threadStatus = NV_OK;
NV_STATUS freeStatus = NV_OK, completeStatus = NV_OK;
S540FirstTxnSnapshot snapshot{};
std::atomic<NvU32> refusalCalls{0};
std::atomic<NvU32> allocationRefusals{0};
std::atomic<NvU32> aggregateOrderingFailures{0};
bool orderingControl = false;
NvU32 checks = 0, failures = 0;
void expect(bool value, int line) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr,"Host diagnostic control line %d\n",line); }
}
}
#define EXPECT(value) fixture::expect(bool(value),__LINE__)
extern "C" NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) {
    return fixture::ordinary ? NV_TRUE : NV_FALSE;
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out) {
    if (fixture::threadStatus != NV_OK) return fixture::threadStatus;
    *out=fixture::thread; return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnGetSnapshot(const void *nv, S540FirstTxnSnapshot *out) {
    if(nv!=&fixture::nv) return NV_ERR_OBJECT_NOT_FOUND;
    if(fixture::snapshotStatus!=NV_OK)return fixture::snapshotStatus;
    *out=fixture::snapshot; return NV_OK;
}
extern "C" void s540FirstTxnObserveServiceRefusal(NvU32 domain,NvU32,NV_STATUS status) {
    if(domain==4) { ++fixture::allocationRefusals; return; }
    const NvU32 ordinal=fixture::refusalCalls.fetch_add(1);
    if(domain!=1 || status!=NV_ERR_NOT_SUPPORTED) ++fixture::aggregateOrderingFailures;
    if(fixture::orderingControl) {
        const NvU32 observed=__atomic_load_n(&counters.unavailableCalls,__ATOMIC_RELAXED);
        if(observed!=(ordinal+1U)/2U) ++fixture::aggregateOrderingFailures;
    }
}
extern "C" NV_STATUS s540FirstTxnBackendBeginRelease(const S540FirstTxnHostIdentity *,NvU64 *permit) {
    *permit=1; return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnBackendEnd(NvU64) { return NV_OK; }
extern "C" NV_STATUS s540FirstTxnHostCaptureAllocation(S540FirstTxnHostIdentity *out) {
    out->owner=&fixture::owner;out->generation=19;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnHostRetainDiagnostic(const S540FirstTxnHostIdentity *,NvBool *retain) {
    *retain=fixture::retainDiagnostic?NV_TRUE:NV_FALSE;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnHostAcquireFree(const S540FirstTxnHostIdentity *,S540FirstTxnHostFreePermit *permit) {
    *permit=fixture::freeStatus==NV_OK?37:0;return fixture::freeStatus;
}
extern "C" NV_STATUS s540FirstTxnHostCompleteFree(const S540FirstTxnHostIdentity *,S540FirstTxnHostFreePermit) {
    return fixture::completeStatus;
}
extern "C" void s540Global_crypto_snapshot(S540NvidiaGlobalCryptoSnapshot *out) { *out={}; }
extern "C" S540DeviceMemoryStatistics s540DeviceMemoryStatistics(void) { return {}; }

static void initializeHost() {
    S540NvidiaGlobalRmPlatformFacts facts{};
    facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;facts.cpuCount=1;
    facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;
    facts.osVersion=facts.osDate="explicit-cpu-control";
    EXPECT(s540GlobalRmHostInitialize(&facts)==NV_OK);
}
static S540HostUnavailableDiagnostics read() {
    S540HostUnavailableDiagnostics out{};
    EXPECT(s540GlobalRmReadUnavailableDiagnostics(&fixture::nv,&out)==NV_OK);
    EXPECT(out.format==1 && out.bytes==sizeof(out));
    return out;
}
static void guardControls() {
    S540HostUnavailableDiagnostics marker;
    std::memset(&marker,0x6d,sizeof(marker));
    auto refuse=[&](const void *nv,NV_STATUS wanted) {
        auto actual=marker;
        EXPECT(s540GlobalRmReadUnavailableDiagnostics(nv,&actual)==wanted);
        EXPECT(std::memcmp(&actual,&marker,sizeof(actual))==0);
    };
    refuse(nullptr,NV_ERR_INVALID_ARGUMENT);
    EXPECT(s540GlobalRmReadUnavailableDiagnostics(&fixture::nv,nullptr)==NV_ERR_INVALID_ARGUMENT);
    refuse(&fixture::foreign,NV_ERR_OBJECT_NOT_FOUND);
    fixture::ordinary=false;refuse(&fixture::nv,NV_ERR_INVALID_STATE);fixture::ordinary=true;
    fixture::snapshotStatus=NV_ERR_TIMEOUT;refuse(&fixture::nv,NV_ERR_TIMEOUT);fixture::snapshotStatus=NV_OK;
    fixture::threadStatus=NV_ERR_OPERATING_SYSTEM;refuse(&fixture::nv,NV_ERR_OPERATING_SYSTEM);fixture::threadStatus=NV_OK;
    fixture::thread=0;refuse(&fixture::nv,NV_ERR_INVALID_STATE);fixture::thread=72;
    refuse(&fixture::nv,NV_ERR_INVALID_STATE);fixture::thread=73;
    fixture::snapshot.originalReturned=NV_FALSE;refuse(&fixture::nv,NV_ERR_NOT_READY);
    fixture::snapshot.originalReturned=NV_TRUE;fixture::snapshot.originalInFlight=NV_TRUE;
    refuse(&fixture::nv,NV_ERR_NOT_READY);fixture::snapshot.originalInFlight=NV_FALSE;
}
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    fixture::snapshot.masterThread=73;fixture::snapshot.originalReturned=NV_TRUE;
    fixture::snapshot.generation=19;
    const int scenario=std::atoi(argv[1]);
    guardControls();
    if(scenario>=0 && scenario<10) {
        NvU32 wantedService=0;
        switch(scenario) {
        case 0: wantedService=510;s540GlobalRmRecordUnavailable(wantedService);break;
        case 1: fixture::ordinary=false;EXPECT(!s540GlobalRmHostShutdown());break;
        case 2: fixture::ordinary=false;EXPECT(!s540GlobalRmHostAllocateOriginal(8));break;
        case 3: fixture::ordinary=false;s540GlobalRmHostFreeOriginal(&fixture::owner);break;
        case 4: {
            initializeHost();void *p=s540GlobalRmHostAllocateOriginal(17);EXPECT(p);
            fixture::freeStatus=NV_ERR_NOT_READY;s540GlobalRmHostFreeOriginal(p);break;
        }
        case 5: {
            initializeHost();void *p=s540GlobalRmHostAllocateOriginal(17);EXPECT(p);
            fixture::completeStatus=NV_ERR_NOT_READY;s540GlobalRmHostFreeOriginal(p);break;
        }
        case 6: {
            fixture::ordinary=false;S540NvidiaGlobalRmHostSnapshot out{};
            s540GlobalRmHostSnapshot(&out);EXPECT(out.unavailableCalls==1);break;
        }
        case 7: wantedService=580;s540GlobalRmRecordService(wantedService);break;
        case 8: s540GlobalRmRecordServiceName(nullptr);break;
        case 9:
            for(auto &entry:serviceUses)entry.name="occupied-static-control";
            s540GlobalRmRecordServiceName("overflow-static-control");break;
        }
        fixture::ordinary=true;
        auto out=read();
        EXPECT(out.unavailableCallsLifetime==1 && out.siteCallsLifetime[scenario]==1);
        EXPECT(out.sitesObservedMask==(1U<<scenario));
        EXPECT(out.firstState==2 && out.observedMask==3);
        EXPECT(out.firstSite==NvU32(scenario) && out.firstService==wantedService);
        EXPECT(counters.unavailableCalls==1 && fixture::refusalCalls==2);
        EXPECT(fixture::allocationRefusals==(scenario==2?1U:0U));
        for(NvU32 site=0;site<10;++site)if(site!=NvU32(scenario))EXPECT(!out.siteCallsLifetime[site]);
        s540GlobalRmRecordUnavailable(18);
        auto later=read();EXPECT(later.firstSite==out.firstSite && later.firstService==out.firstService);
        EXPECT(later.unavailableCallsLifetime==2 && fixture::refusalCalls==4);
    } else if(scenario==10) {
        fixture::orderingControl=true;
        for(NvU32 i=0;i<32;++i)s540GlobalRmRecordUnavailable(i);
        EXPECT(!fixture::aggregateOrderingFailures);
        auto out=read();EXPECT(out.firstService==0 && !out.firstSite && out.unavailableCallsLifetime==32);
        initializeHost();EXPECT(s540GlobalRmHostShutdown());initializeHost();
        auto after=read();EXPECT(std::memcmp(&out,&after,sizeof(out))==0);
        EXPECT(s540GlobalRmHostShutdown());
    } else if(scenario==11) {
        hostUnavailableObservation.total=~0U-1U;
        hostUnavailableObservation.siteCalls[0]=~0U-1U;
        __atomic_store_n(&counters.unavailableCalls,~0U-1U,__ATOMIC_RELAXED);
        s540GlobalRmRecordUnavailable(18);s540GlobalRmRecordUnavailable(510);
        auto out=read();EXPECT(out.unavailableCallsLifetime==~0U && out.siteCallsLifetime[0]==~0U);
        EXPECT(counters.unavailableCalls==~0U && out.firstService==18);
    } else if(scenario==12) {
        hostUnavailableObservation.firstState=1;
        hostUnavailableObservation.firstSite=0xaaaaU;hostUnavailableObservation.firstService=0xbbbbU;
        s540GlobalRmRecordUnavailable(18);
        auto pending=read();EXPECT(pending.observedMask==1 && pending.firstState==1);
        EXPECT(!pending.firstSite && !pending.firstService && pending.unavailableCallsLifetime==1);
        hostUnavailableObservation.firstSite=7;hostUnavailableObservation.firstService=580;
        __atomic_store_n(&hostUnavailableObservation.firstState,2U,__ATOMIC_RELEASE);
        auto published=read();EXPECT(published.observedMask==3 && published.firstSite==7 && published.firstService==580);
    } else if(scenario==13) {
        std::vector<std::thread> writers;
        for(NvU32 n=0;n<8;++n)writers.emplace_back([n]{
            for(NvU32 i=0;i<1000;++i)s540GlobalRmRecordUnavailable(500+n);
        });
        for(auto &writer:writers)writer.join();
        auto out=read();EXPECT(out.unavailableCallsLifetime==8000 && out.siteCallsLifetime[0]==8000);
        EXPECT(counters.unavailableCalls==8000 && fixture::refusalCalls==16000);
        EXPECT(out.firstSite==0 && out.firstService>=500 && out.firstService<508 && out.firstState==2);
        EXPECT(out.sitesObservedMask==1 && !fixture::aggregateOrderingFailures);
    } else if(scenario==14) {
        recordUnavailableAt(77,0xffffffffU);
        auto out=read();EXPECT(out.firstSite==0 && out.firstService==77 && out.sitesObservedMask==1);
    } else if(scenario==15) {
        auto out=read();EXPECT(out.observedMask==1 && !out.firstState && !out.firstSite && !out.firstService);
        EXPECT(!out.unavailableCallsLifetime && !out.sitesObservedMask);
    } else return 2;
    std::printf("{\"cases\":1,\"scenario\":%d,\"checks\":%u,\"failures\":%u}\n",scenario,fixture::checks,fixture::failures);
    return fixture::failures?1:0;
}
