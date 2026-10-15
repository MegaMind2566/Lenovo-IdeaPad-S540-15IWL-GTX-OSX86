/*
 * SPDX-FileCopyrightText: Copyright (c) 2016-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
 * Adapted extraction from NVIDIA open-gpu-kernel-modules 615.78.08,
 * commit 1a82fbfda8f321b056eb3568850f9316c5e465c5.
 * Only the four contiguous uptime functions are compiled here. Their
 * signatures and bodies are unchanged; the original includes and build
 * guards are replaced by the narrow, explicitly declared interface below.
 * This is not the unmodified complete upstream time module.
 * See PROVENANCE.json and reference/time_unix_kernel_os.c.
 */

#include "nvport_time_uptime.h"

NvU64 portTimeGetUptimeMicroseconds(void)
{
    return portTimeGetUptimeNanoseconds() / 1000;
}

NvU64 portTimeGetUptimeNanoseconds(void)
{
    return os_get_monotonic_time_ns();
}

NvU64 portTimeGetUptimeNanosecondsHighPrecision(void)
{
    return os_get_monotonic_time_ns_hr();
}

NvU64 portTimeGetUptimeResolution(void)
{
    return os_get_monotonic_tick_resolution_ns();
}
