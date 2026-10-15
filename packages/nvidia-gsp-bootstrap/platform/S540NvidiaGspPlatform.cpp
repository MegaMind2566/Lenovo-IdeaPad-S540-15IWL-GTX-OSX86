// SPDX-License-Identifier: MIT
#include "S540NvidiaGspPlatform.hpp"

#if defined(KERNEL)
#include <IOKit/IOLib.h>
#include <IOKit/IOService.h>
#include <IOKit/IORegistryEntry.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <IOKit/acpi/IOACPIPlatformDevice.h>
#include <IOKit/graphics/IOFramebuffer.h>
#include <libkern/c++/OSArray.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSSerialize.h>
#include <libkern/c++/OSString.h>
#include <libkern/c++/OSUnserialize.h>
#include <libkern/version.h>
#include <machine/machine_routines.h>
#include <pexpert/pexpert.h>

// Exact exported XNU types: osfmk/i386/mp.h and pexpert/i386/pe_init.c.
extern "C" unsigned int real_ncpus;
extern "C" void *gPEEFISystemTable;

#if defined(NV_VGX_HYPER)
#error The TU117 Darwin profile does not implement an NVIDIA vGPU hypervisor
#endif

namespace {
using namespace S540NvidiaGspPlatform;
Context *currentContext;
constexpr NvU32 kMaximumRegistryNodes = 4096;

bool ordinary() {
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
}
NvU32 little32(const NvU8 *p) {
    return NvU32(p[0]) | (NvU32(p[1]) << 8) | (NvU32(p[2]) << 16) |
           (NvU32(p[3]) << 24);
}
bool property32(IORegistryEntry *entry, const char *key, NvU32 &out) {
    OSObject *object = entry->copyProperty(key);
    if (!object) return false;
    bool ok = false;
    if (auto *data = OSDynamicCast(OSData, object)) {
        if (data->getLength() == 4) {
            out = little32(static_cast<const NvU8 *>(data->getBytesNoCopy()));
            ok = true;
        }
    } else if (auto *number = OSDynamicCast(OSNumber, object)) {
        if (number->unsigned64BitValue() <= 0xffffffffULL) {
            out = number->unsigned32BitValue(); ok = true;
        }
    }
    object->release();
    return ok;
}

IOACPIPlatformDevice *copyCompanion(IOPCIDevice *provider) {
    // Same published alias used by Apple's IOPCICopyACPIDevice. The PCI
    // bridge or an arbitrary service parent is not the endpoint companion.
    OSObject *object = provider->copyProperty("acpi-path");
    auto *path = OSDynamicCast(OSString, object);
    IOACPIPlatformDevice *result = nullptr;
    if (path && path->getLength() && path->getLength() < 1024) {
        IORegistryEntry *entry = IORegistryEntry::fromPath(path->getCStringNoCopy());
        result = OSDynamicCast(IOACPIPlatformDevice, entry);
        if (entry && !result) entry->release();
        if (result && result->isInactive()) { result->release(); result = nullptr; }
    }
    if (object) object->release();
    return result;
}

bool smbiosLimit(IOService *service, NvU32 &limit) {
    OSObject *object = service->copyProperty("SMBIOS-EPS");
    auto *data = OSDynamicCast(OSData, object);
    bool ok = false;
    if (data && data->getLength() >= 24) {
        const auto *p = static_cast<const NvU8 *>(data->getBytesNoCopy());
        const NvU32 bytes = data->getLength();
        NvU32 length = 0;
        if (bytes >= 31 && p[0] == '_' && p[1] == 'S' && p[2] == 'M' && p[3] == '_') {
            length = p[5];
            if (length >= 31 && length <= bytes && p[16] == '_' &&
                p[17] == 'D' && p[18] == 'M' && p[19] == 'I' && p[20] == '_')
                limit = NvU32(p[22]) | (NvU32(p[23]) << 8);
        } else if (p[0] == '_' && p[1] == 'S' && p[2] == 'M' &&
                   p[3] == '3' && p[4] == '_') {
            length = p[6];
            if (length >= 24 && length <= bytes) limit = little32(p + 12);
        }
        NvU8 checksum = 0;
        if (length && length <= bytes)
            for (NvU32 i = 0; i < length; ++i) checksum = NvU8(checksum + p[i]);
        ok = length && length <= bytes && !checksum && limit && limit <= 1024U * 1024U;
    }
    if (object) object->release();
    return ok;
}

bool collectChassis(bool &notebook) {
    OSDictionary *match = IOService::serviceMatching("AppleSMBIOS");
    IOService *service = match ? IOService::copyMatchingService(match) : nullptr;
    if (match) match->release();
    if (!service) return false;
    OSObject *object = service->copyProperty("SMBIOS");
    OSObject *decoded = nullptr;
    auto *data = OSDynamicCast(OSData, object);
    OSSerialize *serialized = nullptr;
    bool ok = false;
    if (!service->isInactive() && !data && OSDynamicCast(OSSerializer, object)) {
        NvU32 limit = 0;
        if (smbiosLimit(service, limit)) {
            serialized = OSSerialize::withCapacity(limit * 2U + 4096U);
            if (serialized && object->serialize(serialized) &&
                serialized->getLength() <= limit * 2U + 4096U) {
                decoded = OSUnserializeXML(serialized->text(), serialized->getLength());
                data = OSDynamicCast(OSData, decoded);
                if (data && data->getLength() > limit) data = nullptr;
            }
        }
    }
    if (!service->isInactive() && data)
        ok = decodeChassis(data->getBytesNoCopy(), data->getLength(), notebook);
    if (decoded) decoded->release();
    if (serialized) serialized->release();
    if (object) object->release();
    service->release();
    return ok;
}

bool collectNvSwitch(bool &present, NvU32 &count) {
    OSDictionary *match = IOService::serviceMatching("IOPCIDevice");
    OSIterator *iterator = match ? IOService::getMatchingServices(match) : nullptr;
    if (match) match->release();
    if (!iterator) return false;
    bool ok = true, found = false;
    count = 0;
    while (OSObject *object = iterator->getNextObject()) {
        auto *device = OSDynamicCast(IOPCIDevice, object);
        if (!device || ++count > kMaximumRegistryNodes || device->isInactive()) { ok = false; break; }
        NvU32 vendor = 0, classCode = 0;
        if (!property32(device, "vendor-id", vendor) || !vendor || vendor >= 0xffffU) { ok = false; break; }
        if (vendor == 0x10de) {
            if (!property32(device, "class-code", classCode)) { ok = false; break; }
            // Original Linux predicate: NVIDIA, PCI_CLASS_BRIDGE_OTHER (0x0680).
            found |= (classCode & 0xffff00U) == 0x068000U;
        }
    }
    ok = ok && iterator->isValid() && count;
    iterator->release();
    if (ok) present = found;
    return ok;
}

bool collectBattery(bool &present, NvU32 &count) {
    const IORegistryPlane *plane = IORegistryEntry::getPlane("IOACPIPlane");
    IORegistryEntry *root = plane ? IORegistryEntry::fromPath("IOACPIPlane:/") : nullptr;
    IORegistryIterator *iterator = root ? IORegistryIterator::iterateOver(
        root, plane, kIORegistryIterateRecursively) : nullptr;
    if (root) root->release();
    if (!iterator) return false;
    bool ok = true, found = false;
    count = 0;
    while (IORegistryEntry *entry = iterator->getNextObject()) {
        if (++count > kMaximumRegistryNodes) { ok = false; break; }
        auto *device = OSDynamicCast(IOACPIPlatformDevice, entry);
        if (!device) continue;
        if (device->isInactive()) { ok = false; break; }
        bool methodPresent = false, evaluated = false;
        const char *methods[2] = {"_BIX", "_BIF"};
        const NvU32 technology[2] = {4, 3};
        for (NvU32 method = 0; method != 2 && !found; ++method) {
            if (device->validateObject(methods[method]) != kIOReturnSuccess) continue;
            methodPresent = true;
            OSObject *result = nullptr;
            const IOReturn status = device->evaluateObject(methods[method], &result);
            auto *package = OSDynamicCast(OSArray, result);
            auto *number = package && package->getCount() > technology[method] ?
                OSDynamicCast(OSNumber, package->getObject(technology[method])) : nullptr;
            if (status == kIOReturnSuccess && number && number->unsigned64BitValue() <= 1) {
                evaluated = true;
                found = number->unsigned64BitValue() == 1;
            }
            if (result) result->release();
        }
        if (methodPresent && !evaluated) ok = false;
        if (!ok || found) break;
    }
    ok = ok && iterator->isValid() && count;
    iterator->release();
    if (ok) present = found;
    return ok;
}

bool collectDate(char (&date)[96]) {
    const char *begin = version;
    NvU32 i = 0;
    while (i < 512 && begin[i] && begin[i] != ':') ++i;
    if (i == 512 || begin[i] != ':') return false;
    begin += i + 1;
    while (*begin == ' ') ++begin;
    NvU32 length = 0;
    while (length + 1 < sizeof(date) && begin[length] && begin[length] != ';') ++length;
    if (!length || begin[length] != ';') return false;
    for (NvU32 n = 0; n < length; ++n) date[n] = begin[n];
    date[length] = 0;
    return true;
}

bool rootBridge(IOACPIPlatformDevice *device) {
    OSObject *result = nullptr;
    if (device->evaluateObject("_HID", &result) != kIOReturnSuccess) {
        if (result) result->release();
        return false;
    }
    bool found = false;
    if (auto *name = OSDynamicCast(OSString, result))
        found = name->isEqualTo("PNP0A03") || name->isEqualTo("PNP0A08");
    else if (auto *number = OSDynamicCast(OSNumber, result)) {
        // ACPI compressed EISA IDs, as returned by EisaId("PNP0A03/08").
        const NvU64 value = number->unsigned64BitValue();
        found = value == 0x030ad041U || value == 0x080ad041U;
    }
    if (result) result->release();
    return found;
}

bool targetConsoleExcluded(IOPCIDevice *target) {
    OSDictionary *match = IOService::serviceMatching("IOFramebuffer");
    OSIterator *iterator = match ? IOService::getMatchingServices(match) : nullptr;
    if (match) match->release();
    if (!iterator) return false;
    ConsoleOwnership ownership{};
    bool complete = true;
    NvU32 count = 0;
    while (OSObject *object = iterator->getNextObject()) {
        if (++count > kMaximumRegistryNodes) { complete = false; break; }
        auto *framebuffer = OSDynamicCast(IOFramebuffer, object);
        if (!framebuffer) { complete = false; continue; }
        if (framebuffer->isInactive() || !framebuffer->isConsoleDevice()) continue;
        bool ownerKnown = false, boundTarget = false;
        NvU32 vendor = 0, classCode = 0;
        IORegistryEntry *entry = framebuffer;
        entry->retain();
        for (NvU32 depth = 0; entry && depth < 64; ++depth) {
            if (auto *pci = OSDynamicCast(IOPCIDevice, entry)) {
                ownerKnown = !pci->isInactive() && property32(pci, "vendor-id", vendor) &&
                    property32(pci, "class-code", classCode);
                boundTarget = pci == target;
                break;
            }
            IORegistryEntry *parent = entry->copyParentEntry(gIOServicePlane);
            entry->release(); entry = parent;
        }
        if (entry) entry->release();
        observeConsoleOwner(ownership, ownerKnown, vendor, classCode, boundTarget);
    }
    complete = complete && iterator->isValid();
    iterator->release();
    return consoleExcludesTarget(ownership, complete);
}
}

struct S540NvidiaGspPlatform::Context::Impl {
    IOPCIDevice *provider;
    IOACPIPlatformDevice *acpi;
    nv_state_t *state;
    S540NvidiaGlobalRmPlatformFacts facts;
    Evidence evidence;
    NvU32 romInFlight;
    char osDate[96];
};

S540NvidiaGspPlatform::Context::Context() : impl_(nullptr) {}
S540NvidiaGspPlatform::Context::~Context() { (void)shutdown(); }
bool S540NvidiaGspPlatform::Context::active() const { return impl_ != nullptr; }
NV_STATUS S540NvidiaGspPlatform::Context::initialize(IOPCIDevice *provider, nv_state_t *state) {
    if (!ordinary() || !provider) return NV_ERR_INVALID_ARGUMENT;
    if (impl_ || currentContext) return NV_ERR_STATE_IN_USE;
    if (provider->isInactive()) return NV_ERR_INVALID_STATE;
    auto *data = static_cast<Impl *>(IOMalloc(sizeof(Impl)));
    if (!data) return NV_ERR_NO_MEMORY;
    *data = Impl{};
    provider->retain(); data->provider = provider; data->state = state;
    data->acpi = copyCompanion(provider);
    data->evidence.acpiCompanion = data->acpi != nullptr;
    data->evidence.romAvailable = data->acpi && data->acpi->validateObject("_ROM") == kIOReturnSuccess;
    impl_ = data; currentContext = this;
    return NV_OK;
}
NV_STATUS S540NvidiaGspPlatform::Context::bindState(nv_state_t *state) {
    if (!ordinary() || !impl_ || !state || impl_->romInFlight || impl_->provider->isInactive()) return NV_ERR_INVALID_STATE;
    if (impl_->state && impl_->state != state) return NV_ERR_STATE_IN_USE;
    impl_->state = state;
    return NV_OK;
}
NV_STATUS S540NvidiaGspPlatform::Context::collect(S540NvidiaGlobalRmPlatformFacts *out) {
    if (!ordinary() || !impl_ || !out || impl_->provider->isInactive()) return NV_ERR_INVALID_STATE;
    auto &f = impl_->facts;
    auto &e = impl_->evidence;
    f = S540NvidiaGlobalRmPlatformFacts{}; f.format = 1;
    bool value = false;
    if (collectChassis(value)) { f.notebook = value; f.known |= S540_GLOBAL_FACT_NOTEBOOK; }
    if (collectBattery(value, e.acpiDevices)) { f.battery = value; f.known |= S540_GLOBAL_FACT_BATTERY; }
    // Kernel-recognized EFI system table, not an injected model-name heuristic.
    f.efi = gPEEFISystemTable != nullptr; f.known |= S540_GLOBAL_FACT_EFI;
    // This predicate means NVIDIA's NV_VGX_HYPER driver profile, not whether
    // CPUID reports some unrelated hypervisor. This build rejects that profile.
    f.vgpuHypervisor = NV_FALSE; f.known |= S540_GLOBAL_FACT_VGPU_HYPERVISOR;
    if (collectNvSwitch(value, e.pciDevices)) { f.nvSwitch = value; f.known |= S540_GLOBAL_FACT_NVSWITCH; }
    e.s0ixHardwareKnown = false; e.s0ixHardware = false;
    if (impl_->acpi) {
        const OSData *table = impl_->acpi->getACPITableData("FACP");
        if (table) e.s0ixHardwareKnown = decodeFadt(table->getBytesNoCopy(), table->getLength(), e.s0ixHardware);
    }
    // The first operational adapter profile deliberately does not support
    // S0ix entry. Keep hardware capability separate from supported policy.
    e.s0ixPolicyEnabled = false; f.s0ix = NV_FALSE; f.known |= S540_GLOBAL_FACT_S0IX;
    const unsigned int cpus = __atomic_load_n(&real_ncpus, __ATOMIC_ACQUIRE);
    const NvU64 frequency = gPEClockFrequencyInfo.cpu_frequency_hz;
    if (cpus && frequency) {
        f.cpuCount = cpus; f.cpuFrequencyHz = frequency; f.known |= S540_GLOBAL_FACT_CPU;
    }
    if (version_major > 0 && version_minor >= 0 && version_revision >= 0 && osrelease[0] && collectDate(impl_->osDate)) {
        f.osMajor = NvU32(version_major); f.osMinor = NvU32(version_minor);
        f.osBuild = NvU32(version_revision); f.osVersion = osrelease; f.osDate = impl_->osDate;
        f.known |= S540_GLOBAL_FACT_OS_VERSION;
    }
    e.known = f.known; e.missing = S540_GLOBAL_FACT_ALL & ~f.known;
    *out = f;
    return e.missing ? NV_ERR_NOT_READY : NV_OK;
}
NV_STATUS S540NvidiaGspPlatform::Context::collectSegment(NvU32 &segment) {
    if (!ordinary() || !impl_ || !impl_->acpi || impl_->provider->isInactive())
        return NV_ERR_NOT_READY;
    const IORegistryPlane *plane = IORegistryEntry::getPlane("IOACPIPlane");
    if (!plane) return NV_ERR_NOT_READY;
    IORegistryEntry *entry = impl_->acpi;
    entry->retain();
    NV_STATUS status = NV_ERR_NOT_READY;
    for (NvU32 depth = 0; entry && depth < 64; ++depth) {
        auto *device = OSDynamicCast(IOACPIPlatformDevice, entry);
        if (device && !device->isInactive() && rootBridge(device)) {
            UInt64 value = 0;
            const IOReturn validation = device->validateObject("_SEG");
            if (validation == kIOReturnSuccess &&
                device->evaluateInteger("_SEG", &value) == kIOReturnSuccess && value <= 0xffffU) {
                segment = NvU32(value); status = NV_OK;
            } else if (validation == kIOReturnNotFound) {
                // ACPI's missing-_SEG default applies only to this positively
                // identified PCI root bridge, never to the endpoint/parent.
                segment = 0; status = NV_OK;
            }
            break;
        }
        IORegistryEntry *parent = entry->copyParentEntry(plane);
        entry->release(); entry = parent;
    }
    if (entry) entry->release();
    return status;
}
NV_STATUS S540NvidiaGspPlatform::Context::collectDeviceFacts(S540GspDeviceFacts *out, void *pciHandle) {
    if (!ordinary() || !impl_ || !out || impl_->provider->isInactive()) return NV_ERR_INVALID_STATE;
    auto *provider = impl_->provider;
    S540GspDeviceFacts facts{};
    facts.format = 1; facts.pciHandle = pciHandle;
    facts.segmentKnown = collectSegment(facts.segment) == NV_OK;
    if (!provider->lockForArbitration(false)) return NV_ERR_BUSY_RETRY;
    bool valid = !provider->isInactive();
    if (valid) {
        facts.bus = provider->getBusNumber(); facts.slot = provider->getDeviceNumber();
        facts.function = provider->getFunctionNumber();
        for (NvU32 i = 0; i != 16; ++i) facts.configuration[i] = provider->configRead32(NvU8(i * 4U));
        facts.vendor = NvU16(facts.configuration[0]); facts.device = NvU16(facts.configuration[0] >> 16);
        facts.subsystemVendor = NvU16(facts.configuration[11]);
        facts.subsystemDevice = NvU16(facts.configuration[11] >> 16);
        valid = facts.vendor == 0x10de && facts.device == 0x1f91 &&
            facts.subsystemVendor == 0x17aa && facts.subsystemDevice == 0x3806 &&
            (facts.configuration[2] >> 8) == 0x030000U &&
            (facts.configuration[2] & 0xffU) == 0xa1 &&
            (facts.configuration[1] & 2U) && facts.slot < 32 && facts.function < 8;
        facts.pciConfigurationRead = valid;
    }
    NvU32 bar = 0;
    for (NvU32 offset = 0x10; valid && offset <= 0x24; offset += 4) {
        const NvU32 low = facts.configuration[offset / 4U];
        if (!low) continue;
        const NvU32 kind = low & 7U;
        if ((kind != 0 && kind != 4) || bar == 3 || (kind == 4 && offset == 0x24)) { valid = false; break; }
        NvU64 physical = low & ~NvU32(15);
        if (kind == 4) physical |= NvU64(facts.configuration[offset / 4U + 1U]) << 32;
        IODeviceMemory *memory = provider->getDeviceMemoryWithRegister(NvU8(offset));
        IOByteCount span = 0;
        const NvU64 address = memory ? memory->getPhysicalSegment(0, &span, kIOMemoryMapperNone) : 0;
        const NvU64 bytes = memory ? memory->getLength() : 0;
        valid = physical && address == physical && bytes && span >= bytes &&
            physical <= ~NvU64(0) - bytes;
        if (valid) facts.bars[bar++] = S540GspBar{physical, bytes, offset};
        if (kind == 4) offset += 4;
    }
    facts.barsVerified = valid && bar == 3;
    NvU8 capability = NvU8(facts.configuration[13] & 0xfcU);
    NvU64 visited = 0;
    bool express = false;
    if (!(facts.configuration[1] & (1U << 20))) capability = 0;
    for (NvU32 count = 0; capability && count < 48; ++count) {
        if (capability < 0x40 || capability > 0xfc || (capability & 3U)) { valid = false; break; }
        const NvU64 bit = NvU64(1) << (capability / 4U);
        if (visited & bit) { valid = false; break; }
        visited |= bit;
        const NvU8 id = provider->configRead8(capability);
        if (id == 1 && capability <= 0xf8) facts.poweredD0 = (provider->configRead16(NvU8(capability + 4)) & 3U) == 0;
        if (id == 0x10 && capability <= 0xf4) {
            const NvU16 flags = provider->configRead16(NvU8(capability + 2));
            express = ((flags >> 4) & 15U) == 0; // PCI Express endpoint
        }
        capability = NvU8(provider->configRead8(NvU8(capability + 1)) & 0xfcU);
    }
    if (capability) valid = false;
    provider->unlockForArbitration();
    // Original Linux coherent-GPU-memory discovery is AArch64-only. This
    // verified x86 TU117 PCIe profile keeps that distinct NUMA feature NONE;
    // it does not describe or disable coherent CPU/PCIe host-memory DMA.
    facts.noCoherentGpuMemoryProfile = valid && facts.pciConfigurationRead && express && NVCPU_IS_X86_64;
    // Exhaust every active console record before publishing either fact. A
    // positive Intel record alone does not exclude a second NVIDIA console.
    const bool consoleExcluded = targetConsoleExcluded(provider);
    facts.intelConsoleVerified = consoleExcluded;
    facts.nvidiaConsoleExcluded = consoleExcluded;
    *out = facts;
    return valid && facts.segmentKnown && facts.pciConfigurationRead && facts.barsVerified &&
        facts.poweredD0 && facts.intelConsoleVerified && facts.nvidiaConsoleExcluded &&
        facts.noCoherentGpuMemoryProfile ? NV_OK : NV_ERR_NOT_READY;
}
NV_STATUS S540NvidiaGspPlatform::Context::readRom(nv_state_t *state, const NvU32 *input, NvU32 *output) {
    if (!ordinary() || !impl_ || !state || !impl_->state || state != impl_->state || impl_->provider->isInactive())
        return NV_ERR_INVALID_STATE;
    if (!input || !output || !romRequestValid(input[0], input[1])) return NV_ERR_INVALID_ARGUMENT;
    if (!impl_->acpi || !impl_->evidence.romAvailable) return NV_ERR_NOT_SUPPORTED;
    if (impl_->romInFlight) return NV_ERR_STATE_IN_USE;
    OSNumber *offset = OSNumber::withNumber(input[0], 32);
    OSNumber *length = OSNumber::withNumber(input[1], 32);
    if (!offset || !length) {
        if (offset) offset->release(); if (length) length->release();
        return NV_ERR_NO_MEMORY;
    }
    OSObject *params[2] = {offset, length};
    OSObject *result = nullptr;
    ++impl_->evidence.romCalls; ++impl_->romInFlight;
    const IOReturn status = impl_->acpi->evaluateObject("_ROM", &result, params, 2);
    auto *bytes = OSDynamicCast(OSData, result);
    const bool ok = status == kIOReturnSuccess && bytes &&
        bytes->getLength() >= input[1] && bytes->getLength() <= kMaximumRomBytes;
    if (ok) bcopy(bytes->getBytesNoCopy(), output, input[1]);
    else ++impl_->evidence.romFailures;
    if (result) result->release();
    length->release(); offset->release(); --impl_->romInFlight;
    return ok ? NV_OK : NV_ERR_OPERATING_SYSTEM;
}
S540NvidiaGspPlatform::Evidence S540NvidiaGspPlatform::Context::evidence() const {
    return impl_ ? impl_->evidence : Evidence{};
}
NV_STATUS S540NvidiaGspPlatform::Context::shutdown() {
    if (!impl_) return NV_OK;
    if (!ordinary() || impl_->romInFlight) return NV_ERR_IN_USE;
    if (currentContext != this) return NV_ERR_INVALID_STATE;
    currentContext = nullptr;
    if (impl_->acpi) impl_->acpi->release();
    impl_->provider->release(); IOFree(impl_, sizeof(Impl)); impl_ = nullptr;
    return NV_OK;
}
extern "C" NV_STATUS NV_API_CALL s540Global_nv_acpi_rom_method(
    nv_state_t *state, NvU32 *input, NvU32 *output) {
    return currentContext ? currentContext->readRom(state, input, output) : NV_ERR_NOT_SUPPORTED;
}
#else
// Native tests exercise bounded binary decoders only. They do not invent a
// Darwin registry, ACPI namespace, EFI table or kernel CPU-frequency result.
S540NvidiaGspPlatform::Context::Context() : impl_(nullptr) {}
S540NvidiaGspPlatform::Context::~Context() = default;
bool S540NvidiaGspPlatform::Context::active() const { return false; }
NV_STATUS S540NvidiaGspPlatform::Context::initialize(IOPCIDevice *, nv_state_t *) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS S540NvidiaGspPlatform::Context::bindState(nv_state_t *) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS S540NvidiaGspPlatform::Context::shutdown() { return NV_OK; }
NV_STATUS S540NvidiaGspPlatform::Context::collect(S540NvidiaGlobalRmPlatformFacts *) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS S540NvidiaGspPlatform::Context::collectSegment(NvU32 &) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS S540NvidiaGspPlatform::Context::collectDeviceFacts(S540GspDeviceFacts *, void *) { return NV_ERR_NOT_SUPPORTED; }
NV_STATUS S540NvidiaGspPlatform::Context::readRom(nv_state_t *, const NvU32 *, NvU32 *) { return NV_ERR_NOT_SUPPORTED; }
S540NvidiaGspPlatform::Evidence S540NvidiaGspPlatform::Context::evidence() const { return Evidence{}; }
extern "C" NV_STATUS NV_API_CALL s540Global_nv_acpi_rom_method(nv_state_t *, NvU32 *, NvU32 *) { return NV_ERR_NOT_SUPPORTED; }
#endif
