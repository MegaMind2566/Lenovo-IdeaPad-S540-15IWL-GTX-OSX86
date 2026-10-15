// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_PROVIDER_SESSION_HPP
#define S540_NVIDIA_PROVIDER_SESSION_HPP
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#if defined(KERNEL)
class IOPCIDevice;
#endif
namespace S540NvidiaRmPci {
constexpr NvU32 kConfigurationBytes = 4096;
struct Metadata {
    NvU64 generation;
    NvU32 vendorDevice;
    NvU32 revisionClass;
    NvU32 subsystem;
    NvU32 segment;
    NvU8 bus;
    NvU8 device;
    NvU8 function;
    bool segmentKnown;
    bool identityVerified;
    bool readOnly;
    bool providerOpened;
};

// ProviderSession owns exactly one retained PCI provider. It does not call
// open(), change PCI configuration, register interrupts or map GPU memory.
// This is retained read-only observation, not exclusive hardware ownership.
//
// Construct/start/read/stop/destruct only from ordinary schedulable threads
// with interrupts enabled. Kernel start/read callers must hold provider
// arbitration on the calling thread; retained observation does not replace
// that ownership/state guard. The shared startup lease is supplied by the
// aggregate caller. lockForArbitration(false) is not a nonblocking try-lock.
// Native reads may run concurrently. stop() rejects new
// leases, waits for all accepted reads to finish, then releases the provider.
// Its caller must not be executing this session's backend read callback or
// hold provider arbitration while waiting for a different accepted reader that
// needs that same arbitration guard. The finite startup check has no workers.
// Destroy object storage only when no other thread can enter its API.
class ProviderSession {
public:
    ProviderSession();
    ~ProviderSession();
    bool ready() const;
#if defined(KERNEL)
    NV_STATUS start(IOPCIDevice *provider);
#else
    struct Backend {
        void *provider;
        bool (*retain)(void *);
        void (*release)(void *);
        bool (*read)(void *, NvU32 offset, NvU32 width, NvU32 &value);
        bool (*inactive)(void *);
        bool (*bdf)(void *, NvU8 &bus, NvU8 &device, NvU8 &function);
        // Test-only explicitly verified fixture identity. The production
        // IOPCIDevice backend never guesses a PCI segment from domain-id.
        bool segmentKnown;
        NvU32 segment;
    };
    NV_STATUS startNative(const Backend &backend);
#endif
    NV_STATUS stop();
    // Opaque monotonically generated tokens, never pointers to object memory.
    // They are consumed only by these read methods / a future exact C bridge.
    void *handle();
    NV_STATUS metadata(Metadata &output);
    NV_STATUS lookup(NvU32 segment, NvU8 bus, NvU8 device, NvU8 function,
                     void **output, NvU16 *vendor, NvU16 *deviceId);
    NV_STATUS readByte(void *handle, NvU32 offset, NvU8 *output);
    NV_STATUS readWord(void *handle, NvU32 offset, NvU16 *output);
    NV_STATUS readDword(void *handle, NvU32 offset, NvU32 *output);
    NvU32 inFlight();
    bool active();
private:
    enum class State : NvU32 { Stopped, Active, Stopping };
    void *guard_;
    void *provider_;
#if !defined(KERNEL)
    Backend backend_;
#endif
    State state_;
    NvU32 inFlight_;
    Metadata metadata_;
    void lock();
    void unlock();
    void wait();
    void wake();
    bool rawRead(NvU32 offset, NvU32 width, NvU32 &value);
    bool inactive();
    bool retainProvider();
    void releaseProvider();
    bool captureBdf(NvU8 &, NvU8 &, NvU8 &);
    NV_STATUS startLocked();
    NV_STATUS read(void *handle, NvU32 offset, NvU32 width, NvU32 &value);
    ProviderSession(const ProviderSession &) = delete;
    ProviderSession &operator=(const ProviderSession &) = delete;
};
inline bool validConfigurationAccess(NvU32 offset, NvU32 width) {
    return (width == 1 || width == 2 || width == 4) &&
        offset < kConfigurationBytes && width <= kConfigurationBytes - offset &&
        (offset & (width - 1)) == 0;
}
struct Result {
    NvU32 checks;
    NvU32 failures;
    bool session;
    bool reads;
    bool handles;
    bool lifecycle;
    bool cleanup;
    bool passed() const {
        return checks != 0 && failures == 0 && session && reads && handles && lifecycle && cleanup;
    }
};
// Finite startup check, without workers, fault injection, PCI writes or IRQ
// registration. The kernel check owns provider arbitration for its finite
// single-thread sequence; framework arbitration may wait and is not a try-lock.
// The integrated startup lease is supplied by the caller. The session is
// stopped before returning; reusable
// APIs exist for a later true owner, but this check leaves no persistent session.
#if defined(KERNEL)
Result check(IOPCIDevice *provider);
#else
Result check();
#endif
} // namespace S540NvidiaRmPci
#endif
