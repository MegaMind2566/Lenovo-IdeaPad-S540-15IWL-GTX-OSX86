// SPDX-License-Identifier: MIT
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include <stdarg.h>
#ifdef KERNEL
#include <IOKit/IOLib.h>
#else
#include <cstdio>
#endif

extern "C" NvS32 s540GlobalRmFormatV(char *buffer, NvU32 size,
                                      const char *format, va_list arguments)
{
    if ((!buffer && size) || !format) return -1;
    return vsnprintf(buffer, size, format, arguments);
}

extern "C" NvS32 s540GlobalRmLogV(const char *format, va_list arguments)
{
    char message[1024];
    if (!format) return -1;
    const int size = vsnprintf(message, sizeof(message), format, arguments);
#ifdef KERNEL
    IOLog("S540 NVIDIA RM: %s", message);
#else
    std::fputs(message, stderr);
#endif
    return size;
}
