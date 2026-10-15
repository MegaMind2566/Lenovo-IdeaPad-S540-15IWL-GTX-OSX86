// SPDX-License-Identifier: MIT
#include "S540NvidiaSupportRuntime.hpp"
#include "S540NvidiaRmConsumer.hpp"
#include "../upstream/nvport_runtime.h"
#include "../../nvidia-caller-integration/src/S540NvidiaReserve.hpp"
#include "../../nvidia-caller-integration/src/S540NvidiaMutex.hpp"
#include "../../nvidia-nvport-lifecycle/src/S540NvidiaSpinlock.hpp"

namespace {

using S540NvidiaSupportRuntime::Result;

void check(Result &result, bool &component, bool condition)
{
    ++result.checks;
    if (!condition) {
        ++result.failures;
        component = false;
    }
}

void strings(Result &result)
{
    const char unterminated[3] = {'a', 'b', 'c'};
    check(result, result.utilities,
          portStringLength("NvPort") == 6 && portStringLength("") == 0);
    check(result, result.utilities,
          portStringLengthSafe(unterminated, sizeof(unterminated)) == 3 &&
          portStringLengthSafe(unterminated, 0) == 0);
    check(result, result.utilities,
          portStringCompare("TU117", "TU117", 6) == 0 &&
          portStringCompare("TU117", "TU118", 6) < 0 &&
          portStringCompare("\xff", "\x7f", 1) > 0 &&
          portStringCompare("a", "b", 0) == 0);
    check(result, result.utilities,
          portStringCompareIgnoreCase("NvPort", "nVpOrT", 7) == 0 &&
          portStringCompareIgnoreCase("alpha", "BRAVO", 6) < 0);
    char copied[9]{};
    copied[8] = '!';
    check(result, result.utilities,
          portStringCopy(copied, 8, "NvPort", 7) == 7 &&
          portStringCompare(copied, "NvPort", 7) == 0 && copied[8] == '!');
    char truncated[5] = {'!', '!', '!', '!', '!'};
    check(result, result.utilities,
          portStringCopy(truncated, 4, "NvPort", 7) == 4 &&
          portStringCompare(truncated, "NvP", 4) == 0 && truncated[4] == '!');
    char concatenated[12] = {'N', 'v', 0};
    check(result, result.utilities,
          portStringCat(concatenated, sizeof(concatenated), "Port", 5) ==
              concatenated && portStringCompare(concatenated, "NvPort", 7) == 0);
    check(result, result.utilities,
          portStringCat(concatenated, sizeof(concatenated), "Runtime", 8) ==
              concatenated && portStringCompare(concatenated, "NvPortRunti", 12) == 0);
    NvU16 utf16[7] = {0, 0, 0, 0, 0, 0, 0xcccc};
    check(result, result.utilities,
          portStringConvertAsciiToUtf16(utf16, 6, "TU117", 6) == 5 &&
          utf16[0] == 'T' && utf16[4] == '7' && utf16[5] == 0 &&
          utf16[6] == 0xcccc);
    check(result, result.utilities,
          portStringConvertAsciiToUtf16(utf16, 3, "TU117", 6) == 2 &&
          utf16[0] == 'T' && utf16[1] == 'U' && utf16[2] == 0 &&
          portStringConvertAsciiToUtf16(utf16, 0, "TU117", 6) == 0);
    const NvU8 binary[3] = {0, 0xa1, 0xff};
    char hexadecimal[7]{};
    check(result, result.utilities,
          portStringBufferToHex(hexadecimal, 7, binary, 3) == 6 &&
          portStringCompare(hexadecimal, "00a1ff", 7) == 0);
    check(result, result.utilities,
          portStringBufferToHex(hexadecimal, 4, binary, 3) == 3 &&
          portStringCompare(hexadecimal, "00a", 4) == 0 &&
          portStringBufferToHex(hexadecimal, 0, binary, 3) == 0);
    char tokens[] = "alpha,beta,gamma";
    char *saved = nullptr;
    char *token = portStringTok(tokens, ",", &saved);
    check(result, result.utilities, token == tokens &&
          portStringCompare(token, "alpha", 6) == 0 && saved != nullptr);
    token = portStringTok(nullptr, ",", &saved);
    check(result, result.utilities, token != nullptr &&
          portStringCompare(token, "beta", 5) == 0 && saved != nullptr);
    token = portStringTok(nullptr, ",", &saved);
    check(result, result.utilities, token != nullptr &&
          portStringCompare(token, "gamma", 6) == 0 && saved == nullptr &&
          portStringTok(nullptr, ",", &saved) == nullptr);
    char haystack[] = "nvport-runtime";
    char needle[] = "runtime";
    char absent[] = "missing";
    check(result, result.utilities,
          portStringStrStr(haystack, needle) == haystack + 7 &&
          portStringStrStr(haystack, absent) == nullptr);
    check(result, result.utilities,
          portStringStrChar(haystack, 'r') == haystack + 4 &&
          portStringStrChar(haystack, 'z') == nullptr);
}

void endianAndBits(Result &result)
{
    NvU8 buffer[10] = {0xa5, 0, 0, 0, 0, 0, 0, 0, 0, 0x5a};
    portUtilWriteLittleEndian16(buffer + 1, 0x1234);
    check(result, result.utilities, buffer[1] == 0x34 && buffer[2] == 0x12);
    portUtilWriteBigEndian16(buffer + 1, 0x1234);
    check(result, result.utilities, buffer[1] == 0x12 && buffer[2] == 0x34);
    portUtilWriteLittleEndian32(buffer + 1, 0x12345678);
    const NvU8 little32[4] = {0x78, 0x56, 0x34, 0x12};
    check(result, result.utilities, portMemCmp(buffer + 1, little32, 4) == 0);
    portUtilWriteBigEndian32(buffer + 1, 0x12345678);
    const NvU8 big32[4] = {0x12, 0x34, 0x56, 0x78};
    check(result, result.utilities, portMemCmp(buffer + 1, big32, 4) == 0);
    portUtilWriteLittleEndian64(buffer + 1, 0x0123456789abcdefULL);
    const NvU8 little64[8] = {0xef, 0xcd, 0xab, 0x89, 0x67, 0x45, 0x23, 0x01};
    check(result, result.utilities, portMemCmp(buffer + 1, little64, 8) == 0);
    portUtilWriteBigEndian64(buffer + 1, 0x0123456789abcdefULL);
    const NvU8 big64[8] = {0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef};
    check(result, result.utilities, portMemCmp(buffer + 1, big64, 8) == 0 &&
          buffer[0] == 0xa5 && buffer[9] == 0x5a);
    check(result, result.utilities,
          portUtilToUpper('q') == 'Q' && portUtilToUpper('1') == '1' &&
          portUtilToLower('R') == 'r' && portUtilToLower('#') == '#');
    check(result, result.utilities,
          portUtilCountLeadingZeros32(0) == 32 &&
          portUtilCountLeadingZeros32(1) == 31 &&
          portUtilCountLeadingZeros32(0x80000000U) == 0);
    check(result, result.utilities,
          portUtilCountLeadingZeros64(0) == 64 &&
          portUtilCountLeadingZeros64(1) == 63 &&
          portUtilCountLeadingZeros64(0x8000000000000000ULL) == 0);
    check(result, result.utilities,
          portUtilCountTrailingZeros32(0) == 32 &&
          portUtilCountTrailingZeros32(1) == 0 &&
          portUtilCountTrailingZeros32(0x80000000U) == 31);
    check(result, result.utilities,
          portUtilCountTrailingZeros64(0) == 64 &&
          portUtilCountTrailingZeros64(1) == 0 &&
          portUtilCountTrailingZeros64(0x8000000000000000ULL) == 63);
}

// Every selected width exercises boundary success, arithmetic overflow or
// underflow, divide-by-zero refusal and successful division. Unsigned wrapped
// output is not treated as usable after an arithmetic function returns false.
#define S540_CHECK_SAFE_WIDTH(Type, Suffix) \
    do { \
        Type output = 0; \
        const Type maximum = ~Type{0}; \
        check(result, result.utilities, \
              portSafeAdd##Suffix(maximum - 1, 1, &output) == NV_TRUE && \
              output == maximum && \
              portSafeAdd##Suffix(maximum, 1, &output) == NV_FALSE); \
        check(result, result.utilities, \
              portSafeSub##Suffix(7, 2, &output) == NV_TRUE && output == 5 && \
              portSafeSub##Suffix(0, 1, &output) == NV_FALSE); \
        check(result, result.utilities, \
              portSafeMul##Suffix(7, 6, &output) == NV_TRUE && output == 42 && \
              portSafeMul##Suffix(maximum, 2, &output) == NV_FALSE); \
        output = 19; \
        check(result, result.utilities, \
              portSafeDiv##Suffix(42, 0, &output) == NV_FALSE && output == 19 && \
              portSafeDiv##Suffix(42, 6, &output) == NV_TRUE && output == 7); \
    } while (false)

void safeArithmetic(Result &result)
{
    S540_CHECK_SAFE_WIDTH(NvU32, U32);
    S540_CHECK_SAFE_WIDTH(NvU64, U64);
    S540_CHECK_SAFE_WIDTH(NvUPtr, UPtr);
    S540_CHECK_SAFE_WIDTH(NvLength, Length);
}
#undef S540_CHECK_SAFE_WIDTH

void pseudoRandom(Result &result)
{
    // Golden sequence for pinned splitmix64-seeded xorshift128+, seed deadbeef.
    // It is a deterministic CPU utility, never a security entropy source.
    constexpr NvU64 seed = 0xdeadbeefULL;
    PORT_CRYPTO_PRNG *generator = portCryptoPseudoRandomGeneratorCreate(seed);
    check(result, result.utilities, generator != nullptr);
    if (generator != nullptr) {
        check(result, result.utilities,
              portCryptoPseudoRandomGeneratorGetU32(generator) == 0xdb3c4cc4U);
        check(result, result.utilities,
              portCryptoPseudoRandomGeneratorGetU64(generator) ==
                  0xe9590eb5fcf72857ULL);
        NvU8 output[19]{};
        output[0] = 0xa5;
        output[18] = 0x5a;
        const NvU8 expected[17] = {0xc9, 0x0e, 0x9e, 0x45, 0xb6, 0x96, 0x1e,
            0xf4, 0x9b, 0x3b, 0x8c, 0x28, 0xb1, 0x88, 0x2b, 0xa9, 0x96};
        check(result, result.utilities,
              portCryptoPseudoRandomGeneratorFillBuffer(generator, output + 1,
                  sizeof(expected)) == NV_OK &&
              portMemCmp(output + 1, expected, sizeof(expected)) == 0 &&
              output[0] == 0xa5 && output[18] == 0x5a);
        check(result, result.utilities,
              portCryptoPseudoRandomGeneratorFillBuffer(generator, nullptr, 1) ==
                  NV_ERR_INVALID_POINTER &&
              portCryptoPseudoRandomGeneratorFillBuffer(generator, output, 0) == NV_OK &&
              output[0] == 0xa5);
    }
    portCryptoPseudoRandomGeneratorDestroy(generator);
    portCryptoPseudoRandomGeneratorDestroy(nullptr);
    portCryptoPseudoRandomSetSeed(seed);
    check(result, result.utilities, portCryptoDefaultGenerator != nullptr);
    if (portCryptoDefaultGenerator != nullptr) {
        check(result, result.utilities,
              portCryptoPseudoRandomGetU32() == 0xdb3c4cc4U &&
              portCryptoPseudoRandomGetU64() == 0xe9590eb5fcf72857ULL);
        NvU8 output[3]{};
        check(result, result.utilities,
              portCryptoPseudoRandomFillBuffer(output, sizeof(output)) == NV_OK &&
              output[0] == 0xc9 && output[1] == 0x0e && output[2] == 0x9e &&
              portCryptoPseudoRandomFillBuffer(nullptr, 1) == NV_ERR_INVALID_POINTER);
    }
}

void runSupport(void *context)
{
    auto &result = *static_cast<Result *>(context);
    result = {0, 0, true, false, false, true};
    check(result, result.core, s540NvportLifecycleContextAllowed() == NV_TRUE);
    check(result, result.core, s540NvportRuntimeIsCold() == NV_TRUE &&
          !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0);
    if (!result.core) {
        result.cleanup = false;
        return;
    }
    const NvU32 mutexBaseline = S540NvidiaMutex::liveObjects();
    const NvU32 spinlockBaseline = S540NvidiaSpinlock::liveObjects();
    check(result, result.core, S540NvidiaReserve::initialize());
    if (S540NvidiaReserve::ready()) {
        const NV_STATUS initialized = s540NvportRuntimeInitialize();
        check(result, result.core, initialized == NV_OK &&
              s540NvportRuntimeIsInitialized() == NV_TRUE);
        if (initialized == NV_OK) {
            const NvU32 slots = S540NvidiaReserve::liveSlots();
            const NvU32 allocators = s540NvportMemoryAllocatorCount();
            PORT_MEM_TRACK_ALLOCATOR_STATS baseline{};
            check(result, result.core,
                  portMemExTrackingGetActiveStats(nullptr, &baseline) == NV_OK &&
                  baseline.numAllocations == 1 && portCryptoDefaultGenerator != nullptr);
            check(result, result.core,
                  s540NvportRuntimeInitialize() == NV_ERR_INVALID_STATE &&
                  s540NvportRuntimeIsInitialized() == NV_TRUE &&
                  S540NvidiaReserve::liveSlots() == slots);
            result.utilities = true;
            strings(result);
            endianAndBits(result);
            safeArithmetic(result);
            pseudoRandom(result);
            PORT_MEM_TRACK_ALLOCATOR_STATS afterUtilities{};
            check(result, result.cleanup,
                  portMemExTrackingGetActiveStats(nullptr, &afterUtilities) == NV_OK &&
                  afterUtilities.numAllocations == baseline.numAllocations &&
                  S540NvidiaReserve::liveSlots() == slots &&
                  s540NvportMemoryAllocatorCount() == allocators);
            const auto consumer = S540NvidiaRmConsumer::check(
                portMemAllocatorGetGlobalNonPaged());
            result.checks += consumer.checks;
            result.failures += consumer.failures;
            result.consumer = true;
            check(result, result.consumer, consumer.passed());
            result.cleanup = result.cleanup && consumer.cleanup;
            check(result, result.cleanup,
                  s540NvportRuntimeShutdown() == NV_OK &&
                  s540NvportRuntimeIsCold() == NV_TRUE);
        }
        check(result, result.cleanup, s540NvportRuntimeIsCold() == NV_TRUE &&
              S540NvidiaReserve::liveSlots() == 0 &&
              S540NvidiaMutex::liveObjects() == mutexBaseline &&
              S540NvidiaSpinlock::liveObjects() == spinlockBaseline);
        check(result, result.cleanup, S540NvidiaReserve::shutdown());
    }
    check(result, result.cleanup, s540NvportRuntimeIsCold() == NV_TRUE &&
          !S540NvidiaReserve::ready() && S540NvidiaReserve::liveSlots() == 0 &&
          S540NvidiaMutex::liveObjects() == mutexBaseline &&
          S540NvidiaSpinlock::liveObjects() == spinlockBaseline);
}

struct ContinuationContext {
    Result *support;
    S540NvidiaSupportRuntime::StartupContinuation continuation;
    void *context;
};

void runWithContinuation(void *context)
{
    auto &next = *static_cast<ContinuationContext *>(context);
    runSupport(next.support);
    if (!next.support->passed() || next.continuation == nullptr)
        return;
    if (s540NvportRuntimeIsCold() != NV_TRUE ||
        S540NvidiaReserve::ready() || S540NvidiaReserve::liveSlots() != 0) {
        next.support->cleanup = false;
        return;
    }
    next.continuation(next.context);
    if (s540NvportRuntimeIsCold() != NV_TRUE ||
        S540NvidiaReserve::ready() || S540NvidiaReserve::liveSlots() != 0)
        next.support->cleanup = false;
}

} // namespace

S540NvidiaSupportRuntime::IntegratedResult
S540NvidiaSupportRuntime::checkIntegrated()
{
    return checkIntegrated(nullptr, nullptr);
}

S540NvidiaSupportRuntime::IntegratedResult
S540NvidiaSupportRuntime::checkIntegrated(StartupContinuation continuation,
                                       void *context)
{
    IntegratedResult result{};
    // A refused lease or previous lifecycle leaves explicit failed evidence.
    result.support = {1, 1, false, false, false, false};
    ContinuationContext next{&result.support, continuation, context};
    result.v6 = S540NvidiaLifecycleRuntime::checkIntegrated(
        runWithContinuation, &next);
    result.acquired = result.v6.acquired;
    return result;
}
