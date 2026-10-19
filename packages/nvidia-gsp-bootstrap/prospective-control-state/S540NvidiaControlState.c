/* SPDX-License-Identifier: MIT */
#include "nv.h"
#include "os-interface.h"
#include "nv-chardev-numbers.h"
#include "nvport/nvport.h"
#include "nvport/sync/inc/sync_unix_kernel_os_def.h"
#include "S540NvidiaControlState.h"
#include "S540NvidiaGspFirstTransaction.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

#if !defined(S540_NVIDIA_NO_CHARACTER_DEVICE) || S540_NVIDIA_NO_CHARACTER_DEVICE != 1
#error "Explicit no-character-device source profile required"
#endif
#if !defined(S540_NVIDIA_NO_OS_EVENT_BACKEND) || S540_NVIDIA_NO_OS_EVENT_BACKEND != 1
#error "Actual OS-event constructor refusal must be composed"
#endif
#if !defined(NV_X86_64) || NV_ARCH_BITS != 64 || !defined(NV_UNIX)
#error "Control-state ABI requires the selected x86-64 Unix original headers"
#endif

static nv_state_t controlState;
static PORT_SPINLOCK eventLock;
static S540FirstTxnHostIdentity retained;
static NvU64 controlMasterThread;
static const nv_state_t *adapter;
static NvU32 initialized;
#define LD(p) __atomic_load_n((p), __ATOMIC_ACQUIRE)
#define MARK() s540GlobalRmRecordServiceName(__func__)
static __attribute__((noreturn)) void violation(const char *reason)
{
    s540GlobalRmRecordUnavailable(571);
    os_bug_check(0, reason);
    __builtin_trap();
}
NV_STATUS s540ControlStatePrepare(void)
{
    S540FirstTxnHostIdentity identity = {0};
    NvU64 thread = 0;
    NvU32 empty = 0;
    NV_STATUS status;
    if (!s540Darwin_os_semaphore_may_sleep() ||
        s540Darwin_os_get_current_thread(&thread) != NV_OK || !thread)
        return NV_ERR_INVALID_STATE;
    status = s540FirstTxnMasterIdentity(&identity);
    if (status != NV_OK) return status;
    if (!identity.owner || !identity.generation) return NV_ERR_INVALID_STATE;
    if (!__atomic_compare_exchange_n(&initialized, &empty, ~0U, NV_FALSE,
            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return NV_ERR_IN_USE;
    /* This original initializer uses a real OS spinlock directly; it needs
     * neither portInitialize nor an allocator/registry created by global RM. */
    retained = identity;
    controlMasterThread = thread;
    status = portSyncSpinlockInitialize(&eventLock);
    if (status != NV_OK) {
        s540FirstTxnObserveServiceRefusal(8, 571, status);
        return status; /* The one-shot reservation and partial backend stay. */
    }
    controlState.flags = NV_FLAG_CONTROL;
    controlState.event_spinlock = &eventLock;
    __atomic_store_n(&initialized, 1U, __ATOMIC_RELEASE);
    return NV_OK;
}
NV_STATUS s540ControlStateBindAdapter(const void *exactNv)
{
    S540FirstTxnSnapshot snapshot = {0};
    S540FirstTxnHostIdentity identity = {0};
    const nv_state_t *nv = exactNv;
    NvU64 thread = 0;
    const nv_state_t *empty = NULL;
    NV_STATUS status;
    if (LD(&initialized) != 1U || !exactNv ||
        s540Darwin_os_get_current_thread(&thread) != NV_OK || thread != controlMasterThread)
        return NV_ERR_INVALID_STATE;
    status = s540FirstTxnMasterIdentity(&identity);
    if (status != NV_OK) return status;
    if (identity.owner != retained.owner || identity.generation != retained.generation)
        return NV_ERR_INVALID_STATE;
    /* Query verifies exact nv before any original structure dereference. */
    status = s540FirstTxnGetSnapshot(exactNv, &snapshot);
    if (status != NV_OK) return status;
    if (snapshot.generation != retained.generation || snapshot.masterThread != controlMasterThread ||
        snapshot.firstStatus || snapshot.phase != S540_FIRST_OP ||
        nv->primary_vga || (nv->flags & NV_FLAG_CONTROL) ||
        nv->pci_info.vendor_id != 0x10de || nv->pci_info.device_id != 0x1f91 ||
        nv->subsystem_vendor != 0x17aa || nv->subsystem_id != 0x3806)
        return NV_ERR_NOT_SUPPORTED;
    if (!__atomic_compare_exchange_n(&adapter, &empty, nv, NV_FALSE,
            __ATOMIC_RELEASE, __ATOMIC_ACQUIRE)) return NV_ERR_IN_USE;
    return NV_OK;
}
nv_state_t *NV_API_CALL nv_get_ctl_state(void)
{
    MARK();
    if (LD(&initialized) != 1U) violation("control state used before real lock initialization");
    /* All original users protect event_list/refcounts with event_spinlock.
     * The state and its real lock remain allocated throughout the epoch. */
    return &controlState;
}
NvU32 NV_API_CALL nv_get_dev_minor(nv_state_t *nv)
{
    MARK();
    if (LD(&initialized) != 1U) violation("device ordinal queried before control initialization");
    if (nv == &controlState) return NV_MINOR_DEVICE_NUMBER_CONTROL_DEVICE;
    if (nv && nv == LD(&adapter)) return 0; /* The sole admitted device ordinal. */
    violation("foreign device has no assigned character-device ordinal");
}
nv_file_private_t *NV_API_CALL nv_get_file_private(NvS32 fd, NvBool ctl, void **osPrivate)
{
    (void)fd; (void)ctl; (void)osPrivate;
    MARK();
    /* No device nodes, descriptor registration or user-RM entry is exposed.
     * The real table is permanently empty. Never interpret a Darwin fd as an
     * NVIDIA Linux file-private pointer or manufacture a successful lookup. */
    /* Like the original failed lookup, do not modify the private output.
     * Complete original callers initialize it to NULL before lookup. */
    return NULL;
}
void NV_API_CALL nv_put_file_private(void *osPrivate)
{
    (void)osPrivate;
    MARK();
    violation("no file-private reference can originate in the selected empty table");
}
void NV_API_CALL nv_post_event(nv_event_t *event, NvHandle handle, NvU32 index,
    NvU32 info32, NvU16 info16, NvBool valid)
{
    (void)event; (void)handle; (void)index; (void)info32; (void)info16; (void)valid;
    MARK();
    /* Explicit event constructors refuse OS events before acquiring a file.
     * A broken route must not return as if notification had been delivered. */
    violation("OS event reached a source profile with no file/event admission");
}
