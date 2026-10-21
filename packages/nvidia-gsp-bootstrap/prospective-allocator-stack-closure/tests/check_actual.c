/* CPU-only fixtures around the complete transformed original source bodies. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdarg.h>
#include "S540NvidiaAllocatorEpoch.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "S540NvidiaDarwinServices.h"
#include MEMORY_SOURCE
#include CORE_SOURCE
#undef memset
#undef memcpy
extern void *memset(void *,int,size_t);
extern void *memcpy(void *,const void *,size_t);

static _Thread_local NvU64 currentIdentity = 1;
static NvU32 failures, checks, rawAllocations, rawFrees, poisonAllocations, poisonFrees;
static NvU32 moduleInitializations, moduleShutdowns, lockFailure, hook;
static NV_STATUS foreignStatus;
static NvBool epochReserved = NV_TRUE;
static NvU32 epochState = S540_FIRST_GLOBAL_IN_CORE;
static NvBool epochReturned;
#define CHECK(condition) do { ++checks; if (!(condition)) { ++failures; fprintf(stderr,"check %u line %u\n",checks,__LINE__); } } while (0)

NV_STATUS s540FirstTxnGlobalReadMaster(S540FirstTxnGlobalSnapshot *out)
{
    if (!epochReserved || currentIdentity != 1) return NV_ERR_INVALID_STATE;
    *out = (S540FirstTxnGlobalSnapshot){0};
    out->owner = &checks; out->generation = 7; out->masterThread = 1;
    out->state = epochState; out->originalReturned=epochReturned;
    return NV_OK;
}
NV_STATUS s540Darwin_os_get_current_thread(NvU64 *out) { *out=currentIdentity; return NV_OK; }

static void *foreignInitialize(void *unused)
{
    (void)unused; currentIdentity=2; foreignStatus=portInitialize(); return NULL;
}
static void *foreignCompletion(void *unused)
{
    (void)unused; currentIdentity=2; foreignStatus=s540AllocatorMemoryEnd(NV_OK); return NULL;
}
NvLength portSyncSpinlockSize = 8;
NV_STATUS portSyncSpinlockInitialize(PORT_SPINLOCK *lock)
{
    (void)lock;
    if (hook) {
        CHECK(!portIsInitialized()); CHECK(portState.initCount==1);
        CHECK(portMemGlobals.alloc.nonPaged._portAlloc==NULL);
        if (hook==4) {
            PORT_MEM_ALLOCATOR_TRACKING replacement={0};
            PORT_MEM_ALLOCATOR dynamic={0};
            NvU32 total=portMemGlobals.totalAllocators;
            portMemInitializeAllocatorTracking(&portMemGlobals.alloc.paged,
                &portMemGlobals.alloc.pagedImpl.tracking);
            portMemInitializeAllocatorTracking(&portMemGlobals.alloc.nonPaged,&replacement);
            portMemInitializeAllocatorTracking(&dynamic,&portMemGlobals.mainTracking);
            portMemInitializeAllocatorTracking(&dynamic,&replacement);
            CHECK(portMemGlobals.totalAllocators==total);
            CHECK(portMemGlobals.alloc.paged.pTracking==NULL);
            CHECK(portMemGlobals.alloc.nonPaged.pTracking==NULL);
            CHECK(dynamic.pTracking==NULL);
        } else if (hook==1||hook==3) { pthread_t thread; CHECK(pthread_create(&thread,NULL,
                hook==1?foreignInitialize:foreignCompletion,NULL)==0);
            CHECK(pthread_join(thread,NULL)==0); CHECK(foreignStatus==NV_ERR_INVALID_STATE); }
        else CHECK(portInitialize()==NV_ERR_IN_USE);
        CHECK(portState.initCount==1); CHECK(portMemGlobals.initCount==1);
    }
    return lockFailure ? NV_ERR_INSUFFICIENT_RESOURCES : NV_OK;
}
void portSyncSpinlockDestroy(PORT_SPINLOCK *lock) { (void)lock; }
void portSyncSpinlockAcquire(PORT_SPINLOCK *lock) { (void)lock; }
void portSyncSpinlockRelease(PORT_SPINLOCK *lock) { (void)lock; }
void portSyncInitialize(void) { ++moduleInitializations; }
void portSyncShutdown(void) { ++moduleShutdowns; }
#ifndef portDbgInitialize
void portDbgInitialize(void) { ++moduleInitializations; }
#endif
#ifndef portDbgShutdown
void portDbgShutdown(void) { ++moduleShutdowns; }
#endif
void portCryptoInitialize(void) { ++moduleInitializations; }
void portCryptoShutdown(void) { ++moduleShutdowns; }
void portCpuInitialize(void) { ++moduleInitializations; }
void portCpuShutdown(void) { ++moduleShutdowns; }
void *_portMemAllocNonPagedUntracked(NvLength bytes) {
    ++rawAllocations;
    if (bytes > ((NvLength)-1)/2) return NULL;
    return malloc(bytes);
}
void *_portMemAllocPagedUntracked(NvLength bytes) { return _portMemAllocNonPagedUntracked(bytes); }
void _portMemFreeUntracked(void *pointer) { ++rawFrees; free(pointer); }
int NV_API_CALL nv_printf(NvU32 level,const char *format,...) {
    (void)level; char buffer[512]; va_list args; va_start(args,format);
    int result=vsnprintf(buffer,sizeof(buffer),format,args); va_end(args); return result;
}
void *portMemSet(void *pointer, NvU8 value, NvLength bytes) { return memset(pointer,(int)value,bytes); }
void *portMemCopy(void *to, NvLength capacity, const void *from, NvLength bytes) {
    CHECK(bytes<=capacity); return memcpy(to,from,bytes);
}

static void *poisonAlloc(PORT_MEM_ALLOCATOR *allocator,NvLength bytes) {
    (void)allocator; ++poisonAllocations;
    if (bytes > ((NvLength)-1)/2) return NULL;
    return malloc(bytes);
}
static void poisonFree(PORT_MEM_ALLOCATOR *allocator,void *pointer) {
    (void)allocator; ++poisonFrees; free(pointer);
}
static void poisonRelease(PORT_MEM_ALLOCATOR *allocator) { (void)allocator; ++poisonFrees; }

int main(int argc,char **argv)
{
    unsigned scenario=argc>1?(unsigned)atoi(argv[1]):0;
    S540AllocatorEpochSnapshot snapshot={0};
    if (scenario==1) {
        currentIdentity=2; CHECK(portInitialize()==NV_ERR_INVALID_STATE);
        CHECK(portState.initCount==0); CHECK(portMemGlobals.initCount==0); CHECK(rawAllocations==0);
    } else if (scenario==2) {
        hook=1; CHECK(portInitialize()==NV_OK); CHECK(portState.initCount==1); CHECK(portIsInitialized());
    } else if (scenario==3) {
        hook=2; CHECK(portInitialize()==NV_OK); CHECK(portState.initCount==1); CHECK(portIsInitialized());
    } else if (scenario==4) {
        lockFailure=1; CHECK(portInitialize()==NV_ERR_INSUFFICIENT_RESOURCES);
        CHECK(portState.initCount==0); CHECK(portMemGlobals.initCount==0); CHECK(!portIsInitialized());
        CHECK(rawAllocations==1); CHECK(rawFrees==1);
    } else if (scenario==5) {
        CHECK(portMemInitialize()==NV_ERR_INVALID_STATE); CHECK(portMemGlobals.initCount==0);
        epochReserved=NV_FALSE; CHECK(portInitialize()==NV_ERR_INVALID_STATE); CHECK(portState.initCount==0);
    } else if (scenario==6) {
        CHECK(portMemAllocNonPaged(23)==NULL); CHECK(portMemAllocPaged(47)==NULL);
        CHECK(rawAllocations==0); CHECK(portMemGlobals.initCount==0);
        CHECK(s540AllocatorMemoryEnd(NV_OK)==NV_ERR_INVALID_STATE);
        CHECK(s540AllocatorGlobalUse()==NV_ERR_NOT_READY);
    } else if (scenario==7) {
        epochState=S540_FIRST_GLOBAL_READY; epochReturned=NV_TRUE;
        CHECK(portInitialize()==NV_ERR_INVALID_STATE); CHECK(portState.initCount==0);
        CHECK(rawAllocations==0); CHECK(!portIsInitialized());
    } else if (scenario==8) {
        hook=3; CHECK(portInitialize()==NV_OK); CHECK(portState.initCount==1); CHECK(portIsInitialized());
    } else if (scenario==9) {
        hook=4; CHECK(portInitialize()==NV_OK); CHECK(portIsInitialized());
        CHECK(portMemGlobals.totalAllocators==1);
    } else if (scenario==10) {
        CHECK(portInitialize()==NV_OK);
        PORT_MEM_ALLOCATOR_TRACKING replacement={0};
        PORT_MEM_ALLOCATOR *paged=portMemAllocatorGetGlobalPaged();
        PORT_MEM_ALLOCATOR *nonpaged=portMemAllocatorGetGlobalNonPaged();
        NvU32 total=portMemGlobals.totalAllocators;
        portMemInitializeAllocatorTracking(paged,&replacement);
        portMemInitializeAllocatorTracking(nonpaged,&portMemGlobals.alloc.pagedImpl.tracking);
        CHECK(portMemGlobals.totalAllocators==total); CHECK(replacement.pAllocator==NULL);
        paged->pTracking=&replacement; nonpaged->pTracking=&replacement;
        void *a=portMemAllocNonPaged(11),*b=portMemAllocPaged(19);
        CHECK(a&&b); CHECK(replacement.counter.activeAllocs==0);
        CHECK(portMemGlobals.alloc.pagedImpl.tracking.counter.activeAllocs==2);
        portMemFree(a); portMemFree(b);
        CHECK(portMemGlobals.alloc.pagedImpl.tracking.counter.activeAllocs==0);
    } else if (scenario==11) {
        CHECK(portInitialize()==NV_OK);
        PORT_MEM_ALLOCATOR_TRACKING *reserved[]={&portMemGlobals.mainTracking,
            &portMemGlobals.alloc.pagedImpl.tracking,&portMemGlobals.alloc.nonPagedImpl.tracking};
        for (unsigned i=0;i<3;++i) {
            PORT_MEM_ALLOCATOR alias={0}; alias.pTracking=reserved[i];
            alias._portAlloc=poisonAlloc; alias._portFree=poisonFree; alias._portRelease=poisonRelease;
            NvU32 total=portMemGlobals.totalAllocators;
            portMemInitializeAllocatorTracking(&alias,reserved[i]);
            portMemInitializeAllocatorTracking(NULL,reserved[i]);
            CHECK(portMemGlobals.totalAllocators==total);
            CHECK(PORT_ALLOC(&alias,17)==NULL); PORT_FREE(&alias,(void*)&checks);
            portMemAllocatorRelease(&alias); _portMemTrackingRelease(reserved[i],NV_TRUE);
            CHECK(portMemGlobals.totalAllocators==total);
            CHECK(poisonAllocations==0&&poisonFrees==0);
        }
    } else if (scenario==12) {
        CHECK(portInitialize()==NV_OK);
        NvU8 storage[4096]; PORT_MEM_ALLOCATOR *existing=portMemAllocatorCreateOnExistingBlock(storage,sizeof(storage));
        CHECK(existing!=NULL); void *a=PORT_ALLOC(existing,23); CHECK(a!=NULL);
        PORT_FREE(existing,a); portMemAllocatorRelease(existing);
        NvU32 total=portMemGlobals.totalAllocators;
        CHECK(portMemAllocatorCreateOnExistingBlock(portMemAllocatorGetGlobalPaged(),4096)==NULL);
        CHECK(portMemExAllocatorCreateLockedOnExistingBlock(&portMemGlobals.mainTracking,4096,NULL)==NULL);
        CHECK(portMemAllocatorCreateOnExistingBlock((void*)((NvUPtr)&portMemGlobals-16),4096)==NULL);
        CHECK(portMemGlobals.totalAllocators==total); CHECK(portIsInitialized());
    } else {
        CHECK(portInitialize()==NV_OK); CHECK(portState.initCount==1); CHECK(portIsInitialized());
        PORT_MEM_ALLOCATOR *nonpaged=portMemAllocatorGetGlobalNonPaged();
        PORT_MEM_ALLOCATOR *paged=portMemAllocatorGetGlobalPaged();
        nonpaged->_portAlloc=poisonAlloc; paged->_portAlloc=poisonAlloc;
        nonpaged->_portFree=poisonFree; paged->_portFree=poisonFree;
        nonpaged->_portRelease=poisonRelease; paged->_portRelease=poisonRelease;
        void *a=portMemAllocNonPaged(23),*b=portMemAllocPaged(47);
        CHECK(a!=NULL&&b!=NULL); CHECK(poisonAllocations==0);
        portMemFree(a); portMemFree(b); CHECK(poisonFrees==0);
        CHECK(portMemAllocNonPaged(0)==NULL); CHECK(portMemAllocNonPaged((NvLength)-1)==NULL);
        PORT_MEM_ALLOCATOR *dynamic=portMemAllocatorCreateNonPaged(); CHECK(dynamic!=NULL);
        dynamic->_portAlloc=poisonAlloc; dynamic->_portFree=poisonFree;
        a=PORT_ALLOC(dynamic,31); CHECK(a!=NULL); CHECK(poisonAllocations==1);
        PORT_FREE(dynamic,a); CHECK(poisonFrees==1); portMemAllocatorRelease(dynamic);
        portMemAllocatorRelease(nonpaged); portMemAllocatorRelease(paged); CHECK(poisonFrees==1);
        CHECK(portInitialize()==NV_OK); CHECK(portState.initCount==2);
        portShutdown(); CHECK(portState.initCount==1); CHECK(portIsInitialized());
        currentIdentity=2; portShutdown(); portMemShutdown(NV_TRUE);
        currentIdentity=1; portShutdown(); CHECK(portState.initCount==1);
        CHECK(portMemGlobals.initCount==1); CHECK(portIsInitialized());
    }
    s540AllocatorEpochSnapshot(&snapshot);
    CHECK(!snapshot.portableBusy); CHECK(!snapshot.memoryBusy);
    printf("{\"scenario\":%u,\"checks\":%u,\"failures\":%u,\"refused_initializations\":%llu,\"refused_shutdowns\":%llu,\"poison_allocations\":%u,\"poison_frees\":%u}\n",
        scenario,checks,failures,(unsigned long long)snapshot.refusedInitializations,
        (unsigned long long)snapshot.refusedShutdowns,poisonAllocations,poisonFrees);
    return failures?1:0;
}
