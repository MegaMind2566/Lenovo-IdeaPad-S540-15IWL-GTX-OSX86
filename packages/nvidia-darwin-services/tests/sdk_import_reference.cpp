// SPDX-License-Identifier: MIT
// Compile-only SDK import reference; never linked into the runtime.
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <kern/clock.h>
#include <kern/sched_prim.h>
#include <kern/thread.h>
#include <kern/thread_call.h>
#include <kern/task.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#include <sys/kauth.h>
#include <sys/proc.h>
#include <sys/random.h>
extern "C" int cpu_number(void); // Source-backed exported unsupported Intel SPI.
#define REF(name) do { auto volatile pointer = &name; (void)pointer; } while (0)
extern "C" void s540DarwinServicesSdkReference(void) {
    REF(IODelay);
    REF(IOFree);
    REF(IOMalloc);
    REF(IOSimpleLockAlloc);
    REF(IOSimpleLockFree);
    REF(IOSimpleLockLock);
    REF(IOSimpleLockUnlock);
    REF(IOSleep);
    REF(absolutetime_to_nanoseconds);
    REF(assert_wait);
    REF(bzero);
    REF(clock_get_calendar_microtime);
    REF(clock_get_uptime);
    REF(clock_timebase_info);
    REF(cpu_number);
    REF(current_task);
    REF(current_thread);
    REF(kauth_cred_get);
    REF(kauth_cred_getuid);
    REF(kernel_task);
    REF(ml_at_interrupt_context);
    REF(ml_get_interrupts_enabled);
    REF(ml_set_interrupts_enabled);
    REF(nanoseconds_to_absolutetime);
    REF(panic);
    REF(proc_exiting);
    REF(proc_pid);
    REF(proc_rele);
    REF(proc_self);
    REF(proc_selfname);
    REF(proc_selfpid);
    REF(read_random);
    REF(thread_block);
    REF(thread_call_allocate_with_options);
    REF(thread_call_cancel_wait);
    REF(thread_call_enter);
    REF(thread_call_enter_delayed);
    REF(thread_call_free);
    REF(thread_tid);
    REF(thread_wakeup_prim);
}
#undef REF
