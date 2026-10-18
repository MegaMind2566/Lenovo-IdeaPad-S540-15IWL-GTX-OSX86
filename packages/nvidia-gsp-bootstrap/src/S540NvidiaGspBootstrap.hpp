// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_GSP_BOOTSTRAP_HPP
#define S540_NVIDIA_GSP_BOOTSTRAP_HPP
#include "../../nvidia-device-transport/src/S540NvidiaDeviceTransport.hpp"

class IOPCIDevice;
class IOService;

namespace S540NvidiaGspBootstrap {
struct Images {
    const void *gsp;
    NvU64 gspBytes;
    const void *ucodes;
    NvU64 ucodesBytes;
};
enum Gate : NvU32 {
    OriginalAbiClosure = 1U << 0,
    PowerLifetime = 1U << 1,
    AllocationRetirementUnderActiveIrq = 1U << 2,
    OriginalStackBoundary = 1U << 3
};
struct Snapshot {
    NvU32 format;
    NvU32 blockedGates;
    NV_STATUS preparationStatus, initializationStatus, cleanupStatus;
    bool ownsResources, prepared, preparationCompleted, initializationRefused;
    bool hostInitialized, platformBound, transportBound, firmwareBound, timersBound;
    bool firmwareCopied, dmaPolicyAdmitted;
    bool globalInitialized, adapterInitialized, firmwareLoaded;
    bool interruptInstalled, interruptArmed;
    bool cleanupComplete, quarantined, nativeFixture;
};

// Development owner, not an enabled kernel entry point. The ordinary owner
// thread holds the existing outer startup lease for prepare/initialize/stop
// and snapshot. Reads are not independently synchronized against mutation.
// No other standalone/full-RM owner may run before successful stop(). Images
// need remain immutable only during prepare: the retained Store borrows our
// tracked copies, never caller storage.
//
// prepare() success proves only real resource/binding preparation. initialize()
// unconditionally refuses BEFORE every original global/adapter entry: the ABI,
// power lifetime, original stack boundary and allocation retirement while IRQs
// are active are still unresolved. There
// is deliberately no caller-provided readiness flag to bypass those gates.
//
// On any cleanup failure retain this facade and retry stop on its owner thread.
// All implicated storage stays in its heap Impl. Destroying the facade early
// quarantines that Impl permanently rather than invoking member destructors on
// live bindings. Such a leak preserves callbacks' owners; it is a caller error.
class Owner {
public:
    Owner();
    ~Owner();
    NV_STATUS prepare(IOPCIDevice *provider, IOService *service, const Images &);
    NV_STATUS initialize();
    NV_STATUS stop();
    Snapshot snapshot() const;
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
    // Explicit resource fixture, never compiled into the driver. It exercises
    // the same owner with Session's existing native OS-resource backend. The
    // typed Platform/Context fixture supplies no hardware evidence.
    NV_STATUS prepareNativeForTest(IOPCIDevice *,
        const S540NvidiaDeviceTransport::Detail::Backend &, const Images &);
#endif
private:
    struct Impl;
    Impl *impl_;
    Snapshot state_;
    NV_STATUS prepareCommon(IOPCIDevice *, IOService *, const Images &,
        const S540NvidiaDeviceTransport::Detail::Backend *);
    NV_STATUS preparationFailed(NV_STATUS);
    Owner(const Owner &) = delete;
    Owner &operator=(const Owner &) = delete;
};
}
#endif
