// SPDX-License-Identifier: MIT
// Real, bounded diagnostics for the selected original NvPort source profile.
#include "../upstream/nvport_lifecycle.h"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#else
#include "S540NvidiaSpinlock.hpp"
#include <cstdio>
#endif
#include <stdarg.h>

extern "C" NvBool s540NvportLifecycleContextAllowed(void)
{
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled()
        ? NV_TRUE : NV_FALSE;
#else
    return S540NvidiaSpinlockNative::contextAllowed() ? NV_TRUE : NV_FALSE;
#endif
}

extern "C" void portDbgPrintf(const char *format, ...)
{
#if defined(KERNEL)
    // The selected kernel profile does not support diagnostic formatting from
    // an interrupt context or while an IRQ-masking tracking spinlock is held.
    // Refuse that path rather than sleeping/logging under a simple lock.
    if (ml_at_interrupt_context() || !ml_get_interrupts_enabled())
        panic("NVIDIA lifecycle diagnostic requires an ordinary thread");
#endif
    char buffer[512];
    va_list arguments;
    va_start(arguments, format);
    (void)vsnprintf(buffer, sizeof(buffer), format, arguments);
    va_end(arguments);
    buffer[sizeof(buffer) - 1] = '\0';
#if defined(KERNEL)
    IOLog("%s", buffer);
#else
    (void)std::fputs(buffer, stderr);
#endif
}
