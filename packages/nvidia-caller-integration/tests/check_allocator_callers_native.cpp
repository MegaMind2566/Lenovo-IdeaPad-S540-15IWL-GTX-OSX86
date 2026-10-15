// SPDX-License-Identifier: MIT
// Exercise the actual adapted NVIDIA allocation callers, not local substitutes.
#include "../src/S540NvidiaReserve.hpp"
#include "../upstream/nvport_allocator_callers.h"

#include <cstdio>
#include <cstdlib>

static unsigned checks;
static void require(bool condition, const char *message)
{
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "NVIDIA allocator caller check failed: %s\n", message);
        std::exit(1);
    }
}

int main()
{
    static_assert(sizeof(NvLength) == 8, "Preserve NVIDIA allocation width");
    require(!S540NvidiaReserve::ready(), "no implicit reserve initialization");
    require(_portMemAllocNonPagedUntracked(1) == nullptr, "unavailable backend returns failure");
    require(_portMemAllocPagedUntracked(1) == nullptr, "paged wrapper retains backend failure");
    _portMemFreeUntracked(nullptr);
    require(S540NvidiaReserve::initialize(), "ordinary-thread reserve initialization");
    require(_portMemAllocNonPagedUntracked(0) == nullptr, "release-profile zero request");
    require(_portMemAllocPagedUntracked(0) == nullptr, "paged zero request");
    require(_portMemAllocNonPagedUntracked(S540NvidiaReserve::kSlotBytes + 1) == nullptr,
            "oversized request is not silently narrowed");
    require(_portMemAllocNonPagedUntracked(~NvLength(0)) == nullptr,
            "maximum wide request fails safely");
    void *slots[S540NvidiaReserve::kSlotCount] = {};
    for (NvU32 i = 0; i < S540NvidiaReserve::kSlotCount; ++i) {
        slots[i] = i % 2 == 0 ? _portMemAllocNonPagedUntracked(S540NvidiaReserve::kSlotBytes)
                            : _portMemAllocPagedUntracked(S540NvidiaReserve::kSlotBytes);
        require(slots[i] != nullptr, "caller receives an available reserve slot");
        require(reinterpret_cast<NvUPtr>(slots[i]) % S540NvidiaReserve::kAlignment == 0,
                "caller payload alignment");
        for (NvU32 j = 0; j < i; ++j)
            require(slots[i] != slots[j], "live callers never alias");
        auto *bytes = static_cast<NvU8 *>(slots[i]);
        bytes[0] = static_cast<NvU8>(i);
        bytes[S540NvidiaReserve::kSlotBytes - 1] = static_cast<NvU8>(i ^ 0xa5U);
    }
    require(S540NvidiaReserve::liveSlots() == S540NvidiaReserve::kSlotCount,
            "all caller allocations are accounted for");
    require(_portMemAllocNonPagedUntracked(1) == nullptr, "real caller propagates exhaustion");
    require(!S540NvidiaReserve::shutdown() && S540NvidiaReserve::ready(),
            "refuse shutdown while a caller still owns memory");
    for (NvU32 i = 0; i < S540NvidiaReserve::kSlotCount; ++i) {
        const auto *bytes = static_cast<const NvU8 *>(slots[i]);
        require(bytes[0] == static_cast<NvU8>(i)
                && bytes[S540NvidiaReserve::kSlotBytes - 1] == static_cast<NvU8>(i ^ 0xa5U),
                "other caller allocations preserve live contents");
        _portMemFreeUntracked(slots[i]);
    }
    require(S540NvidiaReserve::liveSlots() == 0, "original free caller returns every slot");
    void *again = _portMemAllocNonPagedUntracked(256);
    require(again != nullptr, "original callers reuse released capacity");
    _portMemFreeUntracked(again);
    require(S540NvidiaReserve::shutdown(), "quiescent reserve release");
    require(_portMemAllocPagedUntracked(1) == nullptr, "shutdown is visible to original caller");
    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,"
                "\"upstream_allocation_callers\":3,\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
}
