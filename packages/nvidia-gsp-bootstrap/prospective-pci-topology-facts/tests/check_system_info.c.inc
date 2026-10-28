/* SPDX-License-Identifier: MIT
 * Complete actual retained SystemInfo preparation and caller check. The
 * authority/topology probe, NVOC field layout, allocator, encoder and RPC are
 * explicit CPU endpoints; their implementations are tested separately.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
@HEADERS@
static unsigned cases,checks;
static void expect(int value,const char *why) {
    ++checks;if(!value){fprintf(stderr,"FAILED: %s\n",why);abort();}
}
#define NV_PRINTF(...) ((void)0)
#define NV_ASSERT_OR_RETURN(ok,error) do {if(!(ok))return (error);} while(0)
#define NV_CHECK_OK_OR_GOTO(status,level,expression,label) do { \
    (status)=(expression);if((status)!=NV_OK)goto label; } while(0)
typedef struct OBJGPU {NvU64 identity;} OBJGPU;
typedef struct KernelGsp {
    NvU64 *pEncodedSystemInfo;
    NvU32 encodedSystemInfoKeyLimit,encodedSystemInfoCount;
} KernelGsp;
static OBJGPU gpu={0x1234};
enum {CLEAN,PRE_STICKY,PRE_CANCEL,PRE_IDENTITY,PRE_TOPOLOGY,OOM,
      ENCODER_ERROR,ENCODER_ERROR_AND_STICKY,POST_STICKY,POST_CANCEL,
      POST_IDENTITY,POST_EPOCH,POST_TOPOLOGY,PRE_LOCK_LOST,LATE_CANCEL};
static struct {
    int mode;
    NvBool apiOwner,topology;
    NvU64 identity,epoch;
    NV_STATUS sticky,cancel;
    unsigned guards,allocations,encodes,deferred,frees,sends;
    NV_STATUS deferredStatus;
    void *backing;
} endpoint;
static NvBool rmapiLockIsOwner(void){return endpoint.apiOwner;}
static NV_STATUS _s540RequirePciTopology(OBJGPU *pGpu) {
    expect(pGpu==&gpu,"guard gets exact GPU endpoint");++endpoint.guards;
    if(endpoint.identity!=gpu.identity||endpoint.epoch!=7)return NV_ERR_INVALID_STATE;
    if(endpoint.sticky!=NV_OK)return endpoint.sticky;
    if(endpoint.cancel!=NV_OK)return endpoint.cancel;
    return endpoint.topology?NV_OK:NV_ERR_NOT_SUPPORTED;
}
static void *portMemAllocPaged(size_t bytes) {
    ++endpoint.allocations;expect(bytes==65536,"original 64KiB NVKV capacity");
    if(endpoint.mode==OOM)return NULL;
    expect(endpoint.backing==NULL,"one explicit CPU backing allocation");
    endpoint.backing=malloc(bytes);expect(endpoint.backing!=NULL,"CPU backing");
    memset(endpoint.backing,0xa5,bytes);return endpoint.backing;
}
/* This endpoint deliberately counts rather than releasing: any invocation
 * from the actual retained failure body is a failing ownership mutation. */
static void portMemFree(void *pointer) {
    expect(pointer==endpoint.backing,"attempted physical-release identity");++endpoint.frees;
}
static NV_STATUS s540FirstTxnRequestDeferredCleanupGpu(OBJGPU *pGpu,NV_STATUS status) {
    expect(pGpu==&gpu&&status!=NV_OK,"deferred cleanup preserves actual error");
    ++endpoint.deferred;endpoint.deferredStatus=status;return status;
}
static NV_STATUS _kgspEncodeSystemInfo(OBJGPU *pGpu,KernelGsp *gsp,
    NvU64 *buffer,NvU32 limit,NvU32 *count) {
    ++endpoint.encodes;
    expect(pGpu==&gpu&&buffer==endpoint.backing&&gsp->pEncodedSystemInfo==buffer,
        "actual encoder receives owned backing unchanged");
    expect(limit==8192&&count==&gsp->encodedSystemInfoCount&&*count==0,
        "original encoder capacity and count initialization");
    for(unsigned i=0;i<7;++i)buffer[i]=0x1234000000000000ULL+i;
    *count=7;
    switch(endpoint.mode){
    case ENCODER_ERROR_AND_STICKY:endpoint.sticky=NV_ERR_NOT_SUPPORTED;return NV_ERR_GENERIC;
    case ENCODER_ERROR:return NV_ERR_INVALID_ARGUMENT;
    case POST_STICKY:endpoint.sticky=NV_ERR_NOT_SUPPORTED;break;
    case POST_CANCEL:endpoint.cancel=NV_ERR_OPERATION_ABORTED;break;
    case POST_IDENTITY:++endpoint.identity;break;
    case POST_EPOCH:++endpoint.epoch;break;
    case POST_TOPOLOGY:endpoint.topology=NV_FALSE;break;
    case LATE_CANCEL:endpoint.cancel=NV_ERR_TIMEOUT;break;
    default:break;
    }
    return NV_OK;
}
@PREPARE_BODY@
static NV_STATUS actualCaller(OBJGPU *pGpu,KernelGsp *pKernelGsp) {
    NV_STATUS status=NV_OK;
    @CALLER_STATEMENT@
    ++endpoint.sends; /* Explicit RPC endpoint, not a GSP operation. */
done:
    return status;
}
static void reset(int mode) {
    expect(endpoint.backing==NULL,"CPU teardown happened outside actual code");
    memset(&endpoint,0,sizeof(endpoint));endpoint.mode=mode;
    endpoint.apiOwner=NV_TRUE;endpoint.topology=NV_TRUE;
    endpoint.identity=gpu.identity;endpoint.epoch=7;
    if(mode==PRE_STICKY)endpoint.sticky=NV_ERR_NOT_SUPPORTED;
    if(mode==PRE_CANCEL)endpoint.cancel=NV_ERR_OPERATION_ABORTED;
    if(mode==PRE_IDENTITY)++endpoint.identity;
    if(mode==PRE_TOPOLOGY)endpoint.topology=NV_FALSE;
    if(mode==PRE_LOCK_LOST)endpoint.apiOwner=NV_FALSE;
}
static NV_STATUS wanted(int mode) {
    if(mode==CLEAN)return NV_OK;
    if(mode==OOM)return NV_ERR_NO_MEMORY;
    if(mode==ENCODER_ERROR)return NV_ERR_INVALID_ARGUMENT;
    if(mode==ENCODER_ERROR_AND_STICKY)return NV_ERR_GENERIC;
    if(mode==PRE_CANCEL||mode==POST_CANCEL)return NV_ERR_OPERATION_ABORTED;
    if(mode==PRE_IDENTITY||mode==POST_IDENTITY||mode==POST_EPOCH)return NV_ERR_INVALID_STATE;
    if(mode==PRE_LOCK_LOST)return NV_ERR_INVALID_LOCK_STATE;
    if(mode==LATE_CANCEL)return NV_ERR_TIMEOUT;
    return NV_ERR_NOT_SUPPORTED;
}
int main(void) {
    for(int mode=CLEAN;mode<=LATE_CANCEL;++mode){
        reset(mode);
        NvU64 prior[2]={0x1122,0x3344};
        const int pre=mode>=PRE_STICKY&&mode<=PRE_TOPOLOGY;
        KernelGsp gsp={pre||mode==PRE_LOCK_LOST?prior:NULL,19,23};
        NV_STATUS status=actualCaller(&gpu,&gsp);
        expect(status==wanted(mode),"actual caller propagates precise failure");
        expect(endpoint.sends==(status==NV_OK?1U:0U),"no RPC publication after failure");
        expect(endpoint.frees==0,"retained function never physically frees backing");
        if(pre||mode==PRE_LOCK_LOST){
            expect(endpoint.allocations==0&&endpoint.encodes==0,"pre-guard/lock failure precedes allocation and encoding");
            expect(gsp.pEncodedSystemInfo==prior&&gsp.encodedSystemInfoCount==23&&gsp.encodedSystemInfoKeyLimit==19,
                "pre-work failure preserves prior owned fields");
            expect(endpoint.guards==(mode==PRE_LOCK_LOST?0U:1U),"lock gate precedes topology probe");
            expect(endpoint.deferred==(mode==PRE_LOCK_LOST?0U:1U),"guard failure uses existing deferred branch");
        }else if(mode==OOM){
            expect(endpoint.allocations==1&&endpoint.encodes==0&&endpoint.guards==1&&endpoint.deferred==0,
                "original allocation failure remains before encode without new cleanup");
            expect(gsp.pEncodedSystemInfo==NULL&&gsp.encodedSystemInfoKeyLimit==8192&&gsp.encodedSystemInfoCount==23,
                "allocation failure preserves original field semantics");
        }else{
            expect(endpoint.allocations==1&&endpoint.encodes==1&&gsp.pEncodedSystemInfo==endpoint.backing,
                "encoded owned backing remains retained on both success and error");
            expect(gsp.encodedSystemInfoKeyLimit==8192&&gsp.encodedSystemInfoCount==7,
                "encoded pointer/count/capacity are never cleared on refusal");
            for(unsigned i=0;i<7;++i)expect(gsp.pEncodedSystemInfo[i]==0x1234000000000000ULL+i,
                "actual retained failure preserves encoded bytes");
            const int encoderError=mode==ENCODER_ERROR||mode==ENCODER_ERROR_AND_STICKY;
            expect(endpoint.guards==(encoderError?1U:2U),"post-guard only follows successful encoder");
            expect(endpoint.deferred==(mode==CLEAN?0U:1U),"post-guard/encoder error follows existing deferred branch");
        }
        if(endpoint.deferred)expect(endpoint.deferredStatus==wanted(mode),"exact status passed to retained cleanup");
        free(endpoint.backing);endpoint.backing=NULL; /* CPU harness teardown. */
        ++cases;
    }
    printf("{\"status\":\"passed-actual-SystemInfo-preparation-guards\",\"cases\":%u,\"checks\":%u}\n",cases,checks);
    return 0;
}
