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

/* Exact unsigned arithmetic macro closure. Signed math and casts are outside
 * this profile. portSafeAddLength is already supplied by the v6 interface. */
#ifndef S540_NVPORT_RUNTIME_SAFE_H
#define S540_NVPORT_RUNTIME_SAFE_H
#include "../../nvidia-nvport-lifecycle/upstream/nvport_safe_length.h"
#define PORT_SAFE_INLINE static inline
#define PORT_EXPAND(X) X
#define PORT_SAFE_Add_IMPL_U(a, b, pRes, n) \
    ((*pRes = a + b), ((*pRes < a) ? NV_FALSE : NV_TRUE))
#define PORT_SAFE_Sub_IMPL_U(a, b, pRes, n) \
    ((*pRes = a - b), ((b > a) ? NV_FALSE : NV_TRUE))
#define PORT_SAFE_Mul_IMPL_U(a, b, pRes, n) \
    ((*pRes = a * b), ((a != 0 && b != *pRes/a) ? NV_FALSE : NV_TRUE))
#define PORT_SAFE_DIV_IMPL(a, b, pRes) \
    ((b == 0) ? NV_FALSE : ((*pRes = a / b), NV_TRUE))
#define PORT_SAFE_Div_IMPL_U(a, b, pRes, n) PORT_SAFE_DIV_IMPL(a, b, pRes)
#define PORT_SAFE_Add_IMPL_ PORT_SAFE_Add_IMPL_U
#define PORT_SAFE_Sub_IMPL_ PORT_SAFE_Sub_IMPL_U
#define PORT_SAFE_Mul_IMPL_ PORT_SAFE_Mul_IMPL_U
#define PORT_SAFE_Div_IMPL_ PORT_SAFE_Div_IMPL_U
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
PORT_SAFE_DEFINE_MATH_FUNC(Add, U, 32)
PORT_SAFE_DEFINE_MATH_FUNC(Sub, U, 32)
PORT_SAFE_DEFINE_MATH_FUNC(Mul, U, 32)
PORT_SAFE_DEFINE_MATH_FUNC(Div, U, 32)
PORT_SAFE_DEFINE_MATH_FUNC(Add, U, 64)
PORT_SAFE_DEFINE_MATH_FUNC(Sub, U, 64)
PORT_SAFE_DEFINE_MATH_FUNC(Mul, U, 64)
PORT_SAFE_DEFINE_MATH_FUNC(Div, U, 64)
PORT_SAFE_DEFINE_MATH_FUNC(Add, , UPtr)
PORT_SAFE_DEFINE_MATH_FUNC(Sub, , UPtr)
PORT_SAFE_DEFINE_MATH_FUNC(Mul, , UPtr)
PORT_SAFE_DEFINE_MATH_FUNC(Div, , UPtr)
PORT_SAFE_DEFINE_MATH_FUNC(Sub, , Length)
PORT_SAFE_DEFINE_MATH_FUNC(Mul, , Length)
PORT_SAFE_DEFINE_MATH_FUNC(Div, , Length)
#undef PORT_SAFE_DEFINE_MATH_FUNC
#undef PORT_SAFE_Div_IMPL_
#undef PORT_SAFE_Mul_IMPL_
#undef PORT_SAFE_Sub_IMPL_
#undef PORT_SAFE_Add_IMPL_
#undef PORT_SAFE_Div_IMPL_U
#undef PORT_SAFE_DIV_IMPL
#undef PORT_SAFE_Mul_IMPL_U
#undef PORT_SAFE_Sub_IMPL_U
#undef PORT_SAFE_Add_IMPL_U
#undef PORT_EXPAND
#undef PORT_SAFE_INLINE
#endif
