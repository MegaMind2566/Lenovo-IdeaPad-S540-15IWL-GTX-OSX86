// SPDX-License-Identifier: MIT
// Real Session, Store, GspContext, timers and tracked host. Only Darwin's
// provider/platform observations are explicit CPU fixtures. Original RM entry
// bodies are typed abort tripwires in check_bootstrap_boundary_native.c.
#include "../src/S540NvidiaGspBootstrap.hpp"
#include "../src/S540NvidiaGspFirmwareBridge.h"
#include "../platform/S540NvidiaGspPlatform.hpp"
#include "../timers/S540NvidiaGspTimers.h"
#include "../../nvidia-device-transport/src/nv_device_services.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <thread>
#include <vector>

class IOPCIDevice {};
namespace {
using namespace S540NvidiaDeviceTransport;
unsigned checks;
nv_state_t *fixtureState;
bool fixturePlatformStopFailure;
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { std::fprintf(stderr, "Bootstrap check failed: %s\n", reason); std::exit(1); }
}
bool readImage(const char *path, std::vector<NvU8> &out) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file) return false;
    const auto size = file.tellg();
    if (size <= 0 || size > 128 * 1024 * 1024) return false;
    out.resize(static_cast<size_t>(size)); file.seekg(0);
    return bool(file.read(reinterpret_cast<char *>(out.data()), size));
}
struct ResourceFixture { bool active = false, failStop = false, policyAvailable = true; };
bool ordinary(void *) { return true; }
NV_STATUS start(void *opaque, Snapshot &out) {
    auto &f = *static_cast<ResourceFixture *>(opaque);
    f.active = true;
    out = Snapshot{};
    out.identity = out.providerOwned = out.memoryDecode = out.powerD0 = out.barMapped = true;
    out.mapper = Mapper::Device; out.dmaAddressBits = 64; out.barBytes = 0x1000000;
    out.segmentKnown = true; out.bus = 1; out.dmaPolicySettled = true;
    return NV_OK;
}
NV_STATUS stop(void *opaque) {
    auto &f = *static_cast<ResourceFixture *>(opaque);
    if (f.failStop) return NV_ERR_BUSY_RETRY;
    f.active = false; return NV_OK;
}
bool live(void *opaque) { return static_cast<ResourceFixture *>(opaque)->active; }
NV_STATUS identification(void *, NvU32, NvU32 &) { std::abort(); }
NV_STATUS allocate(void *, NvU32, bool, NvU32, void **, NvU8 **) { std::abort(); }
NV_STATUS page(void *, void *, NvU32, bool, NvU64 &) { std::abort(); }
NV_STATUS map(void *, void *, NvU32) { std::abort(); }
NV_STATUS allocationOperation(void *, void *) { std::abort(); }
NV_STATUS install(void *, const InterruptContract &) { std::abort(); }
NV_STATUS irq(void *) { std::abort(); }
NV_STATUS configRead(void *, NvU32, NvU32, NvU32 &) { std::abort(); }
NV_STATUS configWrite(void *, NvU32, NvU32, NvU32) { std::abort(); }
NV_STATUS policy(void *opaque, DmaRemapPolicy &out) {
    if (!static_cast<ResourceFixture *>(opaque)->policyAvailable) return NV_ERR_NOT_SUPPORTED;
    out = DmaRemapPolicy::MapPhysicalPagesWithoutBounce; return NV_OK;
}
Detail::Backend backend(ResourceFixture &fixture) {
    return Detail::Backend{&fixture, ordinary, start, stop, live, identification,
        allocate, page, map, allocationOperation, allocationOperation, install,
        irq, irq, nullptr, nullptr, nullptr, configRead, configWrite, nullptr, policy};
}
S540GspDeviceFacts deviceFacts() {
    S540GspDeviceFacts f{};
    f.format = 1; f.vendor = 0x10de; f.device = 0x1f91;
    f.subsystemVendor = 0x17aa; f.subsystemDevice = 0x3806;
    f.bus = 1; f.configuration[0] = 0x1f9110de; f.configuration[11] = 0x380617aa;
    f.segmentKnown = f.pciConfigurationRead = f.barsVerified = f.poweredD0 = NV_TRUE;
    f.intelConsoleVerified = f.nvidiaConsoleExcluded = f.noCoherentGpuMemoryProfile = NV_TRUE;
    for (NvU32 i = 0; i != 3; ++i) {
        f.bars[i].physical = 0x1000000ULL * (i + 1);
        f.bars[i].bytes = 0x100000; f.bars[i].offset = 0x10 + i * 8;
    }
    return f;
}
void expectCold() {
    S540NvidiaGlobalRmHostSnapshot host{}; s540GlobalRmHostSnapshot(&host);
    S540GspTimersSnapshot timers{}; s540GspTimersGetSnapshot(&timers);
    expect(!host.initialized && !host.liveBytes && !host.liveAllocations &&
        !host.invalidFrees && !host.unavailableCalls, "real tracked host cold");
    expect(!timers.bound && !s540DarwinLiveObjects() &&
        !abiStatistics().bound && !fixtureState, "all callback owners detached");
}
}

// Explicit native platform fixture. This is not linked with the real Darwin
// Platform implementation and supplies no evidence about an actual provider.
struct S540NvidiaGspPlatform::Context::Impl {
    char osVersion[96], osDate[96];
};
S540NvidiaGspPlatform::Context::Context() : impl_(nullptr) {}
S540NvidiaGspPlatform::Context::~Context() { expect(!impl_, "platform member destroyed only cold"); }
bool S540NvidiaGspPlatform::Context::active() const { return impl_ != nullptr; }
NV_STATUS S540NvidiaGspPlatform::Context::initialize(IOPCIDevice *provider, nv_state_t *state) {
    if (!provider || impl_ || state || fixtureState) return NV_ERR_INVALID_STATE;
    impl_ = new Impl{};
    std::strcpy(impl_->osVersion, "native-bootstrap-platform-fixture");
    std::strcpy(impl_->osDate, "native-bootstrap-platform-fixture");
    return NV_OK;
}
NV_STATUS S540NvidiaGspPlatform::Context::collect(S540NvidiaGlobalRmPlatformFacts *out) {
    if (!impl_ || !out) return NV_ERR_INVALID_STATE;
    *out = S540NvidiaGlobalRmPlatformFacts{};
    out->format = 1; out->known = S540_GLOBAL_FACT_ALL;
    out->cpuCount = 1; out->cpuFrequencyHz = 2000000000ULL; out->osMajor = 25;
    out->osVersion = impl_->osVersion; out->osDate = impl_->osDate;
    return NV_OK;
}
NV_STATUS S540NvidiaGspPlatform::Context::collectDeviceFacts(S540GspDeviceFacts *out, void *handle) {
    if (!impl_ || !out) return NV_ERR_INVALID_STATE;
    *out = deviceFacts(); out->pciHandle = handle; return NV_OK;
}
NV_STATUS S540NvidiaGspPlatform::Context::bindState(nv_state_t *state) {
    if (!impl_ || !state || fixtureState) return NV_ERR_INVALID_STATE;
    fixtureState = state; return NV_OK;
}
NV_STATUS S540NvidiaGspPlatform::Context::shutdown() {
    if (fixturePlatformStopFailure) return NV_ERR_BUSY_RETRY;
    delete impl_; impl_ = nullptr; fixtureState = nullptr; return NV_OK;
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::vector<NvU8> gsp, ucodes;
    if (!readImage(argv[1], gsp) || !readImage(argv[2], ucodes)) return 2;
    const S540NvidiaGspBootstrap::Images images{gsp.data(), gsp.size(), ucodes.data(), ucodes.size()};
    IOPCIDevice provider;
    {
        S540NvidiaGspBootstrap::Owner owner;
        expect(owner.initialize() == NV_ERR_INVALID_STATE && owner.stop() == NV_OK,
            "cold initialization refuses without owning anything");
        ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK,
            "real Session/Context/firmware/timer bindings prepared");
        auto state = owner.snapshot();
        expect(state.prepared && state.hostInitialized && state.platformBound &&
            state.transportBound && state.firmwareBound && state.timersBound &&
            state.firmwareCopied && state.dmaPolicyAdmitted && state.nativeFixture,
            "preparation evidence distinguishes fixture and actual owned bindings");
        expect(!state.globalInitialized && !state.adapterInitialized && !state.firmwareLoaded &&
            !state.interruptInstalled && !state.interruptArmed,
            "no original entry or IRQ activation during preparation");
        expect(owner.initialize() == NV_ERR_NOT_SUPPORTED, "unresolved gates refuse before original entry");
        state = owner.snapshot();
        expect(state.initializationRefused && state.prepared && state.blockedGates == 15,
            "refusal retains reviewable prepared resources and all unresolved gates");
        NV_STATUS foreign = NV_OK;
        std::thread wrong([&] { foreign = owner.stop(); }); wrong.join();
        expect(foreign == NV_ERR_INVALID_STATE && owner.snapshot().ownsResources,
            "wrong-thread stop preserves every owner");
        expect(owner.stop() == NV_OK && !fixture.active && owner.snapshot().cleanupComplete,
            "normal ordered cleanup");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "lease case prepared");
        const void *bytes = nullptr; NvU32 length = 0;
        const void *lease = s540GspFirmwareAcquire(fixtureState, 0, 2, &bytes, &length);
        expect(lease && bytes && bytes != gsp.data() && length == gsp.size() &&
            static_cast<const NvU8 *>(bytes)[0] == gsp[0], "Store delivers an owned immutable copy");
        expect(owner.stop() == NV_ERR_IN_USE, "live firmware lease blocks destruction");
        auto state = owner.snapshot();
        expect(state.ownsResources && state.quarantined && fixture.active &&
            state.firmwareBound && state.transportBound && state.platformBound &&
            !state.timersBound && fixtureState, "partial detach retains original state and all implicated owners");
        s540GspFirmwareRelease(lease);
        expect(owner.stop() == NV_OK && !fixture.active, "lease release permits idempotent cleanup retry");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "platform refusal case prepared");
        fixturePlatformStopFailure = true;
        expect(owner.stop() == NV_ERR_BUSY_RETRY && owner.snapshot().ownsResources && fixtureState,
            "platform unbind refusal pins context until successful retry");
        fixturePlatformStopFailure = false;
        expect(owner.stop() == NV_OK, "platform detach retry releases retained context");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "transport refusal case prepared");
        fixture.failStop = true;
        expect(owner.stop() == NV_ERR_BUSY_RETRY && owner.snapshot().ownsResources && fixture.active,
            "failed transport stop retains heap Session and host image owners");
        S540NvidiaGlobalRmHostSnapshot host{}; s540GlobalRmHostSnapshot(&host);
        expect(host.initialized && host.liveAllocations == 2 && host.liveBytes == gsp.size() + ucodes.size(),
            "owned firmware memory retained until transport quiesces");
        const auto *facts = s540GlobalRmPlatformFacts();
        expect(facts && !std::strcmp(facts->osVersion, "native-bootstrap-platform-fixture") &&
            !std::strcmp(facts->osDate, "native-bootstrap-platform-fixture"),
            "host text remains owned after platform detach and failed transport stop");
        fixture.failStop = false;
        expect(owner.stop() == NV_OK, "transport stop retry releases all owners");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        fixture.policyAvailable = false;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_ERR_NOT_SUPPORTED,
            "unknown DMA policy refuses before device ABI binding");
        expect(!owner.snapshot().ownsResources && owner.snapshot().cleanupComplete,
            "preparation refusal cleans only resources actually acquired");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        S540NvidiaGlobalRmNative::failAllocationAt(2);
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_ERR_NO_MEMORY,
            "tracked allocator admission failure refuses before firmware copy");
        expect(!owner.snapshot().firmwareCopied && !owner.snapshot().ownsResources,
            "failed image capacity admission fully cleans prepared bindings");
        expectCold();
    }
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-bootstrap-owner\",\"status\":\"passed\","
        "\"checks\":%u,\"failures\":0,\"preparation_verified\":true,\"cleanup_retry_verified\":true,"
        "\"platform_fixture\":true,\"original_entry_tripwires\":true,\"real_context_store_transport_timers\":true,"
        "\"original_rm_executed\":false,\"firmware_loaded\":false,\"gpu_initialized\":false,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
}
