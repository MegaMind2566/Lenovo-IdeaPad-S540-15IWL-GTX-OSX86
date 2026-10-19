/* SPDX-License-Identifier: MIT; actual Host/record/backend CPU controls. */
#include "S540NvidiaGlobalRmHostRetention.h"
#include "S540NvidiaGlobalRm.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <thread>

namespace {
NvU32 checks=0,failures=0,stageMode=0;
int owner,nv;
NV_STATUS beginResult=NV_OK,foreignResult=NV_OK;
NvBool shutdownDuringFree=NV_TRUE;
NvU32 observedPermits=0,observedPending=0,observedReleased=0;
NvU64 observedLiveBytes=0;
void *replacement=nullptr;
NvBool addressReused=NV_FALSE;
void expect(bool ok,const char *label) {
    ++checks;if(!ok){++failures;std::fprintf(stderr,"Host retention: %s\n",label);}
}
NV_STATUS injectedCompletion=NV_ERR_INVALID_STATE;
void observer(NvU32 stage,const void *pointer,NvU64,const S540FirstTxnHostIdentity *identity,S540FirstTxnHostFreePermit permit) {
    if((stage==0 && stageMode==5) || (stage==4 && stageMode==4)) {
        std::thread other([] { if(stageMode==5) shutdownDuringFree=s540GlobalRmHostShutdown();
                              beginResult=s540FirstTxnBeginOwner(&owner);
                              if(stageMode==4) shutdownDuringFree=s540GlobalRmHostShutdown(); });other.join();
    }
    if(stage==3 && stageMode==3) injectedCompletion=s540FirstTxnHostCompleteFree(identity,permit);
    if(stage==1 && stageMode==1) {
        std::thread other([] { beginResult=s540FirstTxnBeginOwner(&owner);
                              shutdownDuringFree=s540GlobalRmHostShutdown(); });
        other.join();
    }
    if(stage==3 && stageMode==1) {
        replacement=s540GlobalRmHostAllocateOriginal(17);
        addressReused=replacement==pointer;
    }
    if(stage==1 && stageMode==2) {
        // This actual foreign-thread policy violation atomically publishes
        // first refusal while the main thread owns a physical-free permit.
        std::thread other([] { S540FirstTxnHostIdentity id{};
                              foreignResult=s540FirstTxnHostCaptureAllocation(&id); });
        other.join();
        S540FirstTxnSnapshot txn{};
        expect(s540FirstTxnGetSnapshot(&nv,&txn)==NV_OK,"actual transaction snapshot after first refusal");
        observedPermits=txn.inFlightFreePermits;
    }
    if(stage==3 && stageMode==2) {
        S540GlobalRmHostRetentionSnapshot retained{};
        S540NvidiaGlobalRmHostSnapshot host{};
        s540GlobalRmHostRetentionSnapshot(&retained);s540GlobalRmHostSnapshot(&host);
        observedPending=retained.pendingFrees;observedReleased=retained.releasedPendingCompletions;
        observedLiveBytes=host.liveBytes;
        std::thread other([] { shutdownDuringFree=s540GlobalRmHostShutdown(); });other.join();
    }
}
}
int main(int argc,char **argv) {
    S540NvidiaGlobalRmPlatformFacts facts{};facts.format=1;facts.known=S540_GLOBAL_FACT_ALL;
    facts.cpuCount=1;facts.cpuFrequencyHz=2000000000ULL;facts.osMajor=25;
    facts.osVersion=facts.osDate="host-retention-cpu-fixture";
    expect(s540GlobalRmHostInitialize(&facts)==NV_OK,"real Host initialized");
    if(argc>1 && std::strcmp(argv[1],"allocation-race")==0) {
        stageMode=5;S540HostRetentionNative::observePhysicalFree(observer);
        void *unowned=s540GlobalRmHostAllocateOriginal(23);
        S540HostRetentionNative::observePhysicalFree(nullptr);
        expect(beginResult==NV_OK,"concurrent BeginOwner wins before legacy reservation");
        expect(!shutdownDuringFree,"actual call lease prevents guard deletion before first reservation");
        expect(unowned==nullptr,"unbound capture never publishes backing after owner changed");
        S540NvidiaGlobalRmHostSnapshot heap{};s540GlobalRmHostSnapshot(&heap);
        expect(!heap.liveBytes && !heap.liveAllocations && !heap.allocations && heap.allocationFailures==1,
               "recheck rolls back reservation without actual allocation or retagging");
        std::printf("{\"format\":1,\"component\":\"host-allocation-race\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
            "\"actual_host_backend\":true,\"actual_strong_record\":true,\"legacy_backing_published\":false,"
            "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n",failures?"failed":"passed",checks,failures);
        return failures?1:0;
    }
    if(argc>1) {
        expect(s540FirstTxnBeginOwner(&owner)==NV_OK,"completion-fault owner starts cold");
        void *released=s540GlobalRmHostAllocateOriginal(31);
        expect(released!=nullptr,"completion-fault backing actually allocated");
        stageMode=3;S540HostRetentionNative::observePhysicalFree(observer);
        s540GlobalRmHostFreeOriginal(released);
        S540HostRetentionNative::observePhysicalFree(nullptr);
        expect(injectedCompletion==NV_OK,"test consumes actual committed permit after physicalfree");
        S540NvidiaGlobalRmHostSnapshot host{};S540GlobalRmHostRetentionSnapshot completion{};
        s540GlobalRmHostSnapshot(&host);s540GlobalRmHostRetentionSnapshot(&completion);
        expect(host.liveBytes==0 && host.liveAllocations==0 && host.frees==1,"released backing never counted as retained live bytes");
        expect(completion.pendingFrees==1 && completion.releasedPendingCompletions==1 &&
               !completion.retiredAllocations && !completion.retiredBytes && completion.completionFailures==1,
               "completion refusal keeps only zero-byte metadata reservation");
        S540GlobalRmHostAllocationSnapshot noBacking{};
        expect(s540GlobalRmHostRetentionInspect(released,&noBacking)==NV_ERR_OBJECT_NOT_FOUND,"released pointer not discoverable as a live allocation");
        s540GlobalRmHostFreeOriginal(released);s540GlobalRmHostSnapshot(&host);
        expect(host.invalidFrees==1 && host.frees==1,"later old-pointer free cannot repeat std::free");
        expect(!s540GlobalRmHostShutdown(),"pending completion refuses HostShutdown");
        expect(s540GlobalRmHostRetentionPreflight()==NV_ERR_STATE_IN_USE,"pending completion refuses new transaction");
        expect(s540GlobalRmHostAllocateOriginal(31)==nullptr,"actual duplicate-permit refusal is sticky");
        std::printf("{\"format\":1,\"component\":\"host-completion-fault\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
            "\"actual_host_backend\":true,\"actual_strong_record\":true,\"retained_backing_bytes\":0,\"released_pending_completion\":1,"
            "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n",failures?"failed":"passed",checks,failures);
        return failures?1:0;
    }
    stageMode=4;S540HostRetentionNative::observePhysicalFree(observer);
    void *reserved=s540GlobalRmHostAllocateOriginal(13);
    S540HostRetentionNative::observePhysicalFree(nullptr);stageMode=0;
    expect(reserved && beginResult==NV_ERR_STATE_IN_USE && !shutdownDuringFree,
           "actual unowned allocation reservation blocks BeginOwner and HostShutdown");
    s540GlobalRmHostFreeOriginal(reserved);
    auto *old=static_cast<unsigned char*>(s540GlobalRmHostAllocateOriginal(17));
    expect(old!=nullptr,"unassociated original allocation exists");
    S540GlobalRmHostAllocationSnapshot unassociated{};
    expect(s540GlobalRmHostRetentionInspect(old,&unassociated)==NV_OK && !unassociated.identity.owner && !unassociated.identity.generation,
           "unbound allocation remains explicitly unassociated");
    expect(s540FirstTxnBeginOwner(&owner)==NV_ERR_STATE_IN_USE,"real preflight rejects old original bytes");
    stageMode=1;S540HostRetentionNative::observePhysicalFree(observer);
    s540GlobalRmHostFreeOriginal(old);
    expect(beginResult==NV_ERR_STATE_IN_USE,"concurrent BeginOwner refuses in-flight old original free");
    expect(!shutdownDuringFree,"HostShutdown refuses physical release in flight");
    S540HostRetentionNative::observePhysicalFree(nullptr);stageMode=0;
    S540GlobalRmHostAllocationSnapshot reused{};
    expect(replacement && s540GlobalRmHostRetentionInspect(replacement,&reused)==NV_OK &&
           reused.allocationSerial!=unassociated.allocationSerial && !reused.pendingFree && !reused.retired,
           "new allocation remains distinct even if std::malloc reuses physical address before completion");
    s540GlobalRmHostFreeOriginal(replacement);
    expect(s540GlobalRmHostRetentionPreflight()==NV_OK,"actual original domain is now cold");
    auto *external=static_cast<unsigned char*>(s540GlobalRmHostAllocate(19));
    expect(external!=nullptr,"external owner allocated before transaction");
    std::memset(external,0x73,19);
    expect(s540FirstTxnBeginOwner(&owner)==NV_OK,"actual retained owner starts before original global allocation");
    auto *first=static_cast<unsigned char*>(s540GlobalRmHostAllocateOriginal(64));
    auto *second=static_cast<unsigned char*>(s540GlobalRmHostAllocateOriginal(80));
    expect(first && second,"real original heap allocations before nv attachment");
    std::memset(second,0xA5,80);
    S540GlobalRmHostAllocationSnapshot firstTag{},secondTag{};
    expect(s540GlobalRmHostRetentionInspect(first,&firstTag)==NV_OK && firstTag.identity.owner==&owner && firstTag.identity.generation,
           "immutable real owner/generation captured before Bind");
    expect(s540GlobalRmHostRetentionInspect(second,&secondTag)==NV_OK && secondTag.identity.owner==&owner &&
           secondTag.identity.generation==firstTag.identity.generation && secondTag.allocationSerial>firstTag.allocationSerial,
           "each allocation records independent immutable serial");
    S540GspCancellationToken token=0;
    expect(s540GspCancellationBind(&nv,&token)==NV_OK && s540GspCancellationBegin(token)==NV_OK,"actual cancellation operation bound");
    expect(s540FirstTxnBind(&nv,token)==NV_OK,"exact nv attached once");
    S540GlobalRmHostAllocationSnapshot afterBind{};
    expect(s540GlobalRmHostRetentionInspect(second,&afterBind)==NV_OK &&
           afterBind.identity.owner==secondTag.identity.owner && afterBind.identity.generation==secondTag.identity.generation &&
           afterBind.allocationSerial==secondTag.allocationSerial,"Bind never retags existing owned bytes");
    stageMode=2;S540HostRetentionNative::observePhysicalFree(observer);
    s540GlobalRmHostFreeOriginal(first);
    S540HostRetentionNative::observePhysicalFree(nullptr);stageMode=0;
    expect(foreignResult==NV_ERR_INVALID_STATE,"real foreign-thread refusal published without blocking free");
    expect(observedPermits==1,"pre-refusal physical free permit remains outstanding");
    expect(observedPending==1 && observedReleased==1 && observedLiveBytes==99,
           "released backing and pending completion are separate from actual remaining live bytes");
    expect(!shutdownDuringFree,"HostShutdown refuses until actual record completion");
    S540FirstTxnSnapshot transaction{};
    expect(s540FirstTxnGetSnapshot(&nv,&transaction)==NV_OK && !transaction.inFlightFreePermits &&
           transaction.firstStatus==NV_ERR_INVALID_STATE,"committed permit completes after sticky refusal");
    s540GlobalRmHostFreeOriginal(second);
    s540GlobalRmHostFree(external);
    S540GlobalRmHostAllocationSnapshot retired{};
    expect(s540GlobalRmHostRetentionInspect(second,&retired)==NV_OK && retired.retired &&
           retired.identity.owner==secondTag.identity.owner && retired.identity.generation==secondTag.identity.generation,
           "post-refusal free logically retires exact original allocation");
    expect(second[0]==0xA5 && second[79]==0xA5,"retired original physical bytes remain accessible");
    expect(s540GlobalRmHostRetentionInspect(external,&retired)==NV_OK && retired.retired && !retired.identity.owner && !retired.identity.generation,
           "foreign pre-Bind external bytes retained without invented ownership");
    expect(external[0]==0x73 && external[18]==0x73,"retired external physical bytes remain accessible");
    S540NvidiaGlobalRmHostSnapshot heap{};S540GlobalRmHostRetentionSnapshot retained{};
    s540GlobalRmHostSnapshot(&heap);s540GlobalRmHostRetentionSnapshot(&retained);
    expect(heap.liveAllocations==2 && heap.liveBytes==99 && heap.originalLiveAllocations==1 && heap.originalLiveBytes==80 &&
           heap.externalLiveAllocations==1 && heap.externalLiveBytes==19,"actual held-byte domain counters remain live");
    expect(retained.retiredAllocations==2 && retained.retiredBytes==99 && !retained.pendingFrees && !retained.releasedPendingCompletions,
           "retired backing has no pending or released completion fiction");
    expect(s540GlobalRmHostAllocateOriginal(8)==nullptr,"sticky record refuses later allocation");
    s540GlobalRmHostFreeOriginal(second);
    s540GlobalRmHostSnapshot(&heap);
    expect(heap.invalidFrees==1 && heap.liveBytes==99,"duplicate retired free cannot release or reuse backing");
    expect(!s540GlobalRmHostShutdown() && s540GlobalRmHostRetentionPreflight()==NV_ERR_STATE_IN_USE,
           "retained heap prevents HostShutdown and new transaction preflight");
    expect(s540GlobalRmHostInitialize(&facts)==NV_ERR_STATE_IN_USE,"retained heap refuses reinitialization");
    std::printf("{\"format\":1,\"component\":\"host-heap-retention\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,"
        "\"retained_bytes\":99,\"actual_address_reused\":%s,\"actual_host_backend\":true,\"actual_strong_record\":true,"
        "\"pre_bind_retagging\":false,\"committed_free_completed_after_refusal\":true,"
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"original_entry_admission\":false}\n",
        failures?"failed":"passed",checks,failures,addressReused?"true":"false");
    return failures?1:0;
}
