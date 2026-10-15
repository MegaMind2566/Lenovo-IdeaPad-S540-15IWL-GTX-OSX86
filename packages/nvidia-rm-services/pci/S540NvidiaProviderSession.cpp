// SPDX-License-Identifier: MIT
#include "S540NvidiaProviderSession.hpp"
#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <kern/sched_prim.h>
#include <machine/machine_routines.h>
#else
#include <cstdlib>
#include <pthread.h>
#endif

namespace {
alignas(8) NvU64 gNextGeneration = 1;
static_assert(sizeof(void *) == 8 &&
              __atomic_always_lock_free(sizeof(gNextGeneration), nullptr),
              "PCI session tokens require Intel x86_64 lock-free integers.");
#if !defined(KERNEL)
struct NativeGuard { pthread_mutex_t mutex; pthread_cond_t changed; };
#endif
bool ordinaryThread() {
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}
bool exactTarget(NvU32 identity, NvU32 revision, NvU32 subsystem) {
    return identity == 0x1f9110deU && revision == 0x030000a1U &&
           subsystem == 0x380617aaU;
}
NvU64 newGeneration() {
    // Never wrap or reuse a generation, including across object reconstruction.
    // Bounded contention refusal is preferable to an unbounded startup loop.
    NvU64 current = __atomic_load_n(&gNextGeneration, __ATOMIC_RELAXED);
    for (NvU32 tries = 0; tries < 64; ++tries) {
        if (current == 0 || current == ~NvU64{0}) return 0;
        if (__atomic_compare_exchange_n(&gNextGeneration, &current, current + 1,
                                         false, __ATOMIC_RELAXED, __ATOMIC_RELAXED))
            return current;
    }
    return 0;
}
}

namespace S540NvidiaRmPci {
ProviderSession::ProviderSession() : guard_(nullptr), provider_(nullptr),
#if !defined(KERNEL)
    backend_{},
#endif
    state_(State::Stopped), inFlight_(0), metadata_{} {
    if (!ordinaryThread()) return;
#if defined(KERNEL)
    guard_ = IOLockAlloc();
#else
    auto *guard = static_cast<NativeGuard *>(std::malloc(sizeof(NativeGuard)));
    if (!guard) return;
    if (pthread_mutex_init(&guard->mutex, nullptr) != 0) { std::free(guard); return; }
    if (pthread_cond_init(&guard->changed, nullptr) != 0) {
        (void)pthread_mutex_destroy(&guard->mutex); std::free(guard); return;
    }
    guard_ = guard;
#endif
}
ProviderSession::~ProviderSession() {
    if (!guard_) return;
    // API/object-storage quiescence is the owner's responsibility. In normal
    // thread context this also drains accepted reads before dropping retention.
    if (stop() != NV_OK) return;
#if defined(KERNEL)
    IOLockFree(static_cast<IOLock *>(guard_));
#else
    auto *guard = static_cast<NativeGuard *>(guard_);
    (void)pthread_cond_destroy(&guard->changed);
    (void)pthread_mutex_destroy(&guard->mutex);
    std::free(guard);
#endif
    guard_ = nullptr;
}
bool ProviderSession::ready() const { return guard_ != nullptr; }
void ProviderSession::lock() {
#if defined(KERNEL)
    IOLockLock(static_cast<IOLock *>(guard_));
#else
    (void)pthread_mutex_lock(&static_cast<NativeGuard *>(guard_)->mutex);
#endif
}
void ProviderSession::unlock() {
#if defined(KERNEL)
    IOLockUnlock(static_cast<IOLock *>(guard_));
#else
    (void)pthread_mutex_unlock(&static_cast<NativeGuard *>(guard_)->mutex);
#endif
}
void ProviderSession::wait() {
#if defined(KERNEL)
    (void)IOLockSleep(static_cast<IOLock *>(guard_), this, THREAD_UNINT);
#else
    auto *guard = static_cast<NativeGuard *>(guard_);
    (void)pthread_cond_wait(&guard->changed, &guard->mutex);
#endif
}
void ProviderSession::wake() {
#if defined(KERNEL)
    IOLockWakeup(static_cast<IOLock *>(guard_), this, false);
#else
    (void)pthread_cond_broadcast(&static_cast<NativeGuard *>(guard_)->changed);
#endif
}
bool ProviderSession::retainProvider() {
#if defined(KERNEL)
    static_cast<IOPCIDevice *>(provider_)->retain(); return true;
#else
    return backend_.retain(provider_);
#endif
}
void ProviderSession::releaseProvider() {
#if defined(KERNEL)
    static_cast<IOPCIDevice *>(provider_)->release();
#else
    backend_.release(provider_);
#endif
}
bool ProviderSession::inactive() {
#if defined(KERNEL)
    auto *provider = static_cast<IOPCIDevice *>(provider_);
    // The caller owns provider arbitration. isOpen() recursively takes the
    // same guard, so state/ownership checks cannot race termination/open here.
    return provider->isInactive() || provider->isOpen();
#else
    return backend_.inactive(provider_);
#endif
}
bool ProviderSession::rawRead(NvU32 offset, NvU32 width, NvU32 &value) {
    value = 0;
    if (!validConfigurationAccess(offset, width)) return false;
#if defined(KERNEL)
    auto *provider = static_cast<IOPCIDevice *>(provider_);
    const IOByteCount byteOffset = static_cast<IOByteCount>(offset);
    // Public pinned SDK wrappers dispatch to extendedConfigRead8/16/32. All
    // offsets are explicitly aligned and bounded to the PCI 4 KiB aperture.
    if (width == 1) value = provider->configRead8(byteOffset);
    else if (width == 2) value = provider->configRead16(byteOffset);
    else value = provider->configRead32(byteOffset);
    return true;
#else
    if (!backend_.read(provider_, offset, width, value)) { value = 0; return false; }
    return true;
#endif
}
bool ProviderSession::captureBdf(NvU8 &bus, NvU8 &device, NvU8 &function) {
#if defined(KERNEL)
    auto *provider = static_cast<IOPCIDevice *>(provider_);
    bus = provider->getBusNumber(); device = provider->getDeviceNumber();
    function = provider->getFunctionNumber(); return device <= 31 && function <= 7;
#else
    return backend_.bdf(provider_, bus, device, function) && device <= 31 && function <= 7;
#endif
}
NV_STATUS ProviderSession::startLocked() {
    if (state_ != State::Stopped) return NV_ERR_STATE_IN_USE;
    metadata_ = {};
    if (!retainProvider()) { provider_ = nullptr; return NV_ERR_NO_MEMORY; }
    NvU32 identity = 0, revision = 0, subsystem = 0;
    NvU8 bus = 0, device = 0, function = 0;
    const bool valid = !inactive() && rawRead(0, 4, identity) &&
        rawRead(8, 4, revision) && rawRead(0x2c, 4, subsystem) &&
        exactTarget(identity, revision, subsystem) && captureBdf(bus, device, function) && !inactive();
    const NvU64 generation = valid ? newGeneration() : 0;
    if (!valid || generation == 0) {
        releaseProvider(); provider_ = nullptr;
        return valid ? NV_ERR_NOT_READY : NV_ERR_INVALID_STATE;
    }
    metadata_.generation = generation;
    metadata_.vendorDevice = identity; metadata_.revisionClass = revision;
    metadata_.subsystem = subsystem; metadata_.bus = bus;
    metadata_.device = device; metadata_.function = function;
#if !defined(KERNEL)
    metadata_.segmentKnown = backend_.segmentKnown;
    metadata_.segment = backend_.segmentKnown ? backend_.segment : 0;
#endif
    // No public production PCI-segment association has been established. In
    // particular, IOPCIFamily's domain-id is not treated as a PCI segment.
    metadata_.identityVerified = true; metadata_.readOnly = true;
    metadata_.providerOpened = false;
    state_ = State::Active;
    return NV_OK;
}
#if defined(KERNEL)
NV_STATUS ProviderSession::start(IOPCIDevice *provider) {
    if (!guard_) return NV_ERR_NO_MEMORY;
    if (!ordinaryThread()) return NV_ERR_INVALID_REQUEST;
    if (!provider) return NV_ERR_INVALID_POINTER;
    lock();
    if (state_ != State::Stopped) { unlock(); return NV_ERR_STATE_IN_USE; }
    provider_ = provider;
    const NV_STATUS status = startLocked();
    unlock(); return status;
}
#else
NV_STATUS ProviderSession::startNative(const Backend &backend) {
    if (!guard_) return NV_ERR_NO_MEMORY;
    if (!backend.provider || !backend.retain || !backend.release || !backend.read ||
        !backend.inactive || !backend.bdf) return NV_ERR_INVALID_POINTER;
    lock();
    if (state_ != State::Stopped) { unlock(); return NV_ERR_STATE_IN_USE; }
    backend_ = backend; provider_ = backend.provider;
    const NV_STATUS status = startLocked();
    unlock(); return status;
}
#endif
NV_STATUS ProviderSession::stop() {
    if (!guard_) return NV_OK;
    if (!ordinaryThread()) return NV_ERR_INVALID_REQUEST;
    lock();
    // Only the first stop caller owns the final release. Followers wait for
    // that epoch to finish; a restart racing their wakeup must not be stopped.
    if (state_ == State::Stopped) { unlock(); return NV_OK; }
    if (state_ == State::Stopping) {
        const NvU64 stoppingGeneration = metadata_.generation;
        while (state_ == State::Stopping && metadata_.generation == stoppingGeneration) wait();
        unlock(); return NV_OK;
    }
    state_ = State::Stopping;
    while (inFlight_ != 0) wait();
    if (provider_) { releaseProvider(); provider_ = nullptr; }
    state_ = State::Stopped;
    wake(); unlock(); return NV_OK;
}
void *ProviderSession::handle() {
    if (!guard_ || !ordinaryThread()) return nullptr;
    lock();
    void *result = state_ == State::Active
        ? reinterpret_cast<void *>(static_cast<NvUPtr>(metadata_.generation)) : nullptr;
    unlock(); return result;
}
NV_STATUS ProviderSession::metadata(Metadata &output) {
    output = {};
    if (!guard_) return NV_ERR_NO_MEMORY;
    if (!ordinaryThread()) return NV_ERR_INVALID_REQUEST;
    lock();
    if (state_ != State::Active) { unlock(); return NV_ERR_NOT_READY; }
    output = metadata_;
    unlock(); return NV_OK;
}
NV_STATUS ProviderSession::lookup(NvU32 segment, NvU8 bus, NvU8 device,
                                  NvU8 function, void **output,
                                  NvU16 *vendor, NvU16 *deviceId) {
    if (vendor) *vendor = 0xffffU;
    if (deviceId) *deviceId = 0xffffU;
    if (!output) return NV_ERR_INVALID_POINTER;
    *output = nullptr;
    if (!guard_) return NV_ERR_NO_MEMORY;
    if (!ordinaryThread()) return NV_ERR_INVALID_REQUEST;
    lock();
    if (state_ != State::Active) { unlock(); return NV_ERR_NOT_READY; }
    if (!metadata_.segmentKnown) { unlock(); return NV_ERR_NOT_SUPPORTED; }
    if (device > 31 || function > 7 || segment != metadata_.segment ||
        bus != metadata_.bus || device != metadata_.device || function != metadata_.function) {
        unlock(); return NV_ERR_OBJECT_NOT_FOUND;
    }
    *output = reinterpret_cast<void *>(static_cast<NvUPtr>(metadata_.generation));
    if (vendor) *vendor = static_cast<NvU16>(metadata_.vendorDevice);
    if (deviceId) *deviceId = static_cast<NvU16>(metadata_.vendorDevice >> 16);
    unlock(); return NV_OK;
}
NV_STATUS ProviderSession::read(void *handleValue, NvU32 offset, NvU32 width, NvU32 &value) {
    value = 0;
    if (!guard_) return NV_ERR_NO_MEMORY;
    if (!ordinaryThread()) return NV_ERR_INVALID_REQUEST;
    if (!validConfigurationAccess(offset, width)) return NV_ERR_INVALID_ARGUMENT;
    lock();
    const NvU64 token = static_cast<NvU64>(reinterpret_cast<NvUPtr>(handleValue));
    if (state_ != State::Active || !token || token != metadata_.generation) {
        unlock(); return NV_ERR_INVALID_STATE;
    }
    if (inFlight_ == ~NvU32{0}) { unlock(); return NV_ERR_NOT_READY; }
    ++inFlight_;
    unlock();
    NvU32 identity = 0, revision = 0, subsystem = 0;
    const bool targetValid = !inactive() && rawRead(0, 4, identity) &&
        rawRead(8, 4, revision) && rawRead(0x2c, 4, subsystem) &&
        exactTarget(identity, revision, subsystem);
    const bool readSucceeded = targetValid && rawRead(offset, width, value) && !inactive();
    if (!readSucceeded) value = 0;
    lock();
    --inFlight_;
    if (!inFlight_) wake();
    unlock();
    return readSucceeded ? NV_OK : (targetValid ? NV_ERR_OPERATING_SYSTEM : NV_ERR_INVALID_STATE);
}
NV_STATUS ProviderSession::readByte(void *token, NvU32 offset, NvU8 *output) {
    if (!output) return NV_ERR_INVALID_POINTER;
    *output = 0;
    NvU32 value = 0; const NV_STATUS status = read(token, offset, 1, value);
    if (status == NV_OK) *output = static_cast<NvU8>(value);
    return status;
}
NV_STATUS ProviderSession::readWord(void *token, NvU32 offset, NvU16 *output) {
    if (!output) return NV_ERR_INVALID_POINTER;
    *output = 0;
    NvU32 value = 0; const NV_STATUS status = read(token, offset, 2, value);
    if (status == NV_OK) *output = static_cast<NvU16>(value);
    return status;
}
NV_STATUS ProviderSession::readDword(void *token, NvU32 offset, NvU32 *output) {
    if (!output) return NV_ERR_INVALID_POINTER;
    *output = 0;
    NvU32 value = 0; const NV_STATUS status = read(token, offset, 4, value);
    if (status == NV_OK) *output = value;
    return status;
}
NvU32 ProviderSession::inFlight() {
    if (!guard_ || !ordinaryThread()) return 0;
    lock(); const NvU32 result = inFlight_; unlock(); return result;
}
bool ProviderSession::active() {
    if (!guard_ || !ordinaryThread()) return false;
    lock(); const bool result = state_ == State::Active; unlock(); return result;
}
} // namespace S540NvidiaRmPci
