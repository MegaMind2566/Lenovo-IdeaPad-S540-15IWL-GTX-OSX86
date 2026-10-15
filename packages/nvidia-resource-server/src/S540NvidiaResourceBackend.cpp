// SPDX-License-Identifier: MIT
#include "S540NvidiaResourceBackend.hpp"
#include "../../nvidia-nvport-lifecycle/upstream/nvport_lifecycle.h"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#else
#include <cstdio>
#include <cstdlib>
#include <pthread.h>
#endif
#include <stdarg.h>

// Exact UNIX NVPort opaque layout. Full upstream C translation units see the
// same two fields; no NVIDIA object or allocator layout is redefined here.
struct PORT_RWLOCK {
    void *rwlock;
    PORT_MEM_ALLOCATOR *pAllocator;
};

static_assert(NVCPU_IS_X86_64 && sizeof(void *) == 8,
              "The ResourceServer adapter requires Intel x86_64.");

namespace {
constexpr NvU32 kThreadCount = 32;
constexpr NvU32 kEntriesPerThread = 16;
constexpr NvU32 kLockCount = 32;
constexpr NvU64 kLastStaticEntry = 6;
constexpr NvU64 kTaggedEntryBase = 0x100000;
constexpr NvU32 kTlsError = ~NvU32{0};

struct TlsEntry {
    NvU64 id;
    NvU32 references;
    NvP64 value;
};
struct TlsThread {
    NvU64 thread;
    TlsEntry entries[kEntriesPerThread];
};
struct LockState {
    PORT_RWLOCK *lock;
    NvU64 owner;
    NvU32 mode;
};

void *stateGuard;
TlsThread threadState[kThreadCount];
LockState lockState[kLockCount];
NvU32 liveTlsEntries;
NvU32 liveLocks;
alignas(NvU32) NvU32 assertionFailures;
alignas(NvU32) NvU32 checkFailures;
#if !defined(KERNEL)
alignas(NvU32) NvU32 nextFailure;
bool consumeFailure(S540NvidiaResourceBackendNative::Failure failure) {
    NvU32 expected = static_cast<NvU32>(failure);
    return __atomic_compare_exchange_n(&nextFailure, &expected, NvU32{0}, false,
                                      __ATOMIC_RELAXED, __ATOMIC_RELAXED);
}
#endif

[[noreturn]] void contractFailure(const char *operation) {
#if defined(KERNEL)
    panic("NVIDIA ResourceServer backend contract violated: %s", operation);
#else
    std::fprintf(stderr, "NVIDIA ResourceServer backend contract violated: %s\n", operation);
    std::abort();
#endif
}

class Guard {
public:
    Guard() : token(os_acquire_spinlock(stateGuard)) {}
    ~Guard() { os_release_spinlock(stateGuard, token); }
    Guard(const Guard &) = delete;
    Guard &operator=(const Guard &) = delete;
private:
    NvU64 token;
};

bool ordinaryThread() { return s540NvportLifecycleContextAllowed() == NV_TRUE; }
bool validEntry(NvU64 id) { return id <= kLastStaticEntry || id >= kTaggedEntryBase; }

TlsThread *findThread(NvU64 identity) {
    for (auto &thread : threadState)
        if (thread.thread == identity)
            return &thread;
    return nullptr;
}
TlsEntry *findEntry(TlsThread *thread, NvU64 id) {
    if (thread != nullptr)
        for (auto &entry : thread->entries)
            if (entry.references != 0 && entry.id == id)
                return &entry;
    return nullptr;
}
LockState *findLock(PORT_RWLOCK *lock) {
    for (auto &state : lockState)
        if (state.lock == lock)
            return &state;
    return nullptr;
}

void acquire(PORT_RWLOCK *lock, NvU32 mode) {
    if (stateGuard == nullptr || lock == nullptr || !ordinaryThread())
        contractFailure("RW acquisition state or context");
    const NvU64 thread = portThreadGetCurrentThreadId();
    {
        Guard guard;
        const LockState *state = findLock(lock);
        if (state == nullptr || state->owner == thread)
            contractFailure("unknown or recursively acquired RW lock");
    }
    if (os_acquire_mutex(lock->rwlock) != NV_OK)
        contractFailure("RW backing acquisition");
    {
        Guard guard;
        LockState *state = findLock(lock);
        if (state == nullptr || state->owner != 0)
            contractFailure("RW ownership publication");
        state->owner = thread;
        state->mode = mode;
    }
}

NvBool acquireConditional(PORT_RWLOCK *lock, NvU32 mode) {
    if (stateGuard == nullptr || lock == nullptr || !ordinaryThread())
        return NV_FALSE;
    const NvU64 thread = portThreadGetCurrentThreadId();
    {
        Guard guard;
        const LockState *state = findLock(lock);
        if (state == nullptr || state->owner == thread)
            return NV_FALSE;
    }
    const NV_STATUS status = os_cond_acquire_mutex(lock->rwlock);
    if (status == NV_ERR_TIMEOUT_RETRY)
        return NV_FALSE;
    if (status != NV_OK)
        contractFailure("conditional RW backing acquisition");
    {
        Guard guard;
        LockState *state = findLock(lock);
        if (state == nullptr || state->owner != 0)
            contractFailure("conditional RW ownership publication");
        state->owner = thread;
        state->mode = mode;
    }
    return NV_TRUE;
}

void release(PORT_RWLOCK *lock, NvU32 mode) {
    if (stateGuard == nullptr || lock == nullptr || !ordinaryThread())
        contractFailure("RW release state or context");
    {
        Guard guard;
        LockState *state = findLock(lock);
        if (state == nullptr || state->owner != portThreadGetCurrentThreadId() ||
            state->mode != mode)
            contractFailure("unbalanced RW owner or mode");
        state->owner = 0;
        state->mode = 0;
    }
    os_release_mutex(lock->rwlock);
}

int printFormatted(const char *format, va_list arguments) {
    if (format == nullptr || !ordinaryThread())
        return -1;
    char buffer[768];
    const int result = vsnprintf(buffer, sizeof(buffer), format, arguments);
    buffer[sizeof(buffer) - 1] = '\0';
#if defined(KERNEL)
    IOLog("%s", buffer);
#else
    (void)std::fputs(buffer, stderr);
#endif
    return result;
}

void failureDiagnostic(bool assertion, NvU32 status, const char *expression,
                       const char *file, NvU32 line) {
    (void)__atomic_add_fetch(assertion ? &assertionFailures : &checkFailures,
                             NvU32{1}, __ATOMIC_RELAXED);
    // NVIDIA checks can be reached with a short spin lock held. Preserve the
    // occurrence counter there without making a formatter or logging call.
    if (ordinaryThread())
        portDbgPrintf("NVIDIA ResourceServer %s: %s (%s:%u), status 0x%x\n",
                      assertion ? "assertion" : "check", expression, file,
                      line, status);
}
} // namespace

extern "C" {
NvLength portSyncRwLockSize = sizeof(PORT_RWLOCK);

NV_STATUS s540RsBackendInitialize(void) {
    if (stateGuard != nullptr || !ordinaryThread() ||
        s540NvportMemoryIsInitialized() != NV_TRUE)
        return NV_ERR_INVALID_STATE;
#if !defined(KERNEL)
    if (consumeFailure(S540NvidiaResourceBackendNative::Failure::InitializeGuard))
        return NV_ERR_NO_MEMORY;
#endif
    void *guard = nullptr;
    const NV_STATUS status = os_alloc_spinlock(&guard);
    if (status != NV_OK)
        return status;
    portMemSet(threadState, 0, sizeof(threadState));
    portMemSet(lockState, 0, sizeof(lockState));
    liveTlsEntries = 0;
    liveLocks = 0;
    __atomic_store_n(&assertionFailures, NvU32{0}, __ATOMIC_RELAXED);
    __atomic_store_n(&checkFailures, NvU32{0}, __ATOMIC_RELAXED);
    stateGuard = guard;
    return NV_OK;
}

NvBool s540RsBackendShutdown(void) {
    if (stateGuard == nullptr)
        return NV_TRUE;
    if (!ordinaryThread())
        return NV_FALSE;
    {
        Guard guard;
        if (liveTlsEntries != 0 || liveLocks != 0)
            return NV_FALSE;
    }
    // The enclosing lease guarantees no user or waiter remains at this point.
    void *guard = stateGuard;
    stateGuard = nullptr;
    os_free_spinlock(guard);
    return NV_TRUE;
}

NvBool s540RsBackendIsCold(void) {
    return stateGuard == nullptr && liveTlsEntries == 0 && liveLocks == 0
        ? NV_TRUE : NV_FALSE;
}
NvU32 s540RsBackendLiveLocks(void) {
    if (stateGuard == nullptr)
        return 0;
    Guard guard;
    return liveLocks;
}
NvU32 s540RsBackendLiveTlsEntries(void) {
    if (stateGuard == nullptr)
        return 0;
    Guard guard;
    return liveTlsEntries;
}
NvU32 s540RsBackendAssertionFailures(void) {
    return __atomic_load_n(&assertionFailures, __ATOMIC_RELAXED);
}
NvU32 s540RsBackendCheckFailures(void) {
    return __atomic_load_n(&checkFailures, __ATOMIC_RELAXED);
}

PORT_RWLOCK *portSyncRwLockCreate(PORT_MEM_ALLOCATOR *allocator) {
    if (allocator == nullptr || stateGuard == nullptr || !ordinaryThread())
        return nullptr;
#if !defined(KERNEL)
    if (consumeFailure(S540NvidiaResourceBackendNative::Failure::RwStorage))
        return nullptr;
#endif
    auto *lock = static_cast<PORT_RWLOCK *>(PORT_ALLOC(allocator, sizeof(PORT_RWLOCK)));
    if (lock == nullptr)
        return nullptr;
    lock->rwlock = nullptr;
    lock->pAllocator = allocator;
    NV_STATUS status;
#if !defined(KERNEL)
    if (consumeFailure(S540NvidiaResourceBackendNative::Failure::RwBacking))
        status = NV_ERR_NO_MEMORY;
    else
#endif
        status = os_alloc_mutex(&lock->rwlock);
    if (status != NV_OK) {
        PORT_FREE(allocator, lock);
        return nullptr;
    }
    bool registered = false;
    {
        Guard guard;
        for (auto &state : lockState) {
            if (state.lock == nullptr) {
                state.lock = lock;
                state.owner = 0;
                state.mode = 0;
                ++liveLocks;
                registered = true;
                break;
            }
        }
    }
    if (!registered) {
        os_free_mutex(lock->rwlock);
        PORT_FREE(allocator, lock);
        return nullptr;
    }
    return lock;
}

void portSyncRwLockDestroy(PORT_RWLOCK *lock) {
    if (lock == nullptr)
        return;
    if (stateGuard == nullptr || !ordinaryThread())
        contractFailure("RW destruction state or context");
    {
        Guard guard;
        LockState *state = findLock(lock);
        if (state == nullptr || state->owner != 0)
            contractFailure("RW destruction before quiescence");
        *state = {};
        --liveLocks;
    }
    os_free_mutex(lock->rwlock);
    PORT_FREE(lock->pAllocator, lock);
}
void portSyncRwLockAcquireRead(PORT_RWLOCK *lock) { acquire(lock, 1); }
void portSyncRwLockAcquireWrite(PORT_RWLOCK *lock) { acquire(lock, 2); }
NvBool portSyncRwLockAcquireReadConditional(PORT_RWLOCK *lock) {
    return acquireConditional(lock, 1);
}
NvBool portSyncRwLockAcquireWriteConditional(PORT_RWLOCK *lock) {
    return acquireConditional(lock, 2);
}
void portSyncRwLockReleaseRead(PORT_RWLOCK *lock) { release(lock, 1); }
void portSyncRwLockReleaseWrite(PORT_RWLOCK *lock) { release(lock, 2); }

NvU64 portThreadGetCurrentThreadId(void) {
#if defined(KERNEL)
    return static_cast<NvU64>(reinterpret_cast<NvUPtr>(current_thread()));
#else
    // pthread_t is an opaque integral/pointer token on the supported native
    // hosts; copying its bits avoids treating it as a numeric OS thread ID.
    const pthread_t thread = pthread_self();
    static_assert(sizeof(thread) <= sizeof(NvU64), "Native thread token is too wide.");
    NvU64 identity = 0;
    portMemCopy(&identity, sizeof(identity), &thread, sizeof(thread));
    return identity;
#endif
}

NvP64 *tlsEntryAcquire(NvU64 id) {
    if (stateGuard == nullptr || !ordinaryThread() || !validEntry(id))
        return nullptr;
    const NvU64 identity = portThreadGetCurrentThreadId();
    if (identity == 0)
        return nullptr;
    Guard guard;
    TlsThread *thread = findThread(identity);
    if (TlsEntry *entry = findEntry(thread, id)) {
        if (entry->references == ~NvU32{0})
            return nullptr;
        ++entry->references;
        return &entry->value;
    }
#if !defined(KERNEL)
    if (consumeFailure(S540NvidiaResourceBackendNative::Failure::TlsEntry))
        return nullptr;
#endif
    if (thread == nullptr) {
        for (auto &candidate : threadState) {
            if (candidate.thread == 0) {
                thread = &candidate;
                thread->thread = identity;
                break;
            }
        }
    }
    if (thread == nullptr)
        return nullptr;
    for (auto &entry : thread->entries) {
        if (entry.references == 0) {
            entry.id = id;
            entry.references = 1;
            entry.value = NvP64_NULL;
            ++liveTlsEntries;
            return &entry.value;
        }
    }
    return nullptr;
}

NvP64 tlsEntryGet(NvU64 id) {
    if (stateGuard == nullptr || !ordinaryThread() || !validEntry(id))
        return NvP64_NULL;
    Guard guard;
    TlsEntry *entry = findEntry(findThread(portThreadGetCurrentThreadId()), id);
    return entry != nullptr ? entry->value : NvP64_NULL;
}

NvU32 tlsEntryRelease(NvU64 id) {
    if (stateGuard == nullptr || !ordinaryThread() || !validEntry(id))
        return kTlsError;
    Guard guard;
    TlsThread *thread = findThread(portThreadGetCurrentThreadId());
    TlsEntry *entry = findEntry(thread, id);
    if (entry == nullptr)
        return kTlsError;
    const NvU32 remaining = --entry->references;
    if (remaining == 0) {
        *entry = {};
        --liveTlsEntries;
        bool empty = true;
        for (const auto &candidate : thread->entries)
            empty = empty && candidate.references == 0;
        if (empty)
            thread->thread = 0;
    }
    return remaining;
}

// These exact signatures match NV_ASSERT_FAILED_USES_STRINGS=1 and the
// strings-enabled release source profile recorded by the package manifest.
void nvAssertFailedNoLog(const char *expression, const char *file, NvU32 line) {
    failureDiagnostic(true, NV_OK, expression, file, line);
}
void nvAssertOkFailedNoLog(NvU32 status, const char *expression,
                         const char *file, NvU32 line) {
    failureDiagnostic(true, status, expression, file, line);
}
void nvCheckFailedNoLog(NvU32 level, const char *expression,
                      const char *file, NvU32 line) {
    (void)level;
    failureDiagnostic(false, NV_OK, expression, file, line);
}
void nvCheckOkFailedNoLog(NvU32 level, NvU32 status, const char *expression,
                        const char *file, NvU32 line) {
    (void)level;
    failureDiagnostic(false, status, expression, file, line);
}
int NV_API_CALL nv_printf(NvU32 level, const char *format, ...) {
    (void)level;
    va_list arguments;
    va_start(arguments, format);
    const int result = printFormatted(format, arguments);
    va_end(arguments);
    return result;
}
void nvDbg_Printf(const char *file, int line, const char *function,
                  int level, const char *format, ...) {
    (void)file;
    (void)line;
    (void)function;
    (void)level;
    va_list arguments;
    va_start(arguments, format);
    (void)printFormatted(format, arguments);
    va_end(arguments);
}
} // extern "C"

#if !defined(KERNEL)
void S540NvidiaResourceBackendNative::failNext(Failure failure) {
    __atomic_store_n(&nextFailure, static_cast<NvU32>(failure), __ATOMIC_RELAXED);
}
#endif
