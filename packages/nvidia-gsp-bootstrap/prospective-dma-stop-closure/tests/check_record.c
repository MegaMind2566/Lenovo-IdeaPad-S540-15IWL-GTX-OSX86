/* SPDX-License-Identifier: MIT
 * Actual strong record + actual PM cancellation bodies. Original endpoint,
 * clock/thread, service metadata and backend observations are explicit CPU
 * fixtures. Positive record state is established only by its public APIs. */
#include "S540NvidiaDmaProducer.h"
#include "S540NvidiaIrqClosure.h"
#include "S540NvidiaDarwinServices.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static NvU64 tid=1, now=100;
static NvBool ordinary=NV_TRUE;
static NvU32 checks, failures, serviceStage, irqMode;
static int nv, owner, queue, item, backend;
static S540GspCancellationToken token;
static NvU64 generation, irqGeneration;
static S540FirstTxnLease workLease;
static void expect(NvBool value,const char *why) {
    ++checks; if(!value){++failures;fprintf(stderr,"record: %s\n",why);}
}
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out){*out=tid;return NV_OK;}
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void){return ordinary;}
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void){return now;}
NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32 ms){(void)ms;return NV_OK;}
NV_STATUS s540GlobalRmHostRetentionPreflight(void){return NV_OK;}
NV_STATUS s540FirstTxnOriginalLocksReleased(const void *state){return state==&nv?NV_OK:NV_ERR_INVALID_STATE;}
const S540FirstTxnOriginalDescriptor s540FirstTxnOriginalDescriptors[]={
    {S540_FIRST_DESC_WORK,S540_FIRST_ESSENTIAL_RUN_OR_RETAIN,0,0,0x1234,0,NV_FALSE}};
const NvU32 s540FirstTxnOriginalDescriptorCount=1;
NV_STATUS s540FirstTxnInspectOriginalWork(const void *data,S540FirstTxnOriginalWork *out){
    if(data!=&item)return NV_ERR_INVALID_ARGUMENT;
    memset(out,0,sizeof(*out));out->callback=0x1234;return NV_OK;
}
NV_STATUS s540FirstTxnInspectOriginalEvent(const void *data,S540FirstTxnOriginalEvent *out){(void)data;(void)out;return NV_ERR_NOT_SUPPORTED;}
NV_STATUS s540FirstTxnInspectOriginalOwner(const void *data,NvUPtr *out){(void)data;(void)out;return NV_ERR_NOT_SUPPORTED;}
NV_STATUS s540FirstTxnInspectOriginalRc(const void *state,NvUPtr *out){(void)state;(void)out;return NV_ERR_NOT_SUPPORTED;}
NV_STATUS s540FirstTxnServicesReadQueueContext(const void *q,S540FirstTxnServiceContext *out){
    if(q!=&queue)return NV_ERR_INVALID_ARGUMENT;
    memset(out,0,sizeof(*out));out->stage=serviceStage;out->thread=tid;out->generation=generation;
    out->data=serviceStage==S540_FIRST_SERVICE_RETURNED?NULL:&item;return NV_OK;
}
NV_STATUS s540FirstTxnServicesReadTimerContext(const void *q,S540FirstTxnServiceContext *out){(void)q;(void)out;return NV_ERR_NOT_SUPPORTED;}
NV_STATUS s540FirstTxnIrqReadContext(const void *p,NvU32 role,S540FirstTxnIrqContext *out){
    if(p!=&backend)return NV_ERR_INVALID_ARGUMENT;
    memset(out,0,sizeof(*out));out->nv=&nv;out->generation=irqGeneration;
    out->drained=NV_TRUE;out->maskRequired=NV_TRUE;
    if(role){out->stage=role;out->thread=tid;out->origin=role==1?0:2;}
    if(irqMode==1)out->accepting=NV_TRUE;
    if(irqMode==2)out->controllerAttached=NV_TRUE;
    if(irqMode==3)out->callbacks=1;
    if(irqMode==4)out->pending=1;
    return NV_OK;
}
static void setup(NvBool finishOriginal,NvBool globalReady){
    S540FirstTxnGlobalSnapshot view={0};
    expect(s540FirstTxnBeginOwner(&owner)==NV_OK,"real permanent owner");
    expect(s540FirstTxnGlobalEnter()==NV_OK,"real global IN_CORE");
    expect(s540FirstTxnGlobalOriginalReturned(NV_OK)==NV_OK,"real global return");
    expect(s540FirstTxnGlobalValidated(globalReady?NV_OK:NV_ERR_INVALID_DATA)==(globalReady?NV_OK:NV_ERR_INVALID_DATA),"real global validation boundary");
    expect(s540FirstTxnGlobalGetSnapshot(&view)==NV_OK,"real global snapshot");generation=view.generation;
    expect(s540GspCancellationBind(&nv,&token)==NV_OK,"real cancellation binding");
    expect(s540GspCancellationBegin(token)==NV_OK,"real operation phase");
    if(!globalReady)return;
    expect(s540FirstTxnBind(&nv,token)==NV_OK,"real exact nv binding");
    expect(s540FirstTxnOriginalEnter(&nv)==NV_OK,"real original enter");
    if(finishOriginal){
        expect(s540FirstTxnOriginalExitReady(&nv,NV_OK)==NV_OK,"real exit ready");
        expect(s540FirstTxnOriginalWrapperReturned(&nv)==NV_OK,"real outer wrapper return");
    }
}
static void sticky_cleanup(NvBool cleanup){
    s540FirstTxnObserveServiceRefusal(1,2,NV_ERR_NO_MEMORY);
    expect(s540GspCancellationRevoke(token)==NV_OK,"actual revocation");
    if(cleanup)expect(s540GspCancellationBeginCleanupState(&nv)==NV_OK,"actual cleanup phase");
}
int main(int argc,char **argv){
    int scenario=argc>1?atoi(argv[1]):0;
    S540FirstTxnGlobalSnapshot view, before, after;
    NV_STATUS status;
    NvU64 permit=0;S540FirstTxnHostIdentity identity={0};
    S540GspCancellationCommitLease commit=0;
    setup(scenario!=4,scenario!=5);
    if(scenario==6)expect(s540FirstTxnBackendBegin(&identity,&permit)==NV_OK,"real backend scope retained");
    if(scenario==7||scenario==8||scenario==9||scenario==18){
        serviceStage=S540_FIRST_SERVICE_ADMIT;
        expect(s540FirstTxnWorkAdmit(&nv,&queue,&item,&workLease)==NV_OK,"actual queued work ticket");
        if(scenario!=7){
            tid=2;serviceStage=S540_FIRST_SERVICE_ENTER;
            expect(s540FirstTxnWorkEnter(&nv,&queue,&item,workLease)==NV_OK,"actual work entered");
            if(scenario==9){
                expect(s540FirstTxnWorkOriginalReturned(&nv,NV_OK)==NV_OK,"actual original work returned");
                serviceStage=S540_FIRST_SERVICE_RETURNED;
                expect(s540FirstTxnWorkReturned(&nv,&queue,workLease)==NV_OK,"actual action returned clears ticket");
            }
            if(scenario==18)expect(s540FirstTxnWorkRetain(&nv,&queue,workLease,NV_ERR_NO_MEMORY)==NV_ERR_NO_MEMORY,"actual retained work obligation");
            tid=1;
        }
    }
    if((scenario>=10&&scenario<=14)||scenario==19)
        expect(s540FirstTxnIrqBind(&nv,&backend,&irqGeneration)==NV_OK,"actual backend participant bound");
    if(scenario==19){tid=2;expect(s540FirstTxnIrqEnter(&backend,1)==NV_OK,"actual entered IRQ participant");tid=1;}
    if(scenario==21)expect(s540FirstTxnBeginClosing(&nv)==NV_OK,"real clean CLOSING phase");
    if(scenario!=20&&scenario!=21)sticky_cleanup(scenario!=3);
    else{expect(s540GspCancellationRevoke(token)==NV_OK,"actual clean revocation");expect(s540GspCancellationBeginCleanupState(&nv)==NV_OK,"actual clean cleanup phase");}
    if(scenario==1)tid=2;
    if(scenario==2){S540GspCancellationSnapshot facts={0};expect(s540GspCancellationGetSnapshot(token,&facts)==NV_OK,"deadline snapshot");now=facts.deadlineNs+1;}
    if(scenario==10)irqMode=1;
    if(scenario==11)irqMode=2;
    if(scenario==12)irqMode=3;
    if(scenario==13)irqMode=4;
    if(scenario==15)expect(s540GspCancellationSubmitEnterState(&nv,&commit)==NV_OK,"genuine cleanup endpoint in flight");
    if(scenario==16)ordinary=NV_FALSE;
    expect(s540FirstTxnGlobalGetSnapshot(&before)==NV_OK,"before sticky snapshot");
    memset(&view,0xa5,sizeof(view));
    status=s540FirstTxnCleanupMaskReadMaster(scenario==17?&owner:&nv,&view);
    if(scenario==0||scenario==9||scenario==14||scenario==21){
        expect(status==NV_OK,"retained genuine clean CPU boundary observed");
        expect(view.owner==&owner&&view.nv==&nv&&view.generation==generation,"identity pulled from actual record");
        expect(view.firstStatus==(scenario==21?NV_OK:NV_ERR_NO_MEMORY)&&view.state==S540_FIRST_GLOBAL_READY,"real first error retained with global READY");
    }else{
        expect(status!=NV_OK,"wrong/incomplete/expired/active boundary refuses");
        const unsigned char *bytes=(const unsigned char *)&view;
        NvBool intact=NV_TRUE;for(size_t i=0;i<sizeof(view);++i)if(bytes[i]!=0xa5)intact=NV_FALSE;
        expect(intact,"refusal preserves output");
    }
    expect(s540FirstTxnGlobalGetSnapshot(&after)==NV_OK,"after sticky snapshot");
    expect(before.firstStatus==after.firstStatus&&before.state==after.state&&before.owner==after.owner&&before.generation==after.generation,"observer does not clear status or change epoch");
    if(scenario==0){expect(s540FirstTxnOriginalEnter(&nv)!=NV_OK,"cleanup identity never admits original entry");expect(s540FirstTxnGlobalReadMaster(&view)!=NV_OK,"old operational master remains closed");}
    if(scenario==15){expect(s540GspCancellationCommitLeaveState(&nv,commit)==NV_OK,"real cleanup endpoint returns");expect(s540FirstTxnCleanupMaskReadMaster(&nv,&view)==NV_OK,"actual completion removes busy refusal");}
    if(scenario==6)expect(s540FirstTxnBackendEnd(permit)==NV_OK,"actual preerror backend return");
    printf("{\"scenario\":%d,\"checks\":%u,\"failures\":%u,\"status\":%u}\n",scenario,checks,failures,status);
    return failures?1:0;
}
