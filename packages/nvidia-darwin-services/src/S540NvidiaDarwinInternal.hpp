// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_DARWIN_INTERNAL_HPP
#define S540_NVIDIA_DARWIN_INTERNAL_HPP
#include "S540NvidiaDarwinServices.h"
#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <kern/clock.h>
#include <kern/sched_prim.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#else
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <pthread.h>
#include <time.h>
#endif
namespace S540DarwinInternal {
static_assert(sizeof(void *) == 8 && NVCPU_IS_X86_64, "Intel x86_64 is required.");
bool ordinary();
bool interruptContext();
NvU64 identity();
NvU64 monotonic();
bool fail(NvU32 point);
void *allocate(NvU32 size);
void deallocate(void *, NvU32);
void account(NvS32 delta);
[[noreturn]] void violation(const char *);
struct Guard {
#if defined(KERNEL)
    IOSimpleLock *value;
#else
    pthread_mutex_t value;
    pthread_cond_t changed;
#endif
    bool init();
    void dispose();
    NvU64 lock();
    void unlock(NvU64);
    bool wait(void *event, NvU64 &token, bool interruptible);
    void wake(void *event);
};
struct GuardObject { Guard guard; };
template <typename T> T *create() {
    auto *object = static_cast<T *>(allocate(sizeof(T)));
    if (object == nullptr) return nullptr;
    if (!object->guard.init()) { deallocate(object, sizeof(T)); return nullptr; }
    account(1);
    return object;
}
template <typename T> void destroy(T *object) {
    object->guard.dispose();
    deallocate(object, sizeof(T));
    account(-1);
}
}
#endif
