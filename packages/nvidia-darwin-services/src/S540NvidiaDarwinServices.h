// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_DARWIN_SERVICES_H
#define S540_NVIDIA_DARWIN_SERVICES_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"
#ifdef __cplusplus
extern "C" {
#endif
// Exact pinned os-interface.h signatures, separately named so the v9 selected
// profile and the full-RM facade cannot accidentally share OS object layouts.
struct os_work_queue;
typedef struct os_wait_queue os_wait_queue;
NV_STATUS NV_API_CALL s540Darwin_os_alloc_mutex(void **);
void NV_API_CALL s540Darwin_os_free_mutex(void *);
NV_STATUS NV_API_CALL s540Darwin_os_acquire_mutex(void *);
NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_mutex(void *);
void NV_API_CALL s540Darwin_os_release_mutex(void *);
NV_STATUS NV_API_CALL s540Darwin_os_alloc_spinlock(void **);
void NV_API_CALL s540Darwin_os_free_spinlock(void *);
NvU64 NV_API_CALL s540Darwin_os_acquire_spinlock(void *);
void NV_API_CALL s540Darwin_os_release_spinlock(void *, NvU64);
void *NV_API_CALL s540Darwin_os_alloc_semaphore(NvU32);
void NV_API_CALL s540Darwin_os_free_semaphore(void *);
NV_STATUS NV_API_CALL s540Darwin_os_acquire_semaphore(void *);
NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_semaphore(void *);
NV_STATUS NV_API_CALL s540Darwin_os_release_semaphore(void *);
void *NV_API_CALL s540Darwin_os_alloc_rwlock(void);
void NV_API_CALL s540Darwin_os_free_rwlock(void *);
NV_STATUS NV_API_CALL s540Darwin_os_acquire_rwlock_read(void *);
NV_STATUS NV_API_CALL s540Darwin_os_acquire_rwlock_write(void *);
NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_rwlock_read(void *);
NV_STATUS NV_API_CALL s540Darwin_os_cond_acquire_rwlock_write(void *);
void NV_API_CALL s540Darwin_os_release_rwlock_read(void *);
void NV_API_CALL s540Darwin_os_release_rwlock_write(void *);
NV_STATUS NV_API_CALL s540Darwin_os_alloc_wait_queue(os_wait_queue **);
void NV_API_CALL s540Darwin_os_free_wait_queue(os_wait_queue *);
void NV_API_CALL s540Darwin_os_wait_uninterruptible(os_wait_queue *);
void NV_API_CALL s540Darwin_os_wait_interruptible(os_wait_queue *);
void NV_API_CALL s540Darwin_os_wake_up(os_wait_queue *);
NvBool NV_API_CALL s540Darwin_os_semaphore_may_sleep(void);
NvBool NV_API_CALL s540Darwin_os_is_isr(void);
NV_STATUS NV_API_CALL s540Darwin_os_get_current_thread(NvU64 *);
NvU32 NV_API_CALL s540Darwin_os_get_cpu_number(void);
NvU32 NV_API_CALL s540Darwin_os_get_current_process(void);
void NV_API_CALL s540Darwin_os_get_current_process_name(char *, NvU32);
NV_STATUS NV_API_CALL s540Darwin_os_get_euid(NvU32 *);
NvBool NV_API_CALL s540Darwin_os_is_administrator(void);
NvBool NV_API_CALL s540Darwin_os_check_access(NvU16 accessRight);
NvU32 NV_API_CALL s540Darwin_os_get_current_process_flags(void);
void *NV_API_CALL s540Darwin_os_get_pid_info(void);
void NV_API_CALL s540Darwin_os_put_pid_info(void *);
NV_STATUS NV_API_CALL s540Darwin_os_find_ns_pid(void *, NvU32 *);
NvBool NV_API_CALL s540Darwin_os_is_init_ns(void);
NV_STATUS NV_API_CALL s540Darwin_os_get_system_time(NvU32 *, NvU32 *);
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns(void);
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_time_ns_hr(void);
NvU64 NV_API_CALL s540Darwin_os_get_monotonic_tick_resolution_ns(void);
NV_STATUS NV_API_CALL s540Darwin_os_delay(NvU32);
NV_STATUS NV_API_CALL s540Darwin_os_delay_us(NvU32);
NV_STATUS NV_API_CALL s540Darwin_os_get_random_bytes(NvU8 *, NvU16);
NV_STATUS NV_API_CALL s540Darwin_os_schedule(void);
void NV_API_CALL s540Darwin_os_flush_cpu_write_combine_buffer(void);
NV_STATUS NV_API_CALL s540Darwin_os_queue_work_item(struct os_work_queue *, void *);
NV_STATUS NV_API_CALL s540Darwin_os_flush_work_queue(struct os_work_queue *, NvBool);
NvBool NV_API_CALL s540Darwin_os_is_queue_flush_ongoing(struct os_work_queue *);

// Adapter lifecycle, outside NVIDIA's ABI. Every callback is real and supplied
// by the full-RM facade; an unbound global queue returns NOT_READY. Caller ends
// all producer references before destruction. Stop drains every accepted item.
typedef void (*S540DarwinWorkAction)(void *context, void *data);
NV_STATUS s540DarwinWorkQueueCreate(S540DarwinWorkAction, void *, struct os_work_queue **);
NV_STATUS s540DarwinWorkQueueStop(struct os_work_queue *);
void s540DarwinWorkQueueDestroy(struct os_work_queue *);
NV_STATUS s540DarwinBindGlobalWorkQueue(struct os_work_queue *);
NV_STATUS s540DarwinUnbindGlobalWorkQueue(struct os_work_queue *);

// One-shot timer: callback in ordinary thread context, optional rearm from its
// callback, synchronous cancellation after stopping outside the callback.
typedef struct S540DarwinTimer S540DarwinTimer;
typedef void (*S540DarwinTimerAction)(void *);
NV_STATUS s540DarwinTimerCreate(S540DarwinTimerAction, void *, S540DarwinTimer **);
NV_STATUS s540DarwinTimerArm(S540DarwinTimer *, NvU64 delayNs);
NV_STATUS s540DarwinTimerCancel(S540DarwinTimer *);
void s540DarwinTimerDestroy(S540DarwinTimer *);
NvU32 s540DarwinLiveObjects(void);
#ifdef __cplusplus
}
namespace S540NvidiaDarwinServices {
struct Result {
    NvU32 checks, failures;
    bool synchronization, workQueue, timer, context, cleanup;
    bool passed() const { return failures == 0 && synchronization && workQueue && timer && context && cleanup; }
};
Result check();
}
#if !defined(KERNEL)
namespace S540NvidiaDarwinServicesNative {
enum class Failure : NvU32 { Storage = 1, Guard = 2, Worker = 3 };
void failNext(Failure);
void setContext(bool interruptContext, bool interruptsEnabled);
// Explicit virtual-CPU fixture for native RM tests only; UINT32_MAX unbinds.
// Production kernel always calls the source-backed exported cpu_number SPI.
void setCpuFixture(NvU32);
}
#endif
#endif
#endif
