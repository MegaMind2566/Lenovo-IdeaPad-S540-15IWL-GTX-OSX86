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

/* Fixed integration profile. This is not a complete NvPort configuration. */
#ifndef S540_NVPORT_LIFECYCLE_PROFILE_H
#define S540_NVPORT_LIFECYCLE_PROFILE_H
#if defined(PORT_MEM_TRACK_USE_COUNTER) || defined(PORT_MEM_TRACK_USE_FENCEPOSTS) || defined(PORT_MEM_TRACK_USE_ALLOCLIST) || defined(PORT_MEM_TRACK_USE_CALLERINFO) || defined(PORT_MEM_TRACK_USE_LOGGING) || defined(PORT_MEM_TRACK_USE_LIMIT)
#error "The lifecycle extraction owns its fixed release counter profile."
#endif
#define PORT_MEM_TRACK_USE_COUNTER 1
#define PORT_MEM_TRACK_USE_FENCEPOSTS 0
#define PORT_MEM_TRACK_USE_ALLOCLIST 0
#define PORT_MEM_TRACK_USE_CALLERINFO 0
#define PORT_MEM_TRACK_USE_LOGGING 0
#define PORT_MEM_TRACK_USE_LIMIT 0
#define PORT_MEM_TRACK_ALLOC_SIZE 0
#define PORT_MEM_HEADER_HAS_BLOCK_SIZE 0
#define PORT_MEM_STAGING_SIZE 0
#define PORT_MEM_TRACK_PRINT_LEVEL_SILENT 0
#define PORT_MEM_TRACK_PRINT_LEVEL_BASIC 1
#define PORT_MEM_TRACK_PRINT_LEVEL PORT_MEM_TRACK_PRINT_LEVEL_BASIC
#define PORT_MEM_CALLERINFO_TYPE_PARAM void
#define PORT_MEM_CALLERINFO_COMMA_TYPE_PARAM
#define PORT_MEM_CALLERINFO_COMMA_PARAM
#define PORT_MEM_CALLERINFO_PRINT_ARGS(x) "\n"
#define PORT_MEM_ADD_HEADER_PTR(p) p
#define PORT_MEM_SUB_HEADER_PTR(p) p
#define portMemExTrackingGetActiveStats_SUPPORTED 1
#define portMemExTrackingGetTotalStats_SUPPORTED 1
#define portMemExTrackingGetPeakStats_SUPPORTED 1
#define portMemExTrackingGetHeapSize_SUPPORTED 0
#define portMemGetLargestFreeChunkSize_SUPPORTED 0
#define portMemExTrackingGetNext_SUPPORTED 0
#define PORT_MEM_LIST_INIT(x)
#define PORT_MEM_LIST_DESTROY(x)
#define PORT_MEM_LIST_ADD(x,y)
#define PORT_MEM_LIST_REMOVE(x,y)
#define PORT_MEM_LOG_INIT()
#define PORT_MEM_LOG_DESTROY()
#define PORT_MEM_LOG_ALLOC(x,y,z)
#define PORT_MEM_LOG_FREE(x,y)
#define PORT_MEM_FENCE_INIT(x,y,z)
#define PORT_MEM_FENCE_CHECK(x,y,z)
#define PORT_MEM_CALLERINFO_INIT_TRACKING(x)
#define PORT_MEM_CALLERINFO_INIT_MEM(x)
#define PORT_MEM_PRINT_ERROR(...) portDbgPrintf(__VA_ARGS__)
#define PORT_MEM_PRINT_INFO(...)
#define PORT_MEM_LIMIT_INC(gfid,pMem,size) do { PORT_UNREFERENCED_VARIABLE(gfid); PORT_UNREFERENCED_VARIABLE(pMem); PORT_UNREFERENCED_VARIABLE(size); } while (0)
#define PORT_MEM_LIMIT_DEC(pMem,size) do { PORT_UNREFERENCED_VARIABLE(pMem); PORT_UNREFERENCED_VARIABLE(size); } while (0)
#define PORT_MEM_LIMIT_EXCEEDED(gfid,size) (NV_FALSE)
#if defined(PORT_IS_CHECKED_BUILD) && PORT_IS_CHECKED_BUILD
#error "This extraction implements the upstream release assertion profile only."
#endif
#define PORT_ASSERT_CHECKED(x)
#define PORT_BREAKPOINT_CHECKED()
#define PORT_ASSERT(condition) do { if (!(condition)) s540NvidiaCallerAssertionFailed(#condition, __FILE__, __LINE__); } while (0)
#endif
