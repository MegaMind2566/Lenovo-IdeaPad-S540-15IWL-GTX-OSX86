// SPDX-License-Identifier: MIT
#include "S540NvidiaGspBootstrap.hpp"
#include "S540NvidiaGspContext.h"
#include "S540NvidiaGspFirmware.hpp"
#include "../platform/S540NvidiaGspPlatform.hpp"
#include "../timers/S540NvidiaGspTimers.h"
#include "../../nvidia-device-transport/src/nv_device_services.h"
#include "../../nvidia-firmware-assets/src/S540NvidiaFirmwareAssets.hpp"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
#if defined(KERNEL)
#include <IOKit/IOLib.h>
#else
#include <cstdlib>
#endif

// Distinct placement signature avoids depending on the SDK's hosted <new>.
struct S540BootstrapPlacement { void *address; };
void *operator new(decltype(sizeof(0)), S540BootstrapPlacement p) noexcept {
    return p.address;
}

namespace S540NvidiaGspBootstrap {
namespace {
constexpr NvU32 kBlockedGates = OriginalAbiClosure | PowerLifetime |
    AllocationRetirementUnderActiveIrq | OriginalStackBoundary;
// The pinned Store validates this exact pair. Check lengths before asking the
// tracked allocator to admit either owned image; allocate BOTH before copying.
constexpr NvU64 kGspBytes = 22901632, kUcodesBytes = 8837632;
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
    output[i] = '\0';
    return true;
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
    (void)bytes;
    std::free(memory);
#endif
}
}

struct Owner::Impl {
    S540NvidiaDeviceTransport::Session transport;
    S540NvidiaGspPlatform::Context platform;
    S540NvidiaGspFirmware::Store firmware;
    S540GspContext *context;
    NvU64 thread;
    void *gsp, *ucodes;
    // HostInitialize copies facts shallowly. Keep its text independent of the
    // Platform object, which must detach its state identity before Context free.
    char osVersion[128], osDate[128];
    bool host, deviceBound, firmwareBound, timersBound;
    bool platformBound, nativeFixture;
    Impl() : context(nullptr), thread(0), gsp(nullptr), ucodes(nullptr), osVersion{}, osDate{},
        host(false), deviceBound(false), firmwareBound(false), timersBound(false),
        platformBound(false), nativeFixture(false) {}
    bool owned() const {
        NvU64 current = 0;
        return ordinary(current) && current == thread;
    }
    static NV_STATUS detach(void *owner, void *state, void *dma) {
        auto *self = static_cast<Impl *>(owner);
        if (!self || !self->owned() || !self->context ||
            state != s540GspContextState(self->context) ||
            dma != s540GspContextDmaDevice(self->context))
            return NV_ERR_INVALID_STATE;
        // ContextDestroy has drained original producers/released original
        // state, retaining nv_state, queues and metadata for these real calls.
        if (self->timersBound) {
            NV_STATUS status = s540GspTimersUnbind(static_cast<nv_state_t *>(state));
            if (status != NV_OK) return status;
            self->timersBound = false;
        }
        if (self->firmware.snapshot().active && !self->firmware.shutdown(self->thread))
            return NV_ERR_IN_USE;
        if (self->firmwareBound) {
            NV_STATUS status = S540NvidiaGspFirmware::unbind(&self->firmware);
            if (status != NV_OK) return status;
            self->firmwareBound = false;
        }
        if (self->deviceBound) {
            NV_STATUS status = S540NvidiaDeviceTransport::unbindRmDevice(&self->transport);
            if (status != NV_OK) return status;
            self->deviceBound = false;
        }
        // Remove the ROM callback's nv_state identity BEFORE that state can be
        // freed. The retained transport continues to own the live PCI provider.
        if (self->platform.active()) {
            NV_STATUS status = self->platform.shutdown();
            if (status != NV_OK) return status;
            self->platformBound = false;
        }
        return NV_OK;
    }
};

Owner::Owner() : impl_(nullptr), state_{} {
    state_.format = 1;
    state_.blockedGates = kBlockedGates;
}
Owner::~Owner() {
    // Never run Session/Platform destructors against live external bindings.
    // stop() is the sole release path; an abandoned Impl intentionally remains.
}
NV_STATUS Owner::prepare(IOPCIDevice *provider, IOService *service, const Images &images) {
    return prepareCommon(provider, service, images, nullptr);
}
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
NV_STATUS Owner::prepareNativeForTest(IOPCIDevice *provider,
    const S540NvidiaDeviceTransport::Detail::Backend &backend, const Images &images) {
    return prepareCommon(provider, nullptr, images, &backend);
}
#endif
NV_STATUS Owner::prepareCommon(IOPCIDevice *provider, IOService *service,
    const Images &images, const S540NvidiaDeviceTransport::Detail::Backend *nativeBackend) {
    NvU64 thread = 0;
    if (!ordinary(thread)) return NV_ERR_INVALID_STATE;
    if (impl_) return NV_ERR_STATE_IN_USE;
    if (!provider || (!service && !nativeBackend) || !images.gsp || !images.ucodes ||
        images.gspBytes != kGspBytes || images.ucodesBytes != kUcodesBytes)
        return NV_ERR_INVALID_ARGUMENT;
    // Validate caller bytes before allocation. Store revalidates our immutable
    // copies after the copy, so a changing caller image cannot gain admission.
    if (!S540NvidiaFirmwareAssets::verifyPair(images.gsp, images.gspBytes,
            images.ucodes, images.ucodesBytes).passed()) return NV_ERR_INVALID_DATA;
    void *storage = allocateOwner(sizeof(Impl));
    if (!storage) return NV_ERR_NO_MEMORY;
    impl_ = new (S540BootstrapPlacement{storage}) Impl;
    impl_->thread = thread;
    state_ = Snapshot{}; state_.format = 1; state_.blockedGates = kBlockedGates;
    state_.ownsResources = true;
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
    impl_->nativeFixture = nativeBackend != nullptr;
#else
    if (nativeBackend) return preparationFailed(NV_ERR_NOT_SUPPORTED);
#endif
    NV_STATUS status = impl_->platform.initialize(provider);
    if (status != NV_OK) return preparationFailed(status);
    S540NvidiaGlobalRmPlatformFacts hostFacts{};
    S540GspDeviceFacts deviceFacts{};
    status = impl_->platform.collect(&hostFacts);
    if (status != NV_OK) return preparationFailed(status);
    status = impl_->platform.collectDeviceFacts(&deviceFacts);
    if (status != NV_OK) return preparationFailed(status);
    if (!copyText(impl_->osVersion, sizeof(impl_->osVersion), hostFacts.osVersion) ||
        !copyText(impl_->osDate, sizeof(impl_->osDate), hostFacts.osDate))
        return preparationFailed(NV_ERR_INVALID_DATA);
    hostFacts.osVersion = impl_->osVersion;
    hostFacts.osDate = impl_->osDate;
    status = s540GlobalRmHostInitialize(&hostFacts);
    if (status != NV_OK) return preparationFailed(status);
    impl_->host = true;
#if defined(KERNEL)
    status = impl_->transport.start(provider, service);
#elif defined(S540_GSP_BOOTSTRAP_NATIVE_TEST)
    status = nativeBackend ? impl_->transport.start(*nativeBackend) : NV_STATUS(NV_ERR_NOT_SUPPORTED);
#else
    (void)service;
    status = NV_ERR_NOT_SUPPORTED;
#endif
    if (status != NV_OK) return preparationFailed(status);
    status = impl_->transport.setPciSegment(deviceFacts.segment);
    if (status != NV_OK) return preparationFailed(status);
    NvBool dmaRemap = NV_FALSE;
    status = impl_->transport.requiresDmaRemap(dmaRemap);
    if (status != NV_OK || !dmaRemap)
        return preparationFailed(status == NV_OK ? NV_STATUS(NV_ERR_NOT_SUPPORTED) : status);
    state_.dmaPolicyAdmitted = true;
    deviceFacts.pciHandle = impl_->transport.pciHandle();
    status = s540GspContextCreate(&deviceFacts, &impl_->context);
    // Create may return a retained quarantined context on unwind failure.
    if (status != NV_OK) return preparationFailed(status);
    const S540GspContextDetacher detacher{impl_, Impl::detach};
    status = s540GspContextSetDetacher(impl_->context, &detacher);
    if (status != NV_OK) return preparationFailed(status);
    auto *state = static_cast<nv_state_t *>(s540GspContextState(impl_->context));
    auto *dma = static_cast<nv_dma_device_t *>(s540GspContextDmaDevice(impl_->context));
    status = impl_->platform.bindState(state);
    if (status != NV_OK) return preparationFailed(status);
    impl_->platformBound = true;
    status = S540NvidiaDeviceTransport::bindRmDevice(&impl_->transport, state, dma);
    if (status != NV_OK) return preparationFailed(status);
    impl_->deviceBound = true;
    status = S540NvidiaDeviceTransport::queryRmDmaRemap(state, dmaRemap);
    if (status != NV_OK || !dmaRemap)
        return preparationFailed(status == NV_OK ? NV_STATUS(NV_ERR_NOT_SUPPORTED) : status);
    // Successful tracked allocations are the allocator's capacity admission.
    // No copy begins until both reservations exist. Failure retains their
    // recorded owners until the ordered stop path releases them.
    impl_->gsp = s540GlobalRmHostAllocate(images.gspBytes);
    if (!impl_->gsp) return preparationFailed(NV_ERR_NO_MEMORY);
    impl_->ucodes = s540GlobalRmHostAllocate(images.ucodesBytes);
    if (!impl_->ucodes) return preparationFailed(NV_ERR_NO_MEMORY);
    copyBytes(impl_->gsp, images.gsp, images.gspBytes);
    copyBytes(impl_->ucodes, images.ucodes, images.ucodesBytes);
    state_.firmwareCopied = true;
    status = impl_->firmware.initialize(state, thread, impl_->gsp, images.gspBytes,
        impl_->ucodes, images.ucodesBytes);
    if (status != NV_OK) return preparationFailed(status);
    status = S540NvidiaGspFirmware::bind(&impl_->firmware);
    if (status != NV_OK) return preparationFailed(status);
    impl_->firmwareBound = true;
    status = s540GspTimersBind(state);
    if (status != NV_OK) return preparationFailed(status);
    impl_->timersBound = true;
    state_.prepared = state_.preparationCompleted = true;
    state_.preparationStatus = NV_OK;
    return NV_OK;
}
NV_STATUS Owner::preparationFailed(NV_STATUS status) {
    state_.preparationStatus = status;
    NV_STATUS cleanup = stop();
    return cleanup == NV_OK ? status : cleanup;
}
NV_STATUS Owner::initialize() {
    if (!impl_ || !impl_->owned() || !state_.prepared) return NV_ERR_INVALID_STATE;
    state_.initializationRefused = true;
    state_.initializationStatus = NV_ERR_NOT_SUPPORTED;
    // No original global RM construction, event/private allocation, IRQ arm,
    // rm_init_adapter, secure firmware boot or GPU command is reachable here.
    // In particular do not treat preparation or a D0 snapshot as proof of a
    // retained power-domain lifetime, or symbol closure as runtime ABI proof.
    // Original GSP initialization/disable also release temporary allocations
    // while IRQs are active; Session correctly refuses that unreviewed path.
    return NV_ERR_NOT_SUPPORTED;
}
NV_STATUS Owner::stop() {
    if (!impl_) return NV_OK;
    if (!impl_->owned()) return NV_ERR_INVALID_STATE;
    state_.prepared = false;
    NV_STATUS status = NV_OK;
    if (impl_->context) {
        S540GspContextSnapshot context{};
        s540GspContextSnapshot(impl_->context, &context);
        // These calls remain defensive future-lifetime handling. Current
        // initialize never reaches original code. If an adapter ever exists,
        // disable it while IRQ/MMIO/DMA/provider ownership are ALL still live.
        if (context.adapterInitialized && !context.adapterDisabled) {
            status = s540GspContextDisableAdapter(impl_->context);
            if (status != NV_OK) goto retained;
        }
        if (impl_->transport.interruptInstalled()) {
            status = impl_->transport.stopInterrupt();
            if (status != NV_OK) goto retained;
        }
        if (context.adapterInitialized && !context.adapterShutdown) {
            status = s540GspContextShutdownAdapter(impl_->context, NV_TRUE);
            if (status != NV_OK) goto retained;
        }
        // Never destroy adapter prerequisites underneath an unrelated global
        // owner. This coordinator cannot yet initialize or own global RM.
        if (s540GlobalRmIsInitialized()) { status = NV_ERR_IN_USE; goto retained; }
        status = s540GspContextDestroy(impl_->context, NV_TRUE, nullptr);
        if (status != NV_OK) goto retained;
        impl_->context = nullptr;
    }
    // A failed Create can leave no context/detacher. No external binding is
    // created before registration, so only platform/transport may remain here.
    if (impl_->timersBound || impl_->firmwareBound || impl_->deviceBound ||
        impl_->firmware.snapshot().active) { status = NV_ERR_IN_USE; goto retained; }
    if (impl_->transport.active()) {
        status = impl_->transport.stop();
        if (status != NV_OK) goto retained;
    }
    if (impl_->platform.active()) {
        status = impl_->platform.shutdown();
        if (status != NV_OK) goto retained;
        impl_->platformBound = false;
    }
    if (impl_->gsp) { s540GlobalRmHostFree(impl_->gsp); impl_->gsp = nullptr; }
    if (impl_->ucodes) { s540GlobalRmHostFree(impl_->ucodes); impl_->ucodes = nullptr; }
    if (impl_->host) {
        if (!s540GlobalRmHostShutdown()) { status = NV_ERR_IN_USE; goto retained; }
        impl_->host = false;
    }
    state_.nativeFixture = impl_->nativeFixture;
    impl_->~Impl(); releaseOwner(impl_, sizeof(Impl)); impl_ = nullptr;
    state_.ownsResources = false;
    state_.cleanupComplete = true;
    state_.quarantined = false;
    state_.cleanupStatus = NV_OK;
    return NV_OK;
retained:
    state_.quarantined = true;
    state_.cleanupStatus = status;
    return status;
}
Snapshot Owner::snapshot() const {
    Snapshot result = state_;
    result.ownsResources = impl_ != nullptr;
    if (!impl_) return result;
    result.hostInitialized = impl_->host;
    result.platformBound = impl_->platformBound;
    result.transportBound = impl_->deviceBound;
    result.firmwareBound = impl_->firmwareBound;
    result.timersBound = impl_->timersBound;
    result.interruptInstalled = impl_->transport.interruptInstalled();
    result.interruptArmed = impl_->transport.interruptArmed();
    result.nativeFixture = impl_->nativeFixture;
    if (impl_->context) {
        S540GspContextSnapshot context{};
        s540GspContextSnapshot(impl_->context, &context);
        result.adapterInitialized = context.adapterInitialized;
    }
    return result;
}
}
