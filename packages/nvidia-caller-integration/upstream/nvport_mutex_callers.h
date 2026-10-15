/* SPDX-License-Identifier: MIT */
/*
 * Narrow interface for the five original caller-owned NVPort mutex operations.
 * This is not the complete synchronization module or tracked allocator API.
 */
#ifndef S540_NVPORT_MUTEX_CALLERS_H
#define S540_NVPORT_MUTEX_CALLERS_H

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct PORT_MEM_ALLOCATOR PORT_MEM_ALLOCATOR;
typedef struct PORT_MUTEX PORT_MUTEX;

struct PORT_MUTEX
{
    void *mutex;
    PORT_MEM_ALLOCATOR *pAllocator;
};

NV_STATUS NV_API_CALL os_alloc_mutex(void **);
void NV_API_CALL os_free_mutex(void *);
NV_STATUS NV_API_CALL os_acquire_mutex(void *);
NV_STATUS NV_API_CALL os_cond_acquire_mutex(void *);
void NV_API_CALL os_release_mutex(void *);

NV_STATUS portSyncMutexInitialize(PORT_MUTEX *);
void portSyncMutexDestroy(PORT_MUTEX *);
void portSyncMutexAcquire(PORT_MUTEX *);
NvBool portSyncMutexAcquireConditional(PORT_MUTEX *);
void portSyncMutexRelease(PORT_MUTEX *);

/* A failed mandatory assertion terminates the caller. It never returns success. */
void __attribute__((noreturn)) s540NvidiaCallerAssertionFailed(
    const char *, const char *, int);

#ifdef __cplusplus
}
#endif

#endif /* S540_NVPORT_MUTEX_CALLERS_H */
