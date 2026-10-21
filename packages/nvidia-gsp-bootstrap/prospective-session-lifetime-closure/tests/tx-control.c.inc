/* Exact original send/msgq bodies surround this fixture. Only endpoints below
 * model clocks, GPU registers, printing, timeout and memory-copy notification. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nv.h"
#include "gpu/gpu.h"
#include "S540NvidiaGspCancellation.h"
#undef memcpy
#undef memset
#undef memcmp
#define memcpy(...) __builtin_memcpy(__VA_ARGS__)
#define memset(...) __builtin_memset(__VA_ARGS__)
#define memcmp(...) __builtin_memcmp(__VA_ARGS__)

static nv_state_t exactState, otherState;
static OBJGPU actualGpu;
static MESSAGE_QUEUE_INFO queueInfo;
static msgqMetadata metadata;
static NvU8 ringBytes[4*RM_PAGE_SIZE], stagedBytes[16*RM_PAGE_SIZE], expectedRing[4*RM_PAGE_SIZE];
static NvU32 head, tail, headWrites, spins, timeoutChecks, fences, scenario, checks;
static NvU64 nowNs, eventNs;
static S540GspCancellationToken token;

static void expect(NvBool value,const char *why) {
    ++checks;
    if(!value){fprintf(stderr,"TX control failed: %s\n",why);exit(1);}
}
NvBool s540Darwin_os_semaphore_may_sleep(void){return NV_TRUE;}
NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out){*out=71;return NV_OK;}
NvU64 s540Darwin_os_get_monotonic_time_ns(void){return nowNs;}
NV_STATUS s540Darwin_os_schedule(void){return NV_OK;}
NV_STATUS s540Darwin_os_delay(NvU32 period){(void)period;return NV_OK;}
NvU32 osGpuReadReg032(OBJGPU *gpu,NvU32 address){
    expect(gpu==&actualGpu&&address==2,"actual msgq reads its real fixture TX tail");return tail;
}
void osGpuWriteReg032(OBJGPU *gpu,NvU32 address,NvV32 value){
    expect(gpu==&actualGpu&&address==1,"actual msgq publishes only its real fixture TX head");
    ++headWrites;head=value;
}
void osSpinLoop(void){
    ++spins;
    if(scenario==3&&spins==1)expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"real operation revocation during actual send wait");
    if(scenario==5&&spins==1)nowNs=eventNs+30000000000ULL;
    if((scenario==0||scenario==1||scenario==8)&&spins==2)tail=1;
}
void timeoutSet(TIMEOUT_DATA *data,RMTIMEOUT *timeout,NvU32 period,NvU32 flags){
    (void)data;(void)timeout;(void)flags;expect(period==1000000,"original local timeout remains one second");
}
NV_STATUS timeoutCheck(TIMEOUT_DATA *data,RMTIMEOUT *timeout,NvU32 line){
    (void)data;(void)timeout;(void)line;++timeoutChecks;return spins>=3?NV_ERR_TIMEOUT:NV_OK;
}
static NV_STATUS fixtureEncrypt(void *cc,MESSAGE_QUEUE_INFO *info,GSP_MSG_QUEUE_ELEMENT *element,NvU32 bytes){
    (void)cc;(void)info;(void)element;(void)bytes;expect(NV_FALSE,"CC is outside selected plain TX control");return NV_ERR_NOT_SUPPORTED;
}
static void fixtureCcError(OBJGPU *gpu,ConfidentialCompute *cc){
    (void)gpu;(void)cc;expect(NV_FALSE,"unexpected CC error endpoint");
}
static void *fixtureCopy(void *out,NvLength capacity,const void *in,NvLength bytes){
    expect(bytes<=capacity,"actual copy preserves its destination capacity");return memcpy(out,in,bytes);
}
static void fixtureStoreFence(void){
    ++fences;
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    if(scenario==6)expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"real revoke after final fragment copy and before publication");
    if(scenario==7&&fences==2)expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,
        "real revoke inside authentic submit before TX_HEAD commit");
}
#undef NV_PRINTF
#undef NV_PRINTF_COND
#define NV_PRINTF(...) do{}while(0)
#define NV_PRINTF_COND(...) do{}while(0)
#undef portMemCopy
#undef portAtomicMemoryFenceStore
#undef confComputeSetErrorState
#define gspMsgQueueCCEncrypt fixtureEncrypt
#define confComputeSetErrorState fixtureCcError
#define portMemCopy fixtureCopy
#define portAtomicMemoryFenceStore fixtureStoreFence
#define READ_REG(gpu,address) osGpuReadReg032((gpu),(address))
#define WRITE_REG(gpu,address,value) osGpuWriteReg032((gpu),(address),(value))

/* EXACT_ACTUAL_BODIES */

static void reset(NvU32 which,NvBool bind,NvBool cleanup,NvBool partial){
    scenario=which;headWrites=spins=timeoutChecks=fences=0;nowNs=eventNs=1000000000ULL;token=0;
    memset(&queueInfo,0,sizeof(queueInfo));memset(&metadata,0,sizeof(metadata));
    memset(&actualGpu,0,sizeof(actualGpu));memset(ringBytes,0x33,sizeof(ringBytes));
    memset(stagedBytes,0xa5,sizeof(stagedBytes));
    actualGpu.pOsGpuInfo=&exactState;
    metadata.pGpu=&actualGpu;metadata.pOurEntries=ringBytes;metadata.txLinked=NV_TRUE;
    metadata.tx.msgSize=RM_PAGE_SIZE;metadata.tx.msgCount=4;metadata.regTxHead=1;metadata.regTxTail=2;
    metadata.txWritePtr=partial?3:0;metadata.txReadPtr=0;metadata.txFree=partial?1:4;
    head=metadata.txWritePtr;tail=0;
    queueInfo.hQueue=&metadata;queueInfo.pCmdQueueElement=(GSP_MSG_QUEUE_ELEMENT *)stagedBytes;
    queueInfo.queueElementHdrSize=GSP_MSG_QUEUE_ELEMENT_SIZE_NO_ENCRYPTION;
    queueInfo.queueElementSizeMin=RM_PAGE_SIZE;queueInfo.queueElementSizeMax=16*RM_PAGE_SIZE;
    if(bind){
        expect(s540GspCancellationBind(&exactState,&token)==NV_OK&&token,"genuine cancellation binding");
        expect(s540GspCancellationBegin(token)==NV_OK,"genuine cancellation operation scope");
        if(cleanup){
            expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"real PM event before cleanup");
            expect(s540GspCancellationBeginCleanupState(&exactState)==NV_OK,"real cleanup scope");
            nowNs=eventNs+30000000000ULL-1;
        }
    }
}
static NV_STATUS send(NvBool original){
    return original?s540TxUnmodifiedOriginal(&queueInfo,&actualGpu,NVDM_TYPE_RM_RPC,RM_PAGE_SIZE+64):
        GspMsgQueueSendCommand(&queueInfo,&actualGpu,NVDM_TYPE_RM_RPC,RM_PAGE_SIZE+64);
}
static void finish(void){
    if(!token)return;
    expect(s540GspCancellationFinish(token)==NV_OK,"real cancellation finish after original body returned");
    expect(s540GspCancellationUnbind(token)==NV_OK,"real cancellation generation unbound without fake callback completion");
}
int main(void){
    reset(0,NV_FALSE,NV_FALSE,NV_TRUE);
    expect(send(NV_TRUE)==NV_OK&&headWrites==1&&head==5,"unmodified original waits then commits exact message");
    memcpy(expectedRing,ringBytes,sizeof(ringBytes));
    reset(1,NV_FALSE,NV_FALSE,NV_TRUE);
    expect(send(NV_FALSE)==NV_OK&&headWrites==1&&head==5&&memcmp(expectedRing,ringBytes,sizeof(ringBytes))==0,
        "no matching cancellation binding preserves exact original queue publication and bytes");
    reset(2,NV_TRUE,NV_FALSE,NV_FALSE);
    expect(send(NV_FALSE)==NV_OK&&headWrites==1&&head==2&&metadata.txWritePtr==2,"ordinary active operation commits genuine two-fragment message");finish();
    reset(3,NV_TRUE,NV_FALSE,NV_TRUE);
    expect(send(NV_FALSE)==NV_ERR_OPERATION_ABORTED&&headWrites==0&&head==3&&metadata.txWritePtr==3,
        "revocation during second-fragment wait returns actual abort without publication");
    expect(ringBytes[3*RM_PAGE_SIZE]!=0x33&&ringBytes[0]==0x33,"first staged fragment retained, existing peer-owned bytes untouched");finish();
    reset(4,NV_TRUE,NV_TRUE,NV_FALSE);
    expect(send(NV_FALSE)==NV_OK&&headWrites==1&&head==2,"genuine cleanup can commit before its unchanged deadline");finish();
    reset(5,NV_TRUE,NV_TRUE,NV_TRUE);
    expect(send(NV_FALSE)==NV_ERR_TIMEOUT&&headWrites==0&&metadata.txWritePtr==3,"real cleanup deadline expiry stops waiting without command publication");
    {S540GspCancellationSnapshot snapshot={0};expect(s540GspCancellationGetSnapshot(token,&snapshot)==NV_OK&&snapshot.deadlineNs==eventNs+30000000000ULL&&snapshot.cleanupExpirations,
        "actual fixed thirty-second deadline and expiration retained");}finish();
    reset(6,NV_TRUE,NV_FALSE,NV_FALSE);
    expect(send(NV_FALSE)==NV_ERR_OPERATION_ABORTED&&headWrites==0&&metadata.txWritePtr==0,
        "revocation after all fragment copies prevents final submit and retains unpublished slots");finish();
    reset(7,NV_TRUE,NV_FALSE,NV_FALSE);
    expect(send(NV_FALSE)==NV_OK&&headWrites==1&&head==2&&metadata.txWritePtr==2,
        "revocation after final check but before TX_HEAD preserves genuine accepted-send result");finish();
    reset(8,NV_TRUE,NV_FALSE,NV_TRUE);
    expect(s540GspCancellationRevokeAt(token,eventNs)==NV_OK,"revoke distinct bound identity");actualGpu.pOsGpuInfo=&otherState;
    expect(send(NV_FALSE)==NV_OK&&headWrites==1&&head==5,"foreign GPU identity retains original behavior rather than borrowing cancellation authority");finish();
    reset(9,NV_FALSE,NV_FALSE,NV_TRUE);
    expect(send(NV_TRUE)==NV_ERR_BUSY_RETRY&&headWrites==0&&metadata.txWritePtr==3,"unmodified original full queue timeout");
    reset(10,NV_FALSE,NV_FALSE,NV_TRUE);
    expect(send(NV_FALSE)==NV_ERR_BUSY_RETRY&&headWrites==0&&metadata.txWritePtr==3,"unbound original timeout status and publication preserved");
    printf("{\"status\":\"passed\",\"checks\":%u,\"failures\":0,\"actual_send_and_msgq_bodies\":true,\"real_cancellation_record\":true,\"hardware_endpoints_fixture\":true,\"original_entry_admission\":false,\"pm_30_second_shutdown_bound_proven\":false}\n",checks);
    return 0;
}
