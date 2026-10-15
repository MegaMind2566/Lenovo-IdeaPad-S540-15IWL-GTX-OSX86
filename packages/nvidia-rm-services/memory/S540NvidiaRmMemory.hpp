// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RM_MEMORY_HPP
#define S540_NVIDIA_RM_MEMORY_HPP

#include "nv_memory_services.h"

namespace S540NvidiaRmMemory {
constexpr NvU32 kPageBytes = 4096;
constexpr NvU32 kMaxPages = 16;
constexpr NvU32 kMaxAllocations = 8;
constexpr NvU32 kMaxMappings = 32;

struct Statistics {
    NvU32 allocations;
    NvU32 mappings;
    NvU32 deferred;
    NvU32 rejected;
    NvU32 releaseErrors;
    NvU64 bytes;
};

// Lifecycle is externally serialized/quiesced under the transport lease.
// All calls require an ordinary thread with interrupts enabled and no spin
// lock held. The registry uses an ordinary sleeping mutex, never an IRQ lock.
bool initialize();
bool shutdown();
bool ready();
Statistics statistics();

struct Result {
    NvU32 checks;
    NvU32 failures;
    bool allocation;
    bool mappings;
    bool deferredFree;
    bool bounds;
    bool cleanup;
    bool passed() const {
        return checks != 0 && failures == 0 && allocation && mappings &&
               deferredFree && bounds && cleanup;
    }
};

// Uses the actual C entry points above. The finite profile returns every
// allocation/mapping cold and shuts down its service before returning.
Result check();

#if !defined(KERNEL)
enum class Fault : NvU32 {
    None, Context, LockAllocation, BufferAllocation, BufferContents,
    BufferPrepare, PhysicalLookup, PhysicalShort, PhysicalAlignment,
    MappingAllocation, MappingAddress, BufferComplete
};
void setNativeFault(Fault);
NvU32 nativeLiveResources();
NvU32 nativeIllegalOperations();
#endif
}
#endif
