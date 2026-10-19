/* SPDX-License-Identifier: MIT; real refusal producers before inner free. */
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaGlobalRm.h"
#include "S540NvidiaGlobalCrypto.h"
#include "nv_unsupported_memory.h"
#include <cstdio>
#include <cstring>
int main(int argc,char **argv) {
    NvU32 checks=0,failures=0;
#define EXPECT(v) do {++checks;if(!(v)){++failures;std::fprintf(stderr,"Refusal producer line %d\n",__LINE__);}}while(0)
    if(argc!=2 && argc!=3)return 2;
    const bool prebind=argc==3;
    int owner,nv;
    S540NvidiaGlobalRmPlatformFacts facts{};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;
    facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;facts.osVersion=facts.osDate="refusal-producer-fixture";
    EXPECT(s540GlobalRmHostInitialize(&facts)==NV_OK);
    EXPECT(s540FirstTxnBeginOwner(&owner)==NV_OK);
    auto *p=static_cast<unsigned char*>(s540GlobalRmHostAllocateOriginal(13));
    EXPECT(p!=nullptr);std::memset(p,0x4c,13);
    S540GspCancellationToken token=0;
    if(!prebind) EXPECT(s540GspCancellationBind(&nv,&token)==NV_OK && s540GspCancellationBegin(token)==NV_OK && s540FirstTxnBind(&nv,token)==NV_OK);
    auto status=[&]() -> NV_STATUS {
        if(prebind){S540FirstTxnHostIdentity identity{};return s540FirstTxnHostCaptureAllocation(&identity);}
        S540FirstTxnSnapshot value{};return s540FirstTxnGetSnapshot(&nv,&value)==NV_OK ? value.firstStatus : NV_ERR_INVALID_STATE;
    };
    EXPECT(status()==NV_OK);
    NvU64 address=0x1234,bytes=0x5678;NvS32 node=9;
    EXPECT(s540Global_nv_get_egm_info(nullptr,&address,&bytes,&node)==NV_ERR_NOT_SUPPORTED && address==0x1234 && bytes==0x5678 && node==9);
    s540Global_nv_free_user_mapping(nullptr,nullptr,0,nullptr);
    EXPECT(status()==NV_OK);
    NV_STATUS wanted=NV_ERR_NOT_SUPPORTED;
    if(std::strcmp(argv[1],"host")==0)s540GlobalRmRecordUnavailable(63);
    else if(std::strcmp(argv[1],"crypto")==0)s540Global_libspdm_aead_free(nullptr);
    else if(std::strcmp(argv[1],"memory")==0) {
        void *out=reinterpret_cast<void*>(0x1234);
        EXPECT(s540Global_nv_alloc_user_mapping(nullptr,nullptr,0,0,0,0,&address,&out)==NV_ERR_NOT_SUPPORTED &&
               address==0x1234 && out==reinterpret_cast<void*>(0x1234));
    } else if(std::strcmp(argv[1],"invalid")==0) {s540GlobalRmHostFree(p);wanted=NV_ERR_INVALID_ARGUMENT;}
    else return 2;
    S540FirstTxnSnapshot refused{};
    EXPECT(status()==wanted);
    // Deliberately before any WorkOriginalReturned/DirectOriginalReturned note.
    s540GlobalRmHostFreeOriginal(p);
    S540GlobalRmHostAllocationSnapshot retained{};
    EXPECT(s540GlobalRmHostRetentionInspect(p,&retained)==NV_OK && retained.retired);
    EXPECT(p[0]==0x4c && p[12]==0x4c);
    S540NvidiaGlobalRmHostSnapshot heap{};s540GlobalRmHostSnapshot(&heap);
    EXPECT(heap.originalLiveAllocations==1 && heap.originalLiveBytes==13 && !s540GlobalRmHostShutdown());
    EXPECT(status()==wanted && (prebind || (s540FirstTxnGetSnapshot(&nv,&refused)==NV_OK && !refused.inFlightFreePermits)));
    std::printf("{\"format\":1,\"component\":\"actual-refusal-producer\",\"producer\":\"%s\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"actual_strong_record\":true,\"pre_nv_bind\":%s,\"before_outer_return_note\":true,\"disabled_query_did_not_fail\":true,\"official_noop_did_not_fail\":true,"
        "\"retained_bytes\":13,\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n",argv[1],failures?"failed":"passed",checks,failures,prebind?"true":"false");
    return failures?1:0;
}
