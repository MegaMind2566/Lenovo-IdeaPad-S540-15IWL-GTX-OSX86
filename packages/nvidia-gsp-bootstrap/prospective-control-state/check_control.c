/* SPDX-License-Identifier: MIT */
/* Actual strong record, Host and Darwin sync; parent original metadata and
 * callback/token readers remain explicitly CPU-only fixtures. */
#define main s540ControlParentUnusedMain
#include "parent-controls.inc"
#undef main
#include "S540NvidiaControlState.h"
#include "control-original-bodies.inc"
#include <limits.h>

static unsigned fatalExpected;
void NV_API_CALL os_bug_check(NvU32 code, const char *reason)
{
    (void)code;
    S540FirstTxnSnapshot observed = snapshot();
    S540NvidiaGlobalRmHostSnapshot heap = {0};
    s540GlobalRmHostSnapshot(&heap);
    _Exit(fatalExpected && reason && observed.firstStatus && heap.unavailableCalls ? 73 : 74);
}
static void beginControlOwner(void)
{
    S540NvidiaGlobalRmPlatformFacts facts = {0};
    facts.format=1; facts.known=S540_GLOBAL_FACT_ALL; facts.cpuCount=1;
    facts.cpuFrequencyHz=2000000000ULL; facts.osMajor=25;
    facts.osVersion=facts.osDate="control-state-explicit-platform-fixture";
    require(s540GlobalRmHostInitialize(&facts)==NV_OK);
    require(s540Darwin_os_get_current_thread(&masterThread)==NV_OK && masterThread);
    require(s540FirstTxnBeginOwner(&retainedOwner)==NV_OK);
}
static void bindControlAdapter(void)
{
    require(s540GspCancellationBind(&nv,&cancelToken)==NV_OK);
    require(s540GspCancellationBegin(cancelToken)==NV_OK);
    require(s540FirstTxnBind(&nv,cancelToken)==NV_OK);
    nv.pci_info.vendor_id=0x10de; nv.pci_info.device_id=0x1f91;
    nv.subsystem_vendor=0x17aa; nv.subsystem_id=0x3806;
}
static void controlCase(unsigned selected)
{
    if (selected==1) {
        expect(s540ControlStatePrepare()==NV_ERR_INVALID_STATE,
               "an actual retained owner must exist before publishing the control state");
    }
    beginControlOwner();
    expect(s540ControlStatePrepare()==NV_OK,
           "real original spinlock initialization works before global portInitialize");
    nv_state_t *ctl=nv_get_ctl_state();
    expect(ctl && ctl!=&nv && ctl->event_spinlock && !ctl->event_list && NV_IS_CTL_DEVICE(ctl),
           "permanent control identity owns an actual initialized lock and empty event list");
    expect(s540ControlStatePrepare()==NV_ERR_IN_USE && nv_get_ctl_state()==ctl,
           "second preparation cannot reinitialize or replace the published lock/state");
    bindControlAdapter();
    expect(s540ControlStateBindAdapter((void *)(NvUPtr)1)==NV_ERR_INVALID_ARGUMENT,
           "exact record identity is checked before dereferencing a foreign adapter pointer");
    if (selected==2) {
        nv.primary_vga=NV_TRUE;
        expect(s540ControlStateBindAdapter(&nv)==NV_ERR_NOT_SUPPORTED,
               "primary VGA cannot acquire the selected nonconsole device ordinal");
        nv.primary_vga=NV_FALSE;
    }
    require(s540ControlStateBindAdapter(&nv)==NV_OK);
    expect(s540ControlStateBindAdapter(&nv)==NV_ERR_IN_USE &&
           nv_get_dev_minor(&nv)==0 && nv_get_dev_minor(ctl)==NV_MINOR_DEVICE_NUMBER_CONTROL_DEVICE,
           "the sole exact adapter and control identities have immutable distinct ordinals");
    const NvS32 descriptors[]={-1,0,1,INT_MAX,INT_MIN};
    for(unsigned i=0;i<sizeof(descriptors)/sizeof(descriptors[0]);++i){
        void *privateHandle=(void *)(NvUPtr)0x55;
        expect(!nv_get_file_private(descriptors[i],NV_TRUE,&privateHandle) && privateHandle==(void *)(NvUPtr)0x55,
               "failed lookup preserves output and cannot turn a Darwin descriptor into an NVIDIA file reference");
    }
    NvP64 eventOutput=NV_PTR_TO_NvP64((void *)(NvUPtr)0x1234);
    expect(control_osUserHandleToKernelPtr(1,NV_PTR_TO_NvP64((void *)(NvUPtr)5),&eventOutput)==NV_ERR_OBJECT_NOT_FOUND &&
           eventOutput==NV_PTR_TO_NvP64((void *)(NvUPtr)0x1234),
           "complete original handle lookup takes the real lock, finds no event and preserves output");
    if(selected==3){
        NvU8 byte=0x55;
        require(!s540Global_libspdm_random_bytes(&byte,1));
        const NvU32 earlier=snapshot().firstStatus;
        expect(nv_get_ctl_state()==ctl &&
               control_osUserHandleToKernelPtr(1,0,&eventOutput)==NV_ERR_OBJECT_NOT_FOUND &&
               snapshot().firstStatus==earlier,
               "permanent control lifetime and empty lookup survive a real earlier refusal without clearing it");
    }
    if(selected==4 || selected==5){
        fatalExpected=1;
        if(selected==4)nv_put_file_private(NULL);
        else nv_post_event(NULL,0,0,0,0,NV_FALSE);
        _Exit(75);
    }
    expect(!s540GlobalRmHostShutdown(),
           "actual transaction retention prevents owner shutdown while the control lock remains live");
}
static void acceptedCallbackCannotPublish(void)
{
    setup();mode=8;pendingWork=newWork();
    require(s540Darwin_os_queue_work_item(deviceQueue,pendingWork)==NV_OK);
    require(s540Darwin_os_flush_work_queue(deviceQueue,NV_FALSE)==NV_OK);
    expect(callbackControlStatus==NV_ERR_INVALID_STATE && snapshot().workActionReturned==1,
           "a real accepted work callback cannot publish the master's control state");
    expect(!snapshot().firstStatus && s540ControlStatePrepare()==NV_OK,
           "the refused callback cannot reserve initialization or poison the actual master's later publication");
    expect(nv_get_ctl_state()->event_spinlock!=NULL,
           "only actual master publication supplies the permanent original event lock");
}
int main(void)
{
    unsigned total=0;
    for(unsigned selected=1;selected<=6;++selected){
        int pipefd[2];require(pipe(pipefd)==0);pid_t child=fork();require(child>=0);
        if(!child){close(pipefd[0]);checks=failures=0;
            if(selected==6)acceptedCallbackCannotPublish();else controlCase(selected);
            unsigned result[2]={checks,failures};require(write(pipefd[1],result,sizeof(result))==sizeof(result));
            close(pipefd[1]);_Exit(failures?1:0);}
        close(pipefd[1]);unsigned result[2]={0};ssize_t got=read(pipefd[0],result,sizeof(result));
        close(pipefd[0]);int status=0;require(waitpid(child,&status,0)==child);
        if(selected==4 || selected==5){++total;if(got || !WIFEXITED(status) || WEXITSTATUS(status)!=73)++failures;}
        else {require(got==sizeof(result));total+=result[0];failures+=result[1];
            if(!WIFEXITED(status)||WEXITSTATUS(status))++failures;}
    }
    printf("{\"checks\":%u,\"failures\":%u,\"component\":\"permanent-control-empty-file-table\","
           "\"actual_strong_record\":true,\"actual_host_and_sync\":true,"
           "\"fatal_diagnostic_handler\":\"explicit-process-exit-fixture\",\"hardware_admission\":false}\n",total,failures);
    return failures?1:0;
}
