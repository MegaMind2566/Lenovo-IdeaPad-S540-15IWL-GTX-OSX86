/* SPDX-License-Identifier: MIT */
#include "Participants.h"
#include "nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>

static _Thread_local NvU64 currentTid=1;
static _Thread_local NvBool ordinary=NV_TRUE;
static _Thread_local NvBool authenticated=NV_TRUE;
static _Thread_local NvU32 observedOrigin=0;
static _Atomic NvU64 now=1;
static unsigned checks;
static int state,foreign;
static void require(NvBool value){++checks;if(!value)abort();}
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *out){*out=currentTid;return NV_OK;}
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void){return ordinary;}
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void){return atomic_load(&now);}
NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32 ms){(void)ms;return NV_OK;}
NV_STATUS s540FirstTxnIrqReadEnteredScope(const void *nv,NvU32 role,NvU32 *origin){
    if(!authenticated||nv!=&state||role<1||role>2)return NV_ERR_INVALID_STATE;
    *origin=role==1?0:observedOrigin;return NV_OK;
}

static _Atomic unsigned workerStage;
static NV_STATUS foreignLeave,workerCheck;
static void *bottom(void *unused){
    (void)unused;currentTid=2;observedOrigin=2;
    require(s540GspCancellationEnterIrqScope(&state,2,2)==NV_OK);
    require(s540GspCancellationCurrentScopeActive());
    require(s540GspCancellationIrqOrigin(2)==2);
    atomic_store(&workerStage,1);
    while(atomic_load(&workerStage)==1){}
    workerCheck=s540GspCancellationCheckCurrent();
    require(s540GspCancellationLeaveIrqScope(&state,2)==NV_OK);
    return NULL;
}
static void *wrongThread(void *unused){
    (void)unused;currentTid=3;authenticated=NV_FALSE;
    require(s540GspCancellationEnterIrqScope(&state,2,2)==NV_ERR_INVALID_STATE);
    foreignLeave=s540GspCancellationLeaveIrqScope(&state,1);return NULL;
}
int main(void){
    S540GspCancellationToken token=0;
    S540GspCancellationLease lease=0;
    pthread_t worker;
    require(s540GspCancellationBind(&state,&token)==NV_OK&&token);
    require(s540GspCancellationBegin(token)==NV_OK);
    ordinary=NV_FALSE;
    require(s540GspCancellationEnterIrqScope(&state,1,0)==NV_OK);
    require(s540GspCancellationCurrentScopeActive()&&s540GspCancellationCheckCurrent()==NV_OK);
    require(s540GspCancellationIrqOrigin(1)==2);
    require(s540GspCancellationEnterIrqScope(&state,1,0)==NV_ERR_IN_USE);
    require(s540GspCancellationEnterIrqScope(&foreign,1,0)==NV_ERR_INVALID_STATE);
    require(s540GspCancellationCaptureCurrent(&state,&lease)==NV_OK&&lease);
    require(s540GspCancellationEnterLease(lease,&state)==NV_ERR_INVALID_STATE);
    require(!pthread_create(&worker,NULL,wrongThread,NULL));require(!pthread_join(worker,NULL));
    require(foreignLeave==NV_ERR_INVALID_STATE);
    require(s540GspCancellationLeaveIrqScope(&state,1)==NV_OK);
    ordinary=NV_TRUE;
    require(s540GspCancellationDiscardLease(lease,&state)==NV_OK);
    require(s540GspCancellationEnterIrqScope(&state,2,0)==NV_ERR_INVALID_STATE);
    require(!pthread_create(&worker,NULL,bottom,NULL));
    while(!atomic_load(&workerStage)){}
    require(s540GspCancellationFinish(token)==NV_ERR_IN_USE);
    require(s540GspCancellationRevoke(token)==NV_OK);
    require(s540GspCancellationBeginCleanupState(&state)==NV_OK);
    atomic_store(&workerStage,2);require(!pthread_join(worker,NULL));
    require(workerCheck==NV_ERR_OPERATION_ABORTED);
    // Genuine coalescing preserves an older OP origin across cleanup.
    observedOrigin=2|4;
    require(s540GspCancellationEnterIrqScope(&state,2,2|4)==NV_OK);
    require(s540GspCancellationIrqOrigin(2)==2);
    require(s540GspCancellationCheckCurrent()==NV_ERR_OPERATION_ABORTED);
    require(s540GspCancellationLeaveIrqScope(&state,2)==NV_OK);
    observedOrigin=4;
    require(s540GspCancellationEnterIrqScope(&state,2,4)==NV_OK);
    require(s540GspCancellationCheckCurrent()==NV_OK);
    ordinary=NV_FALSE;
    require(s540GspCancellationEnterIrqScope(&state,1,0)==NV_OK);
    require(s540GspCancellationIrqOrigin(1)==4);
    require(s540GspCancellationCheckCurrent()==NV_OK);
    require(s540GspCancellationLeaveIrqScope(&state,1)==NV_OK);
    require(s540GspCancellationIrqOrigin(2)==4);
    ordinary=NV_TRUE;
    require(s540GspCancellationFinish(token)==NV_ERR_IN_USE);
    require(s540GspCancellationLeaveIrqScope(&state,2)==NV_OK);
    atomic_store(&now,30000000002ULL);
    require(s540GspCancellationEnterIrqScope(&state,2,4)==NV_OK);
    require(s540GspCancellationCheckCurrent()==NV_ERR_TIMEOUT);
    require(s540GspCancellationLeaveIrqScope(&state,2)==NV_OK);
    require(s540GspCancellationFinish(token)==NV_OK);
    require(s540GspCancellationEnterIrqScope(&state,1,0)==NV_ERR_INVALID_STATE);
    require(s540GspCancellationUnbind(token)==NV_OK);
    printf("{\"status\":\"passed\",\"checks\":%u,\"actual_cancellation_translation_unit\":true}\n",checks);
    return 0;
}
