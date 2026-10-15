// SPDX-License-Identifier: MIT
// CPU-only execution of the adapted NVIDIA memory callers and clock backend.
#include "../src/S540NvidiaMemory.hpp"
#include "../src/S540NvidiaClock.hpp"

#include <cstdio>
#include <cstdlib>
#include <sys/mman.h>
#include <unistd.h>

static unsigned checks;

static void require(bool condition, const char *message)
{
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "Memory adapter check failed: %s\n", message);
        std::exit(1);
    }
}

static int sign(NvS32 value) { return (value > 0) - (value < 0); }

static void buffers()
{
    const NvLength lengths[] = {0, 1, 2, 3, 4, 7, 15, 31, 63, 127, 255, 256};
    NvU8 source[272], destination[272];
    for (unsigned i = 0; i < sizeof(source); ++i)
        source[i] = static_cast<NvU8>((i * 37U + 0x80U) & 0xffU);
    for (NvLength length : lengths) {
        for (unsigned offset = 0; offset < 4; ++offset) {
            for (unsigned variant = 0; variant < 2; ++variant) {
                for (auto &value : destination) value = 0xa5;
                void *result = variant == 0
                    ? portMemCopy(destination + 8 + offset, length, source + offset, length)
                    : portMemCopyAligned(destination + 8 + offset, length, source + offset, length);
                require(result == destination + 8 + offset, "copy return pointer");
                bool correct = true;
                for (unsigned i = 0; i < sizeof(destination); ++i) {
                    NvU8 expected = (i >= 8 + offset && i < 8 + offset + length)
                        ? source[i - 8] : 0xa5;
                    correct = correct && destination[i] == expected;
                }
                require(correct, "copy bytes and surrounding canaries");
            }
            for (auto &value : destination) value = 0xa5;
            require(portMemSet(destination + 8 + offset, 0xe7, length) == destination + 8 + offset,
                    "set return pointer");
            bool correct = true;
            for (unsigned i = 0; i < sizeof(destination); ++i) {
                NvU8 expected = (i >= 8 + offset && i < 8 + offset + length) ? 0xe7 : 0xa5;
                correct = correct && destination[i] == expected;
            }
            require(correct, "set bytes and surrounding canaries");
            require(portMemCmp(source + offset, source + offset, length) == 0,
                    "equal buffers");
        }
    }
    const NvU8 low[] = {0x80, 0x00, 0xff};
    const NvU8 high[] = {0x80, 0x01, 0x00};
    require(sign(portMemCmp(low, high, sizeof(low))) == -1, "unsigned comparison, first difference");
    require(sign(portMemCmp(high, low, sizeof(low))) == 1, "reverse comparison");
    const NvU8 zero = 0, top = 0xff;
    require(sign(portMemCmp(&top, &zero, 1)) == 1, "high-bit byte is unsigned");
    require(sign(portMemCmp(&zero, &top, 1)) == -1, "unsigned inverse comparison");

    NvU8 value = 0x42;
    require(portMemCopy(&value, 0, nullptr, 50) == &value && value == 0x42,
            "upstream zero-destination no-op");
    require(portMemCopy(nullptr, 0, nullptr, 0) == nullptr, "zero-destination null no-op");
    require(portMemCopy(&value, 1, nullptr, 1) == nullptr && value == 0x42,
            "null source refused");
    require(portMemCopy(nullptr, 1, &value, 1) == nullptr, "null destination refused");
    require(portMemCopy(&value, 1, source, 2) == nullptr && value == 0x42,
            "insufficient destination refused");
    require(portMemCopyAligned(&value, 1, source, 2) == nullptr && value == 0x42,
            "aligned caller retains destination bound");
    require(portMemSet(nullptr, 1, 1) == nullptr, "null set follows upstream release behavior");
    require(portMemSet(&value, 0, 0) == &value && value == 0x42, "zero set no-op");
    require(portMemCmp(nullptr, nullptr, 0) == 0, "zero compare accepts null");
    require(portMemCmp(nullptr, &value, 1) == -1, "null first compare follows upstream behavior");
    require(portMemCmp(&value, nullptr, 1) == -1, "null second compare follows upstream behavior");
}

static void chunkPolicy()
{
    const NvLength maximum = 0xffffffffULL;
    const NvLength lengths[] = {0, 1, maximum - 1, maximum, maximum + 1,
                                2 * maximum, 2 * maximum + 1, ~NvLength(0)};
    for (NvLength length : lengths) {
        const NvU32 chunk = S540NvidiaMemory::chunkLength(length);
        require(chunk == (length > maximum ? maximum : length), "64-bit chunk bound");
        require(chunk <= length && (length == 0 || chunk > 0), "chunk makes bounded progress");
    }
}

static void guardPages()
{
    const long page = sysconf(_SC_PAGESIZE);
    require(page > 0, "native page size");
    auto *memory = static_cast<NvU8 *>(mmap(nullptr, static_cast<size_t>(page) * 5,
        PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0));
    require(memory != MAP_FAILED, "guard-page mapping");
    require(mprotect(memory + page, static_cast<size_t>(page), PROT_READ | PROT_WRITE) == 0
            && mprotect(memory + 3 * page, static_cast<size_t>(page), PROT_READ | PROT_WRITE) == 0,
            "guard-page buffer protection");
    NvU8 *source = memory + 2 * page - 31;
    NvU8 *destination = memory + 4 * page - 31;
    for (unsigned i = 0; i < 31; ++i) source[i] = static_cast<NvU8>(i + 0x80);
    require(portMemCopy(destination, 31, source, 31) == destination, "copy ends at unmapped boundary");
    require(portMemCmp(source, destination, 31) == 0, "compare ends at unmapped boundary");
    require(portMemSet(destination, 0x7b, 31) == destination, "set ends at unmapped boundary");
    bool correct = true;
    for (unsigned i = 0; i < 31; ++i) correct = correct && destination[i] == 0x7b;
    require(correct, "guard-page set contents");
    require(munmap(memory, static_cast<size_t>(page) * 5) == 0, "guard-page cleanup");
}

static void clockIntegration()
{
    require(S540NvidiaClock::backendReady(), "clock backend preflight");
    NvU64 previous = 0;
    for (unsigned i = 0; i < 16; ++i) {
        const NvU64 sampled = portTimeGetUptimeNanosecondsHighPrecision();
        NvU64 copied = 0;
        require(portMemCopy(&copied, sizeof(copied), &sampled, sizeof(sampled)) == &copied,
                "clock sample crosses memory caller");
        require(copied == sampled && copied >= previous, "copied clock sample stays monotonic");
        require(portMemCmp(&copied, &sampled, sizeof(sampled)) == 0, "clock sample byte identity");
        previous = copied;
    }
}

int main()
{
    static_assert(sizeof(NvLength) == 8 && sizeof(NvU32) == 4, "NVIDIA ABI widths");
    buffers();
    chunkPolicy();
    guardPages();
    clockIntegration();
    std::printf("{\"format\":1,\"status\":\"passed\",\"checks\":%u,"
        "\"component\":\"memory-and-clock\",\"execution\":\"native-user-space\","
        "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false,"
        "\"wide_length_policy\":\"checked-without-large-allocation\"}\n", checks);
    return 0;
}
