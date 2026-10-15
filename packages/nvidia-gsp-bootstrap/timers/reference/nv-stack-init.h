/*
 * SPDX-FileCopyrightText: Copyright (c) 2001-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

#ifndef _NV_LINUX_H_
#define _NV_LINUX_H_

#include "nvstatus.h"
#include "nv.h"
static inline int nv_kmem_cache_alloc_stack_atomic(nvidia_stack_t **stack)
{
    nvidia_stack_t *sp = NULL;
#if defined(NVCPU_X86_64)
    if (rm_is_altstack_in_use())
    {
        sp = NV_KMEM_CACHE_ALLOC_ATOMIC(nvidia_stack_t_cache);
        if (sp == NULL)
            return -ENOMEM;
        sp->size = sizeof(sp->stack);
        sp->top = sp->stack + sp->size;
    }
#endif
    *stack = sp;
    return 0;
}

static inline int nv_kmem_cache_alloc_stack(nvidia_stack_t **stack)
{
    nvidia_stack_t *sp = NULL;
#if defined(NVCPU_X86_64)
    if (rm_is_altstack_in_use())
    {
        sp = NV_KMEM_CACHE_ALLOC(nvidia_stack_t_cache);
        if (sp == NULL)
            return -ENOMEM;
        sp->size = sizeof(sp->stack);
        sp->top = sp->stack + sp->size;
    }
#endif
    *stack = sp;
    return 0;
