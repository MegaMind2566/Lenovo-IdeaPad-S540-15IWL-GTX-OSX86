/* SPDX-License-Identifier: MIT; scratch strong record. No readiness fallback. */
#include "S540NvidiaGspFirstTransaction.h"
#include "deps/nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#define LD(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define ST(p,v) __atomic_store_n((p),(v), __ATOMIC_RELEASE)
#define CAPACITY 64
#define FREE_UNIT (1ULL << 48)
#define TAG_ID_MAX (~(NvU64)0 >> 3)
enum { READY=1, CLAIMED=2, ACTIVE=3, RETAINED=4, COMPLETE=5 };
enum { SITE_BIND=1, SITE_ROOT=2, SITE_PHASE=3, SITE_SERVICE=4,
       SITE_OWNER=5, SITE_EVENT=6, SITE_WORK=7, SITE_DIRECT=8, SITE_HOST=9 };
/* control atomically orders first status/site against every committed physical
 * free permit. Low32 status, next16 site, upper16 outstanding free permits. */
static struct {
    NvU64 control, generation, masterThread, nextId, anchor, cancelToken, sealSerial;
    const void *owner, *nv;
    NvU32 phase, gate, freeGate, originalInFlight, originalExitReady,
          originalReturned, cleanupRequested, firmwareRetained;
    const void *firmware[3];
    NvU32 workAccepted, workOriginalReturned, workActionReturned,
          directAccepted, directOriginalReturned, directActionReturned;
    S540FirstTxnServiceCounters counters;
} record;
typedef struct Entry {
    NvU64 tag, thread, cancellation, eventId, arm;
    const void *service, *data;
    NvU32 descriptor, originalReturned;
} Entry;
static Entry work[CAPACITY], direct[CAPACITY];
static struct { NvU64 id; const void *object; NvUPtr classId; } owners[CAPACITY];
static struct {
    NvU64 id, ownerId, borrowers, lastArm;
    const void *event, *timer;
    NvU32 descriptor, sealed, destroyed;
} events[CAPACITY];
static const void *unknownObjects[CAPACITY];
static struct { const void *allocation, *mapping, *mappingPriv; } retainedAllocations[CAPACITY];
static struct { NvU64 id, thread; } frees[CAPACITY];
static NvU64 lastEpoch;
extern NV_STATUS s540GlobalRmHostRetentionPreflight(void);
static NvU64 currentThread(void) {
    NvU64 tid=0; return s540Darwin_os_get_current_thread(&tid)==NV_OK ? tid : 0;
}
static NvBool bound(void) { return LD(&record.generation)!=0; }
static NvBool exact(const void *nv) { return bound() && nv && nv==LD(&record.nv); }
static NvBool master(void) { NvU64 tid=currentThread(); return tid && tid==LD(&record.masterThread); }
static NV_STATUS first(void) { return (NV_STATUS)(NvU32)LD(&record.control); }
static NV_STATUS refuse(NV_STATUS status, NvU32 site) {
    NvU64 old, desired;
    if (status==NV_OK) status=NV_ERR_INVALID_STATE;
    old=LD(&record.control);
    for (;;) {
        if ((NvU32)old) { status=(NV_STATUS)(NvU32)old; break; }
        desired=(old & 0xffff000000000000ULL) | ((NvU64)(site & 0xffffU)<<32) | (NvU32)status;
        if (__atomic_compare_exchange_n(&record.control,&old,desired,NV_FALSE,
            __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)) break;
    }
    ST(&record.phase,(NvU32)S540_FIRST_RETAINED);
    return status;
}
static NV_STATUS lockGate(void) {
    NvU32 empty=0;
    return __atomic_compare_exchange_n(&record.gate,&empty,1U,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE) ? NV_OK : NV_ERR_BUSY_RETRY;
}
static void unlockGate(void) { ST(&record.gate,0U); }
static NvU64 nextId(void) {
    NvU64 id=__atomic_add_fetch(&record.nextId,1ULL,__ATOMIC_RELAXED);
    return id && id<=TAG_ID_MAX ? id : 0;
}
static NvS32 active(Entry *entries,NvU64 tid) {
    NvU32 i; if(!tid)return -1;
    for(i=0;i<CAPACITY;++i) if((LD(&entries[i].tag)&7)==ACTIVE && LD(&entries[i].thread)==tid) return (NvS32)i;
    return -1;
}
static NvBool authorized(void) {
    NvU64 tid=currentThread();
    return bound() && tid && (tid==LD(&record.masterThread) || active(work,tid)>=0 || active(direct,tid)>=0);
}
static NvS32 findEntry(Entry *entries,NvU64 id) {
    NvU32 i; if(!id)return -1;
    for(i=0;i<CAPACITY;++i) if((LD(&entries[i].tag)>>3)==id) return (NvS32)i;
    return -1;
}
static NvS32 freeEntry(Entry *entries) {
    NvU32 i; for(i=0;i<CAPACITY;++i)if(!LD(&entries[i].tag))return (NvS32)i; return -1;
}
static NvS32 eventIndex(const void *event,NvU64 id) {
    NvU32 i; for(i=0;i<CAPACITY;++i)if(LD(&events[i].id) && events[i].event==event && (!id||events[i].id==id))return (NvS32)i; return -1;
}
static NvS32 ownerIndex(const void *object) {
    NvU32 i; for(i=0;i<CAPACITY;++i)if(LD(&owners[i].id)&&owners[i].object==object)return (NvS32)i; return -1;
}
static NvS32 descriptor(NvU32 role,NvUPtr callback,NvUPtr classId,NvU32 flags) {
    NvU32 i;
    for(i=0;i<s540FirstTxnOriginalDescriptorCount;++i){
        const S540FirstTxnOriginalDescriptor *d=&s540FirstTxnOriginalDescriptors[i];
        if(d->role==role && d->policy==S540_FIRST_ESSENTIAL_RUN_OR_RETAIN &&
           d->callback==callback && d->ownerClass==classId &&
           (flags & d->flagsMask)==d->flagsValue) return (NvS32)i;
    }
    return -1;
}
static NvU32 liveEntries(Entry *entries) {
    NvU32 i,n=0;for(i=0;i<CAPACITY;++i)if(LD(&entries[i].tag))++n;return n;
}
static NvU64 borrowers(void) {
    NvU32 i;NvU64 n=0;for(i=0;i<CAPACITY;++i)if(LD(&events[i].id))n+=LD(&events[i].borrowers);return n;
}
static NV_STATUS checkedMaster(const void *nv) {
    return exact(nv) && master() && s540Darwin_os_semaphore_may_sleep() ? NV_OK : NV_ERR_INVALID_STATE;
}
static NV_STATUS serviceContext(const void *service,const void *data,NvU32 stage,NvBool timer,NvU64 arm) {
    S540FirstTxnServiceContext context={0};
    NV_STATUS status=timer ? s540FirstTxnServicesReadTimerContext(service,&context) : s540FirstTxnServicesReadQueueContext(service,&context);
    if(status!=NV_OK)return status;
    if(context.stage!=stage || context.thread!=currentThread() ||
       (!timer && context.generation!=LD(&record.generation)) ||
       (timer && context.generation!=arm) || context.data!=data) return NV_ERR_INVALID_STATE;
    return NV_OK;
}
static NV_STATUS checkExecution(void) {
    NV_STATUS status=first();
    if(status!=NV_OK)return status;
    if(!s540GspCancellationCurrentScopeActive())return NV_ERR_INVALID_STATE;
    return s540GspCancellationCheckCurrent();
}
NV_STATUS s540FirstTxnBeginOwner(const void *owner) {
    NvU32 empty=S540_FIRST_UNBOUND;NvU64 tid=currentThread(),epoch;NV_STATUS status;
    if(!owner||!tid||!s540Darwin_os_semaphore_may_sleep())return NV_ERR_INVALID_ARGUMENT;
    if(!__atomic_compare_exchange_n(&record.phase,&empty,~0U,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_ERR_IN_USE;
    status=s540GlobalRmHostRetentionPreflight();
    if(status!=NV_OK && first()==NV_OK){
        empty=~0U;
        if(__atomic_compare_exchange_n(&record.phase,&empty,(NvU32)S540_FIRST_UNBOUND,NV_FALSE,
            __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return status;
        /* A real refusal raced preflight failure. Preserve its retained owner. */
    }
    epoch=__atomic_add_fetch(&lastEpoch,1ULL,__ATOMIC_RELAXED);
    if(!epoch)return refuse(NV_ERR_INSUFFICIENT_RESOURCES,SITE_BIND);
    record.owner=owner;record.masterThread=tid;
    ST(&record.generation,epoch);
    empty=~0U;
    (void)__atomic_compare_exchange_n(&record.phase,&empty,(NvU32)S540_FIRST_OP,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
    /* Never overwrite RETAINED published by a genuine failure while reserving.
     * Source hooks run after their monotonic counter publication; an unbound
     * earlier refusal is instead observed by actual preflight. */
    return first();
}
NV_STATUS s540FirstTxnBind(const void *nv,S540GspCancellationToken token) {
    S540GspCancellationSnapshot snapshot={0};S540GspCancellationLease anchor=0;NV_STATUS status;
    if(!bound()||!master()||!nv||LD(&record.nv)||LD(&record.phase)!=S540_FIRST_OP)return NV_ERR_INVALID_STATE;
    status=s540GspCancellationGetSnapshot(token,&snapshot);
    if(status!=NV_OK||!snapshot.bound||snapshot.generation!=token||snapshot.ownerThread!=currentThread()||snapshot.phase!=S540_GSP_CANCEL_OPERATION)
        return refuse(status!=NV_OK?status:NV_ERR_INVALID_STATE,SITE_BIND);
    status=s540GspCancellationCaptureCurrent(nv,&anchor); /* Exact actual nv identity. */
    if(status!=NV_OK)return refuse(status,SITE_BIND);
    record.cancelToken=token;record.anchor=anchor;ST(&record.nv,nv);
    return first();
}
NV_STATUS s540FirstTxnOriginalEnter(const void *nv) {
    NvU32 empty=0;NV_STATUS status;
    if(checkedMaster(nv)!=NV_OK||LD(&record.phase)!=S540_FIRST_OP||LD(&record.originalReturned))return NV_ERR_INVALID_STATE;
    status=checkExecution();if(status!=NV_OK)return refuse(status,SITE_ROOT);
    if(!__atomic_compare_exchange_n(&record.originalInFlight,&empty,1U,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_IN_USE,SITE_ROOT);
    return NV_OK;
}
NV_STATUS s540FirstTxnRequestDeferredCleanup(const void *nv,NV_STATUS failure) {
    if(checkedMaster(nv)!=NV_OK||!LD(&record.originalInFlight))return NV_ERR_INVALID_STATE;
    ST(&record.cleanupRequested,1U);return refuse(failure,SITE_ROOT);
}
NV_STATUS s540FirstTxnRetainInitFirmware(const void *nv,const void *fw,const void *log,const void *ucodes) {
    const void *values[3]={fw,log,ucodes};NvU32 i;
    if(checkedMaster(nv)!=NV_OK||!LD(&record.originalInFlight))return NV_ERR_INVALID_STATE;
    if(LD(&record.firmwareRetained)){
        for(i=0;i<3;++i)if(record.firmware[i]!=values[i])return refuse(NV_ERR_INVALID_STATE,SITE_ROOT);
        return NV_OK;
    }
    for(i=0;i<3;++i)record.firmware[i]=values[i];ST(&record.firmwareRetained,1U);return NV_OK;
}
NV_STATUS s540FirstTxnRetainOriginalAllocation(const void *nv,const void *allocation,const void *mapping,const void *mappingPriv) {
    NvU32 i;NV_STATUS status;
    if(!exact(nv)||!authorized()||!allocation)return NV_ERR_INVALID_ARGUMENT;
    status=lockGate();if(status!=NV_OK)return refuse(status,SITE_ROOT);
    for(i=0;i<CAPACITY;++i)if(retainedAllocations[i].allocation==allocation){
        status=retainedAllocations[i].mapping==mapping && retainedAllocations[i].mappingPriv==mappingPriv?NV_OK:NV_ERR_INVALID_STATE;
        unlockGate();return refuse(status==NV_OK?NV_ERR_INVALID_STATE:status,SITE_ROOT);
    }
    for(i=0;i<CAPACITY;++i)if(!retainedAllocations[i].allocation)break;
    if(i==CAPACITY){unlockGate();return refuse(NV_ERR_INSUFFICIENT_RESOURCES,SITE_ROOT);}
    retainedAllocations[i].mapping=mapping;retainedAllocations[i].mappingPriv=mappingPriv;
    ST(&retainedAllocations[i].allocation,allocation);unlockGate();return refuse(NV_ERR_INVALID_STATE,SITE_ROOT);
}
NV_STATUS s540FirstTxnOriginalExitReady(const void *nv,NV_STATUS outcome) {
    NV_STATUS status;
    if(checkedMaster(nv)!=NV_OK||!LD(&record.originalInFlight)||LD(&record.originalExitReady))return NV_ERR_INVALID_STATE;
    if(outcome!=NV_OK)(void)refuse(outcome,SITE_ROOT);
    status=s540FirstTxnOriginalLocksReleased(nv);
    if(status!=NV_OK)return refuse(status,SITE_ROOT);
    ST(&record.originalExitReady,1U);return first()!=NV_OK?first():outcome;
}
NV_STATUS s540FirstTxnOriginalWrapperReturned(const void *nv) {
    NV_STATUS status;
    if(checkedMaster(nv)!=NV_OK||!LD(&record.originalInFlight)||!LD(&record.originalExitReady))return NV_ERR_INVALID_STATE;
    status=s540FirstTxnOriginalLocksReleased(nv);if(status!=NV_OK)return refuse(status,SITE_ROOT);
    ST(&record.originalReturned,1U);ST(&record.originalInFlight,0U);return first();
}
NV_STATUS s540FirstTxnBeginClosing(const void *nv) {
    NvU32 expected=S540_FIRST_OP;NV_STATUS status;
    if(checkedMaster(nv)!=NV_OK||!LD(&record.originalReturned)||LD(&record.originalInFlight))return NV_ERR_INVALID_STATE;
    if(first()!=NV_OK)return first();
    status=s540FirstTxnOriginalLocksReleased(nv);if(status!=NV_OK)return refuse(status,SITE_PHASE);
    status=lockGate();if(status!=NV_OK)return refuse(status,SITE_PHASE);
    if(!__atomic_compare_exchange_n(&record.phase,&expected,(NvU32)S540_FIRST_CLOSING,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){unlockGate();return first()!=NV_OK?first():NV_ERR_INVALID_STATE;}
    unlockGate();return first();
}
NV_STATUS s540FirstTxnRegisterOwner(const void *nv,const void *object) {
    NvUPtr classId=0;NvS32 d;NvU32 i;NV_STATUS status;
    if(!exact(nv)||!object||!authorized()||LD(&record.phase)!=S540_FIRST_OP)return NV_ERR_INVALID_STATE;
    status=s540FirstTxnInspectOriginalOwner(object,&classId);
    if(status!=NV_OK)return refuse(status,SITE_OWNER);
    d=descriptor(S540_FIRST_DESC_OWNER,0,classId,0);if(d<0)return refuse(NV_ERR_NOT_SUPPORTED,SITE_OWNER);
    status=lockGate();if(status!=NV_OK)return refuse(status,SITE_OWNER);
    if(first()!=NV_OK||LD(&record.phase)!=S540_FIRST_OP){unlockGate();return refuse(NV_ERR_NOT_READY,SITE_OWNER);}
    if(ownerIndex(object)>=0){unlockGate();return NV_OK;}
    for(i=0;i<CAPACITY;++i)if(!LD(&owners[i].id))break;
    if(i==CAPACITY){unlockGate();return refuse(NV_ERR_INSUFFICIENT_RESOURCES,SITE_OWNER);}
    owners[i].object=object;owners[i].classId=classId;ST(&owners[i].id,nextId());unlockGate();return NV_OK;
}
NV_STATUS s540FirstTxnEventConstruct(const void *nv,const void *event,const void *timer,S540FirstTxnLease *out) {
    S540FirstTxnOriginalEvent metadata={0};NvS32 owner,d;NvU32 i;NV_STATUS status;
    if(out)*out=0;
    if(!exact(nv)||!event||!timer||!out||!authorized()||LD(&record.phase)!=S540_FIRST_OP)return NV_ERR_INVALID_STATE;
    status=s540FirstTxnInspectOriginalEvent(event,&metadata);if(status!=NV_OK)return refuse(status,SITE_EVENT);
    /* pUserData is opaque: do not inspect it as NVOC until callback row
     * authenticates a reviewed typed event registration. */
    d=-1;
    for(i=0;i<s540FirstTxnOriginalDescriptorCount;++i){
        const S540FirstTxnOriginalDescriptor *row=&s540FirstTxnOriginalDescriptors[i];
        if(row->role==S540_FIRST_DESC_EVENT && row->policy==S540_FIRST_ESSENTIAL_RUN_OR_RETAIN &&
           row->callback==metadata.callback && row->ownerClass){d=(NvS32)i;break;}
    }
    if(d<0)return refuse(NV_ERR_NOT_SUPPORTED,SITE_EVENT);
    owner=ownerIndex(metadata.owner);
    if(owner<0||owners[owner].classId!=s540FirstTxnOriginalDescriptors[d].ownerClass)return refuse(NV_ERR_INVALID_STATE,SITE_EVENT);
    status=lockGate();if(status!=NV_OK)return refuse(status,SITE_EVENT);
    if(first()!=NV_OK||LD(&record.phase)!=S540_FIRST_OP){unlockGate();return refuse(NV_ERR_NOT_READY,SITE_EVENT);}
    if(eventIndex(event,0)>=0){unlockGate();return refuse(NV_ERR_IN_USE,SITE_EVENT);}
    for(i=0;i<CAPACITY;++i)if(!LD(&events[i].id))break;
    if(i==CAPACITY){unlockGate();return refuse(NV_ERR_INSUFFICIENT_RESOURCES,SITE_EVENT);}
    events[i].event=event;events[i].timer=timer;events[i].ownerId=owners[owner].id;events[i].descriptor=(NvU32)d;
    ST(&events[i].id,nextId());*out=events[i].id;unlockGate();return NV_OK;
}
static NV_STATUS authenticateEvent(NvS32 e) {
    S540FirstTxnOriginalEvent metadata={0};NvS32 owner;NV_STATUS status;
    const S540FirstTxnOriginalDescriptor *row;
    if(e<0||LD(&events[e].destroyed))return NV_ERR_INVALID_STATE;
    row=&s540FirstTxnOriginalDescriptors[events[e].descriptor];
    status=s540FirstTxnInspectOriginalEvent(events[e].event,&metadata);
    if(status!=NV_OK)return status;
    owner=ownerIndex(metadata.owner);
    return row->role==S540_FIRST_DESC_EVENT && row->callback==metadata.callback && row->ownerClass &&
        owner>=0 && owners[owner].id==events[e].ownerId && owners[owner].classId==row->ownerClass ? NV_OK:NV_ERR_INVALID_STATE;
}
static NV_STATUS admit(const void *nv,const void *service,const void *data,NvU64 eventId,NvU64 arm,NvBool isDirect,NvU64 *out) {
    S540FirstTxnOriginalWork metadata={0};Entry *entries=isDirect?direct:work;NvS32 e=-1,d=-1,entry;NvU64 id;NvU32 phase;
    S540GspCancellationLease scope=0;NV_STATUS status;
    if(out)*out=0;
    if(!exact(nv)||!service||!data||!out)return NV_ERR_INVALID_ARGUMENT;
    status=serviceContext(service,data,S540_FIRST_SERVICE_ADMIT,isDirect,arm);
    if(status!=NV_OK)return refuse(status,isDirect?SITE_DIRECT:SITE_WORK);
    phase=LD(&record.phase);
    if(!authorized()||(phase!=S540_FIRST_OP && phase!=S540_FIRST_DRAINING))return refuse(NV_ERR_NOT_READY,isDirect?SITE_DIRECT:SITE_WORK);
    if(phase==S540_FIRST_DRAINING && master())return refuse(NV_ERR_NOT_READY,isDirect?SITE_DIRECT:SITE_WORK);
    status=checkExecution();if(status!=NV_OK)return refuse(status,isDirect?SITE_DIRECT:SITE_WORK);
    if(isDirect){
        e=eventIndex(data,eventId);
        if(e<0||events[e].timer!=service||LD(&events[e].sealed)||!arm)return refuse(NV_ERR_INVALID_STATE,SITE_DIRECT);
        status=authenticateEvent(e);if(status!=NV_OK)return refuse(status,SITE_DIRECT);
        d=(NvS32)events[e].descriptor;
    }else{
        status=s540FirstTxnInspectOriginalWork(data,&metadata);if(status!=NV_OK)return refuse(status,SITE_WORK);
        d=descriptor(S540_FIRST_DESC_WORK,metadata.callback,0,metadata.flags);
        if(d<0)return refuse(NV_ERR_NOT_SUPPORTED,SITE_WORK);
        if(s540FirstTxnOriginalDescriptors[d].eventArgument){
            e=eventIndex(metadata.parameter,0);
            if(e<0||LD(&events[e].sealed)||LD(&events[e].destroyed))return refuse(NV_ERR_INVALID_STATE,SITE_WORK);
        }
    }
    status=lockGate();if(status!=NV_OK)return refuse(status,isDirect?SITE_DIRECT:SITE_WORK);
    if(first()!=NV_OK){unlockGate();return first();}
    phase=LD(&record.phase);
    if((phase!=S540_FIRST_OP && phase!=S540_FIRST_DRAINING) || (phase==S540_FIRST_DRAINING && master())){
        unlockGate();return refuse(NV_ERR_NOT_READY,isDirect?SITE_DIRECT:SITE_WORK);
    }
    if(isDirect && arm<=LD(&events[e].lastArm)){unlockGate();return refuse(NV_ERR_INVALID_STATE,SITE_DIRECT);}
    entry=freeEntry(entries);id=nextId();
    if(entry<0||!id){unlockGate();return refuse(NV_ERR_INSUFFICIENT_RESOURCES,isDirect?SITE_DIRECT:SITE_WORK);}
    if(e>=0)__atomic_add_fetch(&events[e].borrowers,1ULL,__ATOMIC_ACQ_REL);
    status=s540GspCancellationCaptureCurrent(nv,&scope);
    if(status!=NV_OK){if(e>=0)__atomic_sub_fetch(&events[e].borrowers,1ULL,__ATOMIC_ACQ_REL);unlockGate();return refuse(status,isDirect?SITE_DIRECT:SITE_WORK);}
    if(isDirect)ST(&events[e].lastArm,arm);
    entries[entry].service=service;entries[entry].data=data;entries[entry].eventId=e>=0?events[e].id:0;
    entries[entry].arm=arm;entries[entry].descriptor=(NvU32)d;entries[entry].cancellation=scope;
    entries[entry].thread=0;entries[entry].originalReturned=0;
    ST(&entries[entry].tag,(id<<3)|READY);
    if(isDirect)__atomic_add_fetch(&record.directAccepted,1U,__ATOMIC_RELAXED);else __atomic_add_fetch(&record.workAccepted,1U,__ATOMIC_RELAXED);
    *out=id;unlockGate();return NV_OK;
}
NV_STATUS s540FirstTxnWorkAdmit(const void *nv,const void *q,const void *data,NvU64 *out){return admit(nv,q,data,0,0,NV_FALSE,out);}
NV_STATUS s540FirstTxnDirectAdmit(const void *nv,const void *t,const void *event,NvU64 eventId,NvU64 arm,NvU64 *out){return admit(nv,t,event,eventId,arm,NV_TRUE,out);}
NV_STATUS s540FirstTxnWorkRejected(const void *nv,const void *q,const void *data,NV_STATUS status) {
    NV_STATUS probe;if(!exact(nv)||!q||!data)return NV_ERR_INVALID_ARGUMENT;
    probe=serviceContext(q,data,S540_FIRST_SERVICE_ADMIT,NV_FALSE,0);
    return refuse(probe!=NV_OK?probe:status,SITE_WORK);
}
static NV_STATUS enter(const void *nv,const void *service,const void *data,NvU64 id,NvBool timer) {
    Entry *entries=timer?direct:work;NvS32 i=findEntry(entries,id),e;NvU64 tag;NV_STATUS status;
    if(!exact(nv)||i<0||entries[i].service!=service||entries[i].data!=data)return NV_ERR_INVALID_STATE;
    status=serviceContext(service,data,S540_FIRST_SERVICE_ENTER,timer,entries[i].arm);if(status!=NV_OK)return refuse(status,timer?SITE_DIRECT:SITE_WORK);
    if(first()!=NV_OK)return first();
    if(timer){
        e=eventIndex(data,entries[i].eventId);status=authenticateEvent(e);
    }else{
        S540FirstTxnOriginalWork metadata={0};
        status=s540FirstTxnInspectOriginalWork(data,&metadata);
        if(status==NV_OK && descriptor(S540_FIRST_DESC_WORK,metadata.callback,0,metadata.flags)!=(NvS32)entries[i].descriptor)status=NV_ERR_INVALID_STATE;
        if(status==NV_OK && entries[i].eventId){
            e=eventIndex(metadata.parameter,entries[i].eventId);status=authenticateEvent(e);
        }
    }
    if(status!=NV_OK)return refuse(status,timer?SITE_DIRECT:SITE_WORK);
    tag=(id<<3)|READY;
    if(!__atomic_compare_exchange_n(&entries[i].tag,&tag,(id<<3)|CLAIMED,NV_FALSE,
       __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_IN_USE,timer?SITE_DIRECT:SITE_WORK);
    status=s540GspCancellationEnterLease(entries[i].cancellation,nv);
    if(status!=NV_OK){ST(&entries[i].tag,(id<<3)|RETAINED);return refuse(status,timer?SITE_DIRECT:SITE_WORK);}
    entries[i].thread=currentThread();ST(&entries[i].tag,(id<<3)|ACTIVE);
    status=checkExecution();
    if(status!=NV_OK){(void)s540GspCancellationLeaveLease(entries[i].cancellation,nv);ST(&entries[i].thread,0ULL);ST(&entries[i].tag,(id<<3)|RETAINED);return refuse(status,timer?SITE_DIRECT:SITE_WORK);}
    return NV_OK;
}
NV_STATUS s540FirstTxnWorkEnter(const void *nv,const void *q,const void *data,NvU64 id){return enter(nv,q,data,id,NV_FALSE);}
NV_STATUS s540FirstTxnDirectEnter(const void *nv,const void *t,NvU64 id){NvS32 i=findEntry(direct,id);return i<0?NV_ERR_INVALID_STATE:enter(nv,t,direct[i].data,id,NV_TRUE);}
static NV_STATUS originalReturned(const void *nv,NV_STATUS status,NvBool timer) {
    Entry *entries=timer?direct:work;NvS32 i=active(entries,currentThread());NvU32 empty=0;
    if(!exact(nv)||i<0||!s540GspCancellationCurrentScopeActive())return NV_ERR_INVALID_STATE;
    /* Original action executes outside the service guard. Its active ticket,
     * exact real thread and explicit original call site authenticate this mark;
     * shared service stage can legitimately change during concurrent admit. */
    if(!__atomic_compare_exchange_n(&entries[i].originalReturned,&empty,1U,NV_FALSE,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_IN_USE,timer?SITE_DIRECT:SITE_WORK);
    if(timer)__atomic_add_fetch(&record.directOriginalReturned,1U,__ATOMIC_RELAXED);else __atomic_add_fetch(&record.workOriginalReturned,1U,__ATOMIC_RELAXED);
    if(status!=NV_OK)return refuse(status,timer?SITE_DIRECT:SITE_WORK);
    return NV_OK;
}
NV_STATUS s540FirstTxnWorkOriginalReturned(const void *nv,NV_STATUS s){return originalReturned(nv,s,NV_FALSE);}
NV_STATUS s540FirstTxnDirectOriginalReturned(const void *nv,NV_STATUS s){return originalReturned(nv,s,NV_TRUE);}
static void releaseBorrow(Entry *entry) {
    NvU32 i;if(!entry->eventId)return;
    for(i=0;i<CAPACITY;++i)if(LD(&events[i].id)==entry->eventId){
        NvU64 old=LD(&events[i].borrowers);
        while(old && !__atomic_compare_exchange_n(&events[i].borrowers,&old,old-1,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){}
        if(!old)(void)refuse(NV_ERR_INVALID_STATE,SITE_EVENT);return;
    }
    (void)refuse(NV_ERR_INVALID_STATE,SITE_EVENT);
}
static NV_STATUS returned(const void *nv,const void *service,NvU64 id,NvBool timer) {
    Entry *entries=timer?direct:work;NvS32 i=findEntry(entries,id);NvU64 tag;NV_STATUS status;
    if(!exact(nv)||i<0||entries[i].service!=service)return NV_ERR_INVALID_STATE;
    status=serviceContext(service,timer?entries[i].data:0,S540_FIRST_SERVICE_RETURNED,timer,entries[i].arm);
    if(status!=NV_OK)return refuse(status,timer?SITE_DIRECT:SITE_WORK);
    if(!LD(&entries[i].originalReturned)||entries[i].thread!=currentThread())return refuse(NV_ERR_INVALID_STATE,timer?SITE_DIRECT:SITE_WORK);
    tag=(id<<3)|ACTIVE;
    if(!__atomic_compare_exchange_n(&entries[i].tag,&tag,(id<<3)|CLAIMED,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_IN_USE,timer?SITE_DIRECT:SITE_WORK);
    status=s540GspCancellationLeaveLease(entries[i].cancellation,nv);
    ST(&entries[i].thread,0ULL);
    if(status!=NV_OK){ST(&entries[i].tag,(id<<3)|RETAINED);return refuse(status,timer?SITE_DIRECT:SITE_WORK);}
    /* The original may already have freed work data. Sticky failure retains the
     * transaction, never invents a still-live item after genuine action return. */
    releaseBorrow(&entries[i]);
    if(timer)__atomic_add_fetch(&record.directActionReturned,1U,__ATOMIC_RELAXED);else __atomic_add_fetch(&record.workActionReturned,1U,__ATOMIC_RELAXED);
    ST(&entries[i].tag,0ULL);return NV_OK;
}
NV_STATUS s540FirstTxnWorkReturned(const void *nv,const void *q,NvU64 id){return returned(nv,q,id,NV_FALSE);}
NV_STATUS s540FirstTxnDirectReturned(const void *nv,const void *t,NvU64 id){return returned(nv,t,id,NV_TRUE);}
NV_STATUS s540FirstTxnWorkRetain(const void *nv,const void *q,NvU64 id,NV_STATUS status) {
    NvS32 i=findEntry(work,id);S540FirstTxnServiceContext context={0};NV_STATUS probe;
    if(!exact(nv)||i<0||work[i].service!=q)return NV_ERR_INVALID_STATE;
    probe=s540FirstTxnServicesReadQueueContext(q,&context);
    if(probe!=NV_OK||context.thread!=currentThread()||context.data!=work[i].data||context.generation!=LD(&record.generation)||
       (context.stage!=S540_FIRST_SERVICE_ENTER&&context.stage!=S540_FIRST_SERVICE_RETURNED))return refuse(probe!=NV_OK?probe:NV_ERR_INVALID_STATE,SITE_WORK);
    if((LD(&work[i].tag)&7)==ACTIVE && work[i].thread==currentThread()){
        (void)s540GspCancellationLeaveLease(work[i].cancellation,nv);ST(&work[i].thread,0ULL);
    }
    ST(&work[i].tag,(id<<3)|RETAINED);return refuse(status,SITE_WORK);
}
NV_STATUS s540FirstTxnDirectRetain(const void *nv,const void *timer,NvU64 id,NV_STATUS status) {
    NvS32 i=findEntry(direct,id);S540FirstTxnServiceContext context={0};NV_STATUS probe;
    if(!exact(nv)||i<0||direct[i].service!=timer)return NV_ERR_INVALID_STATE;
    probe=s540FirstTxnServicesReadTimerContext(timer,&context);
    if(probe!=NV_OK||context.thread!=currentThread()||context.data!=direct[i].data||context.generation!=direct[i].arm||
       (context.stage!=S540_FIRST_SERVICE_ADMIT&&context.stage!=S540_FIRST_SERVICE_ENTER&&context.stage!=S540_FIRST_SERVICE_RETURNED&&context.stage!=S540_FIRST_SERVICE_CANCELLED))
        return refuse(probe!=NV_OK?probe:NV_ERR_INVALID_STATE,SITE_DIRECT);
    if((LD(&direct[i].tag)&7)==ACTIVE && direct[i].thread==currentThread()){
        (void)s540GspCancellationLeaveLease(direct[i].cancellation,nv);ST(&direct[i].thread,0ULL);
    }
    ST(&direct[i].tag,(id<<3)|RETAINED);return refuse(status,SITE_DIRECT);
}
NV_STATUS s540FirstTxnDirectCancelled(const void *nv,const void *t,NvU64 id) {
    NvS32 i=findEntry(direct,id);NvU64 tag;NV_STATUS status;
    if(!exact(nv)||!master()||i<0||direct[i].service!=t)return NV_ERR_INVALID_STATE;
    status=serviceContext(t,direct[i].data,S540_FIRST_SERVICE_CANCELLED,NV_TRUE,direct[i].arm);
    if(status!=NV_OK)return refuse(status,SITE_DIRECT);
    tag=(id<<3)|READY;
    if(!__atomic_compare_exchange_n(&direct[i].tag,&tag,(id<<3)|CLAIMED,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_IN_USE,SITE_DIRECT);
    status=s540GspCancellationDiscardLease(direct[i].cancellation,nv);
    if(status!=NV_OK){ST(&direct[i].tag,(id<<3)|RETAINED);return refuse(status,SITE_DIRECT);}
    releaseBorrow(&direct[i]);ST(&direct[i].tag,0ULL);return NV_OK;
}
static NV_STATUS inspectCounters(const void *nv) {
    S540FirstTxnServiceCounters view={0};NV_STATUS status=s540FirstTxnOriginalReadServiceCounters(nv,&view);
    if(status!=NV_OK)return refuse(status,SITE_SERVICE);
#define CACHE(field) ST(&record.counters.field,view.field)
    CACHE(hostInitialized);CACHE(cryptoOverflow);CACHE(hostUnavailable);CACHE(hostInvalidFrees);
    CACHE(memoryUnavailableEver);CACHE(memoryViolationsEver);CACHE(cryptoUnavailable);CACHE(cryptoMaskLow);CACHE(cryptoMaskHigh);
#undef CACHE
    if(!view.hostInitialized||view.hostUnavailable||view.hostInvalidFrees||view.memoryUnavailableEver||view.memoryViolationsEver||
       view.cryptoUnavailable||view.cryptoMaskLow||view.cryptoMaskHigh||view.cryptoOverflow)return refuse(NV_ERR_INVALID_STATE,SITE_SERVICE);
    return NV_OK;
}
NV_STATUS s540FirstTxnSeal(const void *nv) {
    NvU32 expected=S540_FIRST_CLOSING,i;NV_STATUS status;
    if(checkedMaster(nv)!=NV_OK)return NV_ERR_INVALID_STATE;
    if(first()!=NV_OK)return first();
    status=s540FirstTxnOriginalLocksReleased(nv);if(status!=NV_OK)return refuse(status,SITE_PHASE);
    if(!__atomic_compare_exchange_n(&record.phase,&expected,(NvU32)S540_FIRST_DRAINING,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_ERR_INVALID_STATE;
    status=s540FirstTxnServicesSealAndDrain(nv,LD(&record.generation));if(status!=NV_OK)return refuse(status,SITE_SERVICE);
    status=s540FirstTxnServicesValidateRetired(nv,LD(&record.generation));if(status!=NV_OK)return refuse(status,SITE_SERVICE);
    if(first()!=NV_OK)return first();
    if(LD(&record.gate)||LD(&record.freeGate)||(LD(&record.control)>>48)||liveEntries(work)||liveEntries(direct)||borrowers()||LD(&record.originalInFlight))return refuse(NV_ERR_IN_USE,SITE_PHASE);
    status=inspectCounters(nv);if(status!=NV_OK)return status;
    for(i=0;i<CAPACITY;++i)if(LD(&events[i].id))ST(&events[i].sealed,1U);
    ST(&record.sealSerial,LD(&record.generation));expected=S540_FIRST_DRAINING;
    if(!__atomic_compare_exchange_n(&record.phase,&expected,(NvU32)S540_FIRST_SEALED,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return first()!=NV_OK?first():NV_ERR_INVALID_STATE;
    return first();
}
NV_STATUS s540FirstTxnBeginDestructive(const void *nv) {
    NvU32 expected=S540_FIRST_SEALED;NV_STATUS status;
    if(checkedMaster(nv)!=NV_OK)return NV_ERR_INVALID_STATE;
    if(first()!=NV_OK)return first();
    status=s540FirstTxnOriginalLocksReleased(nv);if(status!=NV_OK)return refuse(status,SITE_PHASE);
    status=s540FirstTxnServicesValidateRetired(nv,LD(&record.generation));if(status!=NV_OK)return refuse(status,SITE_SERVICE);
    status=inspectCounters(nv);if(status!=NV_OK)return status;
    if(!__atomic_compare_exchange_n(&record.phase,&expected,(NvU32)S540_FIRST_DESTRUCTIVE,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_ERR_INVALID_STATE;
    return s540FirstTxnCheckBeforeDestroy(nv);
}
NV_STATUS s540FirstTxnCheckBeforeDestroy(const void *nv) {
    if(!exact(nv)||!master())return NV_ERR_INVALID_STATE;
    if(first()!=NV_OK)return first();
    if(LD(&record.phase)!=S540_FIRST_DESTRUCTIVE||LD(&record.sealSerial)!=LD(&record.generation)||LD(&record.gate)||LD(&record.freeGate)||
       (LD(&record.control)>>48)||liveEntries(work)||liveEntries(direct)||borrowers()||LD(&record.originalInFlight))return refuse(NV_ERR_IN_USE,SITE_PHASE);
    /* Called under original locks: consume the prior outside-lock seal only.
     * New source service failures must independently publish sticky refusal. */
    return first();
}
NV_STATUS s540FirstTxnEventCanDestroy(const void *nv,const void *event,const void *timer,NvU64 id) {
    NvS32 i;NV_STATUS status=s540FirstTxnCheckBeforeDestroy(nv);if(status!=NV_OK)return status;
    i=eventIndex(event,id);
    if(i<0||events[i].timer!=timer||!LD(&events[i].sealed)||LD(&events[i].borrowers)||LD(&events[i].destroyed))return refuse(NV_ERR_INVALID_STATE,SITE_EVENT);
    /* Caller holds real registry guard: pull stage is lock-free, no drain/query
     * can re-enter that guard. Cancellation generation is the actual last arm. */
    status=serviceContext(timer,event,S540_FIRST_SERVICE_CANCELLED,NV_TRUE,LD(&events[i].lastArm));
    return status==NV_OK?first():refuse(status,SITE_EVENT);
}
NV_STATUS s540FirstTxnEventDestroyed(const void *nv,const void *event,const void *timer,NvU64 id) {
    NvS32 i=eventIndex(event,id);NV_STATUS status;
    if(!exact(nv)||!master()||i<0||events[i].timer!=timer||!LD(&events[i].sealed)||LD(&events[i].borrowers)||LD(&events[i].destroyed))return NV_ERR_INVALID_STATE;
    status=serviceContext(timer,event,S540_FIRST_SERVICE_DESTROYED,NV_TRUE,id);
    /* Destroyed probe generation uses event generation, not a freed timer read. */
    if(status!=NV_OK)return refuse(status,SITE_EVENT);
    ST(&events[i].destroyed,1U);return NV_OK;
}
NV_STATUS s540FirstTxnCheckBeforeDeleteObject(const void *object) {
    NvU32 i;NV_STATUS status;
    if(!bound())return NV_OK;
    if(!object)return NV_OK;
    if(ownerIndex(object)<0){
        status=lockGate();
        if(status==NV_OK){for(i=0;i<CAPACITY;++i)if(unknownObjects[i]==object)break;
            if(i==CAPACITY)for(i=0;i<CAPACITY;++i)if(!unknownObjects[i]){ST(&unknownObjects[i],object);break;}
            unlockGate();
            if(i==CAPACITY)return refuse(NV_ERR_INSUFFICIENT_RESOURCES,SITE_OWNER);
        }
        return refuse(status!=NV_OK?status:NV_ERR_NOT_SUPPORTED,SITE_OWNER);
    }
    return s540FirstTxnCheckBeforeDestroy(LD(&record.nv));
}
void s540FirstTxnObserveServiceRefusal(NvU32 domain,NvU32 symbol,NV_STATUS status) {
    (void)domain;(void)symbol;
    if(LD(&record.phase)!=S540_FIRST_UNBOUND)(void)refuse(status,SITE_SERVICE);
}
NV_STATUS s540FirstTxnHostCaptureAllocation(S540FirstTxnHostIdentity *out) {
    if(!out)return NV_ERR_INVALID_ARGUMENT;out->owner=0;out->generation=0;
    if(!bound())return LD(&record.phase)==S540_FIRST_UNBOUND?NV_ERR_OBJECT_NOT_FOUND:NV_ERR_NOT_READY;
    if(!authorized())return refuse(NV_ERR_INVALID_STATE,SITE_HOST);
    if(first()!=NV_OK)return first();
    out->owner=LD(&record.owner);out->generation=LD(&record.generation);return NV_OK;
}
NV_STATUS s540FirstTxnHostAcquireFree(const S540FirstTxnHostIdentity *identity,NvU64 *out) {
    NvU32 empty=0,i;NvU64 control,id;NV_STATUS status=NV_OK;
    if(out)*out=0;if(!identity||!out)return NV_ERR_INVALID_ARGUMENT;
    if(!bound())return LD(&record.phase)!=S540_FIRST_UNBOUND?NV_ERR_NOT_READY:(!identity->owner&&!identity->generation?NV_ERR_OBJECT_NOT_FOUND:NV_ERR_INVALID_STATE);
    if(identity->owner!=LD(&record.owner)||identity->generation!=LD(&record.generation)||!authorized())return refuse(NV_ERR_INVALID_STATE,SITE_HOST);
    if(!__atomic_compare_exchange_n(&record.freeGate,&empty,1U,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_BUSY_RETRY,SITE_HOST);
    for(i=0;i<CAPACITY;++i)if(!LD(&frees[i].id))break;
    id=nextId();control=LD(&record.control);
    if(i==CAPACITY||!id)status=NV_ERR_INSUFFICIENT_RESOURCES;
    else for(;;){
        if((NvU32)control){status=(NV_STATUS)(NvU32)control;break;}
        if((control>>48)==0xffffU){status=NV_ERR_INSUFFICIENT_RESOURCES;break;}
        if(__atomic_compare_exchange_n(&record.control,&control,control+FREE_UNIT,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
            frees[i].thread=currentThread();ST(&frees[i].id,id);*out=id;break;
        }
    }
    ST(&record.freeGate,0U);
    return status==NV_OK?NV_OK:refuse(status,SITE_HOST);
}
NV_STATUS s540FirstTxnHostCompleteFree(const S540FirstTxnHostIdentity *identity,NvU64 id) {
    NvU32 i;NvU64 expected=id,control;
    if(!identity||!id||identity->owner!=LD(&record.owner)||identity->generation!=LD(&record.generation))return NV_ERR_INVALID_STATE;
    for(i=0;i<CAPACITY;++i)if(LD(&frees[i].id)==id)break;
    if(i==CAPACITY||frees[i].thread!=currentThread())return refuse(NV_ERR_INVALID_STATE,SITE_HOST);
    if(!__atomic_compare_exchange_n(&frees[i].id,&expected,0ULL,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return refuse(NV_ERR_IN_USE,SITE_HOST);
    control=LD(&record.control);
    for(;;){if(!(control>>48))return refuse(NV_ERR_INVALID_STATE,SITE_HOST);
        if(__atomic_compare_exchange_n(&record.control,&control,control-FREE_UNIT,NV_FALSE,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_OK;}
}
NV_STATUS s540FirstTxnGetSnapshot(const void *nv,S540FirstTxnSnapshot *out) {
    NvU32 i;NvU64 control;S540FirstTxnSnapshot result={0};
    if(!out||!exact(nv))return NV_ERR_INVALID_ARGUMENT;control=LD(&record.control);
    result.phase=(NvU32)control?S540_FIRST_RETAINED:LD(&record.phase);result.firstStatus=(NvU32)control;result.firstSite=(NvU32)((control>>32)&0xffffU);
    result.generation=LD(&record.generation);result.masterThread=LD(&record.masterThread);result.sealSerial=LD(&record.sealSerial);
    result.workAccepted=LD(&record.workAccepted);result.workOriginalReturned=LD(&record.workOriginalReturned);result.workActionReturned=LD(&record.workActionReturned);
    result.directAccepted=LD(&record.directAccepted);result.directOriginalReturned=LD(&record.directOriginalReturned);result.directActionReturned=LD(&record.directActionReturned);
    result.liveWork=liveEntries(work);result.liveDirect=liveEntries(direct);result.eventBorrowers=(NvU32)borrowers();result.inFlightFreePermits=(NvU32)(control>>48);
    for(i=0;i<CAPACITY;++i){if(LD(&owners[i].id))++result.ownerCount;if(LD(&events[i].id))++result.eventCount;if(LD(&unknownObjects[i]))++result.unknownRetainedObjects;if(LD(&retainedAllocations[i].allocation))++result.retainedOriginalAllocations;}
    result.originalInFlight=!!LD(&record.originalInFlight);result.originalExitReady=!!LD(&record.originalExitReady);result.originalReturned=!!LD(&record.originalReturned);
    result.cleanupRequested=!!LD(&record.cleanupRequested);result.firmwareRetained=!!LD(&record.firmwareRetained);
    for(i=0;i<3;++i)result.firmware[i]=LD(&record.firmware[i]);
#define COPY(field) result.counters.field=LD(&record.counters.field)
    COPY(hostInitialized);COPY(cryptoOverflow);COPY(hostUnavailable);COPY(hostInvalidFrees);
    COPY(memoryUnavailableEver);COPY(memoryViolationsEver);COPY(cryptoUnavailable);COPY(cryptoMaskLow);COPY(cryptoMaskHigh);
#undef COPY
    *out=result;return NV_OK;
}
