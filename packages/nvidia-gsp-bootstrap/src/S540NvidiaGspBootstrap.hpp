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
    bool workerActive, powerDomainJoined, powerOnCompleted, powerRevoked, powerAcknowledged;
    NvU64 workerThread;
};

// Development owner, not an enabled kernel entry point. The ordinary caller
// holds the existing outer startup lease for prepare/initialize/stop. A stable
// persistent worker owns every RM/transport/firmware operation, including PM
// revocation teardown. Public lifecycle calls are externally serialized;
// snapshots are published under a separate guard.
// No other standalone/full-RM owner may run before successful stop(). Images
// need remain immutable only during prepare: the retained Store borrows our
// tracked copies, never caller storage.
//
// prepare() success proves only real resource/binding preparation. initialize()
// unconditionally refuses BEFORE every original global/adapter entry: the ABI,
// original stack boundary and allocation capacity while IRQs are active still
// require validation. The power gate additionally checks the real PM child,
// its completed on transition and monotonic revocation state. There
// is deliberately no caller-provided readiness flag to bypass those gates.
//
// On any cleanup failure retain this facade and retry stop from an ordinary thread.
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
    using NativeAction = NV_STATUS (*)(void *fixture, void *state);
    // Inspection/lease actions on the same real persistent owner thread.
    NV_STATUS runNativeForTest(NativeAction, void *);
    NV_STATUS revokePowerNativeForTest();
    NV_STATUS failPowerAcknowledgementNativeForTest(bool);
#endif
private:
    struct Impl;
    Impl *impl_;
    Snapshot state_;
    NV_STATUS prepareCommon(IOPCIDevice *, IOService *, const Images &,
        const S540NvidiaDeviceTransport::Detail::Backend *);
    Owner(const Owner &) = delete;
    Owner &operator=(const Owner &) = delete;
};
}
#endif
