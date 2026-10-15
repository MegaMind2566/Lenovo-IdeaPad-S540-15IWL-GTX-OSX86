/*
 * SPDX-FileCopyrightText: Copyright (c) 2014-2017 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
 * Adapted extraction of three allocator callers, not the unmodified complete
 * upstream memory module. All three function bodies are unchanged.
 *
 * This is the upstream release assertion profile. Its checked assertions are
 * intentionally absent, exactly as reference/debug.h defines for release.
 * Checked builds and their diagnostics are not implemented by this extraction.
 * The backend's bounded-reserve and context contract remains a caller condition.
 */
#include "nvport_allocator_callers.h"

#if defined(PORT_IS_CHECKED_BUILD) && PORT_IS_CHECKED_BUILD
#error "The allocator caller implements the release assertion profile only."
#endif
#ifdef PORT_ASSERT_CHECKED
#error "The allocator caller owns its explicit release assertion profile."
#endif
#define PORT_ASSERT_CHECKED(x)

void *
_portMemAllocPagedUntracked
(
    NvLength lengthBytes
)
{
    return _portMemAllocNonPagedUntracked(lengthBytes);
}

void *
_portMemAllocNonPagedUntracked
(
    NvLength lengthBytes
)
{
    void *pMem = NULL;
    PORT_ASSERT_CHECKED(lengthBytes > 0);
    if (lengthBytes > 0)
        os_alloc_mem(&pMem, lengthBytes);
    return pMem;
}



void
_portMemFreeUntracked
(
    void *pData
)
{
    if (pData != NULL)
    {
        os_free_mem(pData);
    }
}

