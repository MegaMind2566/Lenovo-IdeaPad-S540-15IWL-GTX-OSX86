/*
 * SPDX-FileCopyrightText: Copyright (c) 2014-2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
 * Exact original spinlock and mutex caller bodies plus allocator-owned Create
 * bodies from sync_common.h. The real tracked PORT_FREE path is now available.
 * The original full sync initializer and unsupported object types are omitted.
 */
#include "nvport_lifecycle.h"
#define PORT_UNREFERENCED_VARIABLE(x) ((void)sizeof(&(x)))
#include "nvport_lifecycle_profile.h"

const NvLength portSyncSpinlockSize = sizeof(PORT_SPINLOCK);
const NvLength portSyncMutexSize = sizeof(PORT_MUTEX);

NV_STATUS
portSyncSpinlockInitialize
(
    PORT_SPINLOCK *pSpinlock
)
{
    if (pSpinlock == NULL)
    {
        return NV_ERR_INVALID_POINTER;
    }
    pSpinlock->pAllocator = NULL;
    return os_alloc_spinlock(&pSpinlock->lock);
}

void
portSyncSpinlockDestroy
(
    PORT_SPINLOCK *pSpinlock
)
{
    PORT_ASSERT_CHECKED(pSpinlock != NULL);
    os_free_spinlock(pSpinlock->lock);
    if (pSpinlock->pAllocator != NULL)
    {
        PORT_FREE(pSpinlock->pAllocator, pSpinlock);
    }
}

void
portSyncSpinlockAcquire
(
    PORT_SPINLOCK *pSpinlock
)
{
    PORT_ASSERT_CHECKED(pSpinlock != NULL);
    pSpinlock->oldIrql = os_acquire_spinlock(pSpinlock->lock);
}

void
portSyncSpinlockRelease
(
    PORT_SPINLOCK *pSpinlock
)
{
    PORT_ASSERT_CHECKED(pSpinlock           != NULL);
    os_release_spinlock(pSpinlock->lock, pSpinlock->oldIrql);
}

NV_STATUS
portSyncMutexInitialize
(
    PORT_MUTEX *pMutex
)
{
    if (pMutex == NULL)
    {
        return NV_ERR_INVALID_POINTER;
    }
    pMutex->pAllocator = NULL;
    return os_alloc_mutex(&pMutex->mutex);
}

void
portSyncMutexDestroy
(
    PORT_MUTEX *pMutex
)
{
    PORT_ASSERT_CHECKED(pMutex != NULL);
    os_free_mutex(pMutex->mutex);
    if (pMutex->pAllocator != NULL)
    {
        PORT_FREE(pMutex->pAllocator, pMutex);
    }
}

void
portSyncMutexAcquire
(
    PORT_MUTEX *pMutex
)
{
    NV_STATUS status;
    PORT_ASSERT_CHECKED(pMutex != NULL);
    PORT_ASSERT_CHECKED(portSyncExSafeToSleep());
    status = os_acquire_mutex(pMutex->mutex);
    PORT_ASSERT(status == NV_OK);
}

NvBool
portSyncMutexAcquireConditional
(
    PORT_MUTEX *pMutex
)
{
    PORT_ASSERT_CHECKED(pMutex != NULL);
    return os_cond_acquire_mutex(pMutex->mutex) == NV_OK;

}

void
portSyncMutexRelease
(
    PORT_MUTEX *pMutex
)
{
    PORT_ASSERT_CHECKED(pMutex != NULL);
    os_release_mutex(pMutex->mutex);
}

PORT_SPINLOCK *
portSyncSpinlockCreate
(
    PORT_MEM_ALLOCATOR *pAllocator
)
{
    PORT_SPINLOCK *pSpinlock;
    PORT_ASSERT_CHECKED(pAllocator != NULL);
    pSpinlock = PORT_ALLOC(pAllocator, portSyncSpinlockSize);
    if (pSpinlock != NULL)
    {
        if (portSyncSpinlockInitialize(pSpinlock) != NV_OK)
        {
            PORT_FREE(pAllocator, pSpinlock);
            return NULL;
        }
        pSpinlock->pAllocator = pAllocator;
    }
    return pSpinlock;
}

PORT_MUTEX *
portSyncMutexCreate
(
    PORT_MEM_ALLOCATOR *pAllocator
)
{
    PORT_MUTEX *pMutex;
    PORT_ASSERT_CHECKED(pAllocator != NULL);
    pMutex = PORT_ALLOC(pAllocator, portSyncMutexSize);
    if (pMutex != NULL)
    {
        if (portSyncMutexInitialize(pMutex) != NV_OK)
        {
            PORT_FREE(pAllocator, pMutex);
            return NULL;
        }
        pMutex->pAllocator = pAllocator;
    }
    return pMutex;
}

