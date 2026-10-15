// SPDX-License-Identifier: MIT
#include "S540NvidiaReserve.hpp"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <machine/machine_routines.h>
#else
#include <cstdlib>
#endif

static_assert(NVCPU_IS_X86_64 && sizeof(void *) == 8,
              "The reserve supports Intel x86_64 only.");
static_assert(sizeof(NvU64) == 8 && sizeof(NvUPtr) == sizeof(void *),
              "Preserve the NVIDIA size and pointer ABI.");
static_assert(__atomic_always_lock_free(sizeof(NvU64), nullptr),
              "The slot bitmap must never use a runtime atomic lock.");
static_assert(S540NvidiaReserve::kSlotCount <= 64 &&
                  S540NvidiaReserve::kSlotBytes %
                      S540NvidiaReserve::kAlignment == 0,
              "Every slot must fit the bitmap and preserve alignment.");

namespace {

// Trivial zero initialization only: no static C++ constructors or destructors.
void *gBacking;
alignas(8) NvU64 gLiveMask;

bool lifecycleContext()
{
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}

} // namespace

bool S540NvidiaReserve::initialize()
{
    if (!lifecycleContext())
        return false;
    if (ready())
        return true;

    void *backing = nullptr;
#if defined(KERNEL)
    backing = IOMallocAligned(static_cast<vm_size_t>(kReserveBytes), kAlignment);
#else
    if (::posix_memalign(&backing, kAlignment,
                         static_cast<size_t>(kReserveBytes)) != 0)
        backing = nullptr;
#endif
    if (backing == nullptr)
        return false;

    __atomic_store_n(&gLiveMask, NvU64{0}, __ATOMIC_RELAXED);
    __atomic_store_n(&gBacking, backing, __ATOMIC_RELEASE);
    return true;
}

bool S540NvidiaReserve::shutdown()
{
    if (!lifecycleContext())
        return false;
    if (__atomic_load_n(&gLiveMask, __ATOMIC_ACQUIRE) != 0)
        return false;
    void *backing = __atomic_load_n(&gBacking, __ATOMIC_ACQUIRE);
    if (backing == nullptr)
        return true;

    // External quiescence is mandatory; this is not a concurrent reclamation
    // scheme. No allocate/free invocation may overlap lifecycle operations.
    __atomic_store_n(&gBacking, static_cast<void *>(nullptr), __ATOMIC_RELEASE);
#if defined(KERNEL)
    IOFreeAligned(backing, static_cast<vm_size_t>(kReserveBytes));
#else
    ::free(backing);
#endif
    return true;
}

bool S540NvidiaReserve::ready()
{
    return __atomic_load_n(&gBacking, __ATOMIC_ACQUIRE) != nullptr;
}

NvU32 S540NvidiaReserve::liveSlots()
{
    NvU64 live = __atomic_load_n(&gLiveMask, __ATOMIC_ACQUIRE);
    NvU32 count = 0;
    // A fixed bounded count avoids a compiler-emitted population-count helper.
    for (NvU32 slot = 0; slot < kSlotCount; ++slot) {
        count += static_cast<NvU32>(live & 1);
        live >>= 1;
    }
    return count;
}

extern "C" NV_STATUS NV_API_CALL os_alloc_mem(void **address, NvU64 size)
{
    if (address == nullptr)
        return NV_ERR_INVALID_ARGUMENT;
    *address = nullptr;
    if (size == 0)
        return NV_ERR_INVALID_ARGUMENT;
    if (size > S540NvidiaReserve::kSlotBytes)
        return NV_ERR_NO_MEMORY;

    auto *backing = static_cast<NvU8 *>(
        __atomic_load_n(&gBacking, __ATOMIC_ACQUIRE));
    if (backing == nullptr)
        return NV_ERR_NO_MEMORY;

    // At most 32 lock-free RMWs. There is no allocator call, lock, retry loop,
    // sleep, logging or memory clearing on this path. Contents are unspecified.
    for (NvU32 slot = 0; slot < S540NvidiaReserve::kSlotCount; ++slot) {
        const NvU64 mask = NvU64{1} << slot;
        const NvU64 previous =
            __atomic_fetch_or(&gLiveMask, mask, __ATOMIC_ACQUIRE);
        if ((previous & mask) == 0) {
            *address = backing + slot * S540NvidiaReserve::kSlotBytes;
            return NV_OK;
        }
    }
    return NV_ERR_NO_MEMORY;
}

extern "C" void NV_API_CALL os_free_mem(void *address)
{
    if (address == nullptr)
        return;
    const auto *backing = static_cast<const NvU8 *>(
        __atomic_load_n(&gBacking, __ATOMIC_ACQUIRE));
    if (backing == nullptr)
        return;

    // Do not dereference an untrusted address or metadata before it. The caller
    // must pass the exact, still-live pointer returned by os_alloc_mem. An
    // invalid or stale pointer remains a caller contract violation; range and
    // alignment checks only keep non-slot values from modifying the bitmap.
    const NvUPtr first = reinterpret_cast<NvUPtr>(backing);
    const NvUPtr value = reinterpret_cast<NvUPtr>(address);
    if (value < first)
        return;
    const NvUPtr offset = value - first;
    if (offset >= S540NvidiaReserve::kReserveBytes ||
        offset % S540NvidiaReserve::kSlotBytes != 0)
        return;

    const NvU64 mask = NvU64{1} << (offset / S540NvidiaReserve::kSlotBytes);
    // Free has no failure result and must not lose the slot under contention.
    __atomic_fetch_and(&gLiveMask, ~mask, __ATOMIC_RELEASE);
}
