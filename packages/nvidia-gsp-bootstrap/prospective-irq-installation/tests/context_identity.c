/* SPDX-License-Identifier: MIT */
/* Execute the unchanged production identity include with complete original
 * NVIDIA headers and the exact composed Context storage. Ordinary execution,
 * metadata registry, strong master snapshot and backend observations below
 * are explicit endpoint fixtures, not whole-session or hardware evidence. */
#include "nv.h"
#include "nv-priv.h"
#include "S540NvidiaGspContext.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaDarwinServices.h"
#include "../S540NvidiaGspIrqIdentity.h"
#include <stdio.h>
#include <stdlib.h>
/* Host fixture initialization/comparison uses libc, outside RM namespace. */
#undef memset
#undef memcmp
#include <string.h>

#include "actual-context-layout.inc"

static S540GspContext context, foreignContext;
static nv_priv_t privateState;
static S540GspContext *metadataContext;
static S540FirstTxnGlobalSnapshot master;
static S540GspIrqModeFacts observedMode;
static NvBool ordinary;
static NvU64 currentThread;
static NV_STATUS threadStatus, masterStatus, backendStatus;
static NvU32 checks, failures, masterReads, backendReads, threadReads;
static NvU32 originalAdapterCalls;
static int pciToken, guardToken, ownerToken, foreignToken;

static void require(NvBool value) { if(!value)abort(); }
static void expect(NvBool value,const char *message) {
    ++checks;
    if(!value){++failures;fprintf(stderr,"context identity: %s\n",message);}
}
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void) { return ordinary; }
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *thread) {
    require(thread!=NULL);++threadReads;
    if(threadStatus==NV_OK)*thread=currentThread;
    return threadStatus;
}
NV_STATUS s540FirstTxnGlobalReadMaster(S540FirstTxnGlobalSnapshot *snapshot) {
    require(snapshot!=NULL);++masterReads;
    if(masterStatus==NV_OK)*snapshot=master;
    return masterStatus;
}
NV_STATUS s540GspIrqReadBackendMode(const void *nv,S540GspIrqModeFacts *facts) {
    require(nv==&context.nv && facts!=NULL);++backendReads;
    if(backendStatus==NV_OK)*facts=observedMode;
    return backendStatus;
}
/* This endpoint must never be reached by installation identity/mode work. */
NvBool NV_API_CALL rm_init_adapter(nvidia_stack_t *stack,nv_state_t *nv) {
    (void)stack;(void)nv;++originalAdapterCalls;abort();
}

#include "actual-context-owner.inc"
#include "../context-identity.c.inc"

static void reset(void) {
    NvU32 i;
    memset(&context,0,sizeof(context));memset(&privateState,0,sizeof(privateState));
    context.nv.priv=&privateState;context.nv.handle=&pciToken;
    context.ownerThread=0x1234;context.firstTxnGeneration=0x5678;
    context.isrGuard=&guardToken;context.metadataBound=NV_TRUE;
    context.state.created=context.state.eventLocks=context.state.privateState=NV_TRUE;
    for(i=0;i<STACKS;++i){context.stacks[i].size=sizeof(context.stacks[i].stack);
        context.stacks[i].top=context.stacks[i].stack+context.stacks[i].size;}
    metadataContext=&context;ordinary=NV_TRUE;currentThread=context.ownerThread;
    threadStatus=masterStatus=backendStatus=NV_OK;
    memset(&master,0,sizeof(master));master.owner=&ownerToken;master.nv=&context.nv;
    master.generation=context.firstTxnGeneration;master.masterThread=context.ownerThread;
    master.validated=NV_TRUE;master.state=S540_FIRST_GLOBAL_READY;
    memset(&observedMode,0,sizeof(observedMode));observedMode.nv=&context.nv;
    observedMode.generation=context.firstTxnGeneration;
    observedMode.known=observedMode.messageSignaled=observedMode.msiCapable=NV_TRUE;
    observedMode.interruptType=0x55;observedMode.msiVectors=1;
    masterReads=backendReads=threadReads=0;
}
static S540GspIrqIdentity identity(void) {
    S540GspIrqIdentity id;
    require(s540GspContextReadIrqIdentity(&context,&id)==NV_OK);
    return id;
}
static void readRefused(S540GspContext *selected,NV_STATUS status,const char *message) {
    S540GspIrqIdentity output,unchanged;
    memset(&output,0xa5,sizeof(output));unchanged=output;
    expect(s540GspContextReadIrqIdentity(selected,&output)==status &&
        !memcmp(&output,&unchanged,sizeof(output)),message);
}
static void modeRefused(const S540GspIrqIdentity *id,NV_STATUS status,const char *message) {
    NvU32 unchanged=context.nv.flags;
    expect(s540GspContextSelectMessageInterrupt(&context,id)==status &&
        (NvU32)context.nv.flags==unchanged,message);
}
#define REFUSE_READ(change,message) do { reset();change;readRefused(&context,NV_ERR_INVALID_STATE,message); } while(0)
#define FORGE(field,value,message) do { reset();id=identity();id.field=(value);expect(!s540GspContextMatchIrqIdentity(&context,&id),message); } while(0)
#define REFUSE_MODE(change,status,message) do { reset();id=identity();change;modeRefused(&id,status,message); } while(0)

int main(void) {
    S540GspIrqIdentity id;
    NvU32 i,reads;
    const NvU32 roles[]={MAIN,ISR,LOCKED_BH,UNLOCKED_BH};
    reset();id=identity();
    expect(id.context==&context && id.nv==&context.nv && id.privateState==context.nv.priv &&
        id.pciHandle==context.nv.handle && id.isrGuard==context.isrGuard &&
        id.ownerThread==context.ownerThread && id.generation==context.firstTxnGeneration,
        "identity derives original private/pci/owner/epoch storage");
    expect(id.mainStack==&context.stacks[MAIN] && id.isrStack==&context.stacks[ISR] &&
        id.lockedStack==&context.stacks[LOCKED_BH] && id.unlockedStack==&context.stacks[UNLOCKED_BH] &&
        id.mainStack!=id.isrStack && id.isrStack!=id.lockedStack && id.lockedStack!=id.unlockedStack,
        "main ISR locked and unlocked BH own distinct exact Context stack slots");
    expect(!privateState.flags && privateState.pGpu==NULL && !context.state.adapterAttempted,
        "identity acquisition succeeds with private-only storage before any original adapter attempt");
    expect(s540GspContextMatchIrqIdentity(&context,&id) && masterReads==1 && threadReads==1,
        "read requires actual ordinary owner plus one strong master snapshot");
    expect(!s540GspContextMatchIrqIdentity(NULL,&id) && !s540GspContextMatchIrqIdentity(&context,NULL) &&
        !s540GspContextMatchIrqIdentity(&foreignContext,&id),"null and foreign identity subjects refuse");
    expect(!irqStackInitialized(NULL) && !irqStackInitialized((nvidia_stack_t *)((NvU8 *)&context.stacks[MAIN]+1)),
        "null and misaligned stack addresses refuse before member access");
    for(i=0;i<4;++i)expect(irqStackInitialized(&context.stacks[roles[i]]) &&
        !((NvUPtr)&context.stacks[roles[i]]&15U) && !((NvUPtr)context.stacks[roles[i]].stack&15U),
        "original owned stack and payload obey 16-byte alignment");

    reset();readRefused(NULL,NV_ERR_INVALID_STATE,"null Context leaves output unchanged");
    expect(s540GspContextReadIrqIdentity(&context,NULL)==NV_ERR_INVALID_STATE,"null identity output refuses");
    REFUSE_READ(ordinary=NV_FALSE,"nonordinary owner leaves output unchanged");
    expect(!masterReads && !threadReads,"nonordinary refusal reaches no thread or global-master query");
    REFUSE_READ(currentThread++,"foreign thread leaves output unchanged");
    REFUSE_READ(threadStatus=NV_ERR_TIMEOUT,"failed thread read leaves output unchanged");
    REFUSE_READ(context.metadataBound=NV_FALSE,"unbound metadata leaves output unchanged");
    REFUSE_READ(metadataContext=&foreignContext,"foreign actual metadata registry leaves output unchanged");
    REFUSE_READ(metadataContext=NULL,"missing actual metadata registry leaves output unchanged");
    REFUSE_READ(context.state.created=NV_FALSE,"uncreated Context leaves output unchanged");
    REFUSE_READ(context.state.eventLocks=NV_FALSE,"missing event locks leave output unchanged");
    REFUSE_READ(context.state.privateState=NV_FALSE,"missing private lifecycle leaves output unchanged");
    REFUSE_READ(context.nv.priv=NULL,"null actual original private pointer leaves output unchanged");
    REFUSE_READ(context.isrGuard=NULL,"missing actual ISR guard leaves output unchanged");
    REFUSE_READ(context.state.originalReleased=NV_TRUE,"released original storage leaves output unchanged");
    REFUSE_READ(context.state.finalDetach=NV_TRUE,"detached Context leaves output unchanged");
    REFUSE_READ(context.state.quarantined=NV_TRUE,"quarantined Context leaves output unchanged");
    REFUSE_READ(context.firstTxnGeneration=0,"missing transaction epoch leaves output unchanged");
    reset();masterStatus=NV_ERR_TIMEOUT;readRefused(&context,NV_ERR_TIMEOUT,"strong master refusal is propagated unchanged");
    REFUSE_READ(master.nv=&foreignToken,"foreign global nv leaves output unchanged");
    REFUSE_READ(master.generation++,"foreign global generation leaves output unchanged");
    REFUSE_READ(master.masterThread++,"foreign global master leaves output unchanged");
    REFUSE_READ(master.owner=NULL,"missing strong global owner leaves output unchanged");
    REFUSE_READ(master.validated=NV_FALSE,"unvalidated strong global epoch leaves output unchanged");
    REFUSE_READ(master.state=S540_FIRST_GLOBAL_RETURNED,"nonready strong global epoch leaves output unchanged");
    for(i=0;i<4;++i){reset();context.stacks[roles[i]].size--;
        readRefused(&context,NV_ERR_INVALID_STATE,"wrong original stack extent leaves output unchanged");}
    for(i=0;i<4;++i){reset();context.stacks[roles[i]].top=context.stacks[roles[i]].stack;
        readRefused(&context,NV_ERR_INVALID_STATE,"wrong original stack top leaves output unchanged");}

    FORGE(context,&foreignContext,"forged Context identity refuses");
    FORGE(nv,&foreignToken,"forged original nv identity refuses");
    FORGE(pciHandle,&foreignToken,"forged PCI handle identity refuses");
    FORGE(mainStack,&context.stacks[ISR],"forged main stack identity refuses");
    FORGE(isrStack,&context.stacks[MAIN],"forged ISR stack identity refuses");
    FORGE(lockedStack,&context.stacks[UNLOCKED_BH],"forged locked BH stack identity refuses");
    FORGE(unlockedStack,&context.stacks[LOCKED_BH],"forged unlocked BH stack identity refuses");
    FORGE(privateState,&foreignToken,"forged original private pointer refuses");
    FORGE(isrGuard,&foreignToken,"forged ISR guard identity refuses");
    FORGE(ownerThread,context.ownerThread+1,"forged original owner thread refuses");
    FORGE(generation,context.firstTxnGeneration+1,"forged original epoch refuses");
    FORGE(generation,0,"zero identity epoch refuses");
    reset();id=identity();ordinary=NV_FALSE;currentThread++;context.state.adapterAttempted=NV_TRUE;
    reads=threadReads;
    expect(s540GspContextMatchIrqIdentity(&context,&id) && threadReads==reads && masterReads==1,
        "hard-ISR immutable identity match queries no ordinary-thread/master endpoint or mutable adapter flag");

    reset();id=identity();context.nv.flags=(NvU32)0xffffU&~(NV_FLAG_USES_MSI|NV_FLAG_USES_MSIX);
    reads=context.nv.flags;
    expect(s540GspContextSelectMessageInterrupt(&context,&id)==NV_OK &&
        (NvU32)context.nv.flags==(reads|NV_FLAG_USES_MSI) && backendReads==1,
        "actual backend facts select exact original MSI flag preserving every unrelated flag");
    modeRefused(&id,NV_ERR_IN_USE,"prior MSI selection refuses without changing flags");
    REFUSE_MODE(context.nv.flags=NV_FLAG_USES_MSIX,NV_ERR_IN_USE,"prior MSI-X selection refuses");
    REFUSE_MODE(observedMode.known=NV_FALSE,NV_ERR_NOT_SUPPORTED,"unknown backend mode refuses");
    REFUSE_MODE(observedMode.messageSignaled=NV_FALSE,NV_ERR_NOT_SUPPORTED,"actual nonmessaged interrupt refuses");
    REFUSE_MODE(observedMode.msiCapable=NV_FALSE,NV_ERR_NOT_SUPPORTED,"missing actual MSI capability refuses");
    REFUSE_MODE(observedMode.msixCapable=NV_TRUE,NV_ERR_NOT_SUPPORTED,"actual MSI-X-capable backend refuses");
    REFUSE_MODE(observedMode.msiVectors=0,NV_ERR_NOT_SUPPORTED,"zero actual MSI vectors refuse");
    REFUSE_MODE(observedMode.msiVectors=2,NV_ERR_NOT_SUPPORTED,"multiple actual MSI vectors refuse");
    REFUSE_MODE(observedMode.nv=&foreignToken,NV_ERR_NOT_SUPPORTED,"foreign backend nv facts refuse");
    REFUSE_MODE(observedMode.generation++,NV_ERR_NOT_SUPPORTED,"foreign backend epoch facts refuse");
    REFUSE_MODE(backendStatus=NV_ERR_TIMEOUT,NV_ERR_TIMEOUT,"actual backend refusal status propagates");
    REFUSE_MODE(context.state.adapterAttempted=NV_TRUE,NV_ERR_INVALID_STATE,"mode mutation refuses after original adapter attempt");
    expect(!backendReads,"adapter-attempt refusal precedes any backend query");
    REFUSE_MODE(context.state.originalReleased=NV_TRUE,NV_ERR_INVALID_STATE,"mode mutation refuses after original release");
    REFUSE_MODE(context.state.quarantined=NV_TRUE,NV_ERR_INVALID_STATE,"mode mutation refuses quarantine");
    REFUSE_MODE(ordinary=NV_FALSE,NV_ERR_INVALID_STATE,"mode mutation requires ordinary owner");
    expect(!backendReads,"nonordinary refusal precedes backend query");
    REFUSE_MODE(currentThread++,NV_ERR_INVALID_STATE,"mode mutation rejects foreign owner thread");
    REFUSE_MODE(id.generation++,NV_ERR_INVALID_STATE,"mode mutation rejects forged retained identity");
    expect(!backendReads,"forged-identity refusal precedes backend query");
    expect(!originalAdapterCalls,"identity and mode selection execute no original adapter initialization");
    printf("{\"checks\":%u,\"failures\":%u,\"original_adapter_calls\":%u}\n",checks,failures,originalAdapterCalls);
    return failures?1:0;
}
