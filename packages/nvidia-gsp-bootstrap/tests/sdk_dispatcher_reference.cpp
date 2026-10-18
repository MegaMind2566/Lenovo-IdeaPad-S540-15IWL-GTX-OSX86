// SPDX-License-Identifier: MIT
// Independent pinned-SDK reference; never linked into the driver.
#include <kern/thread.h>
#include <mach/thread_act.h>
#define REF(name) do { auto volatile operation = &name; (void)operation; } while (0)
extern "C" void s540GspDispatcherSdkReference() {
    REF(kernel_thread_start);
    REF(thread_deallocate);
    REF(thread_terminate);
    REF(current_thread);
}
#undef REF
