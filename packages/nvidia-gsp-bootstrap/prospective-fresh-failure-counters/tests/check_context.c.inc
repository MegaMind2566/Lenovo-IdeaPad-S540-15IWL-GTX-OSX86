/* SPDX-License-Identifier: MIT; actual C bodies, explicit CPU-only endpoints. */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "S540NvidiaGspContext.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540DeviceAllocationDiagnostics.h"
#include "S540AttachFailureWitness.h"
#include "nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

/* Only the state fields touched by the extracted actual adapter boundary are
 * modeled here. This is not an nv_state_t/kernel-layout or RM execution test. */
struct FixtureNv { NvU32 flags; };
struct S540GspContext {
    struct FixtureNv nv;
    NvU32 stacks[1];
    NvU64 firstTxnGeneration;
    S540GspContextSnapshot state;
};
enum { MAIN = 0, NV_DBG_ERRORS = 4, NV_FLAG_INITIALIZED = 1U << 12 };
static S540GspContext context;
static S540FirstTxnSnapshot providedSnapshot;
static NV_STATUS snapshotResult, wrapperResult, enterResult, irqResult, preflightResult;
static NvBool ownerAllowed, hostClean, adapterResult;
static NvU32 checks, snapshotCalls, logCalls, wrapperCalls, enterCalls, adapterCalls;
static char logs[7][768];
static S540FirstTxnServiceCounters providedFresh;
static S540DeviceAllocationDiagnostics providedAllocation;
static S540AttachFailureWitness providedWitness;
static NV_STATUS freshResult, allocationResult, witnessResult;
static NvU32 freshCalls, allocationCalls, witnessCalls, cases;

static void expect(NvBool condition, const char *description)
{
    ++checks;
    if (!condition) {
        fprintf(stderr, "context diagnostic check failed: %s\n", description);
        exit(1);
    }
}
static NvBool owner(S540GspContext *value) { return value == &context && ownerAllowed; }
static NvBool cleanHost(void) { return hostClean; }
NV_STATUS s540GspIrqInstallationCheckContext(S540GspContext *value)
{
    expect(value == &context, "actual IRQ check context");
    return irqResult;
}
static NV_STATUS s540GlobalRmFeatureProfilePreflight(const void *value)
{
    expect(value == &context.nv, "actual preflight state identity");
    return preflightResult;
}
NV_STATUS s540FirstTxnOriginalEnter(const void *value)
{
    expect(value == &context.nv, "actual original-enter state identity");
    ++enterCalls;
    return enterResult;
}
static NvBool rm_init_adapter(void *stack, void *value)
{
    expect(stack == &context.stacks[MAIN] && value == &context.nv,
        "actual original adapter endpoint identities");
    expect(enterCalls == 1 && !wrapperCalls && !snapshotCalls && !logCalls,
        "adapter runs before wrapper-return and diagnostics");
    ++adapterCalls;
    return adapterResult;
}
NV_STATUS s540FirstTxnOriginalWrapperReturned(const void *value)
{
    expect(value == &context.nv && adapterCalls == 1 && !snapshotCalls && !logCalls,
        "diagnostic is after the original wrapper actually returned");
    ++wrapperCalls;
    return wrapperResult;
}
NV_STATUS s540FirstTxnGetSnapshot(const void *value, S540FirstTxnSnapshot *out) {
    expect(value==&context.nv&&out&&wrapperCalls==1&&wrapperResult!=NV_OK&&!snapshotCalls,
        "cached snapshot reads once after actual wrapper return");
    ++snapshotCalls;if(snapshotResult!=NV_OK)return snapshotResult;*out=providedSnapshot;return NV_OK;
}
NV_STATUS s540FirstTxnOriginalReadServiceCounters(const void *value,S540FirstTxnServiceCounters *out) {
    expect(value==&context.nv&&out&&wrapperCalls==1&&snapshotCalls==1&&!freshCalls&&
        !allocationCalls&&!witnessCalls,"fresh service read follows cached read after actual return");
    ++freshCalls;if(freshResult!=NV_OK)return freshResult;*out=providedFresh;return NV_OK;
}
NV_STATUS s540DeviceReadAllocationDiagnostics(const void *value,S540DeviceAllocationDiagnostics *out) {
    expect(value==&context.nv&&out&&wrapperCalls==1&&freshCalls==1&&!allocationCalls&&
        !witnessCalls,"allocation read follows fresh service read after return");
    ++allocationCalls;if(allocationResult!=NV_OK)return allocationResult;*out=providedAllocation;return NV_OK;
}
NV_STATUS s540AttachWitnessRead(const void *value,S540AttachFailureWitness *out) {
    expect(value==&context.nv&&out&&wrapperCalls==1&&allocationCalls==1&&!witnessCalls,
        "constructor witness reads actual bound state only after return");
    ++witnessCalls;if(witnessResult!=NV_OK)return witnessResult;*out=providedWitness;return NV_OK;
}
int NV_API_CALL nv_printf(NvU32 level,const char *format,...) __attribute__((format(printf,2,3)));
int NV_API_CALL nv_printf(NvU32 level,const char *format,...) {
    va_list args;int count;
    expect(level==NV_DBG_ERRORS&&wrapperCalls==1&&snapshotCalls==1&&logCalls<7,
        "bounded ordinary post-wrapper diagnostic calls");
    expect(!strstr(format,"%p")&&!strstr(format,"firmware=")&&!strstr(format,"masterThread="),
        "no kernel addresses, firmware or thread identities");
    va_start(args,format);count=vsnprintf(logs[logCalls],sizeof(logs[logCalls]),format,args);va_end(args);
    expect(count>0&&(size_t)count<sizeof(logs[0]),"bounded diagnostic line");
    expect(logs[logCalls][count-1]=='\n'&&strchr(logs[logCalls],'\n')==&logs[logCalls][count-1],
        "one complete line per diagnostic call");
    ++logCalls;return count;
}
#include "actual-context-failure.inc"
#include "actual-initialize-adapter.inc"
static const char *line(const char *needle) {
    const char *found=NULL;NvU32 i;
    for(i=0;i<logCalls;++i)if(strstr(logs[i],needle)){
        expect(!found,"diagnostic record is unique");found=logs[i];}
    return found;
}
static void decimalField(const char *record,const char *name,unsigned long long value) {
    char expected[96];int n=snprintf(expected,sizeof(expected)," %s=%llu",name,value);
    const char *found=record?strstr(record,expected):NULL;
    expect(n>0&&(size_t)n<sizeof(expected)&&found&&(found[n]==' '||found[n]=='\n'),name);
}
static void hexField(const char *record,const char *name,unsigned long long value) {
    char expected[96];int n=snprintf(expected,sizeof(expected)," %s=0x%llx",name,value);
    const char *found=record?strstr(record,expected):NULL;
    expect(n>0&&(size_t)n<sizeof(expected)&&found&&(found[n]==' '||found[n]=='\n'),name);
}
static void reset(void) {
    memset(&context,0,sizeof(context));memset(&providedSnapshot,0,sizeof(providedSnapshot));
    memset(&providedFresh,0,sizeof(providedFresh));memset(&providedAllocation,0,sizeof(providedAllocation));
    memset(&providedWitness,0,sizeof(providedWitness));memset(logs,0,sizeof(logs));
    context.firstTxnGeneration=19;context.state.privateState=NV_TRUE;
    snapshotResult=wrapperResult=enterResult=irqResult=preflightResult=NV_OK;
    freshResult=allocationResult=witnessResult=NV_OK;
    ownerAllowed=hostClean=adapterResult=NV_TRUE;
    snapshotCalls=logCalls=wrapperCalls=enterCalls=adapterCalls=freshCalls=allocationCalls=witnessCalls=0;
    providedSnapshot.firstStatus=NV_ERR_INVALID_STATE;providedSnapshot.firstSite=2;
    providedSnapshot.phase=S540_FIRST_RETAINED;providedSnapshot.counters.hostUnavailable=7;
    providedSnapshot.counters.hostInvalidFrees=8;providedSnapshot.counters.memoryUnavailableEver=9;
    providedSnapshot.counters.memoryViolationsEver=10;providedSnapshot.counters.cryptoUnavailable=11;
    providedSnapshot.counters.cryptoMaskLow=0x81;providedSnapshot.counters.cryptoMaskHigh=0x82;
    providedSnapshot.counters.cryptoOverflow=1;
    providedFresh.hostInitialized=1;providedFresh.hostUnavailable=0x100000011ULL;
    providedFresh.hostInvalidFrees=0x100000012ULL;providedFresh.memoryUnavailableEver=0x100000013ULL;
    providedFresh.memoryViolationsEver=0x100000014ULL;providedFresh.cryptoUnavailable=0x100000015ULL;
    providedFresh.cryptoMaskLow=0x8000000000000001ULL;providedFresh.cryptoMaskHigh=0x123456789abcdef0ULL;
    providedFresh.cryptoOverflow=1;
    providedAllocation.format=1;providedAllocation.bytes=sizeof(providedAllocation);providedAllocation.observedMask=3;
    providedAllocation.allocationAttemptsLifetime=11;providedAllocation.allocationFailuresLifetime=3;
    providedAllocation.entryRejectionsLifetime=2;providedAllocation.largestRequestedPagesLifetime=129;
    providedAllocation.firstFailure.status=NV_ERR_NO_MEMORY;providedAllocation.firstFailure.pages=127;
    providedAllocation.firstFailure.pageBytes=4096;providedAllocation.firstFailureState=2;
    providedAllocation.firstFailure.stage=6;providedAllocation.firstFailure.contiguous=0;
    providedAllocation.firstFailure.cache=2;providedAllocation.firstFailure.zeroed=1;
    providedAllocation.firstFailure.unprotected=1;providedAllocation.firstFailure.node=-1;
    providedAllocation.firstFailure.cpuObservedMask=7;providedAllocation.firstFailure.maxBasic=7;
    providedAllocation.firstFailure.vendorEbx=0x756e6547U;providedAllocation.firstFailure.vendorEdx=0x49656e69U;
    providedAllocation.firstFailure.vendorEcx=0x6c65746eU;providedAllocation.firstFailure.signature=0x806eaU;
    providedAllocation.firstFailure.family=6;providedAllocation.firstFailure.model=0x8e;
    providedAllocation.firstFailure.leaf1Ecx=0;providedAllocation.firstFailure.leaf7Ecx=0;
    providedWitness.format=1;providedWitness.bytes=sizeof(providedWitness);providedWitness.complete=1;
    providedWitness.lastAttachStage=5;providedWitness.lastClassId=0x1234;providedWitness.lastCtorStage=9;
    providedWitness.lastInstance=0x10000000aULL;providedWitness.firstFailureValid=1;
    providedWitness.firstAttachStage=1;providedWitness.firstClassId=0x5678;providedWitness.firstCtorStage=7;
    providedWitness.firstInstance=0x10000000bULL;providedWitness.firstStatus=NV_ERR_NOT_SUPPORTED;
    providedWitness.observedMask=3;providedWitness.missing=1;providedWitness.gspClient=0;
}
static void failure(void) {
    const char *cached,*fresh,*allocation,*witness,*last;NvU32 expectedLogs=4;
    S540FirstTxnSnapshot oldSnapshot=providedSnapshot;
    S540FirstTxnServiceCounters oldFresh=providedFresh;
    S540DeviceAllocationDiagnostics oldAllocation=providedAllocation;
    S540AttachFailureWitness oldWitness=providedWitness;
    const NvBool allocationShape=providedAllocation.format==1&&providedAllocation.bytes==sizeof(providedAllocation)&&
        (providedAllocation.observedMask&1)&&!(providedAllocation.observedMask&~3U)&&providedAllocation.firstFailureState<=2&&
        (!!(providedAllocation.observedMask&2)==(providedAllocation.firstFailureState==2));
    const NvBool witnessShape=providedWitness.format==1&&providedWitness.bytes==sizeof(providedWitness);
    ++cases;adapterResult=NV_FALSE;wrapperResult=NV_ERR_NOT_SUPPORTED;
    expect(s540GspContextInitializeAdapter(&context)==NV_ERR_NOT_SUPPORTED,"fresh diagnostics preserve wrapper86");
    expect(context.state.quarantined&&context.state.adapterAttempted&&!context.state.adapterInitialized&&
        !context.nv.flags,"fresh diagnostics preserve quarantine and initialization flags");
    expect(snapshotCalls==1&&freshCalls==1&&allocationCalls==1&&witnessCalls==1,
        "every diagnostic source sampled once even when another source is unavailable");
    cached=line("S540 retained profile failure:");fresh=line("S540 fresh service counters:");
    allocation=line("S540 allocation counters:");witness=line("S540 attach witness:");
    expect(cached&&fresh&&allocation&&witness,"all four independent diagnostic sources represented");
    decimalField(cached,"profile",NV_ERR_NOT_SUPPORTED);
    if(snapshotResult==NV_OK){
        expect(strstr(cached,"snapshot=available ")&&strstr(cached,"counters=cached "),"cached source is explicitly identified");
        decimalField(cached,"firstStatus",NV_ERR_INVALID_STATE);decimalField(cached,"firstSite",2);
        decimalField(cached,"hostUnavailable",7);decimalField(cached,"memoryUnavailableEver",9);
    }else{expect(strstr(cached,"snapshot=unavailable ")&&!strstr(cached,"firstStatus="),"unavailable cached data not invented");decimalField(cached,"snapshotStatus",snapshotResult);}
    decimalField(fresh,"available",freshResult==NV_OK);
    if(freshResult==NV_OK){
        decimalField(fresh,"hostInitialized",providedFresh.hostInitialized);
        decimalField(fresh,"hostUnavailable",providedFresh.hostUnavailable);
        decimalField(fresh,"invalidFrees",providedFresh.hostInvalidFrees);
        decimalField(fresh,"memoryUnavailableEver",providedFresh.memoryUnavailableEver);
        decimalField(fresh,"violationsEver",providedFresh.memoryViolationsEver);
        decimalField(fresh,"cryptoUnavailable",providedFresh.cryptoUnavailable);
        hexField(fresh,"cryptoMaskLow",providedFresh.cryptoMaskLow);hexField(fresh,"cryptoMaskHigh",providedFresh.cryptoMaskHigh);
        decimalField(fresh,"cryptoOverflow",providedFresh.cryptoOverflow);
    }else{decimalField(fresh,"status",freshResult);expect(!strstr(fresh,"hostUnavailable="),"unavailable fresh counters not invented");}
    decimalField(allocation,"available",allocationResult==NV_OK&&allocationShape);
    if(allocationResult==NV_OK&&allocationShape){
        decimalField(allocation,"attempts",11);decimalField(allocation,"failures",3);
        decimalField(allocation,"entryRejections",2);decimalField(allocation,"largestRequestedPages",129);
        expect(strstr(allocation,"scope=module-lifetime ")&&strstr(allocation,"independentlySampled=1 "),"counter lifetime and independent sampling explicit");
        expect(!strstr(allocation,"allocations=")&&!strstr(allocation,"mappings="),"no unsafe live binding array claims");
        decimalField(allocation,"firstFailureObserved",!!(providedAllocation.observedMask&2));
        last=line("S540 first published allocation failure:");
        if(providedAllocation.observedMask&2){
            const S540DeviceAllocationFailure *f=&providedAllocation.firstFailure;
            ++expectedLogs;expect(last!=NULL,"observed first failure printed");
            decimalField(last,"stage",f->stage);decimalField(last,"status",f->status);
            decimalField(last,"pages",f->pages);decimalField(last,"pageBytes",f->pageBytes);
            decimalField(last,"contiguous",f->contiguous);decimalField(last,"cache",f->cache);
            decimalField(last,"zeroed",f->zeroed);decimalField(last,"unprotected",f->unprotected);
            expect(strstr(last," node=-1 ")!=NULL,"actual signed NUMA node");
            hexField(last,"cpuObserved",f->cpuObservedMask);
            const char *cpu=line("S540 first allocation CPU observations:");
            if(f->cpuObservedMask){++expectedLogs;expect(cpu!=NULL,"already-observed CPU scalars printed");
                hexField(cpu,"observedMask",f->cpuObservedMask);hexField(cpu,"maxBasic",f->maxBasic);
                expect(strstr(cpu," vendor=756e6547:49656e69:6c65746e ")!=NULL,"actual raw vendor order");
                hexField(cpu,"signature",f->signature);hexField(cpu,"family",f->family);hexField(cpu,"model",f->model);
                hexField(cpu,"leaf1Ecx",f->leaf1Ecx);hexField(cpu,"leaf7Ecx",f->leaf7Ecx);
            }else expect(cpu==NULL,"no invented CPU observation when request never probed");
        }
        else expect(last==NULL,"unobserved last failure not printed");
    }else{expect(!strstr(allocation,"attempts=")&&!line("S540 first published allocation failure:"),"unavailable allocation data not invented");if(allocationResult!=NV_OK)decimalField(allocation,"status",allocationResult);else expect(strstr(allocation,"shapeValid=0")!=NULL,"unknown allocation shape explicit");}
    decimalField(witness,"available",witnessResult==NV_OK&&witnessShape);
    if(witnessResult==NV_OK&&witnessShape){
        decimalField(witness,"complete",1);decimalField(witness,"lastAttachStage",5);
        hexField(witness,"lastClassId",0x1234);decimalField(witness,"lastCtorStage",9);
        decimalField(witness,"lastInstance",0x10000000aULL);decimalField(witness,"firstFailureValid",providedWitness.firstFailureValid);
        last=line("S540 first attach failure:");
        if(providedWitness.firstFailureValid){++expectedLogs;expect(last!=NULL,"actual first constructor failure printed");
            decimalField(last,"stage",1);hexField(last,"classId",0x5678);decimalField(last,"instance",0x10000000bULL);
            decimalField(last,"ctorStage",7);decimalField(last,"status",NV_ERR_NOT_SUPPORTED);
            decimalField(last,"missingObserved",!!(providedWitness.observedMask&1));
            decimalField(last,"missing",(providedWitness.observedMask&1)?providedWitness.missing:0);
            decimalField(last,"gspClientObserved",!!(providedWitness.observedMask&2));
            decimalField(last,"gspClient",(providedWitness.observedMask&2)?providedWitness.gspClient:0);
        }else expect(last==NULL,"no invented constructor failure");
    }else{expect(!strstr(witness,"lastAttachStage=")&&!line("S540 first attach failure:"),"unavailable witness data not invented");if(witnessResult!=NV_OK)decimalField(witness,"status",witnessResult);else expect(strstr(witness,"shapeValid=0")!=NULL,"unknown witness shape explicit");}
    expect(logCalls==expectedLogs&&logCalls<=7,"fixed seven-record upper bound");
    expect(!memcmp(&oldSnapshot,&providedSnapshot,sizeof(oldSnapshot))&&!memcmp(&oldFresh,&providedFresh,sizeof(oldFresh))&&
        !memcmp(&oldAllocation,&providedAllocation,sizeof(oldAllocation))&&!memcmp(&oldWitness,&providedWitness,sizeof(oldWitness)),"diagnostics mutate no source record or counter");
}
int main(void) {
    NvU32 bits;
    for(bits=0;bits<16;++bits){reset();if(bits&1)snapshotResult=NV_ERR_INVALID_STATE;
        if(bits&2)freshResult=NV_ERR_NOT_READY;if(bits&4)allocationResult=NV_ERR_INVALID_STATE;
        if(bits&8)witnessResult=NV_ERR_OBJECT_NOT_FOUND;failure();}
    reset();providedAllocation.format=2;failure();reset();providedAllocation.bytes--;failure();
    reset();providedAllocation.firstFailureState=3;failure();reset();providedAllocation.observedMask=0;failure();reset();providedAllocation.observedMask=5;failure();
    reset();providedWitness.format=2;failure();reset();providedWitness.bytes--;failure();
    reset();providedAllocation.observedMask=1;providedAllocation.firstFailureState=1;failure();reset();providedWitness.firstFailureValid=0;failure();
    reset();providedAllocation.firstFailure.cpuObservedMask=0;failure();
    reset();providedAllocation.firstFailure.pageBytes=0x1234567890ULL;failure();
    reset();providedWitness.observedMask=0;providedWitness.missing=99;providedWitness.gspClient=99;failure();
    reset();memset(&providedFresh,0,sizeof(providedFresh));failure();
    reset();expect(s540GspContextInitializeAdapter(&context)==NV_OK&&context.state.adapterInitialized&&
        (context.nv.flags&NV_FLAG_INITIALIZED)&&!context.state.quarantined&&!snapshotCalls&&!freshCalls&&!allocationCalls&&!witnessCalls&&!logCalls,"successful wrapper has no failure diagnostics");
    reset();adapterResult=NV_FALSE;expect(s540GspContextInitializeAdapter(&context)==NV_ERR_NOT_READY&&context.state.quarantined&&!snapshotCalls&&!logCalls,"clean-wrapper Boolean refusal path unchanged");
    reset();ownerAllowed=NV_FALSE;expect(s540GspContextInitializeAdapter(&context)==NV_ERR_INVALID_STATE&&!adapterCalls&&!snapshotCalls&&!logCalls,"owner refusal unchanged");
    reset();enterResult=NV_ERR_TIMEOUT;expect(s540GspContextInitializeAdapter(&context)==NV_ERR_TIMEOUT&&!adapterCalls&&!snapshotCalls&&!logCalls,"enter refusal unchanged");
    reset();irqResult=NV_ERR_NOT_SUPPORTED;expect(s540GspContextInitializeAdapter(&context)==NV_ERR_NOT_SUPPORTED&&!enterCalls&&!adapterCalls&&!snapshotCalls&&!logCalls,"IRQ refusal unchanged");
    reset();preflightResult=NV_ERR_NOT_SUPPORTED;expect(s540GspContextInitializeAdapter(&context)==NV_ERR_NOT_SUPPORTED&&!enterCalls&&!adapterCalls&&!snapshotCalls&&!logCalls,"feature preflight refusal unchanged");
    printf("{\"status\":\"passed\",\"cases\":%u,\"checks\":%u,\"nonlogging_cases\":6}\n",cases,checks);return 0;
}
