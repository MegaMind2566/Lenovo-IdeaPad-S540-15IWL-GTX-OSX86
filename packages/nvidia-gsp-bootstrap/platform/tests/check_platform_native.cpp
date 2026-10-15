// SPDX-License-Identifier: MIT
#include "../S540NvidiaGspPlatform.hpp"
#include <cstdio>
#include <vector>

namespace {
NvU32 checks, failures;
void expect(bool value) { ++checks; if (!value) ++failures; }
std::vector<NvU8> chassis(NvU8 type) {
    std::vector<NvU8> bytes(17, 0);
    bytes[0] = 3; bytes[1] = 9; bytes[5] = type;
    bytes[11] = 127; bytes[12] = 4;
    return bytes;
}
void checksum(std::vector<NvU8> &bytes) {
    bytes[9] = 0;
    NvU8 sum = 0;
    for (NvU8 value : bytes) sum = NvU8(sum + value);
    bytes[9] = NvU8(0U - sum);
}
}
int main() {
    using namespace S540NvidiaGspPlatform;
    bool value = false;
    for (NvU8 type : {NvU8(9), NvU8(10), NvU8(0x89), NvU8(0x8a)}) {
        auto bytes = chassis(type);
        value = false;
        expect(decodeChassis(bytes.data(), bytes.size(), value) && value);
    }
    for (NvU8 type : {NvU8(1), NvU8(3), NvU8(7), NvU8(23), NvU8(35)}) {
        auto bytes = chassis(type);
        value = true;
        expect(decodeChassis(bytes.data(), bytes.size(), value) && !value);
    }
    for (NvU8 type : {NvU8(0), NvU8(2), NvU8(0x82)}) {
        auto bytes = chassis(type);
        value = true;
        expect(!decodeChassis(bytes.data(), bytes.size(), value) && value);
    }
    auto bytes = chassis(9);
    for (NvU32 length = 0; length < 11; ++length) {
        value = true;
        expect(!decodeChassis(bytes.data(), length, value) && value);
    }
    bytes[1] = 3;
    expect(!decodeChassis(bytes.data(), bytes.size(), value));
    bytes = chassis(9); bytes[1] = 255;
    expect(!decodeChassis(bytes.data(), bytes.size(), value));
    bytes = chassis(9); bytes[9] = 1; bytes[10] = 2;
    expect(!decodeChassis(bytes.data(), 11, value));
    auto second = chassis(3);
    bytes = chassis(9); bytes.resize(11);
    bytes.insert(bytes.end(), second.begin(), second.end());
    expect(!decodeChassis(bytes.data(), bytes.size(), value));
    bytes = chassis(9); bytes.resize(11);
    second = chassis(10); bytes.insert(bytes.end(), second.begin(), second.end());
    expect(decodeChassis(bytes.data(), bytes.size(), value) && value);
    expect(!decodeChassis(nullptr, 128, value));
    expect(!decodeChassis(bytes.data(), 1024U * 1024U + 1U, value));

    std::vector<NvU8> fadt(116, 0);
    fadt[0] = 'F'; fadt[1] = 'A'; fadt[2] = 'C'; fadt[3] = 'P'; fadt[4] = 116;
    checksum(fadt); value = true;
    expect(decodeFadt(fadt.data(), fadt.size(), value) && !value);
    fadt[114] = 0x20; checksum(fadt); value = false;
    expect(decodeFadt(fadt.data(), fadt.size(), value) && value);
    fadt[9] ^= 1; value = false;
    expect(!decodeFadt(fadt.data(), fadt.size(), value) && !value);
    checksum(fadt); fadt[0] = 'X'; checksum(fadt);
    expect(!decodeFadt(fadt.data(), fadt.size(), value));
    fadt[0] = 'F'; fadt[4] = 117; checksum(fadt);
    expect(!decodeFadt(fadt.data(), fadt.size(), value));
    expect(!decodeFadt(nullptr, 116, value));

    expect(romRequestValid(0, 4096));
    expect(romRequestValid(kMaximumRomBytes - kMaximumRomChunk, kMaximumRomChunk));
    expect(!romRequestValid(0, 0));
    expect(!romRequestValid(0, kMaximumRomChunk + 1));
    expect(!romRequestValid(kMaximumRomBytes, 1));
    expect(!romRequestValid(kMaximumRomBytes - 1, 2));
    expect(!romRequestValid(~NvU32(0), ~NvU32(0)));

    ConsoleOwnership console{};
    expect(!consoleExcludesTarget(console, true));
    observeConsoleOwner(console, true, 0x8086, 0x030000, false);
    expect(consoleExcludesTarget(console, true));
    expect(!consoleExcludesTarget(console, false));
    auto uncertain = console;
    observeConsoleOwner(uncertain, false, 0, 0, false);
    expect(!consoleExcludesTarget(uncertain, true));
    auto targetConsole = console;
    observeConsoleOwner(targetConsole, true, 0x10de, 0x030000, true);
    expect(!consoleExcludesTarget(targetConsole, true));
    auto otherConsole = console;
    observeConsoleOwner(otherConsole, true, 0x1002, 0x030000, false);
    expect(consoleExcludesTarget(otherConsole, true));
    auto wrongClass = console;
    observeConsoleOwner(wrongClass, true, 0x8086, 0x060000, false);
    expect(!consoleExcludesTarget(wrongClass, true));
    ConsoleOwnership onlyOther{};
    observeConsoleOwner(onlyOther, true, 0x1002, 0x030000, false);
    expect(!consoleExcludesTarget(onlyOther, true));
    ConsoleOwnership targetIntel{};
    observeConsoleOwner(targetIntel, true, 0x8086, 0x030000, true);
    expect(!consoleExcludesTarget(targetIntel, true));
    auto overflowConsole = console;
    overflowConsole.frames = ~NvU32(0);
    observeConsoleOwner(overflowConsole, true, 0x8086, 0x030000, false);
    expect(overflowConsole.overflow && !consoleExcludesTarget(overflowConsole, true));
    auto inactiveEnumeration = console;
    expect(!consoleExcludesTarget(inactiveEnumeration, false));
    auto foreignNvidia = console;
    observeConsoleOwner(foreignNvidia, true, 0x10de, 0x030000, false);
    expect(consoleExcludesTarget(foreignNvidia, true));

    // Deterministic malformed-table exploration exercises bounded traversal
    // under the same address/undefined sanitizers as the production decoders.
    NvU32 random = 0x619a0421;
    bool outputPreserved = true;
    for (NvU32 iteration = 0; iteration < 2048; ++iteration) {
        random ^= random << 13; random ^= random >> 17; random ^= random << 5;
        std::vector<NvU8> malformed((random & 255U) + 1U);
        for (auto &byte : malformed) {
            random ^= random << 13; random ^= random >> 17; random ^= random << 5;
            byte = NvU8(random);
        }
        bool before = value;
        if (!decodeChassis(malformed.data(), malformed.size(), value) && value != before)
            outputPreserved = false;
        before = value;
        if (!decodeFadt(malformed.data(), malformed.size(), value) && value != before)
            outputPreserved = false;
    }
    expect(outputPreserved);
    Context context;
    S540NvidiaGlobalRmPlatformFacts facts{};
    expect(context.initialize(nullptr, nullptr) == NV_ERR_NOT_SUPPORTED);
    expect(context.collect(&facts) == NV_ERR_NOT_SUPPORTED && !facts.known);
    expect(!context.active() && context.shutdown() == NV_OK);
    expect(context.bindState(nullptr) == NV_ERR_NOT_SUPPORTED);
    NvU32 segment = 0xfeed;
    expect(context.collectSegment(segment) == NV_ERR_NOT_SUPPORTED && segment == 0xfeed);
    S540GspDeviceFacts device{};
    expect(context.collectDeviceFacts(&device) == NV_ERR_NOT_SUPPORTED && !device.segmentKnown);
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-platform-parsers\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,\"malformed_fixtures\":2048,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"hardware_queried\":false}\n", failures ? "failed" : "passed", checks, failures);
    return failures ? 1 : 0;
}
