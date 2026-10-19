/* SPDX-License-Identifier: MIT */
/* Complete original getter bodies/types; lifecycle and TLS endpoints are
 * explicit fixtures. Actual Darwin thread identity, context and spinlock APIs
 * execute in native user space, never in the kernel. No RM acquisition is
 * simulated or claimed: ownership fields are observation-boundary fixtures. */
#include "core/core.h"
#include "core/system.h"
#include "core/locks.h"
#include "rmapi/rmapi.h"
#include "diagnostics/tracer.h"
#include "tls/tls.h"
#include "S540ProspectiveRmLockOwnership.h"
#include "../../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <pthread.h>
#include <stdio.h>

static OBJSYS systemObject, foreignSystem;
OBJSYS *g_pSys;
static NvBool running, portable, threadFail, forceThread;
static NvU64 forcedThread;
static __thread NvP64 tlsValue;
static __thread NvU64 spinToken;
static NvU32 checks, failures, tlsReads, spinEntries, spinDepth;
static void expect(NvBool value) {
    __atomic_add_fetch(&checks,1U,__ATOMIC_RELAXED);
    if (!value) __atomic_add_fetch(&failures,1U,__ATOMIC_RELAXED);
}
static void fill(void *p,NvU32 size) {
    volatile NvU8 *bytes=p;for(NvU32 i=0;i<size;++i)bytes[i]=0x5a;
}
static NvBool equal(const void *a,const void *b,NvU32 size) {
    const volatile NvU8 *x=a,*y=b;
    for(NvU32 i=0;i<size;++i)if(x[i]!=y[i])return NV_FALSE;
    return NV_TRUE;
}
void s540ProspectiveControlContext(NvU32);
static NvP64 fixtureTls(NvU64 id) {
    ++tlsReads; if (id != 7 || spinDepth) ++failures; return tlsValue;
}
static void fixtureSpinAcquire(PORT_SPINLOCK *lock) {
    spinToken = s540Darwin_os_acquire_spinlock(lock); ++spinDepth; ++spinEntries;
}
static void fixtureSpinRelease(PORT_SPINLOCK *lock) {
    if (spinDepth != 1) ++failures; --spinDepth;
    s540Darwin_os_release_spinlock(lock, spinToken);
}
#undef tlsEntryGet
#define tlsEntryGet fixtureTls
#undef portSyncSpinlockAcquire
#define portSyncSpinlockAcquire fixtureSpinAcquire
#undef portSyncSpinlockRelease
#define portSyncSpinlockRelease fixtureSpinRelease
#include "actual-original-lock-bodies.inc"

NvBool s540GlobalRmIsInitialized(void) { return running; }
NvBool portIsInitialized(void) { return portable; }
NV_STATUS os_get_current_thread(NvU64 *out) {
    if (threadFail) return NV_ERR_OPERATING_SYSTEM;
    if (forceThread) { *out = forcedThread; return NV_OK; }
    return s540Darwin_os_get_current_thread(out);
}
static NvU64 current(void) { NvU64 value=0; (void)s540Darwin_os_get_current_thread(&value); return value; }
static void refused(NV_STATUS wanted) {
    S540ProspectiveRmLockOwnership out, before;
    fill(&out,sizeof(out)); before=out;
    expect(s540ProspectiveReadOriginalLockOwnership(&systemObject, &out)==wanted);
    expect(equal(&out,&before,sizeof(out)));
}
static void *foreign(void *unused) {
    S540ProspectiveRmLockOwnership out={0}; (void)unused;
    expect(s540ProspectiveReadOriginalLockOwnership(&systemObject,&out)==NV_OK);
    expect(out.thread!=current() ? NV_FALSE : NV_TRUE);
    expect(!out.apiOwned && !out.perGpuMask && !out.allocationOwned);
    expect(s540ProspectiveOriginalCurrentThreadLocksReleased(&systemObject)==NV_OK);
    return NULL;
}
int main(void) {
    S540ProspectiveRmLockOwnership out={0}, before;
    void *stateLock=NULL,*allocSema=NULL,*apiLock=NULL;
    NvU64 mine; NvU32 readBase,spinBase; pthread_t worker;
    mine=current(); expect(mine!=0 && mine!=~(NvU64)0);
    expect(s540ProspectiveReadOriginalLockOwnership(NULL,&out)==NV_ERR_INVALID_ARGUMENT);
    expect(s540ProspectiveReadOriginalLockOwnership(&systemObject,NULL)==NV_ERR_INVALID_ARGUMENT);
    s540ProspectiveControlContext(1);refused(NV_ERR_INVALID_REQUEST);
    s540ProspectiveControlContext(2);refused(NV_ERR_INVALID_REQUEST);
    s540ProspectiveControlContext(0);expect(tlsReads==0 && spinEntries==0);
    refused(NV_ERR_NOT_READY); expect(tlsReads==0 && spinEntries==0);
    running=NV_TRUE;refused(NV_ERR_NOT_READY);portable=NV_TRUE;
    refused(NV_ERR_NOT_READY);g_pSys=&foreignSystem;refused(NV_ERR_NOT_READY);
    g_pSys=&systemObject;systemObject.PDB_PROP_SYS_DESTRUCTING=NV_TRUE;
    refused(NV_ERR_INVALID_STATE);systemObject.PDB_PROP_SYS_DESTRUCTING=NV_FALSE;
    systemObject.pSema=&foreignSystem;refused(NV_ERR_INVALID_STATE);systemObject.pSema=NULL;
    expect(tlsReads==0 && spinEntries==0);
    threadFail=NV_TRUE;refused(NV_ERR_OPERATING_SYSTEM);threadFail=NV_FALSE;
    forceThread=NV_TRUE;forcedThread=0;refused(NV_ERR_INVALID_STATE);
    forcedThread=~(NvU64)0;refused(NV_ERR_INVALID_STATE);forceThread=NV_FALSE;
    refused(NV_ERR_NOT_READY);expect(tlsReads==0 && spinEntries==0);
    apiLock=s540Darwin_os_alloc_rwlock();expect(apiLock!=NULL);g_RmApiLock.pLock=apiLock;
    g_bResServInit=NV_TRUE;refused(NV_ERR_NOT_READY);
    g_RmApiLock.tlsEntryId=(NvU64)TLS_ERROR_VAL;refused(NV_ERR_NOT_READY);
    g_RmApiLock.tlsEntryId=7;refused(NV_ERR_NOT_READY);
    expect(s540Darwin_os_alloc_spinlock(&stateLock)==NV_OK);rmGpuLockInfo.pLock=stateLock;
    refused(NV_ERR_NOT_READY);
    allocSema=s540Darwin_os_alloc_semaphore(0);expect(allocSema!=NULL);
    rmGpuLockInfo.gpuAllocLock.pWaitSema=allocSema;
    rmGpuLockInfo.gpuAllocLock.threadId=~(NvU64)0;
    expect(s540ProspectiveReadOriginalLockOwnership(&systemObject,&out)==NV_OK);
    expect(out.thread==mine && !out.apiOwned && !out.perGpuMask && !out.allocationOwned);
    expect(s540ProspectiveOriginalCurrentThreadLocksReleased(&systemObject)==NV_OK);
    tlsValue=&systemObject;expect(s540ProspectiveOriginalCurrentThreadLocksReleased(&systemObject)==NV_ERR_INVALID_LOCK_STATE);
    tlsValue=0;rmGpuLockInfo.gpuAllocLock.threadId=mine;
    expect(rmGpuLocksGetOwnedMask()==0); /* Actual blind spot counterexample. */
    expect(s540ProspectiveReadOriginalLockOwnership(&systemObject,&out)==NV_OK && out.allocationOwned && !out.perGpuMask);
    expect(s540ProspectiveOriginalCurrentThreadLocksReleased(&systemObject)==NV_ERR_INVALID_LOCK_STATE);
    rmGpuLockInfo.gpusLockableMask=NVBIT(0)|NVBIT(31);
    rmGpuLockInfo.gpuLocks[0].threadId=mine;rmGpuLockInfo.gpuLocks[31].threadId=mine;
    expect(s540ProspectiveReadOriginalLockOwnership(&systemObject,&out)==NV_OK && out.perGpuMask==(NVBIT(0)|NVBIT(31)));
    expect(s540ProspectiveOriginalCurrentThreadLocksReleased(&systemObject)==NV_ERR_INVALID_LOCK_STATE);
    tlsValue=&systemObject;expect(pthread_create(&worker,NULL,foreign,NULL)==0);
    expect(pthread_join(worker,NULL)==0);
    expect(rmGpuLockInfo.gpuAllocLock.threadId==mine && rmGpuLockInfo.gpuLocks[0].threadId==mine && tlsValue==&systemObject);
    expect(s540ProspectiveOriginalCurrentThreadLocksReleased(&systemObject)==NV_ERR_INVALID_LOCK_STATE);
    tlsValue=0;rmGpuLockInfo.gpuAllocLock.threadId=~(NvU64)0;
    rmGpuLockInfo.gpuLocks[0].threadId=~(NvU64)0;rmGpuLockInfo.gpuLocks[31].threadId=~(NvU64)0;
    expect(s540ProspectiveOriginalCurrentThreadLocksReleased(&systemObject)==NV_OK);
    before=out;readBase=tlsReads;spinBase=spinEntries;
    g_bResServInit=NV_FALSE;refused(NV_ERR_NOT_READY);g_bResServInit=NV_TRUE;
    expect(tlsReads==readBase && spinEntries==spinBase);
    systemObject.PDB_PROP_SYS_DESTRUCTING=NV_TRUE;refused(NV_ERR_INVALID_STATE);
    expect(tlsReads==readBase && spinEntries==spinBase);systemObject.PDB_PROP_SYS_DESTRUCTING=NV_FALSE;
    running=NV_FALSE;refused(NV_ERR_NOT_READY);expect(tlsReads==readBase && spinEntries==spinBase);
    expect(s540ProspectiveOriginalApiOwnership(NULL)==NV_ERR_INVALID_ARGUMENT);
    expect(s540ProspectiveOriginalGpuOwnership(NULL,&out.allocationOwned)==NV_ERR_INVALID_ARGUMENT);
    expect(s540ProspectiveOriginalGpuOwnership(&out.perGpuMask,NULL)==NV_ERR_INVALID_ARGUMENT);
    expect(osAcquireRmSema((void*)1)==NV_OK && osCondAcquireRmSema((void*)1)==NV_OK);
    osReleaseRmSema((void*)1,(void*)1);
    expect(osIsRmSemaOwner((void*)1)==NV_TRUE && osIsAcquiredRmSema((void*)1)==NV_TRUE);
    { NvU32 sideEffect=0;expect(osAllocRmSema(++sideEffect)==NV_OK && sideEffect==0);
      osFreeRmSema(++sideEffect);expect(sideEffect==0); }
    expect(spinDepth==0 && spinEntries>0);(void)before;
    s540Darwin_os_free_semaphore(allocSema);s540Darwin_os_free_spinlock(stateLock);s540Darwin_os_free_rwlock(apiLock);
    expect(s540DarwinLiveObjects()==0);
    printf("{\"format\":1,\"status\":\"%s\",\"component\":\"prospective-rm-lock-ownership\",\"checks\":%u,\"failures\":%u,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"actual_original_bodies\":10,\"state_and_lifecycle_fixtures\":true,\"original_entry_admission\":false}\n",failures?"failed":"passed",checks,failures);
    return failures?1:0;
}
