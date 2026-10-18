// SPDX-License-Identifier: MIT
// Private native control boundary only. Sanitizer global metadata retains the
// original NVSwitch assertion thunk even though this lifecycle has no NVSwitch.
// A call aborts the process; it never represents an available hardware service.
#ifdef KERNEL
#error "The NVSwitch assertion tripwire must never enter a kernel build"
#endif
#include "export_nvswitch.h"
#include "S540NvidiaGlobalRm.h"
extern void abort(void) __attribute__((noreturn));
typedef void (*S540NativeSwitchAssertAbi)(const char *, ...);
_Static_assert(__builtin_types_compatible_p(__typeof__(&nvswitch_os_assert_log),
                                           S540NativeSwitchAssertAbi),
               "The original NVSwitch assertion ABI changed");
void nvswitch_os_assert_log(const char *format, ...)
{
    (void)format;
    s540GlobalRmRecordUnavailable(511);
    abort();
}
