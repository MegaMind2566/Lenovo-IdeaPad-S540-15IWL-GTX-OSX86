// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaDma.hpp"
#include <cstdio>

namespace {
unsigned checks = 0;
unsigned failures = 0;
void check(bool condition) {
    ++checks;
    if (!condition)
        ++failures;
}
}

int main()
{
    using namespace S540NvidiaDma;
    auto *provider = reinterpret_cast<IOService *>(1);
    setNativeFault(Fault::None);
    setNativeMapperMode(MapperMode::Provider);
    const Result normal = S540NvidiaDma::check(provider);
    check(normal.passed());
    check(normal.providerMappingVerified);
    check(normal.mapperMode == MapperMode::Provider);
    check(normal.segments == kBytes / kMaxSegmentBytes);
    check(normal.bytes == kBytes && normal.reason == Reason::None);
    check(normal.completion && normal.cleanup);
    check(nativeLiveResources() == 0 && nativeIllegalOperations() == 0);

    setNativeMapperMode(MapperMode::DirectUntranslated);
    const Result direct = S540NvidiaDma::check(provider);
    check(direct.passed());
    check(!direct.providerMappingVerified);
    check(direct.mapperMode == MapperMode::DirectUntranslated);
    check(nativeLiveResources() == 0 && nativeIllegalOperations() == 0);

    setNativeMapperMode(MapperMode::Provider);
    unsigned faultCases = 0;
    unsigned cleanupCases = 0;
    for (NvU32 value = static_cast<NvU32>(Fault::Context);
         value <= static_cast<NvU32>(Fault::BufferComplete); ++value) {
        setNativeFault(static_cast<Fault>(value));
        const Result result = S540NvidiaDma::check(provider);
        ++faultCases;
        check(!result.passed() && result.failures != 0);
        check(!result.providerMappingVerified);
        check(result.reason != Reason::None);
        check(nativeLiveResources() == 0);
        check(nativeIllegalOperations() == 0);
        if (value < static_cast<NvU32>(Fault::CommandComplete))
            check(result.cleanup);
        else {
            check(!result.cleanup);
            ++cleanupCases;
        }
        // The same state machine must recover after each injected fault.
        setNativeFault(Fault::None);
        const Result recovered = S540NvidiaDma::check(provider);
        check(recovered.passed());
        check(nativeLiveResources() == 0 && nativeIllegalOperations() == 0);
    }
    const Result nullProvider = S540NvidiaDma::check(nullptr);
    check(!nullProvider.passed() && !nullProvider.context);
    check(nativeLiveResources() == 0 && nativeIllegalOperations() == 0);
    unsigned lifecycleCycles = 0;
    for (; lifecycleCycles < 64; ++lifecycleCycles) {
        const Result repeated = S540NvidiaDma::check(provider);
        check(repeated.passed() && repeated.cleanup);
        check(nativeLiveResources() == 0 && nativeIllegalOperations() == 0);
    }
    std::printf("{\"format\":1,\"component\":\"nvidia-dma-transport\","
                "\"status\":\"%s\",\"execution\":\"native-user-space\","
                "\"kernel_runtime\":\"not_tested\",\"gpu_access\":false,"
                "\"checks\":%u,\"failures\":%u,\"dma_checks\":%u,"
                "\"dma_failures\":%u,\"fault_cases\":%u,\"cleanup_cases\":%u,"
                "\"lifecycle_cycles\":%u}\n",
                failures ? "failed" : "passed", checks, failures,
                normal.checks, normal.failures,
                faultCases, cleanupCases, lifecycleCycles);
    return failures ? 1 : 0;
}
