/* SPDX-License-Identifier: MIT; actual first-attempt allocation failure policy. */
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaGlobalRm.h"
#include <cstdio>
#include <cstring>
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    NvU32 checks=0,failures=0;
#define EXPECT(v) do{++checks;if(!(v)){++failures;std::fprintf(stderr,"Allocation failure line %d\n",__LINE__);}}while(0)
    S540NvidiaGlobalRmPlatformFacts facts{};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;
    facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;facts.osVersion=facts.osDate="allocation-failure-fixture";
    EXPECT(s540GlobalRmHostInitialize(&facts)==NV_OK);
    int owner;
    if(std::strcmp(argv[1],"retry")==0) {
        S540NvidiaGlobalRmNative::failAllocationAt(1);
        EXPECT(s540GlobalRmHostAllocateOriginal(13)==nullptr);
        auto *p=s540GlobalRmHostAllocateOriginal(13);EXPECT(p!=nullptr);
        s540GlobalRmHostFreeOriginal(p);
        S540NvidiaGlobalRmHostSnapshot host{};s540GlobalRmHostSnapshot(&host);
        EXPECT(host.allocations==1 && host.frees==1 && !host.liveBytes && !host.unavailableCalls && !host.invalidFrees);
        EXPECT(s540GlobalRmHostRetentionPreflight()==NV_OK);
        EXPECT(s540GlobalRmHostShutdown());
    } else {
        EXPECT(s540FirstTxnBeginOwner(&owner)==NV_OK);
        auto *p=static_cast<unsigned char*>(s540GlobalRmHostAllocateOriginal(13));EXPECT(p!=nullptr);
        std::memset(p,0xa6,13);
        NV_STATUS wanted=NV_ERR_NO_MEMORY;
        if(std::strcmp(argv[1],"fault")==0) {
            S540NvidiaGlobalRmNative::failAllocationAt(2);
            EXPECT(s540GlobalRmHostAllocateOriginal(17)==nullptr);
        } else if(std::strcmp(argv[1],"cap")==0)EXPECT(s540GlobalRmHostAllocateOriginal(256ULL*1024*1024+1)==nullptr);
        else if(std::strcmp(argv[1],"zero")==0){wanted=NV_ERR_INVALID_STATE;EXPECT(s540GlobalRmHostAllocateOriginal(0)==nullptr);}
        else return 2;
        S540FirstTxnHostIdentity identity{};
        EXPECT(s540FirstTxnHostCaptureAllocation(&identity)==wanted);
        S540NvidiaGlobalRmHostSnapshot host{};s540GlobalRmHostSnapshot(&host);
        EXPECT(!host.unavailableCalls && !host.invalidFrees);
        // Immediate original inner cleanup, before an outer return/status note.
        s540GlobalRmHostFreeOriginal(p);
        S540GlobalRmHostAllocationSnapshot allocation{};
        EXPECT(s540GlobalRmHostRetentionInspect(p,&allocation)==NV_OK && allocation.retired &&
            allocation.identity.owner==&owner && allocation.identity.generation);
        EXPECT(p[0]==0xa6 && p[12]==0xa6);
        s540GlobalRmHostSnapshot(&host);
        EXPECT(host.liveBytes==13 && host.liveAllocations==1 && host.frees==0);
        EXPECT(s540FirstTxnHostCaptureAllocation(&identity)==wanted);
        EXPECT(!s540GlobalRmHostShutdown());
    }
    std::printf("{\"format\":1,\"component\":\"host-first-attempt-allocation-failure\",\"scenario\":\"%s\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"actual_host_backend\":true,\"actual_strong_record\":true,\"kernel_execution\":\"not_tested\",\"before_outer_return_note\":true,\"original_entry_admission\":false}\n",
        argv[1],failures?"failed":"passed",checks,failures);
    return failures?1:0;
}
