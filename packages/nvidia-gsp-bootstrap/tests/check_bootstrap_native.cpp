// SPDX-License-Identifier: MIT
// Real Session, Store, GspContext, timers and tracked host. Only Darwin's
// provider/platform observations are explicit CPU fixtures. Original RM entry
// bodies are typed abort tripwires in check_bootstrap_boundary_native.c.
#include "../src/S540NvidiaGspBootstrap.hpp"
#include "../src/S540NvidiaGspDispatcher.hpp"
#include "../src/S540NvidiaGspFirmwareBridge.h"
#include "../platform/S540NvidiaGspPlatform.hpp"
#include "../platform/S540NvidiaGspPower.hpp"
#include "../timers/S540NvidiaGspTimers.h"
#include "../../nvidia-device-transport/src/nv_device_services.h"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#include <cstdio>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
#include <thread>
#include <vector>

class IOPCIDevice {};
namespace {
using namespace S540NvidiaDeviceTransport;
unsigned checks;
nv_state_t *fixtureState;
bool fixturePlatformStopFailure;
bool fixturePlatformUnbindFailure;
S540NvidiaGspBootstrap::Owner *fixtureEarlyPowerRevocation;
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
        irq, irq, nullptr, nullptr, nullptr, configRead, configWrite, nullptr, policy, nullptr};
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
struct FirmwareLeaseFixture { const void *handle = nullptr, *bytes = nullptr; NvU32 length = 0; };
NV_STATUS acquireFirmware(void *opaque, void *state) {
    auto &lease = *static_cast<FirmwareLeaseFixture *>(opaque);
    lease.handle = s540GspFirmwareAcquire(state, 0, 2, &lease.bytes, &lease.length);
    return lease.handle ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);
}
NV_STATUS releaseFirmware(void *opaque, void *) {
    s540GspFirmwareRelease(static_cast<FirmwareLeaseFixture *>(opaque)->handle);
    return NV_OK;
}
NV_STATUS inspect(void *, void *) { return NV_OK; }
NV_STATUS allocateHostBorrower(void *opaque, void *) {
    *static_cast<void **>(opaque) = s540GlobalRmHostAllocate(64);
    return *static_cast<void **>(opaque) ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NO_MEMORY);
}
NV_STATUS releaseHostBorrower(void *opaque, void *) {
    s540GlobalRmHostFree(*static_cast<void **>(opaque)); return NV_OK;
}
// Exercise the actual lease/worker lifetime, rather than a simulated PMstop
// barrier: an external hook remains inside its owner after enqueuing shutdown.
// Even after the worker acknowledges, it must retain that owner until return.
struct PowerHookFixture {
    S540NvidiaGspBootstrap::Dispatcher dispatcher;
    S540NvidiaGspPower::Lease lease;
    std::mutex guard;
    std::condition_variable changed;
    bool entered = false, stopAttempted = false, release = false;
    NV_STATUS postStatus = NV_ERR_NOT_READY, ackStatus = NV_ERR_NOT_READY;
    NV_STATUS stopStatus = NV_ERR_NOT_READY;
    static NV_STATUS request(void *opaque) {
        auto &self = *static_cast<PowerHookFixture *>(opaque);
        const NV_STATUS status = self.dispatcher.post(2);
        std::unique_lock<std::mutex> lock(self.guard);
        self.postStatus = status; self.entered = true; self.changed.notify_all();
        self.changed.wait(lock, [&] { return self.release; });
        return status;
    }
    static NV_STATUS action(void *opaque, NvU32 command) {
        auto &self = *static_cast<PowerHookFixture *>(opaque);
        if (command == 1) return self.lease.startNativeForTest({&self, request});
        const NV_STATUS ack = self.lease.acknowledgeRevocation();
        const NV_STATUS stop = self.lease.stop();
        std::lock_guard<std::mutex> lock(self.guard);
        self.ackStatus = ack; self.stopStatus = stop;
        self.stopAttempted = true; self.changed.notify_all();
        return stop;
    }
};
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
    if (fixtureEarlyPowerRevocation) {
        auto *owner = fixtureEarlyPowerRevocation; fixtureEarlyPowerRevocation = nullptr;
        return owner->revokePowerNativeForTest();
    }
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
NV_STATUS S540NvidiaGspPlatform::Context::unbindState(nv_state_t *state) {
    if (fixturePlatformUnbindFailure) return NV_ERR_BUSY_RETRY;
    if (!impl_ || !state || fixtureState != state) return NV_ERR_INVALID_STATE;
    fixtureState = nullptr; return NV_OK;
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
        PowerHookFixture fixture;
        expect(!s540DarwinLiveObjects(), "PM hook race starts without service owners");
        expect(fixture.dispatcher.start(PowerHookFixture::action, &fixture) == NV_OK,
            "PM hook race uses a real persistent owner worker");
        expect(fixture.dispatcher.invoke(1) == NV_OK, "PM fixture lease starts on owner thread");
        NV_STATUS revokeStatus = NV_ERR_NOT_READY;
        std::thread callback([&] { revokeStatus = fixture.lease.revokeNativeForTest(); });
        {
            std::unique_lock<std::mutex> lock(fixture.guard);
            fixture.changed.wait(lock, [&] { return fixture.entered && fixture.stopAttempted; });
        }
        expect(fixture.postStatus == NV_OK, "external hook enqueues real shutdown before blocking");
        expect(fixture.ackStatus == NV_OK, "worker can acknowledge while PM hook is in flight");
        expect(fixture.stopStatus == NV_ERR_IN_USE, "in-flight external hook pins lease after acknowledgement");
        const auto pinned = fixture.lease.snapshot();
        expect(pinned.retained && pinned.acknowledgementSent && !pinned.acknowledgementPending &&
            !pinned.stopped && pinned.revocationHooksInFlight == 1,
            "independent hook count retains owner without relying on Apple's bounded PM wait");
        {
            std::lock_guard<std::mutex> lock(fixture.guard);
            fixture.release = true; fixture.changed.notify_all();
        }
        callback.join();
        expect(revokeStatus == NV_OK, "external hook returns after explicit release");
        const auto returned = fixture.lease.snapshot();
        expect(returned.retained && returned.revocationHooksInFlight == 0 && returned.revocationPosts == 1,
            "hook completion closes only its own lifetime reference");
        expect(fixture.dispatcher.invoke(2) == NV_OK, "owner retries lease stop after actual callback return");
        const auto stopped = fixture.lease.snapshot();
        expect(!stopped.retained && stopped.stopped && stopped.revocationHooksInFlight == 0,
            "successful retry releases lease storage only after external hook exit");
        expect(fixture.dispatcher.stop() == NV_OK, "PM hook race joins persistent worker");
    }
    expectCold();
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        fixtureEarlyPowerRevocation = &owner;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_ERR_NOT_READY,
            "PM down before original identity publication refuses preparation");
        const auto state = owner.snapshot();
        expect(state.cleanupComplete && !state.ownsResources && !state.workerActive &&
            state.powerRevoked && state.cancellationRevoked && !state.cancellationBound,
            "early PM event drains real prepared owners without original entry");
        expect(state.powerRevokedAtNs &&
            state.cancellationDeadlineNs == state.powerRevokedAtNs + 30000000000ULL,
            "late exact-state binding preserves actual earlier PM event deadline");
        expectCold();
    }
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
            state.firmwareCopied && state.dmaPolicyAdmitted && state.nativeFixture && state.cancellationBound,
            "preparation evidence distinguishes fixture and actual owned bindings");
        expect(!state.globalInitialized && !state.adapterInitialized && !state.firmwareLoaded &&
            !state.interruptInstalled && !state.interruptArmed,
            "no original entry or IRQ activation during preparation");
        expect(owner.initialize() == NV_ERR_NOT_SUPPORTED, "unresolved gates refuse before original entry");
        state = owner.snapshot();
        expect(state.initializationRefused && state.prepared && state.blockedGates == 15 &&
            state.workerActive && state.workerThread && state.powerDomainJoined && state.powerOnCompleted,
            "completed lease retains prepared resources without clearing original-entry power deadline gate");
        NV_STATUS foreign = NV_OK;
        const NvU64 worker = state.workerThread;
        std::thread caller([&] { foreign = owner.initialize(); }); caller.join();
        expect(foreign == NV_ERR_NOT_SUPPORTED && owner.snapshot().workerThread == worker,
            "different caller still dispatches on the exact persistent RM owner thread");
        expect(owner.stop() == NV_OK && !fixture.active && owner.snapshot().cleanupComplete,
            "normal ordered cleanup");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "lease case prepared");
        FirmwareLeaseFixture lease;
        expect(owner.runNativeForTest(acquireFirmware, &lease) == NV_OK &&
            lease.handle && lease.bytes && lease.bytes != gsp.data() && lease.length == gsp.size() &&
            static_cast<const NvU8 *>(lease.bytes)[0] == gsp[0], "Store delivers an owned immutable copy on its owner worker");
        expect(owner.stop() == NV_ERR_IN_USE, "live firmware lease blocks destruction");
        auto state = owner.snapshot();
        expect(state.ownsResources && state.quarantined && fixture.active &&
            state.firmwareBound && state.transportBound && state.platformBound &&
            !state.timersBound && fixtureState, "partial detach retains original state and all implicated owners");
        expect(owner.runNativeForTest(releaseFirmware, &lease) == NV_OK, "firmware release returns to same owner worker");
        expect(owner.stop() == NV_OK && !fixture.active, "lease release permits idempotent cleanup retry");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "platform refusal case prepared");
        fixturePlatformUnbindFailure = true;
        expect(owner.stop() == NV_ERR_BUSY_RETRY && owner.snapshot().ownsResources && fixtureState,
            "platform unbind refusal pins context until successful retry");
        fixturePlatformUnbindFailure = false;
        expect(owner.stop() == NV_OK, "platform detach retry releases retained context");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "PM revocation case prepared");
        expect(owner.failPowerAcknowledgementNativeForTest(true) == NV_OK, "inject actual acknowledgement refusal boundary");
        expect(owner.revokePowerNativeForTest() == NV_OK, "PM down posts to persistent worker");
        expect(owner.runNativeForTest(inspect, nullptr) == NV_OK, "barrier waits for posted PM shutdown action");
        const auto state = owner.snapshot();
        expect(state.powerRevoked && state.cancellationRevoked && state.cancellationBound &&
            state.cancellationDeadlineNs && !state.powerAcknowledged && state.quarantined &&
            state.ownsResources && state.workerActive && !fixture.active && !fixtureState,
            "failed ack retains PM owner and worker after real RM resources drain");
        expect(owner.failPowerAcknowledgementNativeForTest(false) == NV_OK && owner.stop() == NV_OK,
            "retry acknowledges only after cleanup and joins persistent worker");
        expect(owner.snapshot().powerAcknowledged && !owner.snapshot().workerActive &&
            owner.snapshot().cancellationRevoked && !owner.snapshot().cancellationBound,
            "completed PM acknowledgement reported separately from enqueue acceptance");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "PM transport failure case prepared");
        fixture.failStop = true;
        expect(owner.revokePowerNativeForTest() == NV_OK && owner.runNativeForTest(inspect, nullptr) == NV_OK,
            "revocation worker reaches actual transport stop refusal");
        const auto state = owner.snapshot();
        expect(state.powerRevoked && !state.powerAcknowledged && state.ownsResources && fixture.active,
            "hardware-owner cleanup failure never acknowledges the PM drop");
        fixture.failStop = false;
        expect(owner.stop() == NV_OK && owner.snapshot().powerAcknowledged,
            "retained transport cleanup retry precedes real acknowledgement");
        expectCold();
    }
    {
        S540NvidiaGspBootstrap::Owner owner; ResourceFixture fixture;
        expect(owner.prepareNativeForTest(&provider, backend(fixture), images) == NV_OK, "host borrower refusal case prepared");
        void *borrower = nullptr;
        expect(owner.runNativeForTest(allocateHostBorrower, &borrower) == NV_OK,
            "actual tracked borrower keeps host alive");
        expect(owner.stop() == NV_ERR_IN_USE && !fixtureState && owner.snapshot().hostInitialized,
            "host teardown refusal preserves OS fact storage after actual platform destruction");
        const auto *facts = s540GlobalRmPlatformFacts();
        expect(facts && !std::strcmp(facts->osDate, "native-bootstrap-platform-fixture"),
            "host text is independent of freed Platform storage");
        expect(owner.runNativeForTest(releaseHostBorrower, &borrower) == NV_OK && owner.stop() == NV_OK,
            "borrower release permits ordered host and power cleanup retry");
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
        "\"persistent_worker_verified\":true,\"pm_revocation_fixture\":true,\"ack_after_cleanup_verified\":true,"
        "\"pm_hook_lifetime_verified\":true,"
        "\"original_rm_executed\":false,\"firmware_loaded\":false,\"gpu_initialized\":false,"
        "\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
    return 0;
}
