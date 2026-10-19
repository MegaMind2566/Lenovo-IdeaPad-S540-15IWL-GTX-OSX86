// SPDX-License-Identifier: MIT
// Independent pinned-SDK operations used by the actual RM log formatter.
#include <IOKit/IOLib.h>
#include <libkern/OSDebug.h>

extern "C" int s540GlobalRmSdkDevicePrefix(char *buffer, size_t bytes,
    unsigned domain, unsigned bus, unsigned slot, unsigned function,
    const char *severity, unsigned xid)
{
    return snprintf(buffer, bytes, "S540 NVIDIA %04x:%02x:%02x.%x %s Xid %u: ",
                    domain, bus, slot, function, severity, xid);
}

extern "C" unsigned s540GlobalRmSdkStackTrace(void **frames, unsigned count)
{
    return OSBacktrace(frames, count);
}
