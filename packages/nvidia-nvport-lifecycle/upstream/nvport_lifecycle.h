/*
 * SPDX-FileCopyrightText: Copyright (c) 2015-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 */

/* Narrow release-profile NVPort memory and allocator-owned synchronization API.
 * The selected NVIDIA counter profile tracks allocation counts and cumulative
 * requested bytes. Without fenceposts, active/peak byte sizes are not tracked.
 * Lifecycle transitions require an ordinary sleepable thread and external
 * serialization. All allocations and owned objects must be released first.
 */
#ifndef S540_NVPORT_LIFECYCLE_H
#define S540_NVPORT_LIFECYCLE_H

#include "../../nvidia-caller-integration/upstream/nvport_allocator_callers.h"
#include "../../nvidia-caller-integration/upstream/nvport_mutex_callers.h"
#include "../../nvidia-os-adapter/upstream/nvport_memory_primitives.h"
#include "nvport_safe_length.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct PORT_MEM_ALLOCATOR_IMPL PORT_MEM_ALLOCATOR_IMPL;
typedef struct PORT_MEM_ALLOCATOR_TRACKING PORT_MEM_ALLOCATOR_TRACKING;
typedef void *PortMemAllocatorAlloc(PORT_MEM_ALLOCATOR *, NvLength);
typedef void PortMemAllocatorFree(PORT_MEM_ALLOCATOR *, void *);
typedef void PortMemAllocatorRelease(PORT_MEM_ALLOCATOR *);

struct PORT_MEM_ALLOCATOR {
    PortMemAllocatorAlloc *_portAlloc;
    PortMemAllocatorFree *_portFree;
    PortMemAllocatorRelease *_portRelease;
    PORT_MEM_ALLOCATOR_TRACKING *pTracking;
    PORT_MEM_ALLOCATOR_IMPL *pImpl;
};

typedef struct PORT_SPINLOCK
{
    void *lock;
    NvU64 oldIrql;
    PORT_MEM_ALLOCATOR *pAllocator;
} PORT_SPINLOCK;

typedef struct PORT_MEM_TRACK_ALLOCATOR_STATS
{
    NvU32 numAllocations;
    NvLength allocatedSize;
    NvLength usefulSize;
    NvLength metaSize;
} PORT_MEM_TRACK_ALLOCATOR_STATS;

typedef void (*PORT_MEM_OOM_REPORT_CB)(void);

/* Status-returning adaptation of upstream portMemInitialize. Unlike upstream,
 * both bootstrap lock allocations are checked before initialization publishes.
 * No full NvPort core/portInitialize or successful unsupported-service stub.
 */
NV_STATUS s540NvportMemoryInitialize(void);
NvBool s540NvportMemoryIsInitialized(void);
NvBool s540NvportMemoryIsCold(void);
NvU32 s540NvportMemoryAllocatorCount(void);
void portMemShutdown(NvBool);
void *portMemAllocPaged(NvLength);
void *portMemAllocNonPaged(NvLength);
void portMemFree(void *);
PORT_MEM_ALLOCATOR *portMemAllocatorCreatePaged(void);
PORT_MEM_ALLOCATOR *portMemAllocatorCreateNonPaged(void);
void portMemAllocatorRelease(PORT_MEM_ALLOCATOR *);
PORT_MEM_ALLOCATOR *portMemAllocatorGetGlobalNonPaged(void);
PORT_MEM_ALLOCATOR *portMemAllocatorGetGlobalPaged(void);
void portMemInitializeAllocatorTracking(PORT_MEM_ALLOCATOR *, PORT_MEM_ALLOCATOR_TRACKING *);
void *_portMemAllocatorAlloc(PORT_MEM_ALLOCATOR *, NvLength);
void _portMemAllocatorFree(PORT_MEM_ALLOCATOR *, void *);
#define PORT_ALLOC(pAlloc, length) _portMemAllocatorAlloc(pAlloc, length)
#define PORT_FREE(pAlloc, pMem) _portMemAllocatorFree(pAlloc, pMem)

NV_STATUS portMemExTrackingGetActiveStats(const PORT_MEM_ALLOCATOR *, PORT_MEM_TRACK_ALLOCATOR_STATS *);
NV_STATUS portMemExTrackingGetTotalStats(const PORT_MEM_ALLOCATOR *, PORT_MEM_TRACK_ALLOCATOR_STATS *);
NV_STATUS portMemExTrackingGetPeakStats(const PORT_MEM_ALLOCATOR *, PORT_MEM_TRACK_ALLOCATOR_STATS *);
void portMemPrintTrackingInfo(const PORT_MEM_ALLOCATOR_TRACKING *, NvBool);
void portMemPrintAllTrackingInfo(NvBool);
void portMemRegisterOomReportCb(PORT_MEM_OOM_REPORT_CB);
void portMemReportOom(NvLength);

extern const NvLength portSyncSpinlockSize;
extern const NvLength portSyncMutexSize;
NV_STATUS NV_API_CALL os_alloc_spinlock(void **);
void NV_API_CALL os_free_spinlock(void *);
NvU64 NV_API_CALL os_acquire_spinlock(void *);
void NV_API_CALL os_release_spinlock(void *, NvU64);
NV_STATUS portSyncSpinlockInitialize(PORT_SPINLOCK *);
void portSyncSpinlockDestroy(PORT_SPINLOCK *);
void portSyncSpinlockAcquire(PORT_SPINLOCK *);
void portSyncSpinlockRelease(PORT_SPINLOCK *);
PORT_SPINLOCK *portSyncSpinlockCreate(PORT_MEM_ALLOCATOR *);
PORT_MUTEX *portSyncMutexCreate(PORT_MEM_ALLOCATOR *);

/* Implemented by the OS adapter: real formatted diagnostics and context guard. */
void portDbgPrintf(const char *, ...);
NvBool s540NvportLifecycleContextAllowed(void);

#ifdef __cplusplus
}
#endif
#endif
