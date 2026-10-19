/* SPDX-License-Identifier: MIT */
/* Actual full-header wrapper/API-lock bodies; original GPU-init, thread/runtime
 * boundaries and strong-record endpoints are explicit CPU fixtures here.
 * Actual FirstTransaction record integration is tested separately by its owner. */
#include "nv.h"
#include "nv-priv.h"
#include "osapi.h"
#include "core/system.h"
#include "core/locks.h"
#include "core/thread_state.h"
#include "rmapi/rmapi.h"
#include "diagnostics/tracer.h"
#include "tls/tls.h"
#include "S540NvidiaGspFirstTransactionOriginal.h"
#include "control_types.h"
#include "../../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

static nv_state_t nv;
static nv_priv_t privateState;
static OBJGPU gpu;
static OBJSYS systemObject;
static void *nativeApi, *nativeGpu;
static __thread NvP64 tlsValue;
static __thread NvU64 gpuOwner;
static S540OriginalControlResult result;
static NvU32 scenario;
static const void *firmware[3];
static NvBool initialized;
static NvU64 tid(void) { NvU64 value = 0; (void)s540Darwin_os_get_current_thread(&value); return value; }
static void zeros(void *p, NvU64 n) { NvU8 *b = p; for (NvU64 i = 0; i < n; ++i) b[i] = 0; }
static void trace(const void *info, ...) { (void)info; }
static void rwAcquireRead(PORT_RWLOCK *p) { if (s540Darwin_os_acquire_rwlock_read(p) != NV_OK) ++result.identityErrors; }
static void rwAcquireWrite(PORT_RWLOCK *p) { if (s540Darwin_os_acquire_rwlock_write(p) != NV_OK) ++result.identityErrors; else ++result.apiAcquired; }
static NvBool rwReadConditional(PORT_RWLOCK *p) { return s540Darwin_os_cond_acquire_rwlock_read(p) == NV_OK; }
static NvBool rwWriteConditional(PORT_RWLOCK *p) { NV_STATUS s = s540Darwin_os_cond_acquire_rwlock_write(p); if (s == NV_OK) ++result.apiAcquired; return s == NV_OK; }
static void rwReleaseRead(PORT_RWLOCK *p) { s540Darwin_os_release_rwlock_read(p); ++result.apiReleased; }
static void rwReleaseWrite(PORT_RWLOCK *p) { s540Darwin_os_release_rwlock_write(p); ++result.apiReleased; }
static NvP64 *tlsAcquire(NvU64 id) { (void)id; return &tlsValue; }
static NvP64 tlsGet(NvU64 id) { (void)id; return tlsValue; }
static void tlsRelease(NvU64 id) { (void)id; tlsValue = 0; }

#undef SYS_GET_INSTANCE
#define SYS_GET_INSTANCE() (&systemObject)
#undef NV_PRINTF
#define NV_PRINTF(...) ((void)0)
#undef NV_ASSERT
#define NV_ASSERT(v) do { if (!(v)) ++result.identityErrors; } while (0)
#undef NV_ASSERT_OR_RETURN
#define NV_ASSERT_OR_RETURN(v, s) do { if (!(v)) return (s); } while (0)
#undef NV_CHECK_OR_RETURN
#define NV_CHECK_OR_RETURN(l, v, s) NV_ASSERT_OR_RETURN(v, s)
#undef RMTRACE_RMLOCK
#define RMTRACE_RMLOCK(...) ((void)0)
#undef INSERT_LOCK_TRACE
#define INSERT_LOCK_TRACE(...) trace(__VA_ARGS__)
#undef portThreadGetCurrentThreadId
#define portThreadGetCurrentThreadId() tid()
#undef portSyncRwLockAcquireRead
#define portSyncRwLockAcquireRead rwAcquireRead
#undef portSyncRwLockAcquireWrite
#define portSyncRwLockAcquireWrite rwAcquireWrite
#undef portSyncRwLockAcquireReadConditional
#define portSyncRwLockAcquireReadConditional rwReadConditional
#undef portSyncRwLockAcquireWriteConditional
#define portSyncRwLockAcquireWriteConditional rwWriteConditional
#undef portSyncRwLockReleaseRead
#define portSyncRwLockReleaseRead rwReleaseRead
#undef portSyncRwLockReleaseWrite
#define portSyncRwLockReleaseWrite rwReleaseWrite
#undef tlsEntryAcquire
#define tlsEntryAcquire tlsAcquire
#undef tlsEntryGet
#define tlsEntryGet tlsGet
#undef tlsEntryRelease
#define tlsEntryRelease tlsRelease
#undef portSyncExSafeToSleep
#define portSyncExSafeToSleep() s540Darwin_os_semaphore_may_sleep()
#undef osApiLockAcquireConfigureFlags
#define osApiLockAcquireConfigureFlags(f) (f)
#undef osGetMonotonicTimeNs
#define osGetMonotonicTimeNs() s540Darwin_os_get_monotonic_time_ns()
#undef portAtomicIncrementU32
#define portAtomicIncrementU32(p) (__c11_atomic_fetch_add((p), 1U, __ATOMIC_SEQ_CST) + 1U)
#undef portAtomicDecrementU32
#define portAtomicDecrementU32(p) (__c11_atomic_fetch_sub((p), 1U, __ATOMIC_SEQ_CST) - 1U)
#undef portAtomicExAddU64
#define portAtomicExAddU64(p, n) ((void)__c11_atomic_fetch_add((p), (n), __ATOMIC_SEQ_CST))
#undef threadStateGetSetupFlags
#define threadStateGetSetupFlags() 0U
#undef threadStateResetTimeout
#define threadStateResetTimeout(g) NV_OK
#undef osDelay
#define osDelay(n) s540Darwin_os_delay(n)

NvU32 rmGpuLocksGetOwnedMask(void) { return gpuOwner == tid() ? 1U : 0U; }
#include "actual-rmapi-lock-bodies.inc"

NV_STATUS s540FirstTxnRequestDeferredCleanup(const void *state, NV_STATUS failure) {
    ++result.deferredCalls;
    if (state != &nv) ++result.identityErrors;
    if (!result.firstStatus) result.firstStatus = failure;
    result.apiHeldAtDeferred = rmapiLockIsOwner();
    result.gpuHeldAtDeferred = rmGpuLocksGetOwnedMask() != 0;
    return failure;
}
NV_STATUS s540FirstTxnRetainInitFirmware(const void *state, const void *fw, const void *log, const void *ucodes) {
    if (state != &nv) ++result.identityErrors;
    result.firmwareRetained = fw == firmware[0] && log == firmware[1] && ucodes == firmware[2];
    return result.firstStatus;
}
NV_STATUS s540FirstTxnOriginalExitReady(const void *state, NV_STATUS outcome) {
    ++result.exitReadyCalls;
    result.exitAfterActualTokens = !rmapiLockIsOwner() && !rmGpuLocksGetOwnedMask() &&
        !result.runtimeDepth && !result.threadDepth && s540FirstTxnOriginalApiGpuLocksReleased(state) == NV_OK;
    if (!result.exitAfterActualTokens || state != &nv) ++result.identityErrors;
    if (scenario == 2 && !result.firstStatus) result.firstStatus = NV_ERR_NOT_SUPPORTED;
    if (!result.firstStatus && outcome != NV_OK) result.firstStatus = outcome;
    return result.firstStatus;
}
NV_STATUS s540FirstTxnCheckBeforeDestroy(const void *state) {
    if (state != &nv) return NV_ERR_INVALID_STATE;
    NV_STATUS status = s540FirstTxnOriginalReadServiceCounters(state, &result.counters);
    if (status != NV_OK) return status;
    if (!result.counters.hostInitialized || result.counters.hostUnavailable || result.counters.hostInvalidFrees ||
        result.counters.memoryUnavailableEver || result.counters.memoryViolationsEver ||
        result.counters.cryptoUnavailable || result.counters.cryptoMaskLow || result.counters.cryptoMaskHigh || result.counters.cryptoOverflow)
        return NV_ERR_NOT_SUPPORTED;
    return result.firstStatus ? result.firstStatus : NV_ERR_NOT_READY;
}

static NvBool fakeConsoleStatus(nv_state_t *state) { if (state != &nv) ++result.identityErrors; return NV_FALSE; }
static NV_STATUS fakeGpuDrain(NvU32 id, NvBool *enabled, void *unused) { (void)id; (void)unused; *enabled = NV_FALSE; return NV_ERR_NOT_SUPPORTED; }
static NvBool fakeInit(nv_state_t *state);
static void fakeThreadInit(THREAD_STATE_NODE *p, NvU32 flags) { (void)p; (void)flags; ++result.threadDepth; }
static void fakeThreadFree(THREAD_STATE_NODE *p, NvU32 flags) { (void)p; (void)flags; --result.threadDepth; }
#undef NV_ENTER_RM_RUNTIME
#define NV_ENTER_RM_RUNTIME(s, f) do { (void)(s); (f)=NULL; ++result.runtimeDepth; } while (0)
#undef NV_EXIT_RM_RUNTIME
#define NV_EXIT_RM_RUNTIME(s, f) do { (void)(s); (void)(f); --result.runtimeDepth; } while (0)
#undef threadStateInit
#define threadStateInit fakeThreadInit
#undef threadStateFree
#define threadStateFree fakeThreadFree
#undef rm_get_uefi_console_status
#define rm_get_uefi_console_status fakeConsoleStatus
#undef gpumgrQueryGpuDrainState
#define gpumgrQueryGpuDrainState fakeGpuDrain
#undef RmPartiallyInitAdapter
#define RmPartiallyInitAdapter fakeInit
#undef RmInitAdapter
#define RmInitAdapter fakeInit
#undef os_disable_console_access
#define os_disable_console_access() ((void)0)
#undef os_enable_console_access
#define os_enable_console_access() ((void)0)
#include "actual-wrapper-bodies.inc"

static NvBool fakeInit(nv_state_t *state) {
    if (state != &nv || !rmapiLockIsOwner()) ++result.identityErrors;
    if (s540Darwin_os_acquire_semaphore(nativeGpu) != NV_OK) ++result.identityErrors;
    gpuOwner = tid(); ++result.gpuAcquired;
    if (scenario != 1 && scenario != 2)
        _s540RmRetainInitFailure(state, NV_ERR_TIMEOUT, firmware[0], firmware[1], firmware[2]);
    gpuOwner = 0;
    if (s540Darwin_os_release_semaphore(nativeGpu) != NV_OK) ++result.identityErrors;
    ++result.gpuReleased;
    if (scenario == 4) rmapiLockRelease();
    return scenario == 1 || scenario == 2;
}

NV_STATUS s540OriginalControlInitialize(void) {
    zeros(&g_RmApiLock, sizeof(g_RmApiLock));
    nativeApi = s540Darwin_os_alloc_rwlock();
    nativeGpu = s540Darwin_os_alloc_semaphore(1);
    if (!nativeApi || !nativeGpu) return NV_ERR_NO_MEMORY;
    g_RmApiLock.pLock = (PORT_RWLOCK *)nativeApi;
    g_RmApiLock.threadId = ~0ULL; g_RmApiLock.tlsEntryId = 1;
    initialized = NV_TRUE;
    return NV_OK;
}
void s540OriginalControlShutdown(void) {
    if (initialized) { s540Darwin_os_free_rwlock(nativeApi); s540Darwin_os_free_semaphore(nativeGpu); initialized = NV_FALSE; }
}
void s540OriginalControlWrapper(NvU32 which, S540OriginalControlResult *out) {
    zeros(&result, sizeof(result)); zeros(&nv, sizeof(nv)); zeros(&privateState, sizeof(privateState));
    scenario = which; nv.priv = &privateState; privateState.pGpu = &gpu;
    privateState.flags = 0xa55aU;
    firmware[0]=(const void *)(NvUPtr)0x10000U; firmware[1]=(const void *)(NvUPtr)0x20000U; firmware[2]=(const void *)(NvUPtr)0x30000U;
    if (which == 3) g_RmApiLock.pLock = NULL;
    result.wrapperStatus = rm_init_adapter(NULL, &nv) ? NV_OK : NV_ERR_NOT_READY;
    g_RmApiLock.pLock = (PORT_RWLOCK *)nativeApi;
    result.wrapperReturned = NV_TRUE;
    result.ownershipPreserved = privateState.pGpu == &gpu && privateState.flags == 0xa55aU;
    result.guardStatus = s540FirstTxnCheckBeforeDestroy(&nv);
    *out = result;
}
NvBool s540OriginalControlRealTokensAvailable(void) {
    NV_STATUS a = s540Darwin_os_cond_acquire_rwlock_write(nativeApi);
    NV_STATUS g = s540Darwin_os_cond_acquire_semaphore(nativeGpu);
    if (a == NV_OK) s540Darwin_os_release_rwlock_write(nativeApi);
    if (g == NV_OK) (void)s540Darwin_os_release_semaphore(nativeGpu);
    return a == NV_OK && g == NV_OK && !rmapiLockIsOwner() && !rmGpuLocksGetOwnedMask();
}
void s540OriginalControlCurrentCounters(S540FirstTxnServiceCounters *out) {
    (void)s540FirstTxnOriginalReadServiceCounters(&nv, out);
}
NV_STATUS s540OriginalControlCurrentGuard(void) { return s540FirstTxnCheckBeforeDestroy(&nv); }
NV_STATUS s540OriginalControlFullLocksStatus(void) { return s540FirstTxnOriginalLocksReleased(&nv); }
