// SPDX-License-Identifier: MIT
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "S540NvidiaGlobalRmDiagnostics.h"
#include <stdarg.h>
#ifdef KERNEL
#include <IOKit/IOLib.h>
#else
#include <cstdio>
#include <cstdlib>
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

extern "C" NvS32 s540GlobalRmDeviceLogV(
    NvU32 domain, NvU32 bus, NvU32 slot, NvU32 function, NvU32 level,
    NvBool xid, NvU32 error, const char *format, va_list arguments)
{
    if (!format) return -1;
    const char *names[] = {"debug", "info", "notice", "warning",
                           "error", "critical", "alert"};
    const char *name = level < 7 ? names[level] : "info";
    char message[1024];
    const int prefix = xid
        ? snprintf(message, sizeof(message),
                   "S540 NVIDIA %04x:%02x:%02x.%x %s Xid %u: ",
                   domain, bus, slot, function, name, error)
        : snprintf(message, sizeof(message),
                   "S540 NVIDIA %04x:%02x:%02x.%x %s: ",
                   domain, bus, slot, function, name);
    if (prefix < 0 || static_cast<size_t>(prefix) >= sizeof(message)) return -1;
    va_list copy;
    va_copy(copy, arguments);
    const int written = vsnprintf(message + prefix, sizeof(message) - prefix,
                                   format, copy);
    va_end(copy);
    if (written < 0) return -1;
    const size_t available = sizeof(message) - 1 - static_cast<size_t>(prefix);
    const size_t payload = static_cast<size_t>(written) > available
        ? available : static_cast<size_t>(written);
    const size_t emitted = static_cast<size_t>(prefix) + payload;
#ifdef KERNEL
    IOLog("%s", message);
#else
    if (std::fputs(message, stderr) == EOF) return -1;
#endif
    /* Return the actual bounded byte count supplied to the log, rather than
     * claiming that a truncated suffix was emitted. Logging never allocates.
     */
    return static_cast<NvS32>(emitted);
}

extern "C" void s540GlobalRmBugCheck(NvU32 code, const char *text)
{
    // A bug-check string is data, not a printf format. Linux's original API
    // calls panic here; a successful return would hide a fatal RM invariant.
#ifdef KERNEL
    panic("S540 NVIDIA RM bug check %u: %s", code, text ? text : "(no text)");
#else
    std::fprintf(stderr, "S540 NVIDIA RM bug check %u: %s\n",
                 code, text ? text : "(no text)");
    std::abort();
#endif
}
