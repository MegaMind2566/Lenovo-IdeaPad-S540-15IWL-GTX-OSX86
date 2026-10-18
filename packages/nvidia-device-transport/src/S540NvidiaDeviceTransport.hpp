// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_DEVICE_TRANSPORT_HPP
#define S540_NVIDIA_DEVICE_TRANSPORT_HPP
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
class IOPCIDevice;
class IOService;
namespace S540NvidiaDeviceTransport {
constexpr NvU32 kPageBytes = 4096;
constexpr NvU32 kMaximumPages = 8192;
constexpr NvU32 kMaximumAllocations = 32;
enum class Mapper : NvU32 { Unavailable, Device, System, Direct };
// NVIDIA's query chooses whether CPU physical PTEs must pass through the DMA
// mapping callbacks. It is not an IOMMU-presence query. This transport supports
// the explicit, no-bounce mapping path; it does not implement bypass PTEs.
enum class DmaRemapPolicy : NvU32 { Unavailable, MapPhysicalPagesWithoutBounce };
struct Snapshot {
    bool identity;
    bool providerOwned;
    bool memoryDecode;
    bool busMaster;
    bool powerD0;
    bool barMapped;
    bool dmaPolicySettled;
    NvU32 dmaAddressBits;
    Mapper mapper;
    NvU64 barBytes;
    NvU32 segment;
    NvU8 bus;
    NvU8 device;
    NvU8 function;
    bool segmentKnown;
    NvU32 interruptType;
    bool interruptTypeKnown;
    bool messageSignaled;
    bool msiEnabled;
    bool msixEnabled;
};
// An adapter must provide the actual NVIDIA ISR/fault-copy operation, both
// serialized bottom halves and hardware interrupt masking. No synthetic
// callback or guessed register acknowledgement is supplied by this package.
struct InterruptContract {
    void *context;
    bool (*top)(void *context, bool &lockedBottomHalf, bool &unlockedBottomHalf);
    void (*lockedBottomHalf)(void *context);
    void (*unlockedBottomHalf)(void *context);
    // A successful mask is persistent: subsequent original ISR/bottom-half
    // completion cannot re-enable the hardware source. stop retries may reuse
    // that success instead of calling a non-idempotent adapter disable again.
    NV_STATUS (*maskHardware)(void *context);
    bool (*readyToArm)(void *context);
};
struct InterruptStatistics {
    NvU64 controllerCallbacks;
    NvU64 rmHandledCallbacks;
    NvU64 lockedBottomHalves;
    NvU64 unlockedBottomHalves;
};
struct RetirementStatistics {
    NvU32 allocations;
    NvU32 dmaMappings;
    NvU32 pages;
};
namespace Detail {
// Shared state-machine boundary. Native tests replace only these OS/resource
// operations; the kernel path supplies real IOPCIDevice/IODMACommand ownership.
struct Backend {
    void *context;
    bool (*ordinary)(void *);
    NV_STATUS (*start)(void *, Snapshot &);
    NV_STATUS (*stop)(void *);
    bool (*live)(void *);
    NV_STATUS (*readIdentification)(void *, NvU32, NvU32 &);
    NV_STATUS (*allocate)(void *, NvU32, bool, NvU32, void **, NvU8 **);
    NV_STATUS (*pageAddress)(void *, void *, NvU32, bool, NvU64 &);
    NV_STATUS (*mapDma)(void *, void *, NvU32);
    NV_STATUS (*unmapDma)(void *, void *);
    NV_STATUS (*releaseAllocation)(void *, void *);
    NV_STATUS (*installInterrupt)(void *, const InterruptContract &);
    NV_STATUS (*armInterrupt)(void *);
    NV_STATUS (*stopInterrupt)(void *);
    NV_STATUS (*registerGeometry)(void *, NvU64 &, NvU64 &);
    NV_STATUS (*mapRegisters)(void *, NvU64, NvU64, void **);
    NV_STATUS (*unmapRegisters)(void *, void *, NvU64);
    NV_STATUS (*configRead)(void *, NvU32, NvU32, NvU32 &);
    NV_STATUS (*configWrite)(void *, NvU32, NvU32, NvU32);
    InterruptStatistics (*interruptStatistics)(void *);
    NV_STATUS (*dmaRemapPolicy)(void *, DmaRemapPolicy &);
    NV_STATUS (*validateRetainedDma)(void *, void *, NvU32);
};
}
// Ordinary-thread, externally serialized owner. No GPU command is submitted.
// No caller may access object storage concurrently with stop/destruction.
// If stop() fails to quiesce hardware, preserve this object and all allocation
// tokens until a later successful stop; destroying it then is a caller error.
class Session {
public:
    Session();
    ~Session();
    NV_STATUS start(const Detail::Backend &backend);
#if defined(KERNEL)
    NV_STATUS start(IOPCIDevice *provider, IOService *owner);
#endif
    NV_STATUS stop();
    NV_STATUS setRmBinding(bool bound);
    bool active() const;
    Snapshot snapshot() const;
    void *pciHandle() const;
    NV_STATUS readIdentification(NvU32 offset, NvU32 &value);
    NV_STATUS setPciSegment(NvU32 segment);
    NV_STATUS readConfig(NvU32 offset, NvU32 width, NvU32 &value);
    NV_STATUS writeConfig(NvU32 offset, NvU32 width, NvU32 value);
    bool accessible();
    NV_STATUS registerGeometry(NvU64 &physical, NvU64 &bytes);
    NV_STATUS mapRegisters(NvU64 physical, NvU64 bytes, void **address);
    NV_STATUS unmapRegisters(void *address, NvU64 bytes);
    NV_STATUS physicalAddressForHost(NvU64 host, NvU64 &physical);
    // Allocation publishes per-page CPU physical addresses atomically; mapDma
    // publishes device addresses only after complete translation validation.
    // Refusal/failure preserves all caller outputs and input ownership.
    NV_STATUS allocate(NvU32 pages, NvU64 *physicalPages, void **token, bool contiguous = false, NvU32 cache = 0);
    NV_STATUS setDmaAddressSize(NvU32 bits);
    // Checked admission for the scalar NVIDIA ABI. Failure preserves output;
    // callers must pass this gate before an RM entry can reach that callback.
    NV_STATUS requiresDmaRemap(NvBool &required);
    NV_STATUS mapDma(void *token, NvU64 *devicePages);
    NV_STATUS unmapDma(void *token, NvU64 *physicalPages);
    // Exact bound-RM ownership transfers. While an IRQ enable attempt remains
    // undrained, acknowledge logical retirement but retain the same non-reusable
    // backing and IOVA. Generic release/unmap keep their stronger IRQ guard.
    NV_STATUS releaseRmAllocation(void *token, bool &deferred);
    // Preserve a logically freed allocation after a void CPU-unmap callback
    // cannot report a backend completion error to the original owner.
    NV_STATUS retainRmAllocation(void *token);
    NV_STATUS unmapRmDma(void *token, NvU64 *physicalPages, bool &deferred);
    NV_STATUS reclaimRmRetirement(void *token);
    RetirementStatistics retirementStatistics() const;
    NV_STATUS address(void *token, NvU32 page, NvU64 &deviceAddress);
    NV_STATUS borrowHost(void *token, NvU64 offset, NvU64 length, void **address);
    NV_STATUS hostWrite(void *token, NvU64 offset, const void *bytes, NvU64 length);
    NV_STATUS hostRead(void *token, NvU64 offset, void *bytes, NvU64 length);
    NV_STATUS release(void *token);
    NV_STATUS installInterrupt(const InterruptContract &contract);
    NV_STATUS armInterrupt();
    NV_STATUS stopInterrupt();
    bool interruptInstalled() const;
    bool interruptArmed() const;
    InterruptStatistics interruptStatistics() const;
    // Kernel firmware delivery and dynamic ACPI/D3 transitions need a real
    // rm_init_adapter context. Explicit refusal, never successful no-ops.
    NV_STATUS deliverFirmware(const void *, NvU64);
    NV_STATUS transitionPower(NvU32);
private:
    struct Allocation {
        NvU64 generation;
        void *resource;
        NvU8 *host;
        NvU32 pages;
        bool contiguous;
        bool mapped;
        bool dmaRetired;
        bool retired;
    } allocations_[kMaximumAllocations];
    Detail::Backend backend_;
    Snapshot snapshot_;
    InterruptContract interruptContract_;
    void *pciHandle_;
    bool active_;
    bool irqInstalled_;
    bool irqArmed_;
    // An unsuccessful controller-enable call may have had partial effects.
    // Keep all addressable storage until stopInterrupt has drained that attempt.
    bool irqArmAttempted_;
    bool platformOwned_;
    bool rmBound_;
    Allocation *find(void *token);
    Allocation *findOwned(void *token);
    bool ordinary() const;
    bool live() const;
    NV_STATUS releaseEntry(Allocation &entry);
    Session(const Session &) = delete;
    Session &operator=(const Session &) = delete;
};
struct Result {
    NvU32 checks;
    NvU32 failures;
    bool owner;
    bool mmio;
    bool dmaAddresses;
    bool dmaUnavailable;
    bool dmaLifecycle;
    bool interruptRefusal;
    bool adapterGates;
    bool cleanup;
    bool deviceTransferVerified;
    bool interruptsRegistered;
    bool interruptsEnabled;
    Mapper mapper;
    bool passed() const {
        return checks && !failures && owner && mmio &&
            (dmaAddresses || dmaUnavailable) && dmaLifecycle && interruptRefusal && adapterGates && cleanup &&
            !deviceTransferVerified && !interruptsRegistered && !interruptsEnabled;
    }
};
// Finite startup evidence only. The provider must already be D0 and have
// memory decoding enabled; no PCI command/PM register is modified.
Result check(const Detail::Backend &backend);
#if defined(KERNEL)
Result check(IOPCIDevice *provider, IOService *owner);
#endif
enum class PciWriteKind : NvU32 { Refused, CommandBusMaster, RomDisable, LatencySetup };
PciWriteKind pciWriteKind(NvU32 offset, NvU32 width, NvU32 previous, NvU32 value);
bool dmaPageMatches(NvU64 originalPhysical, NvU64 deviceAddress, NvU64 translatedPhysical, NvU32 addressBits);
Mapper selectMapperPolicy(bool providerPropertyPresent, bool publishedDeviceMapper,
                          bool systemMapperAbsent);
const char *mapperName(Mapper mapper);
} // namespace S540NvidiaDeviceTransport
#endif
