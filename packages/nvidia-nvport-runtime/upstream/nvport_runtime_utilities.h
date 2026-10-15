/*
 * SPDX-FileCopyrightText: Copyright (c) 2014-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

/* Exact selected endian, ASCII and bit-count bodies. Pointer overlap,
 * power/alignment, timestamp counters, spin delay and stack traces are excluded. */
#ifndef S540_NVPORT_RUNTIME_UTILITIES_H
#define S540_NVPORT_RUNTIME_UTILITIES_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#define PORT_UTIL_INLINE static inline

PORT_UTIL_INLINE void
portUtilWriteLittleEndian16
(
    void *pBuf,
    NvU16 value
)
{
    *((NvU8*)pBuf + 1) = (NvU8)(value >> 8);
    *((NvU8*)pBuf + 0) = (NvU8)(value);
}

PORT_UTIL_INLINE void
portUtilWriteLittleEndian32
(
    void *pBuf,
    NvU32 value
)
{
    *((NvU8*)pBuf + 3) = (NvU8)(value >> 24);
    *((NvU8*)pBuf + 2) = (NvU8)(value >> 16);
    *((NvU8*)pBuf + 1) = (NvU8)(value >> 8);
    *((NvU8*)pBuf + 0) = (NvU8)(value);
}

PORT_UTIL_INLINE void
portUtilWriteLittleEndian64
(
    void *pBuf,
    NvU64 value
)
{
    *((NvU8*)pBuf + 7) = (NvU8)(value >> 56);
    *((NvU8*)pBuf + 6) = (NvU8)(value >> 48);
    *((NvU8*)pBuf + 5) = (NvU8)(value >> 40);
    *((NvU8*)pBuf + 4) = (NvU8)(value >> 32);
    *((NvU8*)pBuf + 3) = (NvU8)(value >> 24);
    *((NvU8*)pBuf + 2) = (NvU8)(value >> 16);
    *((NvU8*)pBuf + 1) = (NvU8)(value >> 8);
    *((NvU8*)pBuf + 0) = (NvU8)(value);
}

PORT_UTIL_INLINE void
portUtilWriteBigEndian16
(
    void *pBuf,
    NvU16 value
)
{
    *((NvU8*)pBuf + 0) = (NvU8)(value >> 8);
    *((NvU8*)pBuf + 1) = (NvU8)(value);
}

PORT_UTIL_INLINE void
portUtilWriteBigEndian32
(
    void *pBuf,
    NvU32 value
)
{
    *((NvU8*)pBuf + 0) = (NvU8)(value >> 24);
    *((NvU8*)pBuf + 1) = (NvU8)(value >> 16);
    *((NvU8*)pBuf + 2) = (NvU8)(value >> 8);
    *((NvU8*)pBuf + 3) = (NvU8)(value);
}

PORT_UTIL_INLINE void
portUtilWriteBigEndian64
(
    void *pBuf,
    NvU64 value
)
{
    *((NvU8*)pBuf + 0) = (NvU8)(value >> 56);
    *((NvU8*)pBuf + 1) = (NvU8)(value >> 48);
    *((NvU8*)pBuf + 2) = (NvU8)(value >> 40);
    *((NvU8*)pBuf + 3) = (NvU8)(value >> 32);
    *((NvU8*)pBuf + 4) = (NvU8)(value >> 24);
    *((NvU8*)pBuf + 5) = (NvU8)(value >> 16);
    *((NvU8*)pBuf + 6) = (NvU8)(value >> 8);
    *((NvU8*)pBuf + 7) = (NvU8)(value);
}

PORT_UTIL_INLINE char portUtilToUpper(char c)
{
    return (c >= 'a' && c <= 'z') ? (c - 'a' + 'A') : c;
}

PORT_UTIL_INLINE char portUtilToLower(char c)
{
    return (c >= 'A' && c <= 'Z') ? (c - 'A' + 'a') : c;
}

PORT_UTIL_INLINE NvU32 portUtilCountLeadingZeros64(NvU64 n)
{
    if (n == 0)
        return 64;

    return __builtin_clzll(n);
}

PORT_UTIL_INLINE NvU32 portUtilCountLeadingZeros32(NvU32 n)
{
    if (n == 0)
        return 32;

    return __builtin_clz(n);
}

PORT_UTIL_INLINE NvU32 portUtilCountTrailingZeros64(NvU64 n)
{
    if (n == 0)
        return 64;

    return __builtin_ctzll(n);
}

PORT_UTIL_INLINE NvU32 portUtilCountTrailingZeros32(NvU32 n)
{
    if (n == 0)
        return 32;

    return __builtin_ctz(n);
}

#undef PORT_UTIL_INLINE
#endif
