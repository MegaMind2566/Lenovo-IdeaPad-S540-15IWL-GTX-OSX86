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
 * Adapted extraction of five caller-owned mutex operations, not the unmodified
 * complete upstream synchronization module. All function bodies are unchanged.
 *
 * Checked assertions use the upstream release assertion profile only.
 * Mandatory PORT_ASSERT remains active and invokes a real non-returning failure
 * hook. This extraction never constructs a mutex with a tracked allocator;
 * encountering one during destruction is an explicit unsupported-contract
 * failure, not a fake successful tracked-free operation.
 */
#include "nvport_mutex_callers.h"

#if defined(PORT_IS_CHECKED_BUILD) && PORT_IS_CHECKED_BUILD
#error "The mutex caller implements the release assertion profile only."
#endif
#if defined(PORT_ASSERT_CHECKED) || defined(PORT_ASSERT) || defined(PORT_FREE)
#error "The mutex caller owns its explicit assertion and allocator profile."
#endif
#define PORT_ASSERT_CHECKED(x)
#define PORT_ASSERT(condition) \
    do { \
        if (!(condition)) \
            s540NvidiaCallerAssertionFailed(#condition, __FILE__, __LINE__); \
    } while (0)
#define PORT_FREE(allocator, memory) \
    do { \
        (void)(allocator); \
        (void)(memory); \
        s540NvidiaCallerAssertionFailed("tracked allocator mutex is unsupported", \
                                       __FILE__, __LINE__); \
    } while (0)

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



