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
 * Adapted extraction of four normal-RAM primitives, not the unmodified
 * complete upstream memory module. Only the three OS call names are changed:
 * the private bridges preserve NvLength through bounded NvU32 OS-hook chunks.
 *
 * This is the upstream release assertion profile. Its checked assertions are
 * intentionally absent, exactly as reference/debug.h defines for release.
 * Checked builds and their diagnostics are not implemented by this extraction.
 * Copying overlapping buffers remains undefined, as in reference/memory.h.
 */
#include "nvport_memory_primitives.h"

#if defined(PORT_IS_CHECKED_BUILD) && PORT_IS_CHECKED_BUILD
#error "The adapted memory caller implements the release assertion profile only."
#endif
#ifdef PORT_ASSERT_CHECKED
#error "The adapted memory caller owns its explicit release assertion profile."
#endif
#define PORT_ASSERT_CHECKED(x)

void *
portMemCopy
(
    void       *pDestination,
    NvLength    destSize,
    const void *pSource,
    NvLength    srcSize
)
{
    // API guarantees this is a NOP when destSize==0
    if (destSize == 0)
    {
        return pDestination;
    }

    PORT_ASSERT_CHECKED(pDestination != NULL);
    PORT_ASSERT_CHECKED(pSource      != NULL);
    PORT_ASSERT_CHECKED(srcSize      <= destSize);
    PORT_ASSERT_CHECKED(!portUtilCheckOverlap(pDestination, destSize,
                                              pSource,      srcSize));

    if ((pSource == NULL) || (pDestination == NULL) || (srcSize > destSize))
    {
        return NULL;
    }
    return s540NvidiaMemoryCopy(pDestination, pSource, srcSize);
}

void *
portMemCopyAligned
(
    void       *pDestination,
    NvLength    destSize,
    const void *pSource,
    NvLength    srcSize
)
{
    return portMemCopy(pDestination, destSize, pSource, srcSize);
}

void *
portMemSet
(
    void    *pData,
    NvU8     value,
    NvLength lengthBytes
)
{
    if (lengthBytes == 0)
    {
        return pData;
    }
    if (pData == NULL)
    {
        return pData;
    }
    return s540NvidiaMemorySet(pData, value, lengthBytes);
}

NvS32
portMemCmp
(
    const void *pData0,
    const void *pData1,
    NvLength lengthBytes
)
{
    if (lengthBytes == 0)
    {
        return 0;
    }
    if ((pData0 == NULL) || (pData1 == NULL))
    {
        return -1;
    }
    return s540NvidiaMemoryCompare(pData0, pData1, lengthBytes);
}


