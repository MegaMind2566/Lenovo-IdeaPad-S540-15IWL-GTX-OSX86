// SPDX-License-Identifier: MIT
#include "S540NvidiaGspPower.hpp"
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"

namespace S540NvidiaGspPower::Detail {
Protocol::Protocol() : state_{}, lastOn_(false) {}
void Protocol::requested() { state_.onRequested = true; }
bool Protocol::setState(bool on) {
    ++state_.callbacks; lastOn_ = on;
    if (on) { state_.onSet = true; return false; }
    // The initial off callback has no active device state to retire. Every
    // down after an on callback is a monotonic revocation, including a down
    // racing the initial on completion.
    if (!state_.onSet || state_.stopped) return false;
    state_.revoked = true; state_.onCompleted = false;
    if (state_.acknowledgementPending || state_.acknowledgementSent) return false;
    state_.acknowledgementPending = true;
    return true;
}
void Protocol::completed() {
    if (lastOn_ && state_.onSet && !state_.revoked && !state_.stopped)
        state_.onCompleted = true;
}
void Protocol::posted(NV_STATUS status) {
    ++state_.revocationPosts;
    if (status != NV_OK) ++state_.postFailures;
}
void Protocol::acknowledged() {
    state_.acknowledgementPending = false;
    state_.acknowledgementSent = true;
}
void Protocol::stopped() { state_.stopped = true; state_.onCompleted = false; }
bool Protocol::ready() const {
    return state_.onRequested && state_.onSet && state_.onCompleted &&
        !state_.revoked && !state_.stopped;
}
Snapshot Protocol::snapshot() const { return state_; }
}

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <IOKit/IOService.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <IOKit/pwr_mgt/IOPM.h>
#include <IOKit/pwr_mgt/IOPowerConnection.h>
#include <kern/clock.h>
#include <kern/thread.h>
#include <libkern/c++/OSObject.h>
#include "S540NvidiaGspPowerService.hpp"

namespace S540GspPowerKernel {
using namespace S540NvidiaGspPower;
constexpr UInt32 kOnWaitMs = 5000;
constexpr IOReturn kDropDeadlineUs = 30000000;
bool S540NvidiaGspPowerService::init(OSDictionary *properties) {
        if (!IOService::init(properties)) return false;
        guard = IOLockAlloc();
        return guard != nullptr;
    }

void S540NvidiaGspPowerService::free() {
        // finish closes new external hooks only after their own count reaches
        // zero. PMstop's driver-callout wait is bounded; its asynchronous PM
        // request retains this IOService until PM-tree detach completes.
        if (endpoint) endpoint->release();
        if (guard) IOLockFree(guard);
        IOService::free();
    }

bool S540NvidiaGspPowerService::join(IOPCIDevice *provider, const Revocation &action) {
        endpoint = provider; endpoint->retain(); revocation = action;
        if (!attach(provider)) return false;
        attached = true;
        if (!IOService::start(provider)) return false;
        setName("S540NvidiaGspPowerLease");
        PMinit(); pmInitialized = true;
        // A dedicated PM child owns its own desire; it never overwrites the
        // IOPCIDevice nub's existing driver-policy or private request.
        IOPMPowerState states[2]{};
        states[0].version = 1;
        states[1].version = 1;
        states[1].capabilityFlags = kIOPMPowerOn | kIOPMDeviceUsable | kIOPMPreventIdleSleep;
        states[1].inputPowerRequirement = kIOPMPowerOn;
        if (registerPowerDriver(this, states, 2) != kIOReturnSuccess) return false;
        if (changePowerStateTo(0) != kIOReturnSuccess) return false;
        if (provider->addPowerChild(this) != kIOReturnSuccess) return false;
        if (changePowerStateToPriv(1) != kIOReturnSuccess) return false;
        IOLockLock(guard); protocol.requested(); IOLockUnlock(guard);
        return true;
    }

bool S540NvidiaGspPowerService::exactDomain() const {
        // addPowerChild may report success even when no connection was made.
        // Verify the actual retained endpoint is our power-plane parent.
        IORegistryEntry *connection = copyParentEntry(gIOPowerPlane);
        IORegistryEntry *parent = connection ? connection->copyParentEntry(gIOPowerPlane) : nullptr;
        const bool exact = OSDynamicCast(IOPowerConnection, connection) && parent == endpoint;
        if (parent) parent->release();
        if (connection) connection->release();
        return exact;
    }

IOReturn S540NvidiaGspPowerService::setPowerState(unsigned long ordinal, IOService *device) {
        if (device != this || ordinal > 1) return kIOPMAckImplied;
        IOLockLock(guard);
        if (closing) { IOLockUnlock(guard); return kIOPMAckImplied; }
        const bool post = protocol.setState(ordinal == 1);
        const bool pending = protocol.snapshot().acknowledgementPending;
        // This independent count protects the outer owner even if Apple's
        // PM driver-callout timeout expires. Capture the hook under the same
        // guard as closing, and never touch its owner after decrementing.
        const Revocation action = revocation;
        if (post) ++revocationHooksInFlight;
        IOLockWakeup(guard, this, false); IOLockUnlock(guard);
        if (post) {
            const NV_STATUS status = action.requestStop(action.owner);
            IOLockLock(guard); protocol.posted(status);
            --revocationHooksInFlight; IOLockUnlock(guard);
        }
        // An enqueued stop is NOT an acknowledgement. Apple's own timeout is
        // bounded; failed cleanup remains visible and never submits a false ack.
        return pending ? kDropDeadlineUs : kIOPMAckImplied;
    }

void S540NvidiaGspPowerService::powerChangeDone(unsigned long previous) {
        IOService::powerChangeDone(previous);
        IOLockLock(guard); protocol.completed();
        IOLockWakeup(guard, this, false); IOLockUnlock(guard);
    }

NV_STATUS S540NvidiaGspPowerService::waitOn() {
        uint64_t deadline = 0;
        clock_interval_to_deadline(kOnWaitMs, kMillisecondScale, &deadline);
        IOLockLock(guard);
        while (!protocol.ready() && !protocol.snapshot().revoked) {
            const int result = IOLockSleepDeadline(guard, this, deadline, THREAD_UNINT);
            if (result == THREAD_TIMED_OUT) break;
        }
        const bool ready = protocol.ready();
        IOLockUnlock(guard);
        return ready && exactDomain() && !endpoint->isInactive() ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);
    }

Snapshot S540NvidiaGspPowerService::snapshot() const {
        IOLockLock(guard); Snapshot result = protocol.snapshot();
        result.revocationHooksInFlight = revocationHooksInFlight; IOLockUnlock(guard);
        result.retained = true; result.domainJoined = exactDomain();
        return result;
    }

NV_STATUS S540NvidiaGspPowerService::acknowledge() {
        IOLockLock(guard); const auto state = protocol.snapshot(); IOLockUnlock(guard);
        if (!state.acknowledgementPending) return NV_OK;
        // IOServicePM explicitly accepts this acknowledgement even if the
        // original setPowerState call is still in flight (fDriverTimer == -1).
        if (acknowledgeSetPowerState() != kIOReturnSuccess) return NV_ERR_OPERATING_SYSTEM;
        IOLockLock(guard); protocol.acknowledged(); IOLockUnlock(guard);
        return NV_OK;
    }

NV_STATUS S540NvidiaGspPowerService::finish() {
        IOLockLock(guard);
        if (protocol.snapshot().acknowledgementPending || revocationHooksInFlight) {
            IOLockUnlock(guard); return NV_ERR_IN_USE;
        }
        closing = true; IOLockUnlock(guard);
        if (pmInitialized) { PMstop(); pmInitialized = false; }
        IOLockLock(guard); protocol.stopped(); IOLockUnlock(guard);
        if (attached) { IOService::stop(endpoint); detach(endpoint); attached = false; }
        return NV_OK;
    }

OSDefineMetaClassAndStructors(S540NvidiaGspPowerService, IOService);
}
struct S540NvidiaGspPower::Lease::Impl {
    S540GspPowerKernel::S540NvidiaGspPowerService *service;
    NvU64 ownerThread;
};
#else
#include <cstdlib>
#include <mutex>
struct S540NvidiaGspPower::Lease::Impl {
    mutable std::mutex guard;
    Detail::Protocol protocol;
    Revocation revocation;
    NvU64 ownerThread;
    NvU32 revocationHooksInFlight;
    bool failAck;
};
#endif

namespace S540NvidiaGspPower {
namespace {
NvU64 ordinaryThread() {
    NvU64 thread = 0;
    return s540Darwin_os_semaphore_may_sleep() &&
        s540Darwin_os_get_current_thread(&thread) == NV_OK ? thread : 0;
}
}
Lease::Lease() : impl_(nullptr), final_{} {}
Lease::~Lease() {
    // Explicit stop only: a caller that abandons failed cleanup keeps every
    // callback owner retained instead of deleting a live PM service.
}
NV_STATUS Lease::start(IOPCIDevice *provider, const Revocation &action) {
    const NvU64 thread = ordinaryThread();
    if (!thread || !provider || !action.owner || !action.requestStop) return NV_ERR_INVALID_ARGUMENT;
    if (impl_) return NV_ERR_STATE_IN_USE;
#if defined(KERNEL)
    auto *data = static_cast<Impl *>(IOMalloc(sizeof(Impl)));
    if (!data) return NV_ERR_NO_MEMORY;
    *data = Impl{}; data->ownerThread = thread;
    auto *service = new S540GspPowerKernel::S540NvidiaGspPowerService;
    if (!service) { IOFree(data, sizeof(Impl)); return NV_ERR_NO_MEMORY; }
    if (!service->init()) { service->release(); IOFree(data, sizeof(Impl)); return NV_ERR_NO_MEMORY; }
    data->service = service; impl_ = data;
    if (!service->join(provider, action)) return NV_ERR_NOT_READY;
    return service->waitOn();
#else
    (void)provider; (void)action;
    return NV_ERR_NOT_SUPPORTED;
#endif
}
NV_STATUS Lease::status() const {
    if (!impl_ || !ordinaryThread() || ordinaryThread() != impl_->ownerThread) return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    const auto state = impl_->service->snapshot();
    return state.onRequested && state.onCompleted && state.domainJoined &&
        !state.revoked && !state.stopped && !impl_->service->endpoint->isInactive() ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);
#else
    std::lock_guard<std::mutex> lock(impl_->guard);
    return impl_->protocol.ready() ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_NOT_READY);
#endif
}
NV_STATUS Lease::acknowledgeRevocation() {
    if (!impl_) return NV_OK;
    if (!ordinaryThread() || ordinaryThread() != impl_->ownerThread) return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    return impl_->service->acknowledge();
#else
    std::lock_guard<std::mutex> lock(impl_->guard);
    if (impl_->failAck) return NV_ERR_OPERATING_SYSTEM;
    if (impl_->protocol.snapshot().acknowledgementPending) impl_->protocol.acknowledged();
    return NV_OK;
#endif
}
NV_STATUS Lease::stop() {
    if (!impl_) return NV_OK;
    if (!ordinaryThread() || ordinaryThread() != impl_->ownerThread) return NV_ERR_INVALID_STATE;
#if defined(KERNEL)
    NV_STATUS status = impl_->service->finish();
    if (status != NV_OK) return status;
    final_ = impl_->service->snapshot(); final_.retained = false;
    impl_->service->release(); IOFree(impl_, sizeof(Impl)); impl_ = nullptr;
#else
    {
        std::lock_guard<std::mutex> lock(impl_->guard);
        if (impl_->protocol.snapshot().acknowledgementPending || impl_->revocationHooksInFlight)
            return NV_ERR_IN_USE;
        impl_->protocol.stopped(); final_ = impl_->protocol.snapshot();
        final_.nativeFixture = true;
    }
    delete impl_; impl_ = nullptr;
#endif
    return NV_OK;
}
Snapshot Lease::snapshot() const {
    if (!impl_) return final_;
#if defined(KERNEL)
    return impl_->service->snapshot();
#else
    std::lock_guard<std::mutex> lock(impl_->guard);
    Snapshot result = impl_->protocol.snapshot();
    result.revocationHooksInFlight = impl_->revocationHooksInFlight;
    result.retained = result.domainJoined = result.nativeFixture = true;
    return result;
#endif
}
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
NV_STATUS Lease::startNativeForTest(const Revocation &action) {
    NvU64 thread = ordinaryThread();
    if (!thread || !action.owner || !action.requestStop) return NV_ERR_INVALID_ARGUMENT;
    if (impl_) return NV_ERR_STATE_IN_USE;
    impl_ = new Impl{}; impl_->ownerThread = thread; impl_->revocation = action;
    impl_->protocol.requested(); impl_->protocol.setState(true); impl_->protocol.completed();
    return NV_OK;
}
NV_STATUS Lease::revokeNativeForTest() {
    if (!impl_) return NV_ERR_INVALID_STATE;
    // Matches the actual PM callback's guarded state event. The fixture caller
    // ensures callback entry precedes concurrent stop; it need not be the RM
    // thread. The live hook count then prevents stop from deleting its storage.
    Impl *data = impl_;
    Revocation action{};
    {
        std::lock_guard<std::mutex> lock(data->guard);
        if (!data->protocol.setState(false)) return NV_ERR_IN_USE;
        action = data->revocation; ++data->revocationHooksInFlight;
    }
    const NV_STATUS status = action.requestStop(action.owner);
    {
        std::lock_guard<std::mutex> lock(data->guard);
        data->protocol.posted(status); --data->revocationHooksInFlight;
    }
    return status;
}
void Lease::failAcknowledgementNativeForTest(bool failed) {
    if (impl_) { std::lock_guard<std::mutex> lock(impl_->guard); impl_->failAck = failed; }
}
#endif
}
