/* SPDX-License-Identifier: MIT. Actual fixed-table engine, typed PCI reads. */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include "actual-engine.cpp"
using namespace S540NvidiaPciTopology;
namespace {
struct Device { NvU32 configuration[1024]; } devices[10];
Candidate candidates[9];
State state{};
int owner, foreign;
NvU32 calls, checks, failures, failOffset = ~0U;
NV_STATUS readFailure = NV_ERR_TIMEOUT;
bool removeAfterData;
void expect(bool value, int line) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "Topology CPU control line %d\n", line); }
}
#define EXPECT(v) expect(bool(v), __LINE__)
NV_STATUS endpoint(void *, const Candidate &candidate, NvU32 offset, NvU32 width, NvU32 &out) {
    ++calls;
    if (offset == failOffset) return readFailure;
    if ((width != 1U && width != 2U && width != 4U) || offset >= 4096U || width > 4096U - offset)
        return NV_ERR_INVALID_ARGUMENT;
    auto *resource = static_cast<Device *>(candidate.resource);
    const NvU32 value = resource->configuration[offset / 4U] >> ((offset & 3U) * 8U);
    out = width == 1U ? value & 0xffU : width == 2U ? value & 0xffffU : value;
    if (removeAfterData && offset == 0x80U) resource->configuration[0] = ~0U;
    return NV_OK;
}
Reader reader() { return Reader{&owner, endpoint}; }
void fixture(NvU32 bridges = 1U) {
    for (auto &device : devices) device = Device{};
    for (auto &candidate : candidates) candidate = Candidate{};
    const NvU8 gpuBus = NvU8(bridges + 1U);
    for (NvU32 i = 0U; i != bridges; ++i) {
        const NvU8 primary = NvU8(bridges - i - 1U);
        const NvU8 secondary = i ? NvU8(primary + 1U) : gpuBus;
        devices[i].configuration[0] = 0x9d108086U + (i << 16U);
        devices[i].configuration[2] = 0x060400a1U;
        devices[i].configuration[3] = 0x00010000U;
        devices[i].configuration[6] = primary | (NvU32(secondary) << 8U) | (NvU32(gpuBus) << 16U);
        devices[i].configuration[32] = 0x12345678U;
        devices[i].configuration[1023] = 0x87654321U;
        candidates[i] = Candidate{&devices[i], 0U, primary, NvU8(i + 1U), 0U, false};
    }
    devices[bridges].configuration[0] = 0x3e348086U;
    devices[bridges].configuration[2] = 0x0600000aU;
    devices[bridges].configuration[3] = 0U;
    devices[bridges].configuration[63] = 0xab123456U;
    candidates[bridges] = Candidate{&devices[bridges], 0U, 0U, 0U, 0U, true};
}
NvU8 gpuBus(NvU32 bridges = 1U) { return NvU8(bridges + 1U); }
void initialize(NvU32 bridges = 1U) {
    EXPECT(prepare(state, &owner, 0U, gpuBus(bridges), reader(), candidates, bridges + 1U) == NV_OK);
    EXPECT(ready(state, &owner));
}
S540PciTopologyReference reference(NvU32 index) {
    const auto &record = state.records[index];
    return S540PciTopologyReference{record.handle, record.candidate.segment,
        record.candidate.bus, record.candidate.device, record.candidate.function, 0U,
        NvU16(record.identity), NvU16(record.identity >> 16U)};
}
S540PciTopologyGspFacts facts() {
    return S540PciTopologyGspFacts{1U, sizeof(S540PciTopologyGspFacts),
        reference(state.count - 1U), reference(state.count - 1U), reference(0U)};
}
void invalidPrepare(NV_STATUS wanted, NvU32 bridges = 1U, NvU32 segment = 0U) {
    EXPECT(prepare(state, &owner, segment, gpuBus(bridges), reader(), candidates, bridges + 1U) == wanted);
    EXPECT(!state.owner && !state.prepared && !state.count && !state.generation);
}
void errorRead(void *handle, NvU32 offset, NvU32 width, NV_STATUS wanted) {
    NvU32 value = 0x5a5a5a5aU;
    EXPECT(read(state, &owner, handle, offset, width, value) == wanted);
    EXPECT(value == 0x5a5a5a5aU);
}
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const int scenario = std::atoi(argv[1]);
    fixture();
    if (scenario == 0) {
        initialize();
        NvU16 vendor = 0U, device = 0U;
        EXPECT(find(state, &owner, 0U, 0U, 1U, 0U, &vendor, &device) == state.records[0].handle);
        EXPECT(vendor == 0x8086U && device == 0x9d10U);
        EXPECT(validate(state, &owner, facts()) == NV_OK);
        NvU32 value = 0U;
        EXPECT(read(state, &owner, state.records[0].handle, 0x80U, 4U, value) == NV_OK && value == 0x12345678U);
    } else if (scenario == 1) {
        fixture(8U); initialize(8U);
        EXPECT(state.count == 9U && validate(state, &owner, facts()) == NV_OK);
        for (NvU32 i = 0U; i != state.count; ++i)
            EXPECT(find(state, &owner, 0U, candidates[i].bus, candidates[i].device,
                candidates[i].function, nullptr, nullptr) == state.records[i].handle);
    } else if (scenario == 2) {
        initialize(); const NvU32 before = calls;
        NvU16 vendor = 0xaaaaU, device = 0xbbbbU;
        EXPECT(!find(state, &foreign, 0U, 0U, 1U, 0U, &vendor, &device));
        NvU32 value = 0xabcdefU;
        EXPECT(read(state, &foreign, state.records[0].handle, 0U, 4U, value) == NV_ERR_INVALID_STATE);
        EXPECT(validate(state, &foreign, facts()) == NV_ERR_NOT_READY);
        EXPECT(calls == before && value == 0xabcdefU && vendor == 0xaaaaU && device == 0xbbbbU);
    } else if (scenario == 3) {
        initialize(); const NvU32 before = calls;
        NvU16 vendor = 0xaaaaU, device = 0xbbbbU;
        bool denied = true;
        for (NvU32 bus = 0U; bus != 256U; ++bus)
            for (NvU32 slot = 0U; slot != 32U; ++slot)
                for (NvU32 function = 0U; function != 8U; ++function) {
                    if (!bus && !function && slot < 2U) continue;
                    if (find(state, &owner, 0U, NvU8(bus), NvU8(slot), NvU8(function), &vendor, &device))
                        denied = false;
                }
        EXPECT(denied);
        EXPECT(calls == before && vendor == 0xaaaaU && device == 0xbbbbU);
    } else if (scenario == 4) {
        initialize(); State second{};
        EXPECT(prepare(second, &foreign, 0U, gpuBus(), reader(), candidates, 2U) == NV_OK);
        EXPECT(second.records[0].handle != state.records[0].handle);
        const NvU32 before = calls; NvU32 value = 42U;
        EXPECT(read(second, &foreign, state.records[0].handle, 0U, 4U, value) == NV_ERR_OBJECT_NOT_FOUND);
        EXPECT(calls == before && value == 42U);
        errorRead(reinterpret_cast<void *>(NvUPtr(12345U)), 0U, 4U, NV_ERR_OBJECT_NOT_FOUND);
    } else if (scenario == 5) {
        devices[0].configuration[2] = 0x060000a1U; invalidPrepare(NV_ERR_NOT_SUPPORTED);
    } else if (scenario == 6) {
        devices[1].configuration[0] = 0x12341234U; invalidPrepare(NV_ERR_NOT_SUPPORTED);
    } else if (scenario == 7) {
        devices[0].configuration[3] = 0U; invalidPrepare(NV_ERR_NOT_SUPPORTED);
    } else if (scenario == 8) {
        devices[1].configuration[3] = 0x00010000U; invalidPrepare(NV_ERR_NOT_SUPPORTED);
    } else if (scenario == 9) {
        devices[0].configuration[6] |= 1U; invalidPrepare(NV_ERR_INVALID_DATA);
    } else if (scenario == 10) {
        devices[0].configuration[6] = 0x00010200U; invalidPrepare(NV_ERR_INVALID_DATA);
    } else if (scenario == 11) {
        devices[0].configuration[6] = 0x00020100U; invalidPrepare(NV_ERR_INVALID_DATA);
    } else if (scenario == 12) {
        fixture(2U); devices[1].configuration[6] = 0x00030200U; invalidPrepare(NV_ERR_INVALID_DATA, 2U);
    } else if (scenario == 13) {
        candidates[1].rootConfig = false; candidates[1].bus = 1U; invalidPrepare(NV_ERR_INVALID_DATA);
    } else if (scenario == 14) {
        candidates[0].segment = candidates[1].segment = 1U; invalidPrepare(NV_ERR_INVALID_ARGUMENT, 1U, 1U);
    } else if (scenario == 15) {
        candidates[0].segment = 1U; invalidPrepare(NV_ERR_INVALID_ARGUMENT);
    } else if (scenario == 16) {
        candidates[1].rootConfig = false; candidates[1].bus = candidates[0].bus;
        candidates[1].device = candidates[0].device; invalidPrepare(NV_ERR_INVALID_DATA);
    } else if (scenario == 17) {
        for (NvU32 count : {0U, 1U, 10U}) {
            EXPECT(prepare(state, &owner, 0U, gpuBus(), reader(), candidates, count) == NV_ERR_INVALID_ARGUMENT);
            EXPECT(!state.owner);
        }
    } else if (scenario == 18) {
        initialize(); const NvU32 before = calls;
        errorRead(state.records[0].handle, 0U, 0U, NV_ERR_INVALID_ARGUMENT);
        errorRead(state.records[0].handle, 4096U, 4U, NV_ERR_INVALID_ARGUMENT);
        errorRead(state.records[0].handle, 3U, 2U, NV_ERR_INVALID_ARGUMENT);
        EXPECT(calls == before);
    } else if (scenario == 19) {
        initialize(); NvU32 value = 0U;
        EXPECT(read(state, &owner, state.records[1].handle, 255U, 1U, value) == NV_OK && value == 0xabU);
        const NvU32 before = calls; errorRead(state.records[1].handle, 256U, 4U, NV_ERR_NOT_SUPPORTED);
        EXPECT(calls == before);
        EXPECT(read(state, &owner, state.records[0].handle, 4092U, 4U, value) == NV_OK && value == 0x87654321U);
    } else if (scenario == 20) {
        initialize(); failOffset = 0U;
        NvU16 vendor = 0xaaaaU, device = 0xbbbbU;
        EXPECT(!find(state, &owner, 0U, 0U, 1U, 0U, &vendor, &device));
        EXPECT(vendor == 0xaaaaU && device == 0xbbbbU);
        errorRead(state.records[0].handle, 0x80U, 4U, NV_ERR_TIMEOUT);
    } else if (scenario == 21) {
        initialize(); devices[0].configuration[0] = ~0U;
        EXPECT(!find(state, &owner, 0U, 0U, 1U, 0U, nullptr, nullptr));
        errorRead(state.records[0].handle, 0x80U, 4U, NV_ERR_INVALID_DATA);
    } else if (scenario == 22) {
        initialize(); devices[0].configuration[2] ^= 1U;
        errorRead(state.records[0].handle, 0x80U, 4U, NV_ERR_INVALID_STATE);
    } else if (scenario == 23) {
        initialize(); devices[0].configuration[6] ^= 1U << 16U;
        errorRead(state.records[0].handle, 0x80U, 4U, NV_ERR_INVALID_STATE);
    } else if (scenario == 24) {
        initialize(); failOffset = 0x80U;
        errorRead(state.records[0].handle, 0x80U, 4U, NV_ERR_TIMEOUT);
    } else if (scenario == 25) {
        initialize(); removeAfterData = true;
        errorRead(state.records[0].handle, 0x80U, 4U, NV_ERR_INVALID_DATA);
    } else if (scenario == 26) {
        initialize(); auto sample = facts();
        sample.format = 2U; EXPECT(validate(state, &owner, sample) == NV_ERR_INVALID_ARGUMENT);
        sample = facts(); sample.fhb.handle = sample.upstream.handle;
        EXPECT(validate(state, &owner, sample) == NV_ERR_INVALID_DATA);
        sample = facts(); sample.upstream.device ^= 1U;
        EXPECT(validate(state, &owner, sample) == NV_ERR_INVALID_DATA);
        sample = facts(); sample.chipset.vendor ^= 1U;
        EXPECT(validate(state, &owner, sample) == NV_ERR_INVALID_DATA);
        sample = facts(); sample.chipset = sample.upstream;
        EXPECT(validate(state, &owner, sample) == NV_OK);
        sample = facts(); sample.fhb.reserved = 1U;
        EXPECT(validate(state, &owner, sample) == NV_ERR_INVALID_DATA);
    } else if (scenario == 27) {
        initialize(); const void *previous = state.records[0].handle;
        clear(state); EXPECT(!ready(state, &owner)); initialize();
        EXPECT(state.records[0].handle != previous);
    } else if (scenario == 28) {
        initialize();
        EXPECT(find(state, &owner, 0U, 0U, 1U, 0U, nullptr, nullptr) == state.records[0].handle);
        EXPECT(find(state, &owner, 0U, 0U, 0U, 0U, nullptr, nullptr) == state.records[1].handle);
    } else if (scenario == 29) {
        candidates[1].resource = candidates[0].resource;
        candidates[1].rootConfig = false; invalidPrepare(NV_ERR_INVALID_DATA);
    } else if (scenario == 30) {
        const NvU32 before = calls;
        EXPECT(prepare(state, nullptr, 0U, gpuBus(), reader(), candidates, 2U) == NV_ERR_INVALID_ARGUMENT);
        EXPECT(prepare(state, &owner, 0U, gpuBus(), Reader{}, candidates, 2U) == NV_ERR_INVALID_ARGUMENT);
        EXPECT(calls == before && !state.owner);
    } else if (scenario == 31) {
        devices[1].configuration[0] = 0xdead8086U; initialize();
        EXPECT(validate(state, &owner, facts()) == NV_OK);
    } else if (scenario == 32) {
        devices[1].configuration[0] = 0xffff8086U; invalidPrepare(NV_ERR_INVALID_DATA);
    } else return 2;
    std::printf("{\"cases\":1,\"checks\":%u,\"failures\":%u}\n", checks, failures);
    return failures ? 1 : 0;
}
