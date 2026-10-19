// SPDX-License-Identifier: MIT
// Original lock/port bodies use real Darwin services and cancellation record.
// Hardware, object metadata and trace boundaries remain explicit fixtures.
#pragma once
#include "S540NvidiaGspCancellation.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

#define PORT_ATOMIC volatile
#define NV_PRINTF(...) ((void)0)
#define NV_PRINTF_COND(...) ((void)0)
#define NV_ASSERT(...) ((void)0)
#define NV_ASSERT_FAILED(...) ((void)0)
#define DBG_BREAKPOINT() std::abort()
#define PORT_ASSERT(c) do { if (!(c)) std::abort(); } while (0)
#define PORT_ASSERT_CHECKED(c) PORT_ASSERT(c)
#define NV_ASSERT_OR_RETURN(c, e) do { if (!(c)) return (e); } while (0)
#define NV_CHECK_OR_RETURN(l, c, e) NV_ASSERT_OR_RETURN(c, e)
#define NV_RETURN_ADDRESS() reinterpret_cast<void *>(1)
#define NVBIT(v) (1U << (v))
#define RM_LOCK_MODULE_GRP(v) 1U
#define RMTRACE_RMLOCK(...) ((void)0)
template <typename... T> void traceSink(T...) {}
#define INSERT_LOCK_TRACE(...) traceSink(__VA_ARGS__)
#define os_acquire_spinlock s540Darwin_os_acquire_spinlock
#define os_release_spinlock s540Darwin_os_release_spinlock
#define os_acquire_semaphore s540Darwin_os_acquire_semaphore
#define os_cond_acquire_semaphore s540Darwin_os_cond_acquire_semaphore
#define os_release_semaphore s540Darwin_os_release_semaphore
#define os_acquire_rwlock_read s540Darwin_os_acquire_rwlock_read
#define os_acquire_rwlock_write s540Darwin_os_acquire_rwlock_write
#define os_cond_acquire_rwlock_read s540Darwin_os_cond_acquire_rwlock_read
#define os_cond_acquire_rwlock_write s540Darwin_os_cond_acquire_rwlock_write
#define os_release_rwlock_read s540Darwin_os_release_rwlock_read
#define os_release_rwlock_write s540Darwin_os_release_rwlock_write
#define os_semaphore_may_sleep s540Darwin_os_semaphore_may_sleep

using OS_THREAD_HANDLE = NvU64;
struct PORT_SPINLOCK { void *lock; NvU64 oldIrql; };
struct PORT_SEMAPHORE { void *sem; };
struct PORT_RWLOCK { void *rwlock; };
using LOCK_TRACE_INFO = int;
struct OBJGPU { NvU32 gpuInstance; };
enum : NvU32 {
    NV_MAX_DEVICES = 2, GPUS_LOCK_ALL = ~0U,
    GPUS_LOCK_FLAGS_NONE = 0, GPU_LOCK_FLAGS_COND_ACQUIRE = 1,
    GPU_LOCK_FLAGS_SAFE_LOCK_UPGRADE = 2, GPU_LOCK_FLAGS_LOCK_ALLOC = 4,
    RMAPI_LOCK_FLAGS_READ = 2, RMAPI_LOCK_FLAGS_READ_FORCE = 8,
    RMAPI_LOCK_FLAGS_LOW_PRIORITY = 4, API_LOCK_FLAGS_COND_ACQUIRE = 1,
    RM_LOCK_MODULES_NONE = 0, RM_LOCK_MODULES_INIT = 1,
    PDB_PROP_SYS_ENABLE_FORCE_SHARED_LOCK = 1, PDB_PROP_SYS_RM_LOCK_TIME_COLLECT = 2,
    PDB_PROP_SYS_GPU_LOCK_MIDPATH_ENABLED = 3,
    THREAD_STATE_SETUP_FLAGS_DO_NOT_INCLUDE_SLEEP_TIME_ENABLED = 1,
    DPC_RELEASE_ALL_GPU_LOCKS = 1, DPC_RELEASE_SINGLE_GPU_LOCK = 2,
    lockTraceAcquire = 1, lockTraceRelease = 2
};
static const NvU32 MIDPATH_RETRIES = 20, MIDPATH_DELAY_USEC = 30;
static const NvU32 GPU_INST_INVALID = ~0U, GPU_INST_ALLOC_LOCK = 0xff;
struct OBJSYS {
    NvU32 apiLockModuleMask = ~0U;
    bool getProperty(OBJSYS *, NvU32) { return false; }
} fixtureSystem;
#define SYS_GET_INSTANCE() (&fixtureSystem)

typedef struct {
    PORT_RWLOCK *pLock;
    NvU64 threadId, timestamp;
    LOCK_TRACE_INFO traceInfo;
    NvU64 tlsEntryId;
    PORT_ATOMIC NvU32 contentionCount;
    NvU32 lowPriorityAging;
    PORT_ATOMIC NvU64 totalWaitTime, totalRwHoldTime, totalRoHoldTime;
} RMAPI_LOCK;
static RMAPI_LOCK g_RmApiLock;
typedef struct {
    PORT_SEMAPHORE *pWaitSema;
    PORT_ATOMIC NvS32 count;
    PORT_ATOMIC NvBool bRunning, bSignaled;
    OS_THREAD_HANDLE threadId;
    NvU16 priority, priorityPrev;
    NvU64 timestamp;
} GPULOCK;
typedef struct {
    PORT_SPINLOCK *pLock;
    NvU32 gpusLockableMask;
    PORT_ATOMIC NvU32 gpusHiddenMask;
    NvU32 gpusLockedMask, gpusFreezeMask;
    GPULOCK gpuLocks[NV_MAX_DEVICES], gpuAllocLock;
    LOCK_TRACE_INFO traceInfo;
    PORT_ATOMIC NvU64 totalWaitTime, totalHoldTime;
} GPULOCKINFO;
static GPULOCKINFO rmGpuLockInfo;

static thread_local NvP64 fixtureTlsValue;
static bool fixtureTlsFailure;
static std::atomic<unsigned> fixtureAcquireMasks{0}, fixtureReleaseMasks{0};
static std::atomic<NvU32> fixtureAcquireFlags{0}, fixtureReleaseFlags{0};
static std::atomic<S540GspCancellationToken> fixtureRevokeAfterMask{0};
static std::atomic<S540GspCancellationToken> fixtureRevokeAfterWriterContention{0};
static OBJGPU fixtureGpus[] = {{0}, {1}};
inline NvU64 portThreadGetCurrentThreadId() { NvU64 tid = 0; PORT_ASSERT(s540Darwin_os_get_current_thread(&tid) == NV_OK); return tid; }
inline void osGetCurrentThread(OS_THREAD_HANDLE *tid) { *tid = portThreadGetCurrentThreadId(); }
inline NvU64 osGetMonotonicTimeNs() { return s540Darwin_os_get_monotonic_time_ns(); }
inline NvU64 portTimeGetUptimeNanoseconds() { return osGetMonotonicTimeNs(); }
inline NvU32 portUtilCountTrailingZeros32(NvU32 x) { return x ? __builtin_ctz(x) : 32; }
inline NvU32 portUtilCountLeadingZeros32(NvU32 x) { return x ? __builtin_clz(x) : 32; }
inline NvS32 portAtomicDecrementS32(volatile NvS32 *p) { return __atomic_sub_fetch(p, 1, __ATOMIC_SEQ_CST); }
inline NvS32 portAtomicIncrementS32(volatile NvS32 *p) { return __atomic_add_fetch(p, 1, __ATOMIC_SEQ_CST); }
inline NvU32 portAtomicIncrementU32(volatile NvU32 *p) { return __atomic_add_fetch(p, 1, __ATOMIC_SEQ_CST); }
inline NvU32 portAtomicDecrementU32(volatile NvU32 *p) {
    const auto result = __atomic_sub_fetch(p, 1, __ATOMIC_SEQ_CST);
    if (const auto token = fixtureRevokeAfterWriterContention.exchange(0))
        PORT_ASSERT(s540GspCancellationRevoke(token) == NV_OK);
    return result;
}
inline void portAtomicExAddU64(volatile NvU64 *p, NvU64 n) { (void)__atomic_fetch_add(p, n, __ATOMIC_SEQ_CST); }
inline bool portAtomicCompareAndSwapU32(volatile NvU32 *p, NvU32 desired, NvU32 expected) { return __atomic_compare_exchange_n(p, &expected, desired, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); }
inline void portAtomicOrU32(volatile NvU32 *p, NvU32 n) { (void)__atomic_fetch_or(p, n, __ATOMIC_SEQ_CST); }
inline void threadPriorityBoost(NvU64 *a, NvU64 *b) { *a = *b = 0; }
inline void threadPriorityRestore() {}
inline NvU32 osApiLockAcquireConfigureFlags(NvU32 flags) { return flags; }
inline NvU32 threadStateGetSetupFlags() { return 0; }
inline NV_STATUS threadStateResetTimeout(OBJGPU *) { return NV_OK; }
inline NvP64 *tlsEntryAcquire(NvU64) { return fixtureTlsFailure ? nullptr : &fixtureTlsValue; }
inline NvP64 tlsEntryGet(NvU64) { return fixtureTlsValue; }
inline void tlsEntryRelease(NvU64) { fixtureTlsValue = nullptr; }
inline OBJGPU *gpumgrGetGpu(NvU32 id) { return id < NV_MAX_DEVICES ? &fixtureGpus[id] : nullptr; }
inline NvU32 gpumgrGetGpuMask(OBJGPU *p) { return NVBIT(p->gpuInstance); }
inline void _gpuLocksAcquireDisableInterrupts(NvU32, NvU32 flags) {
    ++fixtureAcquireMasks; fixtureAcquireFlags = flags;
    if (const auto token = fixtureRevokeAfterMask.exchange(0))
        PORT_ASSERT(s540GspCancellationRevoke(token) == NV_OK);
}
inline void _gpuLocksReleaseEnableInterrupts(NvU32, NvU32 flags) { ++fixtureReleaseMasks; fixtureReleaseFlags = flags; }
inline NV_STATUS osDelayUs(NvU32 n) { return s540Darwin_os_delay_us(n); }
inline NV_STATUS osDelay(NvU32 n) { return s540Darwin_os_delay(n); }
inline void osGpuLocksQueueRelease(OBJGPU *, NvU32) { std::abort(); }

NvBool portSyncExSafeToSleep(void);
NvBool portSyncExSafeToWake(void);
NvU32 rmGpuLocksGetOwnedMask(void);
NvBool rmapiLockIsOwner(void);
void rmapiLockRelease(void);
static NvBool _rmGpuAllocLockIsOwner(void);
static NvBool _rmGpuLockIsOwner(NvU32);
static NV_STATUS _rmGpuLocksRelease(NvU32, NvU32, OBJGPU *, void *);
