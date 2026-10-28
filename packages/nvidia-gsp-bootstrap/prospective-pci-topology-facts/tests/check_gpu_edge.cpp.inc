/* SPDX-License-Identifier: MIT. Actual GPU-edge and topology validation bodies.
 * Only provider arbitration/configuration endpoints are typed CPU resources.
 */
#include <cstdio>
#include <cstdlib>
#ifndef GPU_SNAPSHOT_HEADER
#define GPU_SNAPSHOT_HEADER "S540NvidiaDeviceTransport.hpp"
#endif
#include GPU_SNAPSHOT_HEADER
#include "actual-engine.cpp"
using UInt8 = NvU8;
class IOPCIDevice {
public:
    NvU8 bus = 2U, device = 0U, function = 0U;
    NvU32 identity = 0x1f9110deU, revision = 0x030000a1U, subsystem = 0x380617aaU;
    bool inactive = false, permit = true, failSecond = false, inactiveAtLock = false;
    bool inactiveAtRead = false, locked = false, protocol = true;
    NvU32 locks = 0U, unlocks = 0U, reads = 0U;
    bool isInactive() const { return inactive; }
    bool lockForArbitration(bool wait) {
        ++locks;
        if (wait || locked) protocol = false;
        if (!permit || (failSecond && locks == 2U)) return false;
        locked = true;
        if (inactiveAtLock) inactive = true;
        return true;
    }
    void unlockForArbitration() {
        if (!locked) protocol = false;
        locked = false; ++unlocks;
    }
    NvU8 getBusNumber() { if (!locked) protocol = false; return bus; }
    NvU8 getDeviceNumber() { if (!locked) protocol = false; return device; }
    NvU8 getFunctionNumber() { if (!locked) protocol = false; return function; }
    NvU32 configRead32(UInt8 offset) {
        if (!locked) protocol = false;
        ++reads;
        if (inactiveAtRead) inactive = true;
        if (offset == 0U) return identity;
        if (offset == 8U) return revision;
        if (offset == 0x2cU) return subsystem;
        protocol = false; return ~0U;
    }
};
namespace S540NvidiaDeviceTransport {
NV_STATUS validateDarwinTopology(void *, const void *, const Snapshot &, const S540PciTopologyGspFacts &);
}
namespace {
using namespace S540NvidiaDeviceTransport;
using namespace S540NvidiaPciTopology;
struct Platform {
    IOPCIDevice *provider;
    bool retained, opened, ordinaryContext;
    State topology;
};
bool ordinary(void *opaque) { return static_cast<Platform *>(opaque)->ordinaryContext; }
bool live(void *opaque) {
    auto *p = static_cast<Platform *>(opaque);
    return p->retained && p->opened && p->provider && !p->provider->isInactive();
}
}
#include "actual-gpu-edge.inc"
namespace {
IOPCIDevice gpu;
Platform platform{};
Snapshot snapshot{};
struct Device { NvU32 config[7]; } bridge, host;
int owner, foreign;
NvU32 engineCalls, cases, checks, failures;
int effect;
bool failReader;
void expect(bool value, int line) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "GPU-edge CPU control line %d case %u\n", line, cases); }
}
#define EXPECT(v) expect(bool(v), __LINE__)
NV_STATUS endpoint(void *, const Candidate &candidate, NvU32 offset, NvU32 width, NvU32 &out) {
    ++engineCalls;
    if (effect) {
        const int selected = effect; effect = 0;
        if (selected == 1) gpu.identity ^= 1U;
        else if (selected == 2) gpu.revision ^= 1U;
        else if (selected == 3) gpu.subsystem ^= 1U;
        else if (selected == 4) ++gpu.bus;
        else if (selected == 5) ++gpu.device;
        else if (selected == 6) ++gpu.function;
        else if (selected == 7) gpu.inactive = true;
    }
    if (failReader) return NV_ERR_TIMEOUT;
    if (width != 4U || offset > 24U || (offset & 3U)) return NV_ERR_INVALID_ARGUMENT;
    out = static_cast<Device *>(candidate.resource)->config[offset / 4U];
    return NV_OK;
}
S540PciTopologyReference reference(NvU32 row) {
    const auto &r = platform.topology.records[row];
    return S540PciTopologyReference{r.handle, r.candidate.segment, r.candidate.bus,
        r.candidate.device, r.candidate.function, 0U, NvU16(r.identity), NvU16(r.identity >> 16U)};
}
S540PciTopologyGspFacts facts() {
    return S540PciTopologyGspFacts{1U, sizeof(S540PciTopologyGspFacts), reference(1U), reference(1U), reference(0U)};
}
void fixture() {
    ++cases;
    gpu = IOPCIDevice{}; platform = Platform{};
    platform.provider = &gpu; platform.retained = true; platform.opened = true; platform.ordinaryContext = true;
    snapshot = Snapshot{}; snapshot.segmentKnown = true; snapshot.bus = 2U;
    bridge = Device{}; host = Device{};
    bridge.config[0] = 0x9d108086U; bridge.config[2] = 0x060400a1U;
    bridge.config[3] = 0x00010000U; bridge.config[6] = 0x00020200U;
    host.config[0] = 0x3e348086U; host.config[2] = 0x0600000aU;
    const Candidate candidates[] = {{&bridge, 0U, 0U, 1U, 0U, false}, {&host, 0U, 0U, 0U, 0U, true}};
    effect = 0; failReader = false;
    EXPECT(prepare(platform.topology, &owner, 0U, 2U, Reader{&owner, endpoint}, candidates, 2U) == NV_OK);
    engineCalls = 0U;
}
NV_STATUS validateNow() { return validateDarwinTopology(&platform, &owner, snapshot, facts()); }
void balanced() { EXPECT(gpu.protocol && !gpu.locked); }
void preRefused(NV_STATUS wanted, NvU32 lockAttempts, NvU32 unlocks, NvU32 reads) {
    EXPECT(validateNow() == wanted);
    EXPECT(engineCalls == 0U);
    EXPECT(gpu.locks == lockAttempts && gpu.unlocks == unlocks && gpu.reads == reads);
    balanced();
}
}
int main() {
    fixture();
    EXPECT(validateNow() == NV_OK);
    EXPECT(engineCalls != 0U && gpu.locks == 2U && gpu.unlocks == 2U && gpu.reads == 6U);
    balanced();
    fixture(); gpu.identity ^= 1U; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 3U);
    fixture(); gpu.revision ^= 1U; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 3U);
    fixture(); gpu.subsystem ^= 1U; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 3U);
    fixture(); ++gpu.bus; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 0U);
    fixture(); ++gpu.device; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 0U);
    fixture(); ++gpu.function; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 0U);
    fixture(); gpu.permit = false; preRefused(NV_ERR_BUSY_RETRY, 1U, 0U, 0U);
    fixture(); gpu.inactive = true; preRefused(NV_ERR_INVALID_STATE, 0U, 0U, 0U);
    fixture(); platform.retained = false; preRefused(NV_ERR_INVALID_STATE, 0U, 0U, 0U);
    fixture(); platform.opened = false; preRefused(NV_ERR_INVALID_STATE, 0U, 0U, 0U);
    fixture(); platform.ordinaryContext = false; preRefused(NV_ERR_INVALID_STATE, 0U, 0U, 0U);
    fixture(); platform.provider = nullptr; preRefused(NV_ERR_INVALID_STATE, 0U, 0U, 0U);
    fixture(); snapshot.segmentKnown = false; preRefused(NV_ERR_INVALID_STATE, 0U, 0U, 0U);
    for (int change = 1; change != 7; ++change) {
        fixture(); effect = change;
        EXPECT(validateNow() == NV_ERR_INVALID_STATE);
        EXPECT(engineCalls != 0U && effect == 0 && gpu.locks == 2U && gpu.unlocks == 2U);
        EXPECT(gpu.reads == (change <= 3 ? 6U : 3U));
        balanced();
    }
    fixture(); effect = 7;
    EXPECT(validateNow() == NV_ERR_INVALID_STATE);
    EXPECT(engineCalls != 0U && gpu.locks == 1U && gpu.unlocks == 1U && gpu.reads == 3U);
    balanced();
    fixture(); gpu.failSecond = true;
    EXPECT(validateNow() == NV_ERR_BUSY_RETRY);
    EXPECT(engineCalls != 0U && gpu.locks == 2U && gpu.unlocks == 1U && gpu.reads == 3U);
    balanced();
    fixture(); effect = 1; failReader = true;
    EXPECT(validateNow() == NV_ERR_TIMEOUT);
    EXPECT(engineCalls == 1U && gpu.locks == 1U && gpu.unlocks == 1U && gpu.reads == 3U);
    balanced();
    fixture(); gpu.inactiveAtLock = true; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 0U);
    fixture(); gpu.inactiveAtRead = true; preRefused(NV_ERR_INVALID_STATE, 1U, 1U, 3U);
    fixture();
    EXPECT(validateDarwinTopology(&platform, &foreign, snapshot, facts()) == NV_ERR_NOT_READY);
    EXPECT(engineCalls == 0U && gpu.locks == 1U && gpu.unlocks == 1U && gpu.reads == 3U);
    balanced();
    if (failures) return 1;
    std::printf("{\"cases\":%u,\"checks\":%u}\n", cases, checks);
    return 0;
}
