// SPDX-License-Identifier: MIT
#include "S540NvidiaGlobalRmSystem.h"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <libkern/OSDebug.h>
#include <mach/vm_param.h>
#elif defined(__APPLE__)
#include <mach/vm_param.h>
#include <execinfo.h>
#include <cstdio>
#else
#include <execinfo.h>
#include <cstdio>
#endif

#if !defined(__x86_64__)
#error "This system profile is supported only for Darwin x86_64"
#endif
#if defined(KERNEL) || defined(__APPLE__)
static_assert(static_cast<NvU64>(MACH_VM_MAX_ADDRESS) ==
              S540_DARWIN_X86_64_USER_MAP_LIMIT,
              "Public Mach user-map limit differs from reviewed XNU profile");
#endif

extern "C" NvU64 s540GlobalRmSystemUserAddressLimit(void)
{
#if defined(KERNEL) || defined(__APPLE__)
    // This is XNU's 64-bit user-map bound even on our kernel worker. Reading
    // kernel_task/current_task's kernel map would report the wrong address
    // space. No userspace request entry is exposed by this bootstrap owner.
    return static_cast<NvU64>(MACH_VM_MAX_ADDRESS);
#else
    // The Linux control exercises the declared Darwin source profile. It is
    // not a measurement of Linux TASK_SIZE or target-kernel compatibility.
    return S540_DARWIN_X86_64_USER_MAP_LIMIT;
#endif
}

extern "C" NvU32 s540GlobalRmSystemDumpStack(void)
{
    void *frames[S540_GLOBAL_RM_STACK_TRACE_FRAMES] = {};
#if defined(KERNEL)
    const NvU32 captured = OSBacktrace(frames, S540_GLOBAL_RM_STACK_TRACE_FRAMES);
    const NvU32 count = captured > S540_GLOBAL_RM_STACK_TRACE_FRAMES
        ? S540_GLOBAL_RM_STACK_TRACE_FRAMES : captured;
    // OSBacktrace collects actual bounded kernel return addresses without
    // allocating or taking OSReportWithBacktrace's sleeping report mutex.
    IOLog("S540 NVIDIA RM stack trace (%u frames):\n", count);
    for (NvU32 i = 0; i < count; ++i)
        IOLog("S540 NVIDIA RM frame %u: %p\n", i, frames[i]);
#else
    const int captured = backtrace(frames, S540_GLOBAL_RM_STACK_TRACE_FRAMES);
    const NvU32 count = captured > 0 ? static_cast<NvU32>(captured) : 0;
    std::fprintf(stderr, "S540 NVIDIA RM stack trace (%u frames):\n", count);
    for (NvU32 i = 0; i < count; ++i)
        std::fprintf(stderr, "S540 NVIDIA RM frame %u: %p\n", i, frames[i]);
#endif
    return count;
}
