// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RESOURCE_BACKEND_HPP
#define S540_NVIDIA_RESOURCE_BACKEND_HPP

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

// Adapter for the selected ordinary-thread RS_STANDALONE source profile.
// Initialize and shut down under the outer runtime lease. Every server, lock,
// TLS reference and worker must be quiescent before shutdown. The full NVIDIA
// TLS library, interrupt TLS, dynamic entry IDs and concurrent-reader lock
// optimization are outside this profile. Reads and writes both take the real
// nonrecursive owner-thread OS mutex; this preserves exclusion and lock order.
// TLS has 32 reusable thread records with 16 entries each. Exhaustion returns
// NULL, and an unmatched release returns ~0U. No entry is silently evicted.

#ifdef __cplusplus
extern "C" {
#endif

typedef struct PORT_MEM_ALLOCATOR PORT_MEM_ALLOCATOR;
typedef struct PORT_RWLOCK PORT_RWLOCK;

NV_STATUS s540RsBackendInitialize(void);
NvBool s540RsBackendShutdown(void);
NvBool s540RsBackendIsCold(void);
NvU32 s540RsBackendLiveLocks(void);
NvU32 s540RsBackendLiveTlsEntries(void);
NvU32 s540RsBackendAssertionFailures(void);
NvU32 s540RsBackendCheckFailures(void);

extern NvLength portSyncRwLockSize;
PORT_RWLOCK *portSyncRwLockCreate(PORT_MEM_ALLOCATOR *);
void portSyncRwLockDestroy(PORT_RWLOCK *);
void portSyncRwLockAcquireRead(PORT_RWLOCK *);
void portSyncRwLockAcquireWrite(PORT_RWLOCK *);
NvBool portSyncRwLockAcquireReadConditional(PORT_RWLOCK *);
NvBool portSyncRwLockAcquireWriteConditional(PORT_RWLOCK *);
void portSyncRwLockReleaseRead(PORT_RWLOCK *);
void portSyncRwLockReleaseWrite(PORT_RWLOCK *);
NvU64 portThreadGetCurrentThreadId(void);
NvP64 *tlsEntryAcquire(NvU64);
NvP64 tlsEntryGet(NvU64);
NvU32 tlsEntryRelease(NvU64);

#ifdef __cplusplus
}
#endif

#if defined(__cplusplus) && !defined(KERNEL)
namespace S540NvidiaResourceBackendNative {
// Each failure is consumed once by the corresponding acquisition path.
enum class Failure : NvU32 { None, InitializeGuard, RwStorage, RwBacking, TlsEntry };
void failNext(Failure failure);
}
#endif

#endif
