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

/*
 * Adapted function extraction from pinned NVIDIA memory_tracking.c.
 * The explicitly documented bootstrap status adaptation is the only changed
 * NVIDIA function body. Existing-block, GSP-limit, fencepost, list, caller-info,
 * logging and complete core lifecycle support are deliberately absent.
 */
#include "../../nvidia-os-adapter/src/S540NvidiaAtomic.h"
#include "nvport_lifecycle.h"
#include "nvport_lifecycle_profile.h"

typedef struct PORT_MEM_FRAGMENTATION
{
    PORT_ATOMIC NvLength largestFreeChunkSize;
    PORT_ATOMIC NvLength freeHeapSize;
} PORT_MEM_FRAGMENTATION;

typedef struct PORT_MEM_COUNTER
{
    PORT_ATOMIC NvU32    activeAllocs;
    PORT_ATOMIC NvU32    totalAllocs;
    PORT_ATOMIC NvU32    peakAllocs;
    PORT_ATOMIC NvLength activeSize;
    PORT_ATOMIC NvLength totalSize;
    PORT_ATOMIC NvLength peakSize;
    PORT_MEM_FRAGMENTATION peakFragmentation;
} PORT_MEM_COUNTER;

struct PORT_MEM_ALLOCATOR_TRACKING
{
    PORT_MEM_ALLOCATOR                 *pAllocator;
    struct PORT_MEM_ALLOCATOR_TRACKING *pPrev;
    struct PORT_MEM_ALLOCATOR_TRACKING *pNext;

#if PORT_MEM_TRACK_USE_COUNTER
    PORT_MEM_COUNTER                    counter;
#endif
#if PORT_MEM_TRACK_USE_ALLOCLIST
    PORT_MEM_LIST                      *pFirstAlloc;
    void                               *listLock;
#endif
#if PORT_MEM_TRACK_USE_CALLERINFO
    PORT_MEM_CALLERINFO                 callerInfo;
#endif
#if PORT_MEM_TRACK_USE_LIMIT
    NvLength                            limitGfid;
    NvLength                            counterGfid;
    NvU32                               gfid;
    NvLength                            limitLibosGfid;
    NvLength                            counterLibosGfid;
#endif
};


#define PORT_MEM_ALLOCATOR_SIZE (sizeof(PORT_MEM_ALLOCATOR)+sizeof(PORT_MEM_ALLOCATOR_TRACKING))
struct PORT_MEM_ALLOCATOR_IMPL
{
    PORT_MEM_ALLOCATOR_TRACKING tracking;
};

#define PORT_MEM_LOCK_DESTROY(lock)                                            \
    do {                                                                       \
        portSyncSpinlockDestroy(lock);                                         \
        _portMemFreeUntracked(lock);                                           \
    } while(0)
#define PORT_MEM_LOCK_ACQUIRE(lock) portSyncSpinlockAcquire(lock)
#define PORT_MEM_LOCK_RELEASE(lock) portSyncSpinlockRelease(lock)


//
// List link operation that operates on structures that have pNext and pPrev
// fields. Assumes the root always exists.
//
#define PORT_LOCKED_LIST_LINK(pRoot, pNode, lock)                              \
    do {                                                                       \
        PORT_MEM_LOCK_ACQUIRE(lock);                                           \
          (pNode)->pNext = (pRoot);                                            \
          (pNode)->pPrev = (pRoot)->pPrev;                                     \
          (pRoot)->pPrev = (pNode);                                            \
          (pNode)->pPrev->pNext = (pNode);                                     \
        PORT_MEM_LOCK_RELEASE(lock);                                           \
    } while(0)

#define PORT_LOCKED_LIST_UNLINK(pRoot, pNode, lock)                            \
    do {                                                                       \
        PORT_MEM_LOCK_ACQUIRE(lock);                                           \
          (pNode)->pNext->pPrev = (pNode)->pPrev;                              \
          (pNode)->pPrev->pNext = (pNode)->pNext;                              \
        PORT_MEM_LOCK_RELEASE(lock);                                           \
    } while (0)

//
// All memory tracking globals are contained in this structure
//
static struct PORT_MEM_GLOBALS
{
    PORT_MEM_ALLOCATOR_TRACKING mainTracking;
    void *trackingLock;
    struct
    {
        PORT_MEM_ALLOCATOR paged;
        PORT_MEM_ALLOCATOR nonPaged;
        PORT_MEM_ALLOCATOR_IMPL pagedImpl;
        PORT_MEM_ALLOCATOR_IMPL nonPagedImpl;
    } alloc;
    PORT_ATOMIC NvU32 initCount;
    PORT_ATOMIC NvU32 totalAllocators;
#if PORT_MEM_TRACK_USE_LIMIT
    NvBool bLimitEnabled;
    PORT_MEM_ALLOCATOR_TRACKING *pGfidTracking[PORT_MEM_LIMIT_MAX_GFID];
#endif
    PORT_MEM_OOM_REPORT_CB pOomReportCb;
    PORT_ATOMIC NvU32 oomCount;
} portMemGlobals;

#define PORT_MEM_OOM_REPORT_INTERVAL 10U

#define PORT_MEM_ATOMIC_ADD_SIZE portAtomicAddSize
#define PORT_MEM_ATOMIC_SUB_SIZE portAtomicSubSize
#define PORT_MEM_ATOMIC_DEC_U32 portAtomicDecrementU32
#define PORT_MEM_ATOMIC_INC_U32 portAtomicIncrementU32
#define PORT_MEM_ATOMIC_CAS_SIZE portAtomicCompareAndSwapSize
#define PORT_MEM_ATOMIC_CAS_U32 portAtomicCompareAndSwapU32
static void *_portMemAllocatorAllocPagedWrapper(PORT_MEM_ALLOCATOR *, NvLength);
static void *_portMemAllocatorAllocNonPagedWrapper(PORT_MEM_ALLOCATOR *, NvLength);
static void _portMemAllocatorFreeWrapper(PORT_MEM_ALLOCATOR *, void *);
static void _portMemAllocatorReleaseWrapper(PORT_MEM_ALLOCATOR *);
static void _portMemTrackingRelease(PORT_MEM_ALLOCATOR_TRACKING *, NvBool);
static void _portMemTrackAlloc(PORT_MEM_ALLOCATOR_TRACKING *, void *, NvLength, NvU32);
static NvBool _portMemTrackFree(PORT_MEM_ALLOCATOR_TRACKING *, void *);
#define PORT_MEM_COUNTER_INIT(pCounter) _portMemCounterInit(pCounter)
#define PORT_MEM_COUNTER_INC(pCounter,size) _portMemCounterInc(pCounter,size)
#define PORT_MEM_COUNTER_DEC(pCounter,size) _portMemCounterDec(pCounter,size)

static NV_INLINE void
_portMemCounterInit
(
    PORT_MEM_COUNTER *pCounter
)
{
    portMemSet(pCounter, 0, sizeof(*pCounter));
}

static NV_INLINE void
_portMemCounterInc
(
    PORT_MEM_COUNTER *pCounter,
    NvLength          size
)
{
    NvU32 activeAllocs;
    NvLength activeSize = 0;

    activeAllocs = PORT_MEM_ATOMIC_INC_U32(&pCounter->activeAllocs);
    PORT_MEM_ATOMIC_INC_U32(&pCounter->totalAllocs);
#if PORT_MEM_TRACK_ALLOC_SIZE
    //
    // activeSize is only tracked on configurations where we can retrieve the
    // allocation size from allocation metadata in _portMemCounterDec.
    //
    activeSize = PORT_MEM_ATOMIC_ADD_SIZE(&pCounter->activeSize, size);
#endif

    //
    // Note: this can overflow on 32-bit platforms if we exceed 4GB cumulative
    // allocations. It's not trivial to fix, since NvPort doesn't emulate 64-bit
    // atomics on 32-bit platforms, so just assume this doesn't happen (or
    // doesn't matter too much if it does, since it's only for reporting).
    //
    PORT_MEM_ATOMIC_ADD_SIZE(&pCounter->totalSize, size);

    // Update the peak stats, if we're updating the peakSize
    {
        NvU32 peakAllocs;
        NvLength peakSize = pCounter->peakSize;
        while (activeSize > peakSize)
        {
            PORT_MEM_ATOMIC_CAS_SIZE(&pCounter->peakSize, activeSize, peakSize);
            peakSize = pCounter->peakSize;
        }

        //
        // Ensure peakAllocs stays (approximately) in sync with peakSize, rather
        // than always taking the greatest peakAllocs, so that the peak stats
        // report is consistent.
        //
        do
        {
            peakAllocs = pCounter->peakAllocs;

            //
            // Only attempt to update the peakAllocs if activeSize is still the
            // peakSize.
            //
            if (activeSize != pCounter->peakSize)
                break;
        } while (!PORT_MEM_ATOMIC_CAS_U32(&pCounter->peakAllocs, activeAllocs, peakAllocs));
    }

#if PORT_MEM_TRACK_ALLOC_SIZE
#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetHeapSize)
    // Check aggregate heap utilization and fragmentation
    if (pCounter == &portMemGlobals.mainTracking.counter)
    {
        NvLength allocatedSize = pCounter->activeSize + (pCounter->activeAllocs * PORT_MEM_STAGING_SIZE);
        NvLength heapSize = portMemExTrackingGetHeapSize();
        NvLength freeHeapSize = heapSize - allocatedSize;

        // Check whether heap utilization is above ~90% (1 - 1/16 == 93.75%)
        if (allocatedSize > (heapSize - (heapSize >> 4)))
        {
            static NvU32 rateLimit = 0;
            if (rateLimit % 50 == 0)
            {
                portDbgPrintf("WARNING: GSP-RM malloc heap usage above 90%% capacity %"NvUPtr_fmtu" / %"NvUPtr_fmtu" bytes\n",
                    allocatedSize, heapSize);
            }
            rateLimit++;
        }

#if PORT_IS_FUNC_SUPPORTED(portMemGetLargestFreeChunkSize)
#define FRAGMENTATION_CHECK_INTERVAL 100
        static NvU32 fragCheckLimit = 0;
        
        if (fragCheckLimit % FRAGMENTATION_CHECK_INTERVAL == 0)
        {
            NvLength largestFreeChunkSize = portMemGetLargestFreeChunkSize();

            // Check whether fragmentation is >=75% (Fragmentation: 1 - (largestFreeChunkSize / freeHeapSize))
            if (largestFreeChunkSize <= (freeHeapSize >> 2))
            {
                portDbgPrintf("WARNING: GSP-RM malloc heap fragmentation above 75%% %"NvUPtr_fmtu" / %"NvUPtr_fmtu")\n",
                    largestFreeChunkSize, freeHeapSize);

                // Compare (freeChunkSize / freeHeapSize) for current and peak (cross-multiplied), then update peak
                if ((largestFreeChunkSize * pCounter->peakFragmentation.freeHeapSize) <=
                    (freeHeapSize * pCounter->peakFragmentation.largestFreeChunkSize))
                {
                    pCounter->peakFragmentation.largestFreeChunkSize = largestFreeChunkSize;
                    pCounter->peakFragmentation.freeHeapSize = freeHeapSize;
                }
            }
        }
        fragCheckLimit++;
#endif
    }
#endif
#endif
}

static NV_INLINE void
_portMemCounterDec
(
    PORT_MEM_COUNTER *pCounter,
    NvLength          size
)
{
    PORT_MEM_ATOMIC_DEC_U32(&pCounter->activeAllocs);
#if PORT_MEM_TRACK_ALLOC_SIZE
    PORT_MEM_ATOMIC_SUB_SIZE(&pCounter->activeSize, size);
#else
    PORT_UNREFERENCED_VARIABLE(size);
#endif
}

static NV_INLINE PORT_MEM_ALLOCATOR_TRACKING *
_portMemGetTracking
(
    const PORT_MEM_ALLOCATOR *pAlloc
)
{
    if (pAlloc == NULL)
        return &portMemGlobals.mainTracking;
    else
        return pAlloc->pTracking;
}

NV_STATUS
s540NvportMemoryInitialize(void)
{
#if PORT_MEM_TRACK_USE_CALLERINFO
    PORT_MEM_CALLERINFO_TYPE_PARAM = PORT_MEM_CALLERINFO_MAKE;
#endif
    PORT_SPINLOCK *pBootstrapLock;
    NV_STATUS status;

    /* Adaptation: caller serializes lifecycle and the OS guard rejects IRQ or
     * interrupt-disabled contexts before either backend allocation. */
    if (!s540NvportLifecycleContextAllowed())
        return NV_ERR_INVALID_STATE;
    if (portMemGlobals.initCount == NV_U32_MAX)
        return NV_ERR_INVALID_STATE;
    if (portMemGlobals.initCount != 0)
    {
        PORT_MEM_ATOMIC_INC_U32(&portMemGlobals.initCount);
        return NV_OK;
    }

    pBootstrapLock = _portMemAllocNonPagedUntracked(portSyncSpinlockSize);
    if (pBootstrapLock == NULL)
        return NV_ERR_NO_MEMORY;
    status = portSyncSpinlockInitialize(pBootstrapLock);
    if (status != NV_OK)
    {
        _portMemFreeUntracked(pBootstrapLock);
        return status;
    }
    /* No fallible operation remains in this fixed COUNTER-only profile. */
    PORT_MEM_ATOMIC_INC_U32(&portMemGlobals.initCount);

    portMemGlobals.mainTracking.pAllocator = NULL;
    portMemGlobals.mainTracking.pNext = &portMemGlobals.mainTracking;
    portMemGlobals.mainTracking.pPrev = &portMemGlobals.mainTracking;
    PORT_MEM_COUNTER_INIT(&portMemGlobals.mainTracking.counter);
    PORT_MEM_LIST_INIT(&portMemGlobals.mainTracking);
    portMemGlobals.trackingLock = pBootstrapLock;

#if PORT_MEM_TRACK_USE_LIMIT
    // Initialize process heap limit to max int (i.e. no limit)
    portMemGlobals.bLimitEnabled = NV_FALSE;
#endif

    portMemGlobals.alloc.paged._portAlloc      = _portMemAllocatorAllocPagedWrapper;
    portMemGlobals.alloc.nonPaged._portAlloc   = _portMemAllocatorAllocNonPagedWrapper;
    portMemGlobals.alloc.paged._portFree       = _portMemAllocatorFreeWrapper;
    portMemGlobals.alloc.nonPaged._portFree    = _portMemAllocatorFreeWrapper;
    portMemGlobals.alloc.paged._portRelease    = NULL;
    portMemGlobals.alloc.nonPaged._portRelease = NULL;

    if (PORT_MEM_TRACK_USE_FENCEPOSTS)
    {
        //
        // Distinct paged and non-paged allocators require PORT_MEM_TRACK_USE_FENCEPOSTS
        // so that the correct allocator can be looked up from the fenceposts in the
        // portMemFree path.
        //
        portMemGlobals.alloc.paged.pImpl    = &portMemGlobals.alloc.pagedImpl;
        portMemGlobals.alloc.nonPaged.pImpl = &portMemGlobals.alloc.nonPagedImpl;

        portMemInitializeAllocatorTracking(&portMemGlobals.alloc.paged,
                                     &portMemGlobals.alloc.paged.pImpl->tracking
                                     PORT_MEM_CALLERINFO_COMMA_PARAM);
        portMemInitializeAllocatorTracking(&portMemGlobals.alloc.nonPaged,
                                  &portMemGlobals.alloc.nonPaged.pImpl->tracking
                                  PORT_MEM_CALLERINFO_COMMA_PARAM);
    }
    else
    {
        // Use the same impl for both paged and nonpaged.
        portMemGlobals.alloc.paged.pImpl    = &portMemGlobals.alloc.pagedImpl;
        portMemGlobals.alloc.nonPaged.pImpl = &portMemGlobals.alloc.pagedImpl;
        portMemInitializeAllocatorTracking(&portMemGlobals.alloc.paged,
                             &portMemGlobals.alloc.pagedImpl.tracking
                             PORT_MEM_CALLERINFO_COMMA_PARAM);
        portMemGlobals.alloc.paged.pTracking    = &portMemGlobals.alloc.pagedImpl.tracking;
        portMemGlobals.alloc.nonPaged.pTracking = &portMemGlobals.alloc.pagedImpl.tracking;
    }
    PORT_MEM_LOG_INIT();
    return NV_OK;
}

void
portMemShutdown(NvBool bForceSilent)
{
    PORT_UNREFERENCED_VARIABLE(bForceSilent);
    if (PORT_MEM_ATOMIC_DEC_U32(&portMemGlobals.initCount) != 0)
        return;

#if (PORT_MEM_TRACK_PRINT_LEVEL > PORT_MEM_TRACK_PRINT_LEVEL_SILENT)
    if (!bForceSilent)
    {
        portMemPrintAllTrackingInfo(NV_TRUE);
    }
#endif
    PORT_MEM_LOG_DESTROY();

    if (PORT_MEM_TRACK_USE_FENCEPOSTS)
    {
        _portMemTrackingRelease(&portMemGlobals.alloc.nonPaged.pImpl->tracking, NV_FALSE);
        _portMemTrackingRelease(&portMemGlobals.alloc.paged.pImpl->tracking, NV_FALSE);
    }
    else
    {
        _portMemTrackingRelease(&portMemGlobals.alloc.pagedImpl.tracking, NV_FALSE);
    }
#if PORT_MEM_TRACK_USE_LIMIT
    _portMemTrackingGfidRelease();
#endif
    PORT_MEM_LOCK_DESTROY(portMemGlobals.trackingLock);
    PORT_MEM_LIST_DESTROY(&portMemGlobals.mainTracking);
    portMemSet(&portMemGlobals, 0, sizeof(portMemGlobals));
}

void *
portMemAllocPaged
(
    NvLength length
    PORT_MEM_CALLERINFO_COMMA_TYPE_PARAM
)
{
#if defined(__COVERITY__)
    return __coverity_alloc__(length);
#endif
    PORT_MEM_ALLOCATOR *pAlloc = portMemAllocatorGetGlobalPaged();
    return _portMemAllocatorAlloc(pAlloc, length PORT_MEM_CALLERINFO_COMMA_PARAM);
}

void *
portMemAllocNonPaged
(
    NvLength length
    PORT_MEM_CALLERINFO_COMMA_TYPE_PARAM
)
{
#if defined(__COVERITY__)
    return __coverity_alloc__(length);
#endif
    PORT_MEM_ALLOCATOR *pAlloc = portMemAllocatorGetGlobalNonPaged();
    return _portMemAllocatorAlloc(pAlloc, length PORT_MEM_CALLERINFO_COMMA_PARAM);
}

void
portMemFree
(
    void *pMem
)
{
    if (pMem != NULL)
    {
#if PORT_MEM_TRACK_USE_FENCEPOSTS
        PORT_MEM_HEADER *pHead = (PORT_MEM_HEADER*)pMem - 1;
        PORT_FREE(pHead->fence.pAllocator, pMem);
#else
        // Paged/nonpaged are logged together if we don't have fenceposts.
        PORT_FREE(portMemAllocatorGetGlobalPaged(), pMem);
#endif
    }

#if defined(__COVERITY__)
    __coverity_free__(pMem);
#endif
}

PORT_MEM_ALLOCATOR *
portMemAllocatorCreatePaged(PORT_MEM_CALLERINFO_TYPE_PARAM)
{
    PORT_MEM_ALLOCATOR *pAllocator;

    pAllocator = portMemAllocPaged(PORT_MEM_ALLOCATOR_SIZE
                                   PORT_MEM_CALLERINFO_COMMA_PARAM);
    if (pAllocator == NULL)
        return NULL;

    pAllocator->pImpl         = (PORT_MEM_ALLOCATOR_IMPL*)(pAllocator + 1);
    pAllocator->_portAlloc    = _portMemAllocatorAllocPagedWrapper;
    pAllocator->_portFree     = _portMemAllocatorFreeWrapper;
    pAllocator->_portRelease  = _portMemAllocatorReleaseWrapper;
    portMemInitializeAllocatorTracking(pAllocator, &pAllocator->pImpl->tracking
                                       PORT_MEM_CALLERINFO_COMMA_PARAM);

    PORT_MEM_PRINT_INFO("Acquired paged allocator %p ", pAllocator);
    PORT_MEM_PRINT_INFO(PORT_MEM_CALLERINFO_PRINT_ARGS(PORT_MEM_CALLERINFO_PARAM));

    return pAllocator;
}

PORT_MEM_ALLOCATOR *
portMemAllocatorCreateNonPaged(PORT_MEM_CALLERINFO_TYPE_PARAM)
{
    PORT_MEM_ALLOCATOR *pAllocator;

    pAllocator = portMemAllocNonPaged(PORT_MEM_ALLOCATOR_SIZE
                                      PORT_MEM_CALLERINFO_COMMA_PARAM);
    if (pAllocator == NULL)
        return NULL;

    pAllocator->pImpl         = (PORT_MEM_ALLOCATOR_IMPL*)(pAllocator + 1);
    pAllocator->_portAlloc    = _portMemAllocatorAllocNonPagedWrapper;
    pAllocator->_portFree     = _portMemAllocatorFreeWrapper;
    pAllocator->_portRelease  = _portMemAllocatorReleaseWrapper;
    portMemInitializeAllocatorTracking(pAllocator, &pAllocator->pImpl->tracking
                                       PORT_MEM_CALLERINFO_COMMA_PARAM);

    PORT_MEM_PRINT_INFO("Acquired nonpaged allocator %p ", pAllocator);
    PORT_MEM_PRINT_INFO(PORT_MEM_CALLERINFO_PRINT_ARGS(PORT_MEM_CALLERINFO_PARAM));
    return pAllocator;
}

void
portMemAllocatorRelease
(
    PORT_MEM_ALLOCATOR *pAllocator
)
{
    if (pAllocator == NULL)
    {
        PORT_BREAKPOINT_CHECKED();
        return;
    }
    _portMemTrackingRelease(pAllocator->pTracking, NV_TRUE);
    PORT_MEM_PRINT_INFO("Released allocator %p\n", pAllocator);

    if (pAllocator->_portRelease != NULL)
        pAllocator->_portRelease(pAllocator);
}

PORT_MEM_ALLOCATOR *
portMemAllocatorGetGlobalNonPaged(void)
{
    return &portMemGlobals.alloc.nonPaged;
}

PORT_MEM_ALLOCATOR *
portMemAllocatorGetGlobalPaged(void)
{
    return &portMemGlobals.alloc.paged;
}

void
portMemInitializeAllocatorTracking
(
    PORT_MEM_ALLOCATOR          *pAlloc,
    PORT_MEM_ALLOCATOR_TRACKING *pTracking
    PORT_MEM_CALLERINFO_COMMA_TYPE_PARAM
)
{
    if (portMemGlobals.initCount == 0)
    {
        portMemSet(pTracking, 0, sizeof(*pTracking));
        if (pAlloc != NULL)
            pAlloc->pTracking = NULL;
        return;
    }

    pTracking->pAllocator = pAlloc;
    if (pAlloc != NULL)
        pAlloc->pTracking = pTracking;
    PORT_LOCKED_LIST_LINK(&portMemGlobals.mainTracking, pTracking, portMemGlobals.trackingLock);
    PORT_MEM_COUNTER_INIT(&pTracking->counter);
    PORT_MEM_LIST_INIT(pTracking);
    PORT_MEM_CALLERINFO_INIT_TRACKING(pTracking);
    PORT_MEM_ATOMIC_INC_U32(&portMemGlobals.totalAllocators);
}

void *
_portMemAllocatorAlloc
(
    PORT_MEM_ALLOCATOR *pAlloc,
    NvLength length
    PORT_MEM_CALLERINFO_COMMA_TYPE_PARAM
)
{
    NvU32 gfid = 0;
    void *pMem = NULL;
#if NVOS_IS_LIBOS && defined(DEBUG)
    ERROR_INJECTION_PROBE_PF(NV2082_CTRL_GSP_INJECT_TARGET_NVPORT_MEM_ALLOC);
    if (g_bMemoryAllocationFailure)
    {
        portDbgPrintf("  !!! MEMORY ALLOCATION FAILURE !!!\n");
        g_bMemoryAllocationFailure = NV_FALSE;
        return NULL;
    }
#endif
    if (pAlloc == NULL)
    {
        PORT_BREAKPOINT_CHECKED();
        return NULL;
    }

#if PORT_MEM_TRACK_USE_LIMIT
    if (portMemGlobals.bLimitEnabled)
    {
        if (osGetCurrentProcessGfid(&gfid) != NV_OK)
        {
            PORT_BREAKPOINT_CHECKED();
            return NULL;
        }
    }
#endif

    // Check if per-process memory limit will be exhausted by this allocation
    if (PORT_MEM_LIMIT_EXCEEDED(gfid, length))
    {
        portMemReportOom(length);
        return NULL;
    }

    if (length > 0)
    {
        NvLength paddedLength;
// RISCV64 requires 64-bit alignment of structures, and length indicates the alignment of the footer
#if defined(__riscv)
        if (PORT_MEM_STAGING_SIZE > 0 && (length & 7))
        {
            if (!portSafeAddLength(length & ~7, 8, &length))
            {
                return NULL;
            }
        }
#endif
        if (!portSafeAddLength(length, PORT_MEM_STAGING_SIZE, &paddedLength))
        {
            return NULL;
        }
        pMem = pAlloc->_portAlloc(pAlloc, paddedLength);
    }
    if (pMem == NULL && length > 0)
    {
        portMemReportOom(length);
    }
    if (pMem != NULL)
    {
        pMem = PORT_MEM_ADD_HEADER_PTR(pMem);
        _portMemTrackAlloc(_portMemGetTracking(pAlloc), pMem, length, gfid
                           PORT_MEM_CALLERINFO_COMMA_PARAM);
    }
    return pMem;
}

void
_portMemAllocatorFree
(
    PORT_MEM_ALLOCATOR *pAlloc,
    void *pMem
)
{
    if (pAlloc == NULL)
    {
        PORT_BREAKPOINT_CHECKED();
        return;
    }
    if (pMem != NULL)
    {
        if (_portMemTrackFree(_portMemGetTracking(pAlloc), pMem))
        {
            pMem = PORT_MEM_SUB_HEADER_PTR(pMem);
            pAlloc->_portFree(pAlloc, pMem);
        }
    }
}

void
portMemPrintTrackingInfo
(
    const PORT_MEM_ALLOCATOR_TRACKING *pTracking,
    NvBool bReportLeaks
)
{
    if (pTracking == NULL)
        pTracking = &portMemGlobals.mainTracking;

    if (pTracking == &portMemGlobals.mainTracking)
        portDbgPrintf("[NvPort] ======== Aggregate Memory Tracking ========\n");
    else if ((pTracking == portMemGlobals.alloc.nonPaged.pTracking) &&
             (pTracking == portMemGlobals.alloc.paged.pTracking))
        portDbgPrintf("[NvPort] ======== Global Allocator Tracking ========\n");
    else if (pTracking == portMemGlobals.alloc.nonPaged.pTracking)
        portDbgPrintf("[NvPort] ======== Global Non-Paged Memory Allocator Tracking ========\n");
    else if (pTracking == portMemGlobals.alloc.paged.pTracking)
        portDbgPrintf("[NvPort] ======== Global Paged Memory Allocator Tracking ========\n");
#if PORT_MEM_TRACK_USE_LIMIT
    else if (isGfidValid(pTracking->gfid))
        portDbgPrintf("[NvPort] ======== GFID %u Tracking ========\n", pTracking->gfid);
#endif
    else
        portDbgPrintf("[NvPort] ======== Memory Allocator %p Tracking ======== \n", pTracking->pAllocator);

    if (bReportLeaks && (pTracking->counter.activeAllocs != 0))
        portDbgPrintf("  !!! MEMORY LEAK DETECTED (%u blocks) !!!\n",
                      pTracking->counter.activeAllocs);

#if PORT_MEM_TRACK_USE_CALLERINFO
    {
        portDbgPrintf("  Allocator acquired "
            PORT_MEM_CALLERINFO_PRINT_ARGS(pTracking->callerInfo));
    }
#endif

#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetHeapSize)
    //
    // Heap is shared across all allocators, so only print it with the
    // aggregate stats.
    //
    if (pTracking == _portMemGetTracking(NULL))
        portDbgPrintf("  HEAP:   %"NvUPtr_fmtu" bytes\n", portMemExTrackingGetHeapSize());
#endif

#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetActiveStats)
    {
        PORT_MEM_TRACK_ALLOCATOR_STATS stats;

        portMemSet(&stats, 0, sizeof(stats));
#if PORT_MEM_TRACK_USE_LIMIT
        if (isGfidValid(pTracking->gfid))
        {
            portMemExTrackingGetGfidActiveStats(pTracking->gfid, &stats);
        }
        else
#endif
        {
            portMemExTrackingGetActiveStats(pTracking->pAllocator, &stats);
        }

        //
        // rmtest_gsp test script (dvs_gsp_sanity.sh) depends on this print, so do not change
        // format without updating script!
        //
        portDbgPrintf("  ACTIVE: %u allocations, %"NvUPtr_fmtu" bytes allocated (%"NvUPtr_fmtu" useful, %"NvUPtr_fmtu" meta)\n",
                    stats.numAllocations,
                    stats.allocatedSize,
                    stats.usefulSize,
                    stats.metaSize);

        if (pTracking->counter.peakFragmentation.freeHeapSize > 0)
        {
            // Only aggregate tracking prints fragmentation data
#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetHeapSize)
#if PORT_IS_FUNC_SUPPORTED(portMemGetLargestFreeChunkSize)
            NvLength allocatedSize = pTracking->counter.activeSize + (pTracking->counter.activeAllocs * PORT_MEM_STAGING_SIZE);
            NvLength heapSize = portMemExTrackingGetHeapSize();
            NvLength largestFreeChunkSize = portMemGetLargestFreeChunkSize();
            NvLength freeHeapSize = heapSize - allocatedSize;

            portDbgPrintf("  FRAG:   %"NvUPtr_fmtu"%% curr fragmentation @ %"NvUPtr_fmtu" bytes largest free chunk with %"NvUPtr_fmtu" bytes free heap\n",
                    (100 - ((100 * largestFreeChunkSize) / freeHeapSize)),
                    largestFreeChunkSize,
                    freeHeapSize);
#endif
#endif

            portDbgPrintf("          %"NvUPtr_fmtu"%% peak fragmentation @ %"NvUPtr_fmtu" bytes largest free chunk with %"NvUPtr_fmtu" bytes free heap\n",
                    (100 - ((100 * pTracking->counter.peakFragmentation.largestFreeChunkSize) / pTracking->counter.peakFragmentation.freeHeapSize)),
                    pTracking->counter.peakFragmentation.largestFreeChunkSize,
                    pTracking->counter.peakFragmentation.freeHeapSize);
        }
    }
#endif

#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetTotalStats)
    {
        PORT_MEM_TRACK_ALLOCATOR_STATS stats;

        portMemSet(&stats, 0, sizeof(stats));
#if PORT_MEM_TRACK_USE_LIMIT
        if (isGfidValid(pTracking->gfid))
        {
            portMemExTrackingGetGfidTotalStats(pTracking->gfid, &stats);
        }
        else
#endif
        {
            portMemExTrackingGetTotalStats(pTracking->pAllocator, &stats);
        }
        portDbgPrintf("  TOTAL:  %u allocations, %"NvUPtr_fmtu" bytes allocated (%"NvUPtr_fmtu" useful, %"NvUPtr_fmtu" meta)\n",
                    stats.numAllocations,
                    stats.allocatedSize,
                    stats.usefulSize,
                    stats.metaSize);
    }
#endif

#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetPeakStats)
    {
        PORT_MEM_TRACK_ALLOCATOR_STATS stats;

        portMemSet(&stats, 0, sizeof(stats));
#if PORT_MEM_TRACK_USE_LIMIT
        if (isGfidValid(pTracking->gfid))
        {
            portMemExTrackingGetGfidPeakStats(pTracking->gfid, &stats);
        }
        else
#endif
        {
            portMemExTrackingGetPeakStats(pTracking->pAllocator, &stats);
        }
        portDbgPrintf("  PEAK:   %u allocations, %"NvUPtr_fmtu" bytes allocated (%"NvUPtr_fmtu" useful, %"NvUPtr_fmtu" meta)\n",
                    stats.numAllocations,
                    stats.allocatedSize,
                    stats.usefulSize,
                    stats.metaSize);
    }
#endif

#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetNext)
    {
        PORT_MEM_TRACK_ALLOC_INFO info;
        NvBool bPrinted = NV_FALSE;
        void *iterator = NULL;

        do
        {
            if (portMemExTrackingGetNext(pTracking->pAllocator, &info, &iterator) != NV_OK)
            {
                portDbgPrintf("  (no active allocations)\n");
                break;
            }
            else if (!bPrinted)
            {
                portDbgPrintf("  Currently active allocations:\n");
                bPrinted = NV_TRUE;
            }
            portDbgPrintf("   - A:%p - 0x%p [%8"NvUPtr_fmtu" bytes] T=%llu ",
                            info.pAllocator,
                            info.pMemory,
                            info.size,
                            info.timestamp);
            portDbgPrintf(PORT_MEM_CALLERINFO_PRINT_ARGS(info.callerInfo));
        } while (iterator != NULL);
    }
#endif
}

void
portMemPrintAllTrackingInfo(NvBool bReportLeaks)
{
    const PORT_MEM_ALLOCATOR_TRACKING *pTracking = &portMemGlobals.mainTracking;
    PORT_MEM_LOCK_ACQUIRE(portMemGlobals.trackingLock);
    do
    {
        portMemPrintTrackingInfo(pTracking, bReportLeaks);
    } while ((pTracking = pTracking->pNext) != &portMemGlobals.mainTracking);
    PORT_MEM_LOCK_RELEASE(portMemGlobals.trackingLock);
}

void
portMemRegisterOomReportCb(PORT_MEM_OOM_REPORT_CB pReportCb)
{
    portMemGlobals.pOomReportCb = pReportCb;
}

void
portMemReportOom(NvLength requestedSize)
{
    NvU32 oomCount;

    if (portMemGlobals.pOomReportCb == NULL)
        return;

    oomCount = PORT_MEM_ATOMIC_INC_U32(&portMemGlobals.oomCount);

    if (oomCount != 1U && (oomCount % PORT_MEM_OOM_REPORT_INTERVAL) != 0U)
        return;

    portDbgPrintf("[NvPort] ===== OOM REPORT #%u (requested %"NvUPtr_fmtu" bytes) =====\n",
                  oomCount, requestedSize);

    portDbgPrintf("  --- GSP-RM Malloc Heap ---\n");
#if PORT_IS_FUNC_SUPPORTED(portMemExTrackingGetHeapSize)
    {
        PORT_MEM_COUNTER *pCounter = &portMemGlobals.mainTracking.counter;
        NvLength heapSize = portMemExTrackingGetHeapSize();
        NvLength allocatedSize = pCounter->activeSize +
            ((NvLength)pCounter->activeAllocs * PORT_MEM_STAGING_SIZE);
        NvLength freeSize = (heapSize > allocatedSize)
                            ? (heapSize - allocatedSize) : 0U;

        portDbgPrintf("  FREE:   %"NvUPtr_fmtu" bytes of %"NvUPtr_fmtu" bytes heap\n",
                    freeSize, heapSize);

#if PORT_IS_FUNC_SUPPORTED(portMemGetLargestFreeChunkSize)
        {
            NvLength largestFreeChunk = portMemGetLargestFreeChunkSize();
            NvLength fragPct = 0U;

            // Clamp the ratio to 100 to avoid an unsigned underflow in the subtraction below.
            if (freeSize > 0U && largestFreeChunk <= freeSize)
            {
                fragPct = 100U - ((100U * largestFreeChunk) / freeSize);
            }

            portDbgPrintf("  FRAG:   %"NvUPtr_fmtu"%% fragmentation,"
                        " largest free chunk %"NvUPtr_fmtu" bytes\n",
                        fragPct, largestFreeChunk);
        }
#endif
    }
#endif

    portMemPrintAllTrackingInfo(NV_FALSE);

#if PORT_MEM_TRACK_USE_LIMIT
    {
        NvU32 gfidIdx;

        for (gfidIdx = 0U; gfidIdx < PORT_MEM_LIMIT_MAX_GFID; ++gfidIdx)
        {
            PORT_MEM_ALLOCATOR_TRACKING *pGfidTracking =
                portMemGlobals.pGfidTracking[gfidIdx];

            if (pGfidTracking == NULL)
                continue;

            portDbgPrintf("  GFID %u: %"NvUPtr_fmtu" / %"NvUPtr_fmtu" bytes RM",
                          gfidIdx + 1U,
                          pGfidTracking->counterGfid,
                          pGfidTracking->limitGfid);
            portDbgPrintf(", %"NvUPtr_fmtu" / %"NvUPtr_fmtu" bytes LibOS",
                          pGfidTracking->counterLibosGfid,
                          pGfidTracking->limitLibosGfid);
            portDbgPrintf("\n");
        }
    }
#endif

    if (portMemGlobals.pOomReportCb != NULL)
    {
        portMemGlobals.pOomReportCb();
    }

    portDbgPrintf("[NvPort] ===== END OOM REPORT =====\n");
}

NV_STATUS
portMemExTrackingGetActiveStats
(
    const PORT_MEM_ALLOCATOR       *pAllocator,
    PORT_MEM_TRACK_ALLOCATOR_STATS *pStats
)
{
    PORT_MEM_ALLOCATOR_TRACKING *pTracking = _portMemGetTracking(pAllocator);
    if (pTracking == NULL)
    {
        return NV_ERR_OBJECT_NOT_FOUND;
    }
    pStats->numAllocations = pTracking->counter.activeAllocs;
    pStats->usefulSize     = pTracking->counter.activeSize;
    pStats->metaSize       = pStats->numAllocations * PORT_MEM_STAGING_SIZE;
    pStats->allocatedSize  = pStats->usefulSize + pStats->metaSize;
    return NV_OK;
}

NV_STATUS
portMemExTrackingGetTotalStats
(
    const PORT_MEM_ALLOCATOR       *pAllocator,
    PORT_MEM_TRACK_ALLOCATOR_STATS *pStats
)
{
    PORT_MEM_ALLOCATOR_TRACKING *pTracking = _portMemGetTracking(pAllocator);
    if (pTracking == NULL)
    {
        return NV_ERR_OBJECT_NOT_FOUND;
    }
    pStats->numAllocations = pTracking->counter.totalAllocs;
    pStats->usefulSize     = pTracking->counter.totalSize;
    pStats->metaSize       = pStats->numAllocations * PORT_MEM_STAGING_SIZE;
    pStats->allocatedSize  = pStats->usefulSize + pStats->metaSize;
    return NV_OK;
}

NV_STATUS
portMemExTrackingGetPeakStats
(
    const PORT_MEM_ALLOCATOR       *pAllocator,
    PORT_MEM_TRACK_ALLOCATOR_STATS *pStats
)
{
    PORT_MEM_ALLOCATOR_TRACKING *pTracking = _portMemGetTracking(pAllocator);
    if (pTracking == NULL)
    {
        return NV_ERR_OBJECT_NOT_FOUND;
    }
    pStats->numAllocations = pTracking->counter.peakAllocs;
    pStats->usefulSize     = pTracking->counter.peakSize;
    pStats->metaSize       = pStats->numAllocations * PORT_MEM_STAGING_SIZE;
    pStats->allocatedSize  = pStats->usefulSize + pStats->metaSize;
    return NV_OK;
}

static void
_portMemTrackingRelease
(
    PORT_MEM_ALLOCATOR_TRACKING *pTracking,
    NvBool bReportLeaks
)
{
    if (pTracking == NULL) return;

#if (PORT_MEM_TRACK_PRINT_LEVEL > PORT_MEM_TRACK_PRINT_LEVEL_SILENT)
    if (bReportLeaks && (pTracking->counter.activeAllocs != 0))
        portMemPrintTrackingInfo(pTracking, bReportLeaks);
#else
    PORT_UNREFERENCED_VARIABLE(bReportLeaks);
#endif

    PORT_LOCKED_LIST_UNLINK(&portMemGlobals.mainTracking, pTracking, portMemGlobals.trackingLock);
    PORT_MEM_LIST_DESTROY(pTracking);
#if PORT_MEM_TRACK_USE_LIMIT
    if (isGfidValid(pTracking->gfid))
    {
        _portMemFreeUntracked(pTracking);
    }
    else
#endif
    {
        PORT_MEM_ATOMIC_DEC_U32(&portMemGlobals.totalAllocators);
    }
}

static void
_portMemTrackAlloc
(
    PORT_MEM_ALLOCATOR_TRACKING *pTracking,
    void                        *pMem,
    NvLength                     size,
    NvU32                        gfid
    PORT_MEM_CALLERINFO_COMMA_TYPE_PARAM
)
{
    PORT_UNREFERENCED_VARIABLE(pMem);
    if (pTracking == NULL) return;

#if PORT_MEM_TRACK_ALLOC_SIZE
    //
    // Either set the block size in the header, or override it with the value
    // from the underlying allocator (which may be bigger than what was
    // requested). This keeps the counters consistent with the free path.
    //
    _portMemExTrackingSetOrGetAllocUsableSize(pMem, &size);
#endif

    PORT_MEM_PRINT_INFO("Allocated %"NvUPtr_fmtu" bytes at address %p", size, pMem);
    PORT_MEM_PRINT_INFO(PORT_MEM_CALLERINFO_PRINT_ARGS(PORT_MEM_CALLERINFO_PARAM));

    PORT_MEM_COUNTER_INC(&pTracking->counter, size);
    PORT_MEM_COUNTER_INC(&portMemGlobals.mainTracking.counter, size);
    PORT_MEM_LIMIT_INC(gfid, pMem, size);

    PORT_MEM_FENCE_INIT(pTracking->pAllocator, pMem, size);
    PORT_MEM_LIST_ADD(pTracking, pMem);
    PORT_MEM_CALLERINFO_INIT_MEM(pMem);
    PORT_MEM_LOG_ALLOC(pTracking->pAllocator, pMem, size);
#if PORT_MEM_TRACK_USE_LIMIT
    if (isGfidValid(gfid))
    {
        NvU32 gfidIdx = gfid - 1;

        PORT_MEM_COUNTER_INC(&portMemGlobals.pGfidTracking[gfidIdx]->counter, size);
    }
#endif
}

static NvBool
_portMemTrackFree
(
    PORT_MEM_ALLOCATOR_TRACKING *pTracking,
    void                        *pMem
)
{
    NvLength size = 0;
#if PORT_MEM_TRACK_USE_FENCEPOSTS
    PORT_MEM_HEADER *pHead = (PORT_MEM_HEADER*)pMem - 1;
#endif

    if (pTracking == NULL) return NV_TRUE;

#if PORT_MEM_TRACK_USE_FENCEPOSTS
    if (pHead->fence.magic == PORT_MEM_FENCE_FREE_MAGIC)
    {
        PORT_MEM_PRINT_ERROR("Detected double free of block at address %p\n", pMem);
        PORT_ASSERT_CHECKED(pHead->fence.magic == PORT_MEM_FENCE_FREE_MAGIC);
        return NV_FALSE;
    }
#endif

#if PORT_MEM_TRACK_ALLOC_SIZE
    size = _portMemExTrackingGetAllocUsableSizeWrapper(pMem);
    PORT_MEM_PRINT_INFO("Freeing %"NvUPtr_fmtu"-byte block at address %p\n", size, pMem);
#else
    PORT_MEM_PRINT_INFO("Freeing block at address %p\n", pMem);
#endif

    PORT_MEM_COUNTER_DEC(&pTracking->counter, size);
    PORT_MEM_COUNTER_DEC(&portMemGlobals.mainTracking.counter, size);
    PORT_MEM_LIMIT_DEC(pMem, size);

    PORT_MEM_FENCE_CHECK(pTracking->pAllocator, pMem, size);
    PORT_MEM_LIST_REMOVE(pTracking, pMem);
    PORT_MEM_LOG_FREE(pTracking->pAllocator, pMem);
#if PORT_MEM_TRACK_USE_LIMIT
    PORT_MEM_HEADER *pMemHeader = PORT_MEM_SUB_HEADER_PTR(pMem);

    if (isGfidValid(pMemHeader->gfid)) 
    {
        NvU32 gfidIdx = pMemHeader->gfid - 1;

        PORT_MEM_COUNTER_DEC(&portMemGlobals.pGfidTracking[gfidIdx]->counter, size);
    }
#endif

#if PORT_MEM_TRACK_USE_FENCEPOSTS
    pHead->fence.magic = PORT_MEM_FENCE_FREE_MAGIC;
#endif

    return NV_TRUE;
}

static void *
_portMemAllocatorAllocPagedWrapper
(
    PORT_MEM_ALLOCATOR *pAlloc,
    NvLength            length
)
{
    PORT_UNREFERENCED_VARIABLE(pAlloc);
    return _portMemAllocPagedUntracked(length);
}

static void *
_portMemAllocatorAllocNonPagedWrapper
(
    PORT_MEM_ALLOCATOR *pAlloc,
    NvLength            length
)
{
    PORT_UNREFERENCED_VARIABLE(pAlloc);
    return _portMemAllocNonPagedUntracked(length);
}

static void
_portMemAllocatorFreeWrapper
(
    PORT_MEM_ALLOCATOR *pAlloc,
    void               *pMem
)
{
    PORT_UNREFERENCED_VARIABLE(pAlloc);
    _portMemFreeUntracked(pMem);
}

static void
_portMemAllocatorReleaseWrapper
(
    PORT_MEM_ALLOCATOR *pAllocator
)
{
    portMemFree(pAllocator);
}

/* Adapter-only introspection. Lifecycle must be externally serialized. */
NvBool s540NvportMemoryIsInitialized(void)
{
    return portMemGlobals.initCount != 0;
}
NvBool s540NvportMemoryIsCold(void)
{
    static const struct PORT_MEM_GLOBALS cold = {0};
    return portMemCmp(&portMemGlobals, &cold, sizeof(portMemGlobals)) == 0;
}
NvU32 s540NvportMemoryAllocatorCount(void)
{
    return portMemGlobals.totalAllocators;
}
