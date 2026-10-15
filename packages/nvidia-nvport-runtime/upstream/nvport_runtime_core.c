/*
 * SPDX-FileCopyrightText: Copyright (c) 2014-2016 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

/* Explicit checked-core adaptation of pinned core.c. The selected profile is
 * memory + PRNG, with pure string/unsigned arithmetic/endian helpers. No sync,
 * CPU, debug, thread or full-core module is falsely reported initialized.
 * Every entry requires the caller's shared lifecycle lease and quiescence.
 */
#include "nvport_runtime.h"

static NvBool runtimeInitialized;
static NvU32 baselineAllocators;

NV_STATUS s540NvportRuntimeInitialize(void)
{
    NV_STATUS status;
    if (!s540NvportLifecycleContextAllowed() || runtimeInitialized ||
        portCryptoDefaultGenerator != NULL || !s540NvportMemoryIsCold())
        return NV_ERR_INVALID_STATE;

    status = s540NvportMemoryInitialize();
    if (status != NV_OK)
        return status;
    baselineAllocators = s540NvportMemoryAllocatorCount();

    /* Upstream void initialization can fail its default-generator allocation.
     * Observe that actual failure before publishing runtime state. */
    portCryptoInitialize();
    if (portCryptoDefaultGenerator == NULL)
    {
        portMemShutdown(NV_TRUE);
        baselineAllocators = 0;
        return NV_ERR_NO_MEMORY;
    }
    runtimeInitialized = NV_TRUE;
    return NV_OK;
}

NV_STATUS s540NvportRuntimeShutdown(void)
{
    PORT_MEM_TRACK_ALLOCATOR_STATS active;
    NvU32 defaultAllocations;
    if (!s540NvportLifecycleContextAllowed() || !runtimeInitialized ||
        !s540NvportMemoryIsInitialized())
        return NV_ERR_INVALID_STATE;

    /* Check before releasing any resource. The sole permitted allocation is
     * the default PRNG, unless a failed upstream reseed already removed it. */
    defaultAllocations = portCryptoDefaultGenerator != NULL ? 1 : 0;
    if (portMemExTrackingGetActiveStats(NULL, &active) != NV_OK ||
        active.numAllocations != defaultAllocations ||
        s540NvportMemoryAllocatorCount() != baselineAllocators)
        return NV_ERR_INVALID_STATE;

    portCryptoShutdown();
    portMemShutdown(NV_TRUE);
    runtimeInitialized = NV_FALSE;
    baselineAllocators = 0;
    return s540NvportRuntimeIsCold() ? NV_OK : NV_ERR_INVALID_STATE;
}

NvBool s540NvportRuntimeIsInitialized(void)
{
    return runtimeInitialized && s540NvportMemoryIsInitialized() &&
           portCryptoDefaultGenerator != NULL;
}

NvBool s540NvportRuntimeIsCold(void)
{
    return !runtimeInitialized && baselineAllocators == 0 &&
           portCryptoDefaultGenerator == NULL && s540NvportMemoryIsCold();
}
