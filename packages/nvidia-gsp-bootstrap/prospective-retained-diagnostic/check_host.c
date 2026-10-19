/* Actual retained Host + strong record; original callback/token metadata are
 * the explicitly labelled parent test fixtures, never runtime authorization. */
#define main s540RetainedParentUnusedMain
#include "parent-controls.inc"
#undef main

static void diagnosticCase(unsigned selected)
{
    setup();
    S540NvidiaGlobalRmHostSnapshot before={0}, after={0};
    S540GlobalRmHostRetentionSnapshot retained={0};
    S540GlobalRmHostAllocationSnapshot allocation={0};
    s540GlobalRmHostSnapshot(&before);
    NvU8 *p=s540GlobalRmHostAllocateOriginal(64);
    require(p!=NULL);
    for(unsigned i=0;i<64;++i)p[i]=(NvU8)(i^0xa5U);
    if(selected==2){
        NvU8 output[4]={0x5a,0x5a,0x5a,0x5a};
        expect(!s540Global_libspdm_random_bytes(output,4) && output[0]==0x5a,
               "actual unavailable crypto operation preserves output and publishes first failure");
    }
    s540GlobalRmHostFreeOriginal(p);
    s540GlobalRmHostSnapshot(&after);
    s540GlobalRmHostRetentionSnapshot(&retained);
    expect(s540GlobalRmHostRetentionInspect(p,&allocation)==NV_OK && allocation.retired &&
           allocation.bytes==64 && !allocation.pendingFree,
           "logical free retains exact real backing and immutable allocation record");
    NvBool readable=NV_TRUE;
    for(unsigned i=0;i<64;++i)if(p[i]!=(NvU8)(i^0xa5U))readable=NV_FALSE;
    expect(readable && after.originalLiveBytes==before.originalLiveBytes+64 &&
           after.frees==before.frees,
           "retained memory remains readable and no physical free is counted");
    if(selected!=2){
        expect(retained.diagnosticRetiredAllocations==1 && retained.diagnosticRetiredBytes==64 &&
               !retained.acquireFailures && !retained.firstStatus && !after.unavailableCalls,
               "planned retention is separate from a service failure");
        expect(snapshot().firstStatus==NV_OK && snapshot().phase==S540_FIRST_OP,
               "diagnostic pinning never invents or clears a transaction error");
    }else{
        expect(!retained.diagnosticRetiredAllocations && retained.acquireFailures==1 &&
               retained.firstStatus && snapshot().firstStatus,
               "actual earlier refusal keeps its original sticky failure and ordinary retention accounting");
    }
    expect(!s540GlobalRmHostShutdown(),
           "real Host shutdown refuses while diagnostic backing and participants remain owned");
    if(selected==3){
        s540GlobalRmHostFreeOriginal(p);s540GlobalRmHostSnapshot(&after);
        expect(after.invalidFrees==before.invalidFrees+1 && p[0]==0xa5U,
               "a second logical free is rejected without releasing or reusing backing");
    }
}

static void diagnosticCallbackCase(unsigned selected)
{
    setup();mode=selected==6?6:0;holdWork=selected==6?0:1;
    pendingWork=newWork();
    if(selected==6){
        diagnosticDirectPointer=s540GlobalRmHostAllocateOriginal(64);require(diagnosticDirectPointer!=NULL);
        nv_start_nano_timer(&nv,handle,0);require(waitFor(&workCalls));waitDirectReturn();
    }else{
        require(s540Darwin_os_queue_work_item(deviceQueue,pendingWork)==NV_OK);require(waitFor(&arrived));
        if(selected==5){
            NvU8 output[1]={0x5a};require(!s540Global_libspdm_random_bytes(output,1));
        }
        __atomic_store_n(&released,1U,__ATOMIC_RELEASE);
        if(selected==7)s540GlobalRmHostFreeOriginal(pendingWork);
    }
    require(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)==NV_OK);
    S540GlobalRmHostRetentionSnapshot retained={0};S540NvidiaGlobalRmHostSnapshot heap={0};
    S540GlobalRmHostAllocationSnapshot allocation={0};S540FirstTxnSnapshot tx=snapshot();
    s540GlobalRmHostRetentionSnapshot(&retained);s540GlobalRmHostSnapshot(&heap);
    expect(s540GlobalRmHostRetentionInspect(pendingWork,&allocation)==NV_OK && allocation.retired &&
           pendingWork->parameter==event && !heap.frees,
           "actual worker's logical free keeps its backing after genuine action return");
    expect(tx.workOriginalReturned==1 && tx.workActionReturned==1 && !tx.liveWork,
           "retaining backing does not invent a still-running original callback");
    if(selected==4 || selected==6){
        expect(!tx.firstStatus && !heap.unavailableCalls &&
               retained.diagnosticRetiredAllocations==(selected==6?3U:1U),
               "real worker/direct authorization admits planned pinning without a fabricated refusal");
        if(selected==6)expect(tx.directOriginalReturned==1 && tx.directActionReturned==1 &&
                            !tx.liveDirect && retained.diagnosticRetiredBytes==64+sizeof(*pendingWork)+sizeof(nvidia_stack_t)+15U,
                            "real direct callback, its genuine temporary stack and queued descendant retain their actual allocations");
    }else if(selected==5){
        expect(tx.firstStatus && !retained.diagnosticRetiredAllocations && retained.acquireFailures==1,
               "a real refusal while worker runs is preserved before its actual free");
    }else{
        expect(heap.invalidFrees==1 && retained.retiredAllocations==1 && tx.firstStatus,
               "concurrent master/worker logical frees retire once and reject the duplicate");
    }
}

int main(void)
{
    unsigned total=0;
    for(unsigned selected=1;selected<=7;++selected){
        int pipefd[2];require(pipe(pipefd)==0);pid_t child=fork();require(child>=0);
        if(!child){close(pipefd[0]);checks=failures=0;
            if(selected<=3)diagnosticCase(selected);else diagnosticCallbackCase(selected);
            unsigned result[2]={checks,failures};require(write(pipefd[1],result,sizeof(result))==sizeof(result));
            close(pipefd[1]);_Exit(failures?1:0);}
        close(pipefd[1]);unsigned result[2]={0};require(read(pipefd[0],result,sizeof(result))==sizeof(result));
        close(pipefd[0]);int status=0;require(waitpid(child,&status,0)==child);
        total+=result[0];failures+=result[1];
        if(!WIFEXITED(status)||WEXITSTATUS(status))++failures;
    }
    printf("{\"checks\":%u,\"failures\":%u,\"actual_host_backing\":true,"
           "\"actual_strong_record\":true,\"callback_and_original_lock_endpoints\":\"explicit-parent-test-fixtures\","
           "\"hardware_admission\":false}\n",total,failures);
    return failures?1:0;
}
