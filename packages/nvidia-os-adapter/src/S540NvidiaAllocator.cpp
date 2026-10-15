// SPDX-License-Identifier: MIT
#include "S540NvidiaAllocator.hpp"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#else
#include <stdlib.h>
#include <string.h>
#endif

#if defined(KERNEL) && defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
#error "The failure-injection backend is only available to native tests."
#endif

#if defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
extern "C" void *s540NvidiaTestAllocate(size_t);
extern "C" void s540NvidiaTestFree(void *, size_t);
#endif

static_assert(NVCPU_IS_X86_64 && sizeof(void *) == 8 && sizeof(size_t) == 8,
              "The allocator adapter supports Intel x86_64 only.");
static_assert(sizeof(NvU64) == 8,
              "Preserve NVIDIA's 64-bit allocation length ABI.");

namespace {

bool ordinaryThreadContext() {
#if defined(KERNEL)
    // These checks cannot prove that no spin lock is held. That remains an
    // explicit caller precondition for allocation and release.
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}

// os_free_mem has no size argument. Retain the original allocation and its exact
// size for IOFree, before the aligned payload. Copy metadata rather than treating
// raw allocation storage as a constructed C++ object.
struct AllocationHeader {
    void *base;
    size_t total;
};
static_assert(sizeof(AllocationHeader) == S540NvidiaAllocator::kHeaderBytes,
              "The allocation-size policy must include the complete header.");

void *allocate(size_t total) {
#if defined(KERNEL)
    return IOMalloc(total);
#elif defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
    return s540NvidiaTestAllocate(total);
#else
    return malloc(total);
#endif
}

void release(void *memory, size_t total) {
#if defined(KERNEL)
    IOFree(memory, total);
#elif defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
    s540NvidiaTestFree(memory, total);
#else
    (void)total;
    free(memory);
#endif
}

} // namespace

extern "C" NV_STATUS NV_API_CALL os_alloc_mem(void **output, NvU64 length) {
    if (output == nullptr)
        return NV_ERR_INVALID_POINTER;
    *output = nullptr;
    if (length == 0)
        return NV_ERR_INVALID_ARGUMENT;
    if (!ordinaryThreadContext())
        return NV_ERR_INVALID_REQUEST;

    size_t total = 0;
    if (!S540NvidiaAllocator::allocationSize(length, total))
        return NV_ERR_NO_MEMORY;
    void *base = allocate(total);
    if (base == nullptr)
        return NV_ERR_NO_MEMORY;

    // Do not depend on IOMalloc's alignment guarantees. The added padding can
    // align every base address without reducing the caller's requested length.
    const size_t mask = S540NvidiaAllocator::kAlignment - 1;
    const size_t padding = (S540NvidiaAllocator::kAlignment
        - (reinterpret_cast<NvUPtr>(base) & mask)) & mask;
    auto *payload = static_cast<NvU8 *>(base) + padding + sizeof(AllocationHeader);
    const AllocationHeader header = {base, total};
    memcpy(payload - sizeof(header), &header, sizeof(header));
    *output = payload;
    return NV_OK;
}

extern "C" void NV_API_CALL os_free_mem(void *memory) {
    if (memory == nullptr || !ordinaryThreadContext())
        return;
    AllocationHeader header = {};
    memcpy(&header, static_cast<NvU8 *>(memory) - sizeof(header), sizeof(header));
    release(header.base, header.total);
}
