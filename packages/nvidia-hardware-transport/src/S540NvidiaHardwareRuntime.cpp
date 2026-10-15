// SPDX-License-Identifier: MIT
#include "S540NvidiaHardwareRuntime.hpp"
#include "S540NvidiaDma.hpp"
#include "S540NvidiaPciPolicy.hpp"
#include "../firmware/S540NvidiaFirmware.hpp"

#if defined(KERNEL)
#include <IOKit/pci/IOPCIDevice.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <libkern/c++/OSArray.h>
#include <machine/machine_routines.h>
#endif

namespace {
using S540NvidiaHardwareRuntime::Result;

void check(Result &r, bool &component, bool condition)
{
    ++r.checks;
    if (!condition) { ++r.failures; component = false; }
}

const char *dmaReason(S540NvidiaDma::Reason reason)
{
    using S540NvidiaDma::Reason;
    switch (reason) {
    case Reason::None: return "none";
    case Reason::InvalidContext: return "invalid_context";
    case Reason::MapperUnavailable: return "mapper_unavailable";
    case Reason::AllocationFailed: return "allocation_failed";
    case Reason::ContentsUnavailable: return "contents_unavailable";
    case Reason::DescriptorPrepareFailed: return "descriptor_prepare_failed";
    case Reason::CommandAllocationFailed: return "command_allocation_failed";
    case Reason::AttachFailed: return "attach_failed";
    case Reason::CommandPrepareFailed: return "command_prepare_failed";
    case Reason::SegmentsInvalid: return "segments_invalid";
    case Reason::PatternMismatch: return "pattern_mismatch";
    case Reason::CommandCompleteFailed: return "command_complete_failed";
    case Reason::ClearFailed: return "clear_failed";
    case Reason::DescriptorCompleteFailed: return "descriptor_complete_failed";
    }
    return "not_run";
}

#if defined(KERNEL)
class ProviderGuard {
    IOPCIDevice *provider_;
    bool locked_;
public:
    explicit ProviderGuard(IOPCIDevice *provider) : provider_(provider),
        locked_(false) {
        if (!provider || ml_at_interrupt_context() ||
            !ml_get_interrupts_enabled() || !provider->lockForArbitration(false))
            return;
        // The arbitration lock serializes compliant open/close/termination.
        // Inspect ownership only while it is held; never open the provider or
        // prepare host DMA for an inactive or already-owned PCI service.
        if (provider->isInactive() || provider->isOpen()) {
            provider->unlockForArbitration();
            return;
        }
        locked_ = true;
    }
    ~ProviderGuard() { if (locked_) provider_->unlockForArbitration(); }
    bool locked() const { return locked_; }
};

NvU64 assignedMemoryLength(IOPCIDevice *provider, S540NvidiaPci::Context &pci,
                          NvU8 bar)
{
    if (bar > 5) return 0;
    NvU32 bars[6] = {};
    for (NvU32 index = 0; index < 6; ++index) {
        if (os_pci_read_dword(pci.handle(), 0x10U + 4U * index, &bars[index]) != NV_OK)
            return 0;
    }
    const NvS32 selectedType = S540NvidiaPci::memoryBarType(bars, bar);
    if (selectedType < 0) return 0;
    // Use only the retained published descriptor list. No PCI convenience
    // getter, mapping, physical address or table/PBA read is needed here.
    OSObject *object = provider->copyProperty("IODeviceMemory");
    auto *array = OSDynamicCast(OSArray, object);
    NvU64 length = 0;
    NvU32 matches = 0;
    if (array && array->getCount() <= 16) {
        for (unsigned int i = 0; i < array->getCount(); ++i) {
            auto *descriptor = OSDynamicCast(IOMemoryDescriptor, array->getObject(i));
            if (!descriptor) continue;
            const NvU64 tag = descriptor->getTag();
            if (!S540NvidiaPci::descriptorTagMatches(tag, bar, selectedType)) continue;
            ++matches;
            length = descriptor->getLength();
        }
    }
    if (object) object->release();
    return matches == 1 ? length : 0;
}
#else
struct NativePciFixture { NvU32 words[64]; };
bool fixtureRead(void *opaque, NvU32 offset, NvU32 width, NvU32 &value)
{
    if (!opaque || offset > 255 || (width != 1 && width != 2 && width != 4) ||
        offset % width || width > 256 - offset) return false;
    auto &fixture = *static_cast<NativePciFixture *>(opaque);
    const NvU32 mask = width == 1 ? 0xffU : width == 2 ? 0xffffU : 0xffffffffU;
    value = (fixture.words[offset / 4] >> ((offset & 3U) * 8)) & mask;
    return true;
}
#endif

struct PreparationContext { IOPCIDevice *provider; Result *result; };

void runPreparation(void *opaque)
{
    auto &context = *static_cast<PreparationContext *>(opaque);
    auto &r = *context.result;
    r = {0, 0, true, true, true, true, true, true,
         "unavailable", "not_run", 0, 0, "pci-context-unbound", 0, 0, 0, false, false};
#if defined(KERNEL)
    ProviderGuard guard(context.provider);
    check(r, r.pciReadAdapter, guard.locked());
    if (!guard.locked()) {
        r.hostDma = r.interruptInventory = r.firmwareParser = r.firmwareRpc = false;
        r.dmaReason = "pci_unavailable";
        r.pciReason = "pci-arbitration-unavailable";
        return;
    }
#endif
    S540NvidiaPci::Context pci;
#if defined(KERNEL)
    const bool bound = pci.bind(context.provider);
#else
    NativePciFixture fixture{};
    fixture.words[0] = 0x1f9110deU;
    fixture.words[1] = 0x00100106U;
    fixture.words[2] = 0x030000a1U;
    fixture.words[0x2c / 4] = 0x380617aaU;
    fixture.words[0x34 / 4] = 0x40;
    fixture.words[0x40 / 4] = 0x00035001U; // PM v3 -> MSI at 0x50.
    fixture.words[0x50 / 4] = 0x00800005U; // 64-bit MSI, one vector, disabled.
    const bool bound = pci.bindNative(fixtureRead, &fixture);
#endif
    check(r, r.pciReadAdapter, bound && pci.bound());
    if (!bound) {
        r.hostDma = r.interruptInventory = r.firmwareParser = r.firmwareRpc = false;
        r.dmaReason = "pci_unavailable";
        check(r, r.cleanup, !pci.bound() && pci.handle() == nullptr);
        return;
    }
    NvU8 byte = 0; NvU16 word = 0; NvU32 dword = 0;
    check(r, r.pciReadAdapter, os_pci_read_byte(pci.handle(), 0, &byte) == NV_OK && byte == 0xde);
    check(r, r.pciReadAdapter, os_pci_read_word(pci.handle(), 0, &word) == NV_OK && word == 0x10de);
    check(r, r.pciReadAdapter, os_pci_read_dword(pci.handle(), 0, &dword) == NV_OK && dword == 0x1f9110deU);
    word = 0xffff;
    check(r, r.pciReadAdapter, os_pci_read_word(pci.handle(), 1, &word) == NV_ERR_INVALID_ARGUMENT && word == 0);
    dword = 0xffffffffU;
    check(r, r.pciReadAdapter, os_pci_read_dword(nullptr, 0, &dword) == NV_ERR_INVALID_STATE && dword == 0);
    const auto inventory = pci.inventory();
    r.pciReason = inventory.reason;
    r.pciCapabilities = inventory.capabilityCount;
    r.msiVectors = inventory.msiVectors;
    r.msixVectors = inventory.msixVectors;
    r.msiObservedEnabled = inventory.msiEnabled;
    r.msixObservedEnabled = inventory.msixEnabled;
    check(r, r.interruptInventory, inventory.valid && inventory.capabilityCount > 0 &&
          inventory.capabilityCount <= 48 && inventory.pmOffset != 0 &&
          inventory.powerState == 0 && !inventory.interruptsArmed &&
          (inventory.command & 2U) != 0);
    if (inventory.valid && inventory.msixOffset) {
#if defined(KERNEL)
        const NvU64 tableLength = assignedMemoryLength(context.provider, pci, inventory.msixTableBar);
        const NvU64 pbaLength = assignedMemoryLength(context.provider, pci, inventory.msixPbaBar);
#else
        const NvU64 tableLength = 0x1000000U, pbaLength = 0x1000000U;
#endif
        const bool geometry =
            S540NvidiaPci::msixGeometry(inventory, inventory.msixTableBar, tableLength) &&
            S540NvidiaPci::msixGeometry(inventory, inventory.msixPbaBar, pbaLength);
        check(r, r.interruptInventory, geometry);
        if (!geometry) r.pciReason = "pci-msix-geometry-invalid";
    }

    // Identity, D0 and memory decoding must pass before host-DMA preparation.
    if (r.pciReadAdapter && r.interruptInventory) {
#if defined(KERNEL)
        const auto dma = S540NvidiaDma::check(context.provider);
#else
        const auto dma = S540NvidiaDma::check(reinterpret_cast<IOService *>(&fixture));
#endif
        r.checks += dma.checks;
        r.failures += dma.failures;
        check(r, r.hostDma, dma.passed());
        r.cleanup = r.cleanup && dma.cleanup;
        r.dmaMode = dma.mapperMode == S540NvidiaDma::MapperMode::Provider ?
            "provider_mapped" : dma.mapperMode == S540NvidiaDma::MapperMode::DirectUntranslated ?
            "direct_untranslated" : "unavailable";
        r.dmaReason = dmaReason(dma.reason);
        r.dmaBytes = dma.bytes;
        r.dmaSegments = dma.segments;
    } else {
        r.hostDma = false;
        r.dmaReason = "pci_unavailable";
    }
    const auto firmware = S540NvidiaFirmware::selfCheck();
    r.checks += firmware.checks;
    r.failures += firmware.failures;
    check(r, r.firmwareParser, firmware.parser && firmware.layout);
    check(r, r.firmwareRpc, firmware.rpc && !firmware.realImageReady);
    r.cleanup = r.cleanup && firmware.cleanup;
    pci.unbind();
    dword = 0xffffffffU;
    check(r, r.cleanup, !pci.bound() && pci.handle() == nullptr &&
          os_pci_read_dword(&pci, 0, &dword) == NV_ERR_INVALID_STATE && dword == 0);
    check(r, r.cleanup, firmware.cleanup);
}

struct ContinuationContext {
    PreparationContext preparation;
    S540NvidiaHardwareRuntime::StartupContinuation continuation;
    void *context;
};

void runWithContinuation(void *opaque)
{
    auto &next = *static_cast<ContinuationContext *>(opaque);
    runPreparation(&next.preparation);
    // runPreparation has released provider arbitration and every DMA object.
    // Keep the existing CPU startup lease while executing the next whole block.
    if (next.preparation.result->passed() && next.continuation)
        next.continuation(next.context);
}
}

S540NvidiaHardwareRuntime::IntegratedResult
S540NvidiaHardwareRuntime::checkIntegrated(IOPCIDevice *provider)
{
    return checkIntegrated(provider, nullptr, nullptr);
}

S540NvidiaHardwareRuntime::IntegratedResult
S540NvidiaHardwareRuntime::checkIntegrated(IOPCIDevice *provider,
                                        StartupContinuation continuation,
                                        void *nextContext)
{
    IntegratedResult result{};
    result.preparation = {1, 1, false, false, false, false, false, false,
                          "unavailable", "not_run", 0, 0,
                          "pci-context-unbound", 0, 0, 0, false, false};
    ContinuationContext context{{provider, &result.preparation}, continuation,
                                nextContext};
    result.v7 = S540NvidiaSupportRuntime::checkIntegrated(runWithContinuation, &context);
    result.acquired = result.v7.acquired;
    return result;
}
