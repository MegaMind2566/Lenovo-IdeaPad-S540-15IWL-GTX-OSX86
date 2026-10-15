// SPDX-License-Identifier: MIT
// Failed mandatory NVIDIA caller assertions must never return unlocked.
#include "../upstream/nvport_mutex_callers.h"

#if defined(KERNEL)
#include <libkern/libkern.h>
#else
#include <cstdio>
#include <cstdlib>
#endif

extern "C" __attribute__((noreturn)) void s540NvidiaCallerAssertionFailed(
    const char *expression, const char *file, int line)
{
#if defined(KERNEL)
    panic("NVIDIA caller assertion failed: %s (%s:%d)", expression, file, line);
#else
    std::fprintf(stderr, "NVIDIA caller assertion failed: %s (%s:%d)\n",
                 expression, file, line);
    std::abort();
#endif
}
