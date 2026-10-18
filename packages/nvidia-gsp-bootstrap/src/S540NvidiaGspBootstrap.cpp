// SPDX-License-Identifier: MIT
#include "S540NvidiaGspBootstrap.hpp"
#include "S540NvidiaGspDispatcher.hpp"
#include "S540NvidiaGspContext.h"
#include "S540NvidiaGspFirmware.hpp"
#include "../platform/S540NvidiaGspPlatform.hpp"
#include "../platform/S540NvidiaGspPower.hpp"
#include "../timers/S540NvidiaGspTimers.h"
#include "../../nvidia-device-transport/src/nv_device_services.h"
#include "../../nvidia-firmware-assets/src/S540NvidiaFirmwareAssets.hpp"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#if defined(KERNEL)
#include <IOKit/IOLib.h>
#else
#include <cstdlib>
#endif

struct S540BootstrapPlacement { void *address; };
void *operator new(decltype(sizeof(0)), S540BootstrapPlacement p) noexcept { return p.address; }

namespace S540NvidiaGspBootstrap {
namespace {
constexpr NvU32 kBlockedGates = OriginalAbiClosure | PowerLifetime |
    AllocationRetirementUnderActiveIrq | OriginalStackBoundary;
constexpr NvU64 kGspBytes = 22901632, kUcodesBytes = 8837632;
enum Command : NvU32 { Prepare = 1, Initialize, Stop, PowerRevoked, Inspect, NativeActionCommand, NativeAckFailure };
bool ordinary(NvU64 &thread) {
    return s540Darwin_os_semaphore_may_sleep() &&
        s540Darwin_os_get_current_thread(&thread) == NV_OK && thread;
}
void copyBytes(void *output, const void *input, NvU64 bytes) {
    auto *to = static_cast<NvU8 *>(output);
    const auto *from = static_cast<const NvU8 *>(input);
    while (bytes--) *to++ = *from++;
}
bool copyText(char *output, NvU32 capacity, const char *input) {
    if (!input || !capacity) return false;
    NvU32 i = 0;
    for (; i + 1 < capacity && input[i]; ++i) output[i] = input[i];
    if (!i || input[i]) return false;
    output[i] = '\0'; return true;
}
void *allocateOwner(NvU64 bytes) {
#if defined(KERNEL)
    return IOMalloc(static_cast<vm_size_t>(bytes));
#else
    return std::malloc(static_cast<size_t>(bytes));
#endif
}
void releaseOwner(void *memory, NvU64 bytes) {
#if defined(KERNEL)
    IOFree(memory, static_cast<vm_size_t>(bytes));
#else
    (void)bytes; std::free(memory);
#endif
}
}

struct Owner::Impl {
    Dispatcher dispatcher;
    S540NvidiaDeviceTransport::Session transport;
    S540NvidiaGspPlatform::Context platform;
    S540NvidiaGspPower::Lease power;
    S540NvidiaGspFirmware::Store firmware;
    S540GspContext *context;
    NvU64 thread;
    void *gsp, *ucodes, *snapshotGuard;
    char osVersion[128], osDate[128];
    bool host, deviceBound, firmwareBound, timersBound, platformBound, nativeFixture;
    Snapshot state, published;
    IOPCIDevice *provider;
    IOService *service;
    Images images;
    const S540NvidiaDeviceTransport::Detail::Backend *nativeBackend;
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
    Owner::NativeAction nativeAction;
    void *nativeActionContext;
    bool nativeAckFailure;
#endif
    Impl() : context(nullptr), thread(0), gsp(nullptr), ucodes(nullptr), snapshotGuard(nullptr),
        osVersion{}, osDate{}, host(false), deviceBound(false), firmwareBound(false),
        timersBound(false), platformBound(false), nativeFixture(false), state{}, published{},
        provider(nullptr), service(nullptr), images{}, nativeBackend(nullptr)
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
        , nativeAction(nullptr), nativeActionContext(nullptr), nativeAckFailure(false)
#endif
    { state.format = published.format = 1; state.blockedGates = published.blockedGates = kBlockedGates; }
    bool owned() const { NvU64 current = 0; return ordinary(current) && current == thread; }
    static NV_STATUS postRevocation(void *owner) {
        auto *self = static_cast<Impl *>(owner);
        return self ? self->dispatcher.post(PowerRevoked) : NV_STATUS(NV_ERR_INVALID_STATE);
    }
    static NV_STATUS action(void *owner, NvU32 command) {
        auto *self = static_cast<Impl *>(owner);
        NV_STATUS status = NV_ERR_INVALID_ARGUMENT;
        if (!self->thread) {
            if (!ordinary(self->thread)) return NV_ERR_INVALID_STATE;
        }
        if (!self->owned()) return NV_ERR_INVALID_STATE;
        switch (command) {
        case Prepare: status = self->prepare(); break;
        case Initialize: status = self->initialize(); break;
        case Stop:
        case PowerRevoked: status = self->stop(); break;
        case Inspect: status = NV_OK; break;
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
        case NativeActionCommand:
            status = self->nativeAction ? self->nativeAction(self->nativeActionContext,
                self->context ? s540GspContextState(self->context) : nullptr) : NV_STATUS(NV_ERR_INVALID_ARGUMENT);
            break;
        case NativeAckFailure:
            self->power.failAcknowledgementNativeForTest(self->nativeAckFailure); status = NV_OK; break;
#endif
        }
        self->publish();
        return status;
    }
    Snapshot current() const {
        Snapshot result = state;
        result.ownsResources = !state.cleanupComplete;
        result.hostInitialized = host; result.platformBound = platformBound;
        result.transportBound = deviceBound; result.firmwareBound = firmwareBound;
        result.timersBound = timersBound; result.nativeFixture = nativeFixture;
        result.interruptInstalled = transport.interruptInstalled();
        result.interruptArmed = transport.interruptArmed(); result.workerThread = thread;
        result.workerActive = true;
        const auto lease = power.snapshot();
        result.powerDomainJoined = lease.domainJoined;
        result.powerOnCompleted = lease.onCompleted;
        result.powerRevoked = lease.revoked;
        result.powerAcknowledged = lease.acknowledgementSent;
        result.blockedGates = kBlockedGates;
        if (power.status() == NV_OK) result.blockedGates &= ~NvU32(PowerLifetime);
        if (context) {
            S540GspContextSnapshot facts{}; s540GspContextSnapshot(context, &facts);
            result.adapterInitialized = facts.adapterInitialized;
        }
        return result;
    }
    void publish() {
        const Snapshot result = current();
        if (s540Darwin_os_acquire_mutex(snapshotGuard) != NV_OK) return;
        published = result; s540Darwin_os_release_mutex(snapshotGuard);
    }
    Snapshot read() const {
        Snapshot result{};
        if (s540Darwin_os_acquire_mutex(snapshotGuard) != NV_OK) return result;
        result = published; s540Darwin_os_release_mutex(snapshotGuard);
        return result;
    }
    static NV_STATUS detach(void *owner, void *state, void *dma) {
        auto *self = static_cast<Impl *>(owner);
        if (!self || !self->owned() || !self->context ||
            state != s540GspContextState(self->context) || dma != s540GspContextDmaDevice(self->context))
            return NV_ERR_INVALID_STATE;
        if (self->timersBound) {
            const NV_STATUS status = s540GspTimersUnbind(static_cast<nv_state_t *>(state));
            if (status != NV_OK) return status;
            self->timersBound = false;
        }
        if (self->firmware.snapshot().active && !self->firmware.shutdown(self->thread)) return NV_ERR_IN_USE;
        if (self->firmwareBound) {
            const NV_STATUS status = S540NvidiaGspFirmware::unbind(&self->firmware);
            if (status != NV_OK) return status;
            self->firmwareBound = false;
        }
        if (self->deviceBound) {
            // This drain is also required after original private-state cleanup:
            // its last frees may retire allocations while IRQs were active.
            NV_STATUS status = S540NvidiaDeviceTransport::drainRmRetirements(&self->transport);
            if (status != NV_OK) return status;
            status = S540NvidiaDeviceTransport::unbindRmDevice(&self->transport);
            if (status != NV_OK) return status;
            self->deviceBound = false;
        }
        if (self->platformBound) {
            const NV_STATUS status = self->platform.unbindState(static_cast<nv_state_t *>(state));
            if (status != NV_OK) return status;
            self->platformBound = false;
        }
        return NV_OK;
    }
    NV_STATUS failed(NV_STATUS failure) {
        state.preparationStatus = failure;
        const NV_STATUS cleanup = stop();
        return cleanup == NV_OK ? failure : cleanup;
    }
    NV_STATUS prepare() {
        state.ownsResources = true;
        const S540NvidiaGspPower::Revocation revocation{this, postRevocation};
        NV_STATUS status;
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
        status = nativeFixture ? power.startNativeForTest(revocation) : power.start(provider, revocation);
#else
        status = power.start(provider, revocation);
#endif
        if (status != NV_OK) return failed(status);
        status = platform.initialize(provider);
        if (status != NV_OK) return failed(status);
        S540NvidiaGlobalRmPlatformFacts hostFacts{}; S540GspDeviceFacts deviceFacts{};
        status = platform.collect(&hostFacts); if (status != NV_OK) return failed(status);
        status = platform.collectDeviceFacts(&deviceFacts); if (status != NV_OK) return failed(status);
        if (!copyText(osVersion, sizeof(osVersion), hostFacts.osVersion) ||
            !copyText(osDate, sizeof(osDate), hostFacts.osDate)) return failed(NV_ERR_INVALID_DATA);
        hostFacts.osVersion = osVersion; hostFacts.osDate = osDate;
        status = s540GlobalRmHostInitialize(&hostFacts); if (status != NV_OK) return failed(status);
        host = true;
#if defined(KERNEL)
        status = transport.start(provider, service);
#elif defined(S540_GSP_BOOTSTRAP_NATIVE_TEST)
        status = nativeBackend ? transport.start(*nativeBackend) : NV_STATUS(NV_ERR_NOT_SUPPORTED);
#else
        status = NV_ERR_NOT_SUPPORTED;
#endif
        if (status != NV_OK) return failed(status);
        status = transport.setPciSegment(deviceFacts.segment); if (status != NV_OK) return failed(status);
        NvBool required = NV_FALSE;
        status = transport.requiresDmaRemap(required);
        if (status != NV_OK || !required) return failed(status == NV_OK ? NV_STATUS(NV_ERR_NOT_SUPPORTED) : status);
        state.dmaPolicyAdmitted = true;
        deviceFacts.pciHandle = transport.pciHandle();
        status = s540GspContextCreate(&deviceFacts, &context); if (status != NV_OK) return failed(status);
        const S540GspContextDetacher detacher{this, detach};
        status = s540GspContextSetDetacher(context, &detacher); if (status != NV_OK) return failed(status);
        auto *nv = static_cast<nv_state_t *>(s540GspContextState(context));
        auto *dma = static_cast<nv_dma_device_t *>(s540GspContextDmaDevice(context));
        status = platform.bindState(nv); if (status != NV_OK) return failed(status);
        platformBound = true;
        status = S540NvidiaDeviceTransport::bindRmDevice(&transport, nv, dma); if (status != NV_OK) return failed(status);
        deviceBound = true;
        status = S540NvidiaDeviceTransport::queryRmDmaRemap(nv, required);
        if (status != NV_OK || !required) return failed(status == NV_OK ? NV_STATUS(NV_ERR_NOT_SUPPORTED) : status);
        // Both tracked capacity reservations must exist before any copy.
        gsp = s540GlobalRmHostAllocate(images.gspBytes); if (!gsp) return failed(NV_ERR_NO_MEMORY);
        ucodes = s540GlobalRmHostAllocate(images.ucodesBytes); if (!ucodes) return failed(NV_ERR_NO_MEMORY);
        copyBytes(gsp, images.gsp, images.gspBytes); copyBytes(ucodes, images.ucodes, images.ucodesBytes);
        state.firmwareCopied = true;
        status = firmware.initialize(nv, thread, gsp, images.gspBytes, ucodes, images.ucodesBytes);
        if (status != NV_OK) return failed(status);
        status = S540NvidiaGspFirmware::bind(&firmware); if (status != NV_OK) return failed(status);
        firmwareBound = true;
        status = s540GspTimersBind(nv); if (status != NV_OK) return failed(status);
        timersBound = true;
        if (power.status() != NV_OK) return failed(NV_ERR_NOT_READY);
        state.prepared = state.preparationCompleted = true; state.preparationStatus = NV_OK;
        // The synchronous caller no longer owns these immutable input pointers.
        // Later lifecycle operations use only our tracked copies.
        images = Images{}; nativeBackend = nullptr; provider = nullptr; service = nullptr;
        return NV_OK;
    }
    NV_STATUS initialize() {
        if (!state.prepared) return NV_ERR_INVALID_STATE;
        state.initializationRefused = true;
        if (power.status() != NV_OK) { state.initializationStatus = NV_ERR_NOT_READY; return NV_ERR_NOT_READY; }
        state.initializationStatus = NV_ERR_NOT_SUPPORTED;
        // Persistent ownership and PM revocation do not prove native ABI
        // closure, sufficient allocation capacity or a genuine kernel stack
        // boundary for the original Resource Manager. Never enter it here.
        return NV_ERR_NOT_SUPPORTED;
    }
    NV_STATUS stop() {
        if (state.cleanupComplete) return NV_OK;
        state.prepared = false;
        NV_STATUS status = NV_OK;
        if (context) {
            S540GspContextSnapshot facts{}; s540GspContextSnapshot(context, &facts);
            // Original disable runs while IRQ/MMIO/DMA/power are still live.
            if (facts.adapterInitialized && !facts.adapterDisabled) {
                status = s540GspContextDisableAdapter(context); if (status != NV_OK) goto retained;
            }
            if (transport.interruptInstalled()) {
                status = transport.stopInterrupt(); if (status != NV_OK) goto retained;
            }
            if (deviceBound) {
                status = S540NvidiaDeviceTransport::drainRmRetirements(&transport);
                if (status != NV_OK) goto retained;
            }
            if (facts.adapterInitialized && !facts.adapterShutdown) {
                status = s540GspContextShutdownAdapter(context, NV_TRUE); if (status != NV_OK) goto retained;
            }
            if (s540GlobalRmIsInitialized()) { status = NV_ERR_IN_USE; goto retained; }
            status = s540GspContextDestroy(context, NV_TRUE, nullptr); if (status != NV_OK) goto retained;
            context = nullptr;
        }
        if (timersBound || firmwareBound || deviceBound || firmware.snapshot().active) {
            status = NV_ERR_IN_USE; goto retained;
        }
        if (transport.active()) { status = transport.stop(); if (status != NV_OK) goto retained; }
        if (platform.active()) {
            status = platform.shutdown(); if (status != NV_OK) goto retained;
            platformBound = false;
        }
        if (gsp) { s540GlobalRmHostFree(gsp); gsp = nullptr; }
        if (ucodes) { s540GlobalRmHostFree(ucodes); ucodes = nullptr; }
        if (host) {
            if (!s540GlobalRmHostShutdown()) { status = NV_ERR_IN_USE; goto retained; }
            host = false;
        }
        // Every original/IRQ/DMA/MMIO owner has now actually completed stop.
        // Only then acknowledge the pending PM down, then synchronously stop
        // PM callouts. A refused acknowledgement retains lease and dispatcher.
        status = power.acknowledgeRevocation(); if (status != NV_OK) goto retained;
        status = power.stop(); if (status != NV_OK) goto retained;
        state.cleanupComplete = true; state.ownsResources = false;
        state.quarantined = false; state.cleanupStatus = NV_OK;
        return NV_OK;
retained:
        state.quarantined = true; state.cleanupStatus = status;
        return status;
    }
};

Owner::Owner() : impl_(nullptr), state_{} { state_.format = 1; state_.blockedGates = kBlockedGates; }
Owner::~Owner() { /* Failed cleanup intentionally retains the stable heap owner. */ }
NV_STATUS Owner::prepare(IOPCIDevice *provider, IOService *service, const Images &images) {
    return prepareCommon(provider, service, images, nullptr);
}
NV_STATUS Owner::prepareCommon(IOPCIDevice *provider, IOService *service,
    const Images &images, const S540NvidiaDeviceTransport::Detail::Backend *nativeBackend) {
    NvU64 caller = 0;
    if (!ordinary(caller)) return NV_ERR_INVALID_STATE;
    if (impl_) return NV_ERR_STATE_IN_USE;
    if (!provider || (!service && !nativeBackend) || !images.gsp || !images.ucodes ||
        images.gspBytes != kGspBytes || images.ucodesBytes != kUcodesBytes) return NV_ERR_INVALID_ARGUMENT;
    if (!S540NvidiaFirmwareAssets::verifyPair(images.gsp, images.gspBytes,
            images.ucodes, images.ucodesBytes).passed()) return NV_ERR_INVALID_DATA;
    void *memory = allocateOwner(sizeof(Impl)); if (!memory) return NV_ERR_NO_MEMORY;
    impl_ = new (S540BootstrapPlacement{memory}) Impl;
    NV_STATUS status = s540Darwin_os_alloc_mutex(&impl_->snapshotGuard);
    if (status != NV_OK) { impl_->~Impl(); releaseOwner(impl_, sizeof(Impl)); impl_ = nullptr; return status; }
    impl_->provider = provider; impl_->service = service; impl_->images = images; impl_->nativeBackend = nativeBackend;
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
    impl_->nativeFixture = nativeBackend != nullptr;
#else
    if (nativeBackend) status = NV_ERR_NOT_SUPPORTED;
#endif
    if (status == NV_OK) status = impl_->dispatcher.start(Impl::action, impl_);
    if (status != NV_OK) {
        s540Darwin_os_free_mutex(impl_->snapshotGuard);
        impl_->~Impl(); releaseOwner(impl_, sizeof(Impl)); impl_ = nullptr; return status;
    }
    status = impl_->dispatcher.invoke(Prepare);
    if (status != NV_OK && impl_->read().cleanupComplete) {
        const NV_STATUS shutdown = stop();
        if (shutdown != NV_OK) return shutdown;
    }
    return status;
}
NV_STATUS Owner::initialize() { return impl_ ? impl_->dispatcher.invoke(Initialize) : NV_STATUS(NV_ERR_INVALID_STATE); }
NV_STATUS Owner::stop() {
    if (!impl_) return NV_OK;
    const NV_STATUS status = impl_->dispatcher.invoke(Stop);
    if (status != NV_OK) return status;
    const NV_STATUS joined = impl_->dispatcher.stop();
    if (joined != NV_OK) return joined;
    state_ = impl_->read(); state_.workerActive = false; state_.ownsResources = false;
    s540Darwin_os_free_mutex(impl_->snapshotGuard);
    impl_->~Impl(); releaseOwner(impl_, sizeof(Impl)); impl_ = nullptr;
    return NV_OK;
}
Snapshot Owner::snapshot() const { return impl_ ? impl_->read() : state_; }
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
NV_STATUS Owner::prepareNativeForTest(IOPCIDevice *provider,
    const S540NvidiaDeviceTransport::Detail::Backend &backend, const Images &images) {
    return prepareCommon(provider, nullptr, images, &backend);
}
NV_STATUS Owner::runNativeForTest(NativeAction action, void *fixture) {
    if (!impl_ || !action) return NV_ERR_INVALID_ARGUMENT;
    impl_->nativeAction = action; impl_->nativeActionContext = fixture;
    const NV_STATUS status = impl_->dispatcher.invoke(NativeActionCommand);
    impl_->nativeAction = nullptr; impl_->nativeActionContext = nullptr;
    return status;
}
NV_STATUS Owner::revokePowerNativeForTest() {
    if (!impl_) return NV_ERR_INVALID_STATE;
    return impl_->power.revokeNativeForTest();
}
NV_STATUS Owner::failPowerAcknowledgementNativeForTest(bool failed) {
    if (!impl_) return NV_ERR_INVALID_STATE;
    impl_->nativeAckFailure = failed;
    return impl_->dispatcher.invoke(NativeAckFailure);
}
#endif
}
