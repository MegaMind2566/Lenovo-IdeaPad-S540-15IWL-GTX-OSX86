// SPDX-License-Identifier: MIT
// Focused CPU-only allocator ABI, bounds, alignment, and failure-path checks.
#include "../src/S540NvidiaAllocator.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>

static unsigned checks;

static void require(bool condition, const char *message) {
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "Allocator adapter check failed: %s\n", message);
        std::exit(1);
    }
}

#if defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
static bool failNext;
static size_t backendCalls;
static size_t backendFrees;
static size_t liveTotal;
static void *liveBase;
static void *liveRaw;
static size_t baseOffset;

extern "C" void *s540NvidiaTestAllocate(size_t total) {
    ++backendCalls;
    require(liveBase == nullptr, "focused backend has no outstanding allocation");
    if (failNext) {
        failNext = false;
        return nullptr;
    }
    liveRaw = std::malloc(total + S540NvidiaAllocator::kAlignment);
    require(liveRaw != nullptr, "test backend allocation");
    // Exercise every possible alignment of the backing allocation.
    liveBase = static_cast<NvU8 *>(liveRaw) + baseOffset;
    liveTotal = total;
    std::memset(liveBase, 0xa5, total);
    return liveBase;
}

extern "C" void s540NvidiaTestFree(void *memory, size_t total) {
    ++backendFrees;
    require(memory == liveBase && total == liveTotal,
            "free receives exact original base and total size");
    std::free(liveRaw);
    liveBase = nullptr;
    liveRaw = nullptr;
    liveTotal = 0;
}
#endif

static void sizeAndFailurePolicy() {
    const size_t maximum = static_cast<size_t>(-1);
    size_t total = 99;
    require(!S540NvidiaAllocator::allocationSize(0, total) && total == 0,
            "zero-size policy clears total");
    require(S540NvidiaAllocator::allocationSize(1, total)
                && total == 1 + S540NvidiaAllocator::kMaximumOverhead,
            "small allocation contains header and worst alignment padding");
    require(S540NvidiaAllocator::allocationSize(
                maximum - S540NvidiaAllocator::kMaximumOverhead, total)
                && total == maximum,
            "largest representable policy length does not overflow");
    require(!S540NvidiaAllocator::allocationSize(
                maximum - S540NvidiaAllocator::kMaximumOverhead + 1, total)
                && total == 0,
            "first overflowing total is refused");
    require(os_alloc_mem(nullptr, 1) == NV_ERR_INVALID_POINTER,
            "missing output pointer refused");
    void *output = reinterpret_cast<void *>(1);
    require(os_alloc_mem(&output, 0) == NV_ERR_INVALID_ARGUMENT && output == nullptr,
            "zero request clears output and reports invalid argument");
    output = reinterpret_cast<void *>(1);
    require(os_alloc_mem(&output, ~NvU64(0)) == NV_ERR_NO_MEMORY && output == nullptr,
            "overflowing request clears output and reports allocation failure");
    os_free_mem(nullptr);
#if defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
    require(backendCalls == 0 && backendFrees == 0,
            "invalid requests and null free do not call the backend");
    failNext = true;
    output = reinterpret_cast<void *>(1);
    require(os_alloc_mem(&output, 32) == NV_ERR_NO_MEMORY && output == nullptr,
            "native backend failure clears output and returns no memory");
    require(backendCalls == 1 && backendFrees == 0 && liveBase == nullptr,
            "failed allocation neither frees nor leaks a backing allocation");
#endif
}

static void allocationRoundTrips() {
    const NvU64 lengths[] = {1, 2, 15, 16, 17, 31, 32, 255, 4096, 65537};
    for (size_t offset = 0; offset < S540NvidiaAllocator::kAlignment; ++offset) {
#if defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
        baseOffset = offset;
#endif
        for (NvU64 length : lengths) {
            void *memory = nullptr;
            require(os_alloc_mem(&memory, length) == NV_OK && memory != nullptr,
                    "ordinary RAM allocation succeeds");
            require((reinterpret_cast<NvUPtr>(memory)
                        & (S540NvidiaAllocator::kAlignment - 1)) == 0,
                    "payload preserves 16-byte alignment");
            auto *bytes = static_cast<NvU8 *>(memory);
#if defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
            require(bytes[0] == 0xa5 && bytes[length - 1] == 0xa5,
                    "allocation does not silently promise zeroed memory");
            require(bytes >= static_cast<NvU8 *>(liveBase)
                            + S540NvidiaAllocator::kHeaderBytes
                        && bytes + length <= static_cast<NvU8 *>(liveBase) + liveTotal,
                    "payload and header fit exact backing allocation");
#endif
            for (NvU64 i = 0; i < length; ++i)
                bytes[i] = static_cast<NvU8>((i * 37 + length) & 0xff);
            bool correct = true;
            for (NvU64 i = 0; i < length; ++i)
                correct = correct && bytes[i] == static_cast<NvU8>((i * 37 + length) & 0xff);
            require(correct, "complete requested payload remains writable and readable");
            os_free_mem(memory);
        }
    }
#if defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
    require(liveBase == nullptr && backendCalls == backendFrees + 1,
            "every successful backing allocation is released once");
#endif
}

int main() {
    sizeAndFailurePolicy();
    allocationRoundTrips();
    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,"
        "\"component\":\"host-ram-allocator\",\"execution\":\"native-user-space\","
        "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false,"
        "\"failure_injection\":%s}\n", checks,
#if defined(S540_NVIDIA_ALLOCATOR_TEST_BACKEND)
        "true"
#else
        "false"
#endif
    );
    return 0;
}
