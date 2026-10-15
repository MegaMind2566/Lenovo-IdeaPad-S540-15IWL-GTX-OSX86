/*
 * SPDX-FileCopyrightText: Copyright (c) 2015-2015 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

/* Exact upstream unsigned length-add macro closure, with helper macros
 * undefined after the length-add expansion. Other SAFE functions omitted. */
#ifndef S540_NVPORT_SAFE_LENGTH_H
#define S540_NVPORT_SAFE_LENGTH_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#define PORT_SAFE_INLINE static inline
#define PORT_EXPAND(X) X
#define PORT_SAFE_Add_IMPL_U(a, b, pRes, n) \
    ((*pRes = a + b), ((*pRes < a) ? NV_FALSE : NV_TRUE))
#define PORT_SAFE_Add_IMPL_ PORT_SAFE_Add_IMPL_U
#define PORT_SAFE_DEFINE_MATH_FUNC(_op_, _US_, _size_)                          \
    PORT_SAFE_INLINE NvBool                                                     \
    portSafe##_op_##_US_##_size_                                                \
    (                                                                           \
        Nv##_US_##_size_  x,                                                    \
        Nv##_US_##_size_  y,                                                    \
        Nv##_US_##_size_ *pRes                                                  \
    )                                                                           \
    {                                                                           \
        return PORT_EXPAND(PORT_SAFE_##_op_##_IMPL_##_US_)(x, y, pRes, _size_); \
    }
PORT_SAFE_DEFINE_MATH_FUNC(Add, , Length)
#undef PORT_EXPAND
#undef PORT_SAFE_Add_IMPL_U
#undef PORT_SAFE_Add_IMPL_
#undef PORT_SAFE_DEFINE_MATH_FUNC
#undef PORT_SAFE_INLINE
#endif
