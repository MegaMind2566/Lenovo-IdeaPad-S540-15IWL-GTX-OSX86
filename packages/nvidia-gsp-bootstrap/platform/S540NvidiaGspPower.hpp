// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_GSP_POWER_HPP
#define S540_NVIDIA_GSP_POWER_HPP
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
class IOPCIDevice;
namespace S540NvidiaGspPower {
// A real, preallocated asynchronous request to the persistent RM owner thread.
// Success means enqueued only; it is never an acknowledgement of quiescence.
struct Revocation { void *owner; NV_STATUS (*requestStop)(void *); };
struct Snapshot {
    bool retained, domainJoined, onRequested, onSet, onCompleted;
    bool revoked, acknowledgementPending, acknowledgementSent, stopped;
    bool nativeFixture;
    NvU32 callbacks, revocationPosts, postFailures, revocationHooksInFlight;
    NvU64 revokedAtNs;
};
namespace Detail {
// Callback protocol shared by the actual IOService and explicit native event
// fixtures. All events are serialized by the service guard, not caller flags.
class Protocol {
public:
    Protocol();
    void requested();
    bool setState(bool on); // true only when a stop must actually be posted
    void revocationObserved(NvU64 eventNs);
    void completed();
    void posted(NV_STATUS);
    void acknowledged();
    void stopped();
    bool ready() const;
    Snapshot snapshot() const;
private:
    Snapshot state_;
    bool lastOn_;
};
}
// One stable ordinary RM owner thread owns start/status/acknowledge/stop.
// IOService PM callbacks run elsewhere and may only enqueue revocation.
// A PM down request is acknowledged only after the owner has actually drained
// original RM, interrupts, DMA and MMIO. Failed cleanup keeps this lease and
// the power-service callback owner alive; no optimistic ack is submitted.
// Stop also requires every external revocation hook to have returned; Apple's
// bounded PMstop wait cannot serve as the outer callback owner's barrier.
// This cannot prevent emergency power loss or Apple's PM timeout escalation.
class Lease {
public:
    Lease();
    ~Lease();
    NV_STATUS start(IOPCIDevice *, const Revocation &);
    NV_STATUS status() const;
    NV_STATUS acknowledgeRevocation();
    NV_STATUS stop();
    Snapshot snapshot() const;
#if defined(S540_GSP_BOOTSTRAP_NATIVE_TEST) && !defined(KERNEL)
    NV_STATUS startNativeForTest(const Revocation &);
    NV_STATUS revokeNativeForTest();
    void failAcknowledgementNativeForTest(bool);
#endif
private:
    struct Impl;
    Impl *impl_;
    Snapshot final_;
    Lease(const Lease &) = delete;
    Lease &operator=(const Lease &) = delete;
};
}
#endif
