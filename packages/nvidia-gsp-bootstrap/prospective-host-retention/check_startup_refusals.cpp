/* SPDX-License-Identifier: MIT; real startup/refusal source interleavings. */
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalCrypto.h"
#include "nv_unsupported_memory.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <thread>
namespace {
NvU32 checks=0, failures=0;
NV_STATUS reservingCapture=NV_OK;
int owner;
void expect(bool value, const char *label) {
    ++checks;if(!value){++failures;std::fprintf(stderr,"Startup refusal: %s\n",label);}
}
void observer(NvU32 stage,const void *,NvU64,const S540FirstTxnHostIdentity *,S540FirstTxnHostFreePermit) {
    if(stage!=6)return;
    std::thread producer([] {
        S540FirstTxnHostIdentity identity{};
        reservingCapture=s540FirstTxnHostCaptureAllocation(&identity);
        s540GlobalRmRecordUnavailable(63);
    });producer.join();
}
void refuse(const char *domain) {
    if(std::strcmp(domain,"crypto")==0)s540Global_libspdm_aead_free(nullptr);
    else if(std::strcmp(domain,"memory")==0) {
        NvU64 address=0x1234;void *output=reinterpret_cast<void*>(0x5678);
        expect(s540Global_nv_alloc_user_mapping(nullptr,nullptr,0,0,0,0,&address,&output)==NV_ERR_NOT_SUPPORTED &&
            address==0x1234 && output==reinterpret_cast<void*>(0x5678),"actual memory refusal preserves outputs");
    } else if(std::strcmp(domain,"invalid")==0)s540GlobalRmHostFreeOriginal(reinterpret_cast<void*>(0x1234));
    else s540GlobalRmRecordUnavailable(63);
}
}
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    S540NvidiaGlobalRmPlatformFacts facts{};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;
    facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;
    facts.osVersion=facts.osDate="startup-race-cpu-fixture";
    if(std::strcmp(argv[1],"lifetime")==0) {
        std::atomic<bool> stop{false};std::atomic<NvU32> readerCalls{0};
        std::thread readers([&] {
            while(!stop.load(std::memory_order_acquire)) {
                S540NvidiaGlobalRmHostSnapshot host{};S540GlobalRmHostRetentionSnapshot retained{};
                S540GlobalRmHostAllocationSnapshot allocation{};
                s540GlobalRmHostSnapshot(&host);s540GlobalRmHostRetentionSnapshot(&retained);
                (void)s540GlobalRmHostRetentionInspect(reinterpret_cast<void*>(0x1234),&allocation);
                // The borrowed pointer is deliberately not dereferenced beyond
                // its call lease. A real original consumer needs outer retention.
                (void)s540GlobalRmPlatformFacts();
                S540NvidiaGlobalRmNative::failAllocationAt(0);
                s540GlobalRmRecordService(1);s540GlobalRmRecordServiceName("lifetime-fixture-static");
                (void)s540GlobalRmObservedServices();(void)s540GlobalRmServiceName(0);
                (void)s540GlobalRmServiceCalls(0);(void)s540GlobalRmServiceMask();
                readerCalls.fetch_add(1,std::memory_order_release);
            }
        });
        constexpr NvU32 producerCalls=10000;
        std::thread producer([] {for(NvU32 i=0;i!=producerCalls;++i)s540GlobalRmRecordUnavailable(63);});
        NvU32 opened=0,closed=0;
        for(NvU32 i=0;i!=2000;++i) {
            if(s540GlobalRmHostInitialize(&facts)==NV_OK)++opened;
            if(s540GlobalRmHostShutdown())++closed;
        }
        producer.join();stop.store(true,std::memory_order_release);readers.join();
        expect(readerCalls.load(std::memory_order_acquire)>0,"concurrent dynamic-guard readers actually ran");
        expect(opened>0 && closed>0,"real Host open and close transitions actually ran");
        expect(s540GlobalRmHostShutdown(),"all call leases leave real Host closeable");
        S540NvidiaGlobalRmHostSnapshot final{};s540GlobalRmHostSnapshot(&final);
        expect(final.unavailableCalls==producerCalls,"producer stream cannot be lost by concurrent initialize reset");
        expect(!final.initialized && !final.liveAllocations && !final.liveBytes,"closed snapshot reads no destroyed guard");
        expect(s540GlobalRmHostInitialize(&facts)==NV_OK,"guard can reopen after actual concurrent readers finish");
        expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_STATE_IN_USE,"persistent true refusal history prevents transaction admission");
        expect(s540GlobalRmHostShutdown(),"no physical backing was allocated by lifetime stress");
        std::printf("{\"format\":1,\"component\":\"host-lifetime-concurrency\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
            "\"reader_calls\":%u,\"opened\":%u,\"closed\":%u,\"producer_calls\":%u,\"actual_host_backend\":true,\"kernel_execution\":\"not_tested\"}\n",
            failures?"failed":"passed",checks,failures,readerCalls.load(),opened,closed,producerCalls);
        return failures?1:0;
    }
    const bool initialize=std::strcmp(argv[1],"initialize")==0;
    if(initialize)refuse("host");
    expect(s540GlobalRmHostInitialize(&facts)==NV_OK,"real Host initialization");
    if(std::strcmp(argv[1],"reserving")==0) {
        S540HostRetentionNative::observePhysicalFree(observer);
        expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_NOT_SUPPORTED,"actual source refusal during RESERVING survives owner publication");
        S540HostRetentionNative::observePhysicalFree(nullptr);
        expect(reservingCapture==NV_ERR_NOT_READY,"RESERVING never admits legacy unbound allocation");
        S540FirstTxnHostIdentity identity{};S540FirstTxnHostFreePermit permit=0;
        expect(s540FirstTxnHostCaptureAllocation(&identity)==NV_ERR_NOT_SUPPORTED,"sticky reservation cannot become healthy operation");
        expect(s540FirstTxnHostAcquireFree(&identity,&permit)!=NV_OK && !permit,"failed startup grants no physical-free permit");
        expect(s540GlobalRmHostAllocateOriginal(8)==nullptr,"failed startup publishes no backing");
    } else {
        if(!initialize)refuse(argv[1]);
        S540NvidiaGlobalRmHostSnapshot before{};s540GlobalRmHostSnapshot(&before);
        expect(s540GlobalRmHostRetentionPreflight()==NV_ERR_STATE_IN_USE,"absolute source-ever preflight rejects historical refusal");
        expect(s540GlobalRmHostShutdown(),"cold Host guard may close without transaction admission");
        expect(s540GlobalRmPlatformFacts()==nullptr,"closed guard exposes no new facts borrow");
        expect(s540GlobalRmHostInitialize(&facts)==NV_OK,"cold guard can reopen");
        S540NvidiaGlobalRmHostSnapshot after{};s540GlobalRmHostSnapshot(&after);
        expect(after.unavailableCalls==before.unavailableCalls && after.invalidFrees==before.invalidFrees,"Host ever counters persist across close and initialize");
        expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_STATE_IN_USE,"actual preflight never accepts erased historical refusal");
    }
    S540NvidiaGlobalRmHostSnapshot heap{};s540GlobalRmHostSnapshot(&heap);
    expect(!heap.liveBytes && !heap.liveAllocations && !heap.allocations && !heap.frees,"startup controls allocate and free no physical backing");
    std::printf("{\"format\":1,\"component\":\"host-startup-refusal\",\"scenario\":\"%s\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"actual_host_backend\":true,\"actual_strong_record\":true,\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"original_entry_admission\":false}\n",
        argv[1],failures?"failed":"passed",checks,failures);
    return failures?1:0;
}
