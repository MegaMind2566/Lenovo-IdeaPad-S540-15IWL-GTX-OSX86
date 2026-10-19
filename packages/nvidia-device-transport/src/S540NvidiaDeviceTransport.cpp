// SPDX-License-Identifier: MIT
#include "S540NvidiaDeviceTransport.hpp"
namespace {
NvU64 nextGeneration = 0;
static_assert(__atomic_always_lock_free(sizeof(nextGeneration), nullptr),
              "Device allocation token generation must not require a runtime lock.");
NvU64 generation() {
    NvU64 current = __atomic_load_n(&nextGeneration, __ATOMIC_RELAXED);
    do {
        if (current >= (~NvU64(0) >> 1)) return 0;
    } while (!__atomic_compare_exchange_n(&nextGeneration, &current, current + 1,
                   false, __ATOMIC_RELAXED, __ATOMIC_RELAXED));
    return current + 1;
}
void bytesCopy(void *destination, const void *source, NvU64 length) {
    auto *out = static_cast<NvU8 *>(destination);
    const auto *in = static_cast<const NvU8 *>(source);
    for (NvU64 i = 0; i != length; ++i) out[i] = in[i];
}
}
namespace S540NvidiaDeviceTransport {
namespace {
bool directFactsAdmitProbe(const Detail::DirectRouteFacts &facts) {
    return facts.platformIdentity && facts.platformLive && !facts.platformMapperPresent &&
           !facts.providerMapperPresent && facts.factoryWouldNotWait;
}
}
NV_STATUS Detail::attestDirectRoute(const DirectRouteBackend &backend) {
    if (!backend.context || !backend.observe || !backend.createBypassProbe ||
        !backend.releaseBypassProbe) return NV_ERR_INVALID_ARGUMENT;
    DirectRouteFacts before{};
    NV_STATUS status = backend.observe(backend.context, before);
    if (status != NV_OK) return status;
    if (!directFactsAdmitProbe(before)) return NV_ERR_NOT_SUPPORTED;
    void *probe = nullptr;
    status = backend.createBypassProbe(backend.context, &probe);
    if (status == NV_OK && !probe) status = NV_ERR_NOT_SUPPORTED;
    if (status == NV_OK) {
        DirectRouteFacts after{};
        status = backend.observe(backend.context, after);
        if (status == NV_OK && (!directFactsAdmitProbe(after) ||
            after.platformIdentity != before.platformIdentity)) status = NV_ERR_NOT_SUPPORTED;
    }
    if (probe) backend.releaseBypassProbe(backend.context, probe);
    return status;
}
NV_STATUS Detail::readPciPdi(const PciDwordReader &reader, NvU64 &pdi) {
    if (!reader.context || !reader.read) return NV_ERR_INVALID_ARGUMENT;
    // kernel-open/common/inc/nv-pci.h and nv-pci.c:3054-3257, pinned 615.78.08.
    constexpr NvU32 first = 0x100, end = 0x1000, iterations = (end - first) / 8;
    constexpr NvU32 dvsecId = 0x23, vendor = 0x10de, designatedId = 3, minimumBytes = 0x14;
    NvU32 offset = first;
    for (NvU32 i = 0; i != iterations; ++i) {
        if (offset < first || offset >= end || (offset & 3)) return NV_ERR_INVALID_OFFSET;
        NvU32 header = 0;
        if (reader.read(reader.context, offset, header) != NV_OK) return NV_ERR_INVALID_READ;
        if ((header & 0xffff) == dvsecId) {
            NvU32 header1 = 0, header2 = 0;
            if (reader.read(reader.context, offset + 4, header1) != NV_OK ||
                reader.read(reader.context, offset + 8, header2) != NV_OK)
                return NV_ERR_INVALID_READ;
            if ((header1 & 0xffff) == vendor && (header2 & 0xffff) == designatedId) {
                const NvU32 length = (header1 >> 20) & 0xfff;
                if (length < minimumBytes) return NV_ERR_INVALID_DATA;
                if (offset > end - minimumBytes) return NV_ERR_INVALID_OFFSET;
                NvU32 low = 0, high = 0;
                if (reader.read(reader.context, offset + 0xc, low) != NV_OK ||
                    reader.read(reader.context, offset + 0x10, high) != NV_OK)
                    return NV_ERR_INVALID_READ;
                const NvU64 captured = (NvU64(high) << 32) | low;
                if (!captured || captured == ~NvU64(0)) return NV_ERR_NOT_SUPPORTED;
                pdi = captured;
                return NV_OK;
            }
        }
        offset = (header >> 20) & 0xfff;
        if (!offset) return NV_ERR_NOT_SUPPORTED;
    }
    return NV_ERR_CYCLE_DETECTED;
}
#if defined(KERNEL)
void destroyDarwinBackend(void *);
#endif
Session::Session() : allocations_{}, backend_{}, snapshot_{}, interruptContract_{}, pciHandle_(nullptr), active_(false),
    irqInstalled_(false), irqArmed_(false), irqArmAttempted_(false), platformOwned_(false), rmBound_(false),
    hardwareDmaHeld_(false), hardwareDmaState_(nullptr), hardwareDmaGeneration_(0) {}
// Ordinary use always closes successfully. Failed quiescence deliberately
// preserves kernel resources, rather than returning DMA storage to the VM.
Session::~Session() { (void)stop(); }
bool Session::ordinary() const { return backend_.ordinary && backend_.ordinary(backend_.context); }
bool Session::live() const { return active_ && backend_.live && backend_.live(backend_.context); }
bool Session::active() const { return active_; }
Snapshot Session::snapshot() const { return snapshot_; }
void *Session::pciHandle() const { return active_ ? pciHandle_ : nullptr; }
NV_STATUS Session::start(const Detail::Backend &backend) {
    if (active_ || backend_.context) return NV_ERR_STATE_IN_USE;
    if (!backend.context || !backend.ordinary || !backend.start || !backend.stop ||
        !backend.live || !backend.readIdentification || !backend.allocate ||
        !backend.releaseAllocation || !backend.pageAddress || !backend.mapDma ||
        !backend.unmapDma || !backend.installInterrupt ||
        !backend.armInterrupt || !backend.stopInterrupt) return NV_ERR_INVALID_ARGUMENT;
    if (!backend.ordinary(backend.context)) return NV_ERR_INVALID_STATE;
    Snapshot captured{};
    NV_STATUS status = backend.start(backend.context, captured);
    if (status != NV_OK) return status;
    if (!captured.identity || !captured.providerOwned || !captured.memoryDecode ||
        !captured.powerD0 || !captured.barMapped || captured.barBytes < 0x1804) {
        const NV_STATUS cleaned = backend.stop(backend.context);
        if (cleaned != NV_OK) {
            backend_ = backend; snapshot_ = captured; active_ = true;
            return cleaned;
        }
        return NV_ERR_INVALID_STATE;
    }
    const NvU64 id = generation();
    if (!id) {
        const NV_STATUS cleaned = backend.stop(backend.context);
        if (cleaned != NV_OK) { backend_ = backend; snapshot_ = captured; active_ = true; return cleaned; }
        return NV_ERR_INSUFFICIENT_RESOURCES;
    }
    backend_ = backend;
    snapshot_ = captured;
    pciHandle_ = reinterpret_cast<void *>(static_cast<NvUPtr>(id | (NvU64(1) << 63)));
    active_ = true;
    return NV_OK;
}
NV_STATUS Session::readIdentification(NvU32 offset, NvU32 &value) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    // Only NVIDIA public read-only PMC_BOOT_0 and PBUS_PCI_NV_0 are exposed.
    if (offset != 0 && offset != 0x1800) return NV_ERR_NOT_SUPPORTED;
    if (snapshot_.barBytes < 4 || offset > snapshot_.barBytes - 4)
        return NV_ERR_INVALID_ADDRESS;
    NvU32 captured = 0;
    NV_STATUS status = backend_.readIdentification(backend_.context, offset, captured);
    if (status == NV_OK) value = captured;
    return status;
}
NV_STATUS Session::setPciSegment(NvU32 segment) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    snapshot_.segment = segment; snapshot_.segmentKnown = true;
    return NV_OK;
}
NV_STATUS Session::readConfig(NvU32 offset, NvU32 width, NvU32 &value) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if ((width != 1 && width != 2 && width != 4) || offset >= 4096 ||
        width > 4096 - offset || (offset & (width - 1))) return NV_ERR_INVALID_ARGUMENT;
    return backend_.configRead ? backend_.configRead(backend_.context, offset, width, value) : NV_STATUS(NV_ERR_NOT_SUPPORTED);
}
NV_STATUS Session::writeConfig(NvU32 offset, NvU32 width, NvU32 value) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if ((width != 1 && width != 2 && width != 4) || offset >= 4096 ||
        width > 4096 - offset || (offset & (width - 1))) return NV_ERR_INVALID_ARGUMENT;
    return backend_.configWrite ? backend_.configWrite(backend_.context, offset, width, value) : NV_STATUS(NV_ERR_NOT_SUPPORTED);
}
bool Session::accessible() {
    NvU32 identity = 0, revision = 0, subsystem = 0;
    return readConfig(0,4,identity) == NV_OK && readConfig(8,4,revision) == NV_OK &&
        readConfig(0x2c,4,subsystem) == NV_OK && identity == 0x1f9110de &&
        (revision & 0xffU) == 0xa1 && subsystem == 0x380617aa;
}
NV_STATUS Session::registerGeometry(NvU64 &physical, NvU64 &bytes) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    return backend_.registerGeometry ? backend_.registerGeometry(backend_.context, physical, bytes) : NV_STATUS(NV_ERR_NOT_SUPPORTED);
}
NV_STATUS Session::mapRegisters(NvU64 physical, NvU64 bytes, void **address) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if (!bytes || !address || physical > ~NvU64(0) - (bytes - 1)) return NV_ERR_INVALID_ARGUMENT;
    return backend_.mapRegisters ? backend_.mapRegisters(backend_.context, physical, bytes, address) : NV_STATUS(NV_ERR_NOT_SUPPORTED);
}
NV_STATUS Session::unmapRegisters(void *address, NvU64 bytes) {
    if (!ordinary() || !active_) return NV_ERR_INVALID_STATE;
    return backend_.unmapRegisters ? backend_.unmapRegisters(backend_.context, address, bytes) : NV_STATUS(NV_ERR_NOT_SUPPORTED);
}
NV_STATUS Session::physicalAddressForHost(NvU64 host, NvU64 &physical) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    for (const auto &entry : allocations_) if (entry.resource && !entry.retired) {
        const NvU64 start = static_cast<NvU64>(reinterpret_cast<NvUPtr>(entry.host));
        const NvU64 bytes = NvU64(entry.pages) * kPageBytes;
        if (host >= start && host - start < bytes) {
            const NvU64 offset = host - start;
            NvU64 page = 0;
            NV_STATUS status = backend_.pageAddress(backend_.context, entry.resource,
                static_cast<NvU32>(offset / kPageBytes), false, page);
            if (status == NV_OK) physical = page + offset % kPageBytes;
            return status;
        }
    }
    return NV_ERR_INVALID_ADDRESS;
}
Session::Allocation *Session::find(void *token) {
    Allocation *entry = findOwned(token);
    return entry && !entry->retired ? entry : nullptr;
}
Session::Allocation *Session::findOwned(void *token) {
    const NvU64 requested = static_cast<NvU64>(reinterpret_cast<NvUPtr>(token));
    if (!requested) return nullptr;
    for (auto &entry : allocations_)
        if (entry.resource && entry.generation == requested) return &entry;
    return nullptr;
}
NV_STATUS Session::allocate(NvU32 pages, NvU64 *physicalPages, void **token, bool contiguous, NvU32 cache) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if (!pages || pages > kMaximumPages || !physicalPages || !token)
        return NV_ERR_INVALID_ARGUMENT;
    if (cache > 2) return NV_ERR_NOT_SUPPORTED;
    Allocation *entry = nullptr;
    for (auto &candidate : allocations_) if (!candidate.resource) { entry = &candidate; break; }
    if (!entry) return NV_ERR_INSUFFICIENT_RESOURCES;
    const NvU64 id = generation();
    if (!id) return NV_ERR_INSUFFICIENT_RESOURCES;
    void *resource = nullptr;
    NvU8 *host = nullptr;
    NV_STATUS status = backend_.allocate(backend_.context, pages, contiguous, cache, &resource, &host);
    if (status != NV_OK) return status;
    bool valid = resource && host;
    NvU64 previous = 0;
    for (NvU32 i = 0; i < pages && valid; ++i) {
        NvU64 address = 0;
        status = backend_.pageAddress(backend_.context, resource, i, false, address);
        valid = status == NV_OK && address && !(address & (kPageBytes - 1)) &&
                address <= ~NvU64(0) - (kPageBytes - 1) &&
                (!contiguous || i == 0 || address == previous + kPageBytes);
        previous = address;
    }
    if (!valid) {
        if (resource) {
            const NV_STATUS cleaned = backend_.releaseAllocation(backend_.context, resource);
            if (cleaned != NV_OK) {
                entry->generation = id; entry->resource = resource; entry->host = host;
                entry->pages = pages; entry->contiguous = contiguous;
                return cleaned;
            }
        }
        return NV_ERR_INVALID_ADDRESS;
    }
    entry->generation = id;
    entry->resource = resource;
    entry->host = host;
    entry->pages = pages;
    entry->contiguous = contiguous;
    entry->mapped = false;
    // The backend page table is immutable through this externally serialized
    // transaction. Only now publish caller outputs.
    for (NvU32 i = 0; i < (contiguous ? 1U : pages); ++i)
        (void)backend_.pageAddress(backend_.context, resource, i, false, physicalPages[i]);
    *token = reinterpret_cast<void *>(static_cast<NvUPtr>(id));
    return NV_OK;
}
NV_STATUS Session::setDmaAddressSize(NvU32 bits) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if (bits < 32 || bits > 64) return NV_ERR_INVALID_ARGUMENT;
    for (const auto &entry : allocations_) if (entry.mapped) return NV_ERR_IN_USE;
    snapshot_.dmaAddressBits = bits;
    return NV_OK;
}
NV_STATUS Session::requiresDmaRemap(NvBool &required) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if (!backend_.dmaRemapPolicy) return NV_ERR_NOT_SUPPORTED;
    DmaRemapPolicy captured = DmaRemapPolicy::Unavailable;
    const NV_STATUS status = backend_.dmaRemapPolicy(backend_.context, captured);
    if (status != NV_OK) return status;
    if (captured != DmaRemapPolicy::MapPhysicalPagesWithoutBounce)
        return NV_ERR_NOT_SUPPORTED;
    // nv_alloc_pages publishes CPU physical PTEs; nv_dma_map_alloc is required
    // even if an eventual validated device address happens to be identical.
    // No result is inferred from Snapshot::mapper or a null mapper pointer.
    required = NV_TRUE;
    return NV_OK;
}
NV_STATUS Session::mapDma(void *token, NvU64 *devicePages) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if (!devicePages) return NV_ERR_INVALID_ARGUMENT;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (entry->mapped && !entry->dmaRetired) return NV_ERR_STATE_IN_USE;
    if (!snapshot_.dmaPolicySettled || snapshot_.mapper == Mapper::Unavailable ||
        snapshot_.dmaAddressBits == 0)
        return NV_ERR_NOT_SUPPORTED;
    const bool retained = entry->mapped;
    if (retained && !backend_.validateRetainedDma) return NV_ERR_NOT_SUPPORTED;
    NV_STATUS status = retained ?
        backend_.validateRetainedDma(backend_.context, entry->resource, snapshot_.dmaAddressBits) :
        backend_.mapDma(backend_.context, entry->resource, snapshot_.dmaAddressBits);
    if (status != NV_OK) return status;
    bool valid = true;
    NvU64 previous = 0;
    for (NvU32 i = 0; i < entry->pages && valid; ++i) {
        NvU64 address = 0;
        status = backend_.pageAddress(backend_.context, entry->resource, i, true, address);
        valid = status == NV_OK && address && !(address & (kPageBytes - 1)) &&
                address <= ~NvU64(0) - (kPageBytes - 1) &&
                address + kPageBytes - 1 <= (snapshot_.dmaAddressBits == 64 ?
                    ~NvU64(0) : ((NvU64(1) << snapshot_.dmaAddressBits) - 1)) &&
                (!entry->contiguous || i == 0 || address == previous + kPageBytes);
        previous = address;
    }
    if (!valid) {
        // A retained mapping can still be addressable by hardware DMA or an
        // undrained IRQ, even after the original logical owner released it.
        // Failed revalidation must never tear down that old ownership.
        if (!retained && backend_.unmapDma(backend_.context, entry->resource) != NV_OK)
            entry->mapped = true;
        return NV_ERR_INVALID_ADDRESS;
    }
    entry->mapped = true;
    entry->dmaRetired = false;
    for (NvU32 i = 0; i < (entry->contiguous ? 1U : entry->pages); ++i)
        (void)backend_.pageAddress(backend_.context, entry->resource, i, true, devicePages[i]);
    return NV_OK;
}
NV_STATUS Session::unmapDma(void *token, NvU64 *physicalPages) {
    if (!ordinary() || !active_) return NV_ERR_INVALID_STATE;
    if (!physicalPages) return NV_ERR_INVALID_ARGUMENT;
    if (irqArmAttempted_ || hardwareDmaHeld_) return NV_ERR_IN_USE;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (!entry->mapped || entry->dmaRetired) return NV_ERR_INVALID_STATE;
    NV_STATUS status = backend_.unmapDma(backend_.context, entry->resource);
    if (status != NV_OK) return status;
    entry->mapped = false;
    for (NvU32 i = 0; i < (entry->contiguous ? 1U : entry->pages); ++i)
        (void)backend_.pageAddress(backend_.context, entry->resource, i, false, physicalPages[i]);
    return NV_OK;
}
NV_STATUS Session::unmapRmDma(void *token, NvU64 *physicalPages, bool &deferred) {
    if (!ordinary() || !active_ || !rmBound_) return NV_ERR_INVALID_STATE;
    if (!physicalPages) return NV_ERR_INVALID_ARGUMENT;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (!entry->mapped || entry->dmaRetired) return NV_ERR_INVALID_STATE;
    if (!irqArmAttempted_ && !hardwareDmaHeld_) {
        const NV_STATUS status = unmapDma(token, physicalPages);
        if (status == NV_OK) deferred = false;
        return status;
    }
    // The immutable physical table was published at allocation. Validate it
    // before acknowledging retirement; no completion or page reuse occurs.
    for (NvU32 i = 0; i < entry->pages; ++i) {
        NvU64 physical = 0;
        const NV_STATUS status = backend_.pageAddress(backend_.context, entry->resource, i, false, physical);
        if (status != NV_OK) return status;
        if (!physical || (physical & (kPageBytes - 1)) ||
            physical > ~NvU64(0) - (kPageBytes - 1)) return NV_ERR_INVALID_ADDRESS;
    }
    entry->dmaRetired = true;
    for (NvU32 i = 0; i < (entry->contiguous ? 1U : entry->pages); ++i)
        (void)backend_.pageAddress(backend_.context, entry->resource, i, false, physicalPages[i]);
    deferred = true;
    return NV_OK;
}
NV_STATUS Session::releaseRmAllocation(void *token, bool &deferred) {
    if (!ordinary() || !active_ || !rmBound_) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (entry->mapped && !entry->dmaRetired) return NV_ERR_IN_USE;
    if (!irqArmAttempted_ && !hardwareDmaHeld_) {
        const NV_STATUS status = releaseEntry(*entry);
        if (status == NV_OK) deferred = false;
        return status;
    }
    const NV_STATUS retained = retainRmAllocation(token);
    if (retained != NV_OK) return retained;
    deferred = true;
    return NV_OK;
}
NV_STATUS Session::retainRmAllocation(void *token) {
    if (!ordinary() || !active_ || !rmBound_) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (entry->mapped && !entry->dmaRetired) return NV_ERR_IN_USE;
    entry->retired = true;
    return NV_OK;
}
NV_STATUS Session::reclaimRmRetirement(void *token) {
    if (!ordinary() || !active_ || !rmBound_) return NV_ERR_INVALID_STATE;
    if (irqArmAttempted_ || hardwareDmaHeld_) return NV_ERR_IN_USE;
    Allocation *entry = findOwned(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (entry->retired) return releaseEntry(*entry);
    if (entry->dmaRetired) {
        const NV_STATUS status = backend_.unmapDma(backend_.context, entry->resource);
        if (status != NV_OK) return status;
        entry->mapped = entry->dmaRetired = false;
    }
    return NV_OK;
}
NV_STATUS Session::checkRmRetirementDrain() const {
    if (!ordinary() || !active_ || !rmBound_) return NV_ERR_INVALID_STATE;
    return irqArmAttempted_ || hardwareDmaHeld_ ? NV_STATUS(NV_ERR_IN_USE) : NV_STATUS(NV_OK);
}
RetirementStatistics Session::retirementStatistics() const {
    RetirementStatistics out{};
    for (const auto &entry : allocations_) if (entry.resource) {
        if (entry.retired) ++out.allocations;
        if (entry.dmaRetired) ++out.dmaMappings;
        if (entry.retired || entry.dmaRetired) out.pages += entry.pages;
    }
    return out;
}
NV_STATUS Session::address(void *token, NvU32 page, NvU64 &deviceAddress) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    if (page >= entry->pages) return NV_ERR_INVALID_ARGUMENT;
    return backend_.pageAddress(backend_.context, entry->resource, page,
                               entry->mapped && !entry->dmaRetired, deviceAddress);
}
NV_STATUS Session::borrowHost(void *token, NvU64 offset, NvU64 length, void **address) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    const NvU64 size = NvU64(entry->pages) * kPageBytes;
    if (!address || !length || offset > size || length > size - offset)
        return NV_ERR_INVALID_ARGUMENT;
    *address = entry->host + offset;
    return NV_OK;
}
NV_STATUS Session::hostWrite(void *token, NvU64 offset, const void *bytes, NvU64 length) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    const NvU64 size = NvU64(entry->pages) * kPageBytes;
    if (!bytes || !length || offset > size || length > size - offset)
        return NV_ERR_INVALID_ARGUMENT;
    bytesCopy(entry->host + offset, bytes, length);
    return NV_OK;
}
NV_STATUS Session::hostRead(void *token, NvU64 offset, void *bytes, NvU64 length) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    Allocation *entry = find(token);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    const NvU64 size = NvU64(entry->pages) * kPageBytes;
    if (!bytes || !length || offset > size || length > size - offset)
        return NV_ERR_INVALID_ARGUMENT;
    bytesCopy(bytes, entry->host + offset, length);
    return NV_OK;
}
NV_STATUS Session::releaseEntry(Allocation &entry) {
    if (irqArmAttempted_ || hardwareDmaHeld_) return NV_ERR_IN_USE;
    NV_STATUS status = NV_OK;
    if (entry.mapped) {
        status = backend_.unmapDma(backend_.context, entry.resource);
        if (status != NV_OK) return status;
        entry.mapped = false;
        entry.dmaRetired = false;
    }
    NV_STATUS released = backend_.releaseAllocation(backend_.context, entry.resource);
    if (status == NV_OK) status = released;
    // Failed completion preserves ownership. Keep this slot and provider
    // quarantined until a backend can establish safe resource release.
    if (released != NV_OK) return released;
    entry = Allocation{};
    return status;
}
NV_STATUS Session::release(void *token) {
    if (!ordinary() || !active_) return NV_ERR_INVALID_STATE;
    // Generic release requires both the real controller drain and independent
    // original hardware-DMA stop proof once that lifetime has begun.
    if (irqArmAttempted_ || hardwareDmaHeld_) return NV_ERR_IN_USE;
    Allocation *entry = find(token);
    return entry ? releaseEntry(*entry) : NV_STATUS(NV_ERR_OBJECT_NOT_FOUND);
}
NV_STATUS Session::installInterrupt(const InterruptContract &contract) {
    if (!ordinary() || !live()) return NV_ERR_INVALID_STATE;
    if (irqInstalled_) return NV_ERR_STATE_IN_USE;
    if (!contract.context || !contract.top || !contract.lockedBottomHalf ||
        !contract.unlockedBottomHalf || !contract.maskHardware || !contract.readyToArm)
        return NV_ERR_NOT_SUPPORTED;
    NV_STATUS status = backend_.installInterrupt(backend_.context, contract);
    if (status == NV_OK) { irqInstalled_ = true; interruptContract_ = contract; }
    return status;
}
NV_STATUS Session::armInterrupt() {
    if (!ordinary() || !live() || !irqInstalled_) return NV_ERR_INVALID_STATE;
    if (irqArmAttempted_) return NV_ERR_STATE_IN_USE;
    if (!interruptContract_.readyToArm || !interruptContract_.readyToArm(interruptContract_.context))
        return NV_ERR_INVALID_STATE;
    irqArmAttempted_ = true;
    NV_STATUS status = backend_.armInterrupt(backend_.context);
    if (status == NV_OK) irqArmed_ = true;
    return status;
}
NV_STATUS Session::stopInterrupt() {
    if (!ordinary() || !active_) return NV_ERR_INVALID_STATE;
    if (!irqInstalled_) return NV_OK;
    NV_STATUS status = backend_.stopInterrupt(backend_.context);
    if (status == NV_OK) {
        irqArmed_ = false; irqArmAttempted_ = false; irqInstalled_ = false;
        interruptContract_ = InterruptContract{};
    }
    return status;
}
bool Session::interruptInstalled() const { return irqInstalled_; }
bool Session::interruptArmed() const { return irqArmed_; }
InterruptStatistics Session::interruptStatistics() const {
    return ordinary() && active_ && backend_.interruptStatistics ?
        backend_.interruptStatistics(backend_.context) : InterruptStatistics{};
}
NV_STATUS Session::deliverFirmware(const void *, NvU64) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS Session::transitionPower(NvU32) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS Session::setRmBinding(bool bound) {
    if (!ordinary() || !active_) return NV_ERR_INVALID_STATE;
    if (bound == rmBound_) return NV_ERR_INVALID_STATE;
    if (!bound) {
        if (irqArmAttempted_ || hardwareDmaHeld_) return NV_ERR_IN_USE;
        const RetirementStatistics pending = retirementStatistics();
        if (pending.allocations || pending.dmaMappings) return NV_ERR_IN_USE;
    }
    rmBound_ = bound;
    if (!bound) { hardwareDmaState_ = nullptr; hardwareDmaGeneration_ = 0; }
    return NV_OK;
}
NV_STATUS Session::beginHardwareDmaLifetime(const void *originalState) {
    if (!ordinary() || !live() || !rmBound_) return NV_ERR_INVALID_STATE;
    if (!originalState) return NV_ERR_INVALID_ARGUMENT;
    if (hardwareDmaHeld_) return NV_ERR_STATE_IN_USE;
    const NvU64 captured = generation();
    if (!captured) return NV_ERR_INSUFFICIENT_RESOURCES;
    hardwareDmaState_ = originalState;
    hardwareDmaGeneration_ = captured;
    hardwareDmaHeld_ = true;
    return NV_OK;
}
NV_STATUS Session::confirmHardwareDmaStopped(const S540GspDmaStopReceipt *receipt) {
    if (!ordinary() || !active_ || !rmBound_ || !hardwareDmaHeld_) return NV_ERR_INVALID_STATE;
    if (!receipt) return NV_ERR_INVALID_ARGUMENT;
    const NV_STATUS status = s540GspContextValidateDmaStopReceipt(
        hardwareDmaState_, this, hardwareDmaGeneration_, receipt);
    if (status != NV_OK) return status;
    hardwareDmaHeld_ = false;
    return NV_OK;
}
NvU64 Session::hardwareDmaGeneration() const { return hardwareDmaGeneration_; }
bool Session::hardwareDmaLifetimeHeld() const { return hardwareDmaHeld_; }
NV_STATUS Session::stop() {
    if (!active_) return NV_OK;
    if (!ordinary()) return NV_ERR_INVALID_STATE;
    if (rmBound_ || hardwareDmaHeld_) return NV_ERR_IN_USE;
    NV_STATUS status = stopInterrupt();
    if (status != NV_OK) return status;
    NV_STATUS first = NV_OK;
    for (auto &entry : allocations_) if (entry.resource) {
        status = releaseEntry(entry);
        if (first == NV_OK) first = status;
    }
    status = backend_.stop(backend_.context);
    if (status != NV_OK) return status;
    active_ = false;
    pciHandle_ = nullptr;
#if defined(KERNEL)
    if (platformOwned_) destroyDarwinBackend(backend_.context);
#endif
    snapshot_ = Snapshot{};
    backend_ = Detail::Backend{};
    platformOwned_ = false;
    return first;
}
PciWriteKind pciWriteKind(NvU32 offset, NvU32 width, NvU32 previous, NvU32 value) {
    if (offset == 4 && (width == 1 || width == 2) &&
        !((previous ^ value) & ~4U) && (value & 2U)) return PciWriteKind::CommandBusMaster;
    // Exact original osinit.c:osInitMapping writes, not general BAR permission.
    if (offset == 0x30 && width == 4 && value == 0) return PciWriteKind::RomDisable;
    if (offset == 0x0c && width == 4 && value == 0x0000f800) return PciWriteKind::LatencySetup;
    return PciWriteKind::Refused;
}
bool dmaPageMatches(NvU64 originalPhysical, NvU64 deviceAddress, NvU64 translatedPhysical, NvU32 addressBits) {
    if (addressBits < 32 || addressBits > 64 || !originalPhysical || !deviceAddress ||
        (originalPhysical & (kPageBytes - 1)) || (deviceAddress & (kPageBytes - 1)) ||
        deviceAddress > ~NvU64(0) - (kPageBytes - 1)) return false;
    const NvU64 mask = addressBits == 64 ? ~NvU64(0) : (NvU64(1) << addressBits) - 1;
    return deviceAddress + kPageBytes - 1 <= mask && translatedPhysical == originalPhysical;
}
Mapper selectMapperPolicy(bool providerPropertyPresent, bool publishedDeviceMapper,
                          bool frameworkDirectAttested) {
    if (providerPropertyPresent && publishedDeviceMapper) return Mapper::Device;
    if (!providerPropertyPresent && frameworkDirectAttested) return Mapper::Direct;
    return Mapper::Unavailable;
}
const char *mapperName(Mapper mapper) {
    switch (mapper) {
        case Mapper::Device: return "device";
        case Mapper::System: return "system";
        case Mapper::Direct: return "direct-untranslated";
        default: return "unavailable";
    }
}
} // namespace S540NvidiaDeviceTransport
