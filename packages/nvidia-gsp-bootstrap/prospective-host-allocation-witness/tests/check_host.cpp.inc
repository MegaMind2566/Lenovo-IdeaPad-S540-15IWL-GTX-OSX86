/* SPDX-License-Identifier: MIT.
 * Actual whole transformed Host and ACPI facade, plus the actual extracted
 * os_alloc_mem body. Typed CPU endpoints replace Darwin/record services.
 * GNU ld --wrap=malloc controls only backing failure in scenario23; all other
 * allocations call the real allocator. No production reset/injection exists.
 */
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
#include "actual-host.cpp"
#include "actual-acpi.c"
#include "actual-os.inc"

namespace fixture {
int nv, foreign, owner;
bool ordinary = true;
NvU64 thread = 73;
NV_STATUS snapshotStatus = NV_OK, threadStatus = NV_OK;
NV_STATUS captureStatus = NV_OK, confirmStatus = NV_OK;
bool badInitialIdentity = false;
std::atomic<NvU32> captureCalls{0};
std::atomic<NvU32> refusalCalls{0}, allocationRefusals{0};
std::atomic<NvU32> aggregateOrderingFailures{0}, allocationOrderingFailures{0};
std::atomic<bool> failBacking{false};
bool aggregateOrdering = false, allocationOrdering = false;
NvU32 aggregateOrderingBase = 0, refusalOrderingBase = 0;
S540FirstTxnSnapshot snapshot{};
NvU32 checks = 0, failures = 0;
void expect(bool value, int line) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr,"Host allocation control line %d\n",line); }
}
}
#define EXPECT(value) fixture::expect(bool(value),__LINE__)
extern "C" void *__real_malloc(std::size_t);
extern "C" void *__wrap_malloc(std::size_t bytes) {
    if (fixture::failBacking.load(std::memory_order_relaxed)) return nullptr;
    return __real_malloc(bytes);
}
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
    if(domain==4) {
        const NvU32 ordinal=fixture::allocationRefusals.fetch_add(1);
        if(fixture::allocationOrdering &&
           __atomic_load_n(&hostAllocationObservation.allocationFailures,__ATOMIC_RELAXED)!=ordinal)
            ++fixture::allocationOrderingFailures;
        return;
    }
    const NvU32 ordinal=fixture::refusalCalls.fetch_add(1);
    if(domain!=1 || status!=NV_ERR_NOT_SUPPORTED) ++fixture::aggregateOrderingFailures;
    if(fixture::aggregateOrdering) {
        const NvU32 event=ordinal-fixture::refusalOrderingBase;
        const NvU32 count=__atomic_load_n(&counters.unavailableCalls,__ATOMIC_RELAXED);
        if(count!=fixture::aggregateOrderingBase+(event+1U)/2U) ++fixture::aggregateOrderingFailures;
        /* Both original refusal publications precede the new observation. */
        if(__atomic_load_n(&hostAllocationObservation.producerTotal,__ATOMIC_RELAXED)!=event/2U)
            ++fixture::aggregateOrderingFailures;
    }
}
extern "C" NV_STATUS s540FirstTxnBackendBeginRelease(const S540FirstTxnHostIdentity *,NvU64 *permit) {
    *permit=1;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnBackendEnd(NvU64) { return NV_OK; }
extern "C" NV_STATUS s540FirstTxnHostCaptureAllocation(S540FirstTxnHostIdentity *out) {
    const NvU32 ordinal=fixture::captureCalls.fetch_add(1);
    out->owner=nullptr;out->generation=0;
    const NV_STATUS status=ordinal ? fixture::confirmStatus : fixture::captureStatus;
    if(status!=NV_OK)return status;
    out->owner=fixture::badInitialIdentity ? nullptr : &fixture::owner;
    out->generation=19;
    return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnHostRetainDiagnostic(const S540FirstTxnHostIdentity *,NvBool *retain) {
    *retain=NV_FALSE;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnHostAcquireFree(const S540FirstTxnHostIdentity *,S540FirstTxnHostFreePermit *permit) {
    *permit=37;return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnHostCompleteFree(const S540FirstTxnHostIdentity *,S540FirstTxnHostFreePermit) {
    return NV_OK;
}
extern "C" void s540Global_crypto_snapshot(S540NvidiaGlobalCryptoSnapshot *out) { *out={}; }
extern "C" S540DeviceMemoryStatistics s540DeviceMemoryStatistics(void) { return {}; }

static void initializeHost() {
    S540NvidiaGlobalRmPlatformFacts facts{};
    facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;facts.cpuCount=1;
    facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;
    facts.osVersion=facts.osDate="typed-host-allocation-control";
    EXPECT(s540GlobalRmHostInitialize(&facts)==NV_OK);
}
static S540HostAllocationDiagnostics read() {
    S540HostAllocationDiagnostics out{};
    EXPECT(s540GlobalRmReadAllocationDiagnostics(&fixture::nv,&out)==NV_OK);
    EXPECT(out.format==1 && out.bytes==sizeof(out) && sizeof(out)==104);
    EXPECT(!out.reserved);
    return out;
}
static void guardControls() {
    S540HostAllocationDiagnostics marker;
    std::memset(&marker,0x6d,sizeof(marker));
    auto refuse=[&](const void *nv,NV_STATUS wanted) {
        auto actual=marker;
        EXPECT(s540GlobalRmReadAllocationDiagnostics(nv,&actual)==wanted);
        EXPECT(std::memcmp(&actual,&marker,sizeof(actual))==0);
    };
    refuse(nullptr,NV_ERR_INVALID_ARGUMENT);
    EXPECT(s540GlobalRmReadAllocationDiagnostics(&fixture::nv,nullptr)==NV_ERR_INVALID_ARGUMENT);
    refuse(&fixture::foreign,NV_ERR_OBJECT_NOT_FOUND);
    fixture::ordinary=false;refuse(&fixture::nv,NV_ERR_INVALID_STATE);fixture::ordinary=true;
    fixture::snapshotStatus=NV_ERR_TIMEOUT;refuse(&fixture::nv,NV_ERR_TIMEOUT);fixture::snapshotStatus=NV_OK;
    fixture::threadStatus=NV_ERR_OPERATING_SYSTEM;refuse(&fixture::nv,NV_ERR_OPERATING_SYSTEM);fixture::threadStatus=NV_OK;
    fixture::thread=0;refuse(&fixture::nv,NV_ERR_INVALID_STATE);
    fixture::thread=72;refuse(&fixture::nv,NV_ERR_INVALID_STATE);fixture::thread=73;
    fixture::snapshot.originalReturned=NV_FALSE;refuse(&fixture::nv,NV_ERR_NOT_READY);
    fixture::snapshot.originalReturned=NV_TRUE;fixture::snapshot.originalInFlight=NV_TRUE;
    refuse(&fixture::nv,NV_ERR_NOT_READY);fixture::snapshot.originalInFlight=NV_FALSE;
    fixture::snapshot.originalReturned=NV_FALSE;fixture::snapshot.originalInFlight=NV_FALSE;
    refuse(&fixture::nv,NV_ERR_NOT_READY);fixture::snapshot.originalReturned=NV_TRUE;
}
static void producerScenario(NvU32 producer) {
    NvU8 guid[16];std::memset(guid,0x5a,sizeof(guid));
    NvU32 data[2]={0x12345678U,0x98765432U};
    NvU32 value=0xdecafaceU,size=8,outputStatus=0xc0ffeeU;
    NvU16 shortSize=8;
    switch(producer) {
    case 1: {
        fixture::ordinary=false;void *out=&fixture::owner;
        EXPECT(os_alloc_mem(&out,123)==NV_ERR_INVALID_STATE);
        EXPECT(out==&fixture::owner);fixture::ordinary=true;
        EXPECT(!fixture::captureCalls.load());break;
    }
    case 2:
        EXPECT(nv_acpi_d3cold_dsm_for_upstream_port(nullptr,guid,1,2,&value)==NV_ERR_NOT_SUPPORTED);break;
    case 3: EXPECT(nv_acpi_ddc_method(nullptr,data,&size,NV_TRUE)==NV_ERR_NOT_SUPPORTED);break;
    case 4: EXPECT(nv_acpi_dod_method(nullptr,data,&size)==NV_ERR_NOT_SUPPORTED);break;
    case 5:
        EXPECT(nv_acpi_dsm_method(nullptr,guid,1,NV_TRUE,2,data,8,&outputStatus,data,&shortSize)==NV_ERR_NOT_SUPPORTED);break;
    case 6: EXPECT(nv_acpi_get_powersource(&value)==NV_ERR_NOT_SUPPORTED);break;
    case 7: EXPECT(nv_acpi_mux_method(nullptr,data,0,"MXDM")==NV_ERR_NOT_SUPPORTED);break;
    case 8: {
        NvU32 handles=0xaabbccddU;nv_acpi_methods_init(&handles);EXPECT(!handles);
        nv_acpi_methods_uninit();nv_acpi_methods_init(nullptr);break;
    }
    default: std::abort();
    }
    EXPECT(data[0]==0x12345678U && data[1]==0x98765432U);
    EXPECT(value==0xdecafaceU && size==8 && shortSize==8 && outputStatus==0xc0ffeeU);
    for(NvU8 byte:guid)EXPECT(byte==0x5aU);
    const auto out=read();
    EXPECT(out.observedMask==7 && out.producerCallsLifetime==1);
    EXPECT(out.producerMask==(1U<<producer) && out.producerFirstState==2);
    EXPECT(out.producerFirstId==producer && out.producerFirstService==0);
    for(NvU32 p=0;p<9;++p)EXPECT(out.producerCalls[p]==(p==producer?1U:0U));
    EXPECT(!out.allocationFailuresLifetime && !out.allocationFirstState && !out.allocationStagesMask);
    EXPECT(counters.unavailableCalls==1 && fixture::refusalCalls.load()==2);
    EXPECT(!fixture::allocationRefusals.load());
    EXPECT(hostUnavailableObservation.total==1 && hostUnavailableObservation.siteCalls[0]==1);
    s540GlobalRmRecordUnavailableProducer(579,0);
    const auto later=read();
    EXPECT(later.producerCallsLifetime==2 && later.producerFirstId==producer && !later.producerFirstService);
    EXPECT(later.producerCalls[0]==1 && later.producerCalls[producer]==1);
}

static void allocationScenario(NvU32 stage) {
    NvU64 bytes=700U+stage;
    NV_STATUS status=NV_ERR_INVALID_STATE;
    fixture::allocationOrdering=true;
    if(stage!=1 && stage!=2 && stage!=3 && stage!=4)initializeHost();
    switch(stage) {
    case 1: fixture::ordinary=false;break;
    case 2: bytes=0;break;
    case 3: bytes=kSingleLimit+1U;status=NV_ERR_NO_MEMORY;break;
    case 4: break;
    case 5: fixture::captureStatus=NV_ERR_NOT_SUPPORTED;status=NV_ERR_NOT_SUPPORTED;break;
    case 6: fixture::badInitialIdentity=true;break;
    case 7: failureOrdinal=1;status=NV_ERR_NO_MEMORY;break;
    case 8: nextAllocationSerial=~NvU64(0);status=NV_ERR_NO_MEMORY;break;
    case 9: fixture::confirmStatus=NV_ERR_TIMEOUT;status=NV_ERR_TIMEOUT;break;
    case 10: fixture::failBacking.store(true);status=NV_ERR_NO_MEMORY;break;
    default: std::abort();
    }
    if(stage==5) {
        void *out=&fixture::owner;
        EXPECT(os_alloc_mem(&out,bytes)==NV_ERR_NO_MEMORY);
        EXPECT(out==&fixture::owner);
    } else EXPECT(!s540GlobalRmHostAllocateOriginal(bytes));
    fixture::failBacking.store(false);fixture::ordinary=true;
    const auto out=read();
    EXPECT(out.observedMask==11 && !out.producerCallsLifetime && !out.producerMask);
    EXPECT(out.allocationFailuresLifetime==1 && out.allocationStagesMask==(1U<<(stage-1U)));
    EXPECT(out.allocationFirstState==2 && out.allocationFirstStage==stage);
    EXPECT(out.allocationFirstStatus==status && out.allocationFirstBytes==bytes);
    EXPECT(out.allocationFirstOriginal==1 && fixture::allocationRefusals.load()==1);
    EXPECT(!fixture::allocationOrderingFailures.load());
    EXPECT(fixture::captureCalls.load()==(stage<=4?0U:stage>=9?2U:1U));
    EXPECT(counters.unavailableCalls==(stage==1?1U:0U));
    EXPECT(fixture::refusalCalls.load()==(stage==1?2U:0U));
    if(stage>=7)EXPECT(!retention.pendingAllocations && !counters.liveAllocations && !counters.liveBytes);
    EXPECT(!s540GlobalRmHostAllocate(0));
    const auto later=read();
    EXPECT(later.allocationFailuresLifetime==2 && later.allocationFirstStage==stage);
    EXPECT(later.allocationFirstStatus==status && later.allocationFirstBytes==bytes && later.allocationFirstOriginal==1);
    EXPECT(later.allocationStagesMask==((1U<<(stage-1U))|2U));
    EXPECT(!fixture::allocationOrderingFailures.load());
}

int main(int argc,char **argv) {
    if(argc!=2)return 2;
    fixture::snapshot.masterThread=73;fixture::snapshot.originalReturned=NV_TRUE;
    fixture::snapshot.generation=19;
    const int scenario=std::atoi(argv[1]);
    guardControls();
    if(scenario==0) {
        const auto out=read();
        EXPECT(out.observedMask==3 && !out.producerCallsLifetime && !out.producerMask);
        EXPECT(!out.producerFirstState && !out.producerFirstId && !out.producerFirstService);
        EXPECT(!out.allocationFailuresLifetime && !out.allocationFirstState && !out.allocationStagesMask);
        EXPECT(!out.allocationFirstStage && !out.allocationFirstStatus && !out.allocationFirstBytes && !out.allocationFirstOriginal);
        EXPECT(!fixture::refusalCalls.load() && !fixture::allocationRefusals.load());
    } else if(scenario>=1 && scenario<=8)producerScenario(static_cast<NvU32>(scenario));
    else if(scenario==9) {
        s540GlobalRmRecordUnavailable(71);
        auto generic=read();EXPECT(!generic.producerCallsLifetime && !generic.producerFirstState);
        EXPECT(counters.unavailableCalls==1 && fixture::refusalCalls.load()==2);
        /* Ordering control begins after the one deliberately excluded event. */
        fixture::aggregateOrderingBase=1;fixture::refusalOrderingBase=2;
        fixture::aggregateOrdering=true;
        for(NvU32 i=0;i<32;++i)s540GlobalRmRecordUnavailableProducer(100+i,i?5U:0xffffffffU);
        fixture::aggregateOrdering=false;
        const auto out=read();EXPECT(!fixture::aggregateOrderingFailures.load());
        EXPECT(out.producerCallsLifetime==32 && out.producerCalls[0]==1 && out.producerCalls[5]==31);
        EXPECT(out.producerMask==33U && out.producerFirstId==0 && out.producerFirstService==100);
        EXPECT(counters.unavailableCalls==33 && fixture::refusalCalls.load()==66);
    } else if(scenario==10) {
        s540GlobalRmRecordUnavailableProducer(513,4);
        EXPECT(!s540GlobalRmHostAllocate(0));
        const auto before=read();EXPECT(before.allocationFirstOriginal==0);
        initializeHost();EXPECT(s540GlobalRmHostShutdown());initializeHost();
        const auto after=read();EXPECT(std::memcmp(&before,&after,sizeof(before))==0);
        EXPECT(s540GlobalRmHostShutdown());
    } else if(scenario==11) {
        hostAllocationObservation.producerFirstState=1;
        hostAllocationObservation.producerFirstId=0xaaaaU;hostAllocationObservation.producerFirstService=0xbbbbU;
        hostAllocationObservation.allocationFirstState=1;
        hostAllocationObservation.allocationFirstStage=0xccccU;hostAllocationObservation.allocationFirstStatus=0xddddU;
        hostAllocationObservation.allocationFirstOriginal=0xeeeeU;hostAllocationObservation.allocationFirstBytes=~NvU64(0);
        std::thread writer([] {s540GlobalRmRecordUnavailableProducer(77,5);observeHostAllocation(NV_ERR_NO_MEMORY,5,123,true);});
        for(NvU32 i=0;i<100;++i) {
            const auto pending=read();EXPECT(pending.observedMask==3);
            EXPECT(pending.producerFirstState==1 && !pending.producerFirstId && !pending.producerFirstService);
            EXPECT(pending.allocationFirstState==1 && !pending.allocationFirstStage && !pending.allocationFirstStatus);
            EXPECT(!pending.allocationFirstBytes && !pending.allocationFirstOriginal);
        }
        writer.join();
        hostAllocationObservation.producerFirstId=5;hostAllocationObservation.producerFirstService=77;
        hostAllocationObservation.allocationFirstStage=5;hostAllocationObservation.allocationFirstStatus=NV_ERR_NO_MEMORY;
        hostAllocationObservation.allocationFirstOriginal=1;hostAllocationObservation.allocationFirstBytes=123;
        __atomic_store_n(&hostAllocationObservation.producerFirstState,2U,__ATOMIC_RELEASE);
        __atomic_store_n(&hostAllocationObservation.allocationFirstState,2U,__ATOMIC_RELEASE);
        const auto published=read();EXPECT(published.observedMask==15);
        EXPECT(published.producerFirstId==5 && published.producerFirstService==77);
        EXPECT(published.allocationFirstStage==5 && published.allocationFirstStatus==NV_ERR_NO_MEMORY);
        EXPECT(published.allocationFirstBytes==123 && published.allocationFirstOriginal==1);
    } else if(scenario==12) {
        hostAllocationObservation.producerTotal=~0U-1U;
        hostAllocationObservation.producerCalls[5]=~0U-1U;
        hostAllocationObservation.allocationFailures=~0U-1U;
        s540GlobalRmRecordUnavailableProducer(18,5);s540GlobalRmRecordUnavailableProducer(99,5);
        observeHostAllocation(NV_ERR_TIMEOUT,9,0xfedcba9876543210ULL,false);
        observeHostAllocation(NV_ERR_NO_MEMORY,10,4096,true);
        /* Private helper range controls, not claims about production branches. */
        observeHostAllocation(NV_ERR_INVALID_ARGUMENT,0,9,true);
        observeHostAllocation(NV_ERR_INVALID_ARGUMENT,32,9,true);
        const auto out=read();
        EXPECT(out.producerCallsLifetime==~0U && out.producerCalls[5]==~0U);
        EXPECT(out.allocationFailuresLifetime==~0U && out.producerFirstService==18 && out.producerFirstId==5);
        EXPECT(out.allocationFirstStage==9 && out.allocationFirstStatus==NV_ERR_TIMEOUT);
        EXPECT(out.allocationFirstBytes==0xfedcba9876543210ULL && !out.allocationFirstOriginal);
        EXPECT(out.allocationStagesMask==0x300U && out.producerMask==32U);
    } else if(scenario==13) {
        std::atomic<NvU32> ready{0};std::atomic<bool> go{false};
        std::vector<std::thread> writers;
        for(NvU32 n=0;n<8;++n)writers.emplace_back([n,&ready,&go]{
            ready.fetch_add(1,std::memory_order_release);
            while(!go.load(std::memory_order_acquire))std::this_thread::yield();
            for(NvU32 i=0;i<1000;++i) {
                s540GlobalRmRecordUnavailableProducer(501+n,1+n);
                observeHostAllocation(NV_ERR_NO_MEMORY,1+n,4096+n,true);
            }
        });
        while(ready.load(std::memory_order_acquire)!=8)std::this_thread::yield();
        go.store(true,std::memory_order_release);
        for(NvU32 sample=0;sample<100;++sample) {
            const auto out=read();
            EXPECT(out.producerCallsLifetime<=8000 && out.allocationFailuresLifetime<=8000);
            EXPECT((out.producerMask&~0x1feU)==0 && (out.allocationStagesMask&~0xffU)==0);
            EXPECT(!(out.observedMask&S540_HOST_ALLOCATION_DIAG_PRODUCER_FIRST) ||
                (out.producerFirstId>=1 && out.producerFirstId<=8 && out.producerFirstService==500+out.producerFirstId));
            EXPECT(!(out.observedMask&S540_HOST_ALLOCATION_DIAG_ALLOCATION_FIRST) ||
                (out.allocationFirstStage>=1 && out.allocationFirstStage<=8));
            EXPECT(!(out.observedMask&S540_HOST_ALLOCATION_DIAG_ALLOCATION_FIRST) ||
                (out.allocationFirstStatus==NV_ERR_NO_MEMORY && out.allocationFirstBytes==4095+out.allocationFirstStage));
            EXPECT(!(out.observedMask&S540_HOST_ALLOCATION_DIAG_ALLOCATION_FIRST) || out.allocationFirstOriginal==1);
            std::this_thread::yield();
        }
        for(auto &writer:writers)writer.join();
        const auto out=read();EXPECT(out.producerCallsLifetime==8000 && out.allocationFailuresLifetime==8000);
        EXPECT(out.producerMask==0x1feU && out.allocationStagesMask==0xffU && out.observedMask==15);
        for(NvU32 p=1;p<=8;++p)EXPECT(out.producerCalls[p]==1000);
        EXPECT(!out.producerCalls[0] && counters.unavailableCalls==8000 && fixture::refusalCalls.load()==16000);
        EXPECT(!fixture::aggregateOrderingFailures.load() && !fixture::allocationRefusals.load());
    } else if(scenario>=14 && scenario<=23)allocationScenario(static_cast<NvU32>(scenario-13));
    else return 2;
    std::printf("{\"cases\":1,\"scenario\":%d,\"checks\":%u,\"failures\":%u}\n",scenario,fixture::checks,fixture::failures);
    return fixture::failures?1:0;
}
