// SPDX-License-Identifier: MIT
#include "S540NvidiaPciPolicy.hpp"
#if defined(KERNEL)
#include <IOKit/pci/IOPCIDevice.h>
#include <machine/machine_routines.h>
#endif

namespace {
S540NvidiaPci::Context *gActiveContext;
static_assert(__atomic_always_lock_free(sizeof(gActiveContext), nullptr),
              "The PCI startup binding must not allocate a runtime lock.");
bool ordinaryThread() {
#if defined(KERNEL)
    return !ml_at_interrupt_context() && ml_get_interrupts_enabled();
#else
    return true;
#endif
}
}

namespace S540NvidiaPci {
Context::Context() :
#if defined(KERNEL)
    device_(nullptr),
#else
    reader_(nullptr), opaque_(nullptr),
#endif
    bound_(false), reads_(0) {}
Context::~Context() { unbind(); }
bool Context::bound() const { return bound_; }
void *Context::handle() { return bound_ ? this : nullptr; }
Context *Context::authenticate(void *handle) {
    Context *active = __atomic_load_n(&gActiveContext, __ATOMIC_ACQUIRE);
    // Compare opaque pointers before inspecting storage: arbitrary handles must
    // never be dereferenced. Lifetime is externally serialized and quiescent.
    return handle != nullptr && handle == active && active->bound_ ? active : nullptr;
}
bool Context::rawRead(NvU32 offset, NvU32 width, NvU32 &value) {
    value = 0;
    if (!ordinaryThread() || !validAccess(offset, width)) return false;
#if defined(KERNEL)
    if (!device_) return false;
    // The pinned public SDK configRead wrappers dispatch to the exported
    // extendedConfigRead entry points even for a UInt8 argument. validAccess
    // above restricts every request to the first 256 bytes; the Apple
    // implementation therefore sets registerNumExtended to zero. No extended
    // configuration offset or config write is reachable through this adapter.
    const UInt8 byteOffset = static_cast<UInt8>(offset);
    if (width == 1) value = device_->configRead8(byteOffset);
    else if (width == 2) value = device_->configRead16(byteOffset);
    else value = device_->configRead32(byteOffset);
#else
    if (!reader_ || !reader_(opaque_, offset, width, value)) { value = 0; return false; }
#endif
    ++reads_;
    // All-ones subfields can be legitimate PCI metadata. Identity dwords are
    // separately verified; do not invent a read-failure sentinel for fields.
    return true;
}
bool Context::bindValidated() {
    if (!ordinaryThread() || bound_) return false;
    Context *expected = nullptr;
    if (!__atomic_compare_exchange_n(&gActiveContext, &expected, this, false,
                                     __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return false;
    NvU32 identity = 0, revision = 0, subsystem = 0;
    if (!rawRead(0, 4, identity) || !rawRead(8, 4, revision) ||
        !rawRead(0x2c, 4, subsystem) || !exactTarget(identity, revision, subsystem)) {
        expected = this;
        (void)__atomic_compare_exchange_n(&gActiveContext, &expected,
                  static_cast<Context *>(nullptr), false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
        return false;
    }
    bound_ = true;
    return true;
}
#if defined(KERNEL)
bool Context::bind(IOPCIDevice *device) {
    if (bound_ || !device) return false;
    device_ = device;
    if (bindValidated()) return true;
    device_ = nullptr;
    return false;
}
#else
bool Context::bindNative(Reader reader, void *opaque) {
    if (bound_ || !reader) return false;
    reader_ = reader; opaque_ = opaque;
    if (bindValidated()) return true;
    reader_ = nullptr; opaque_ = nullptr;
    return false;
}
#endif
void Context::unbind() {
    Context *expected = this;
    (void)__atomic_compare_exchange_n(&gActiveContext, &expected,
              static_cast<Context *>(nullptr), false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
    bound_ = false;
#if defined(KERNEL)
    device_ = nullptr;
#else
    reader_ = nullptr; opaque_ = nullptr;
#endif
}
NV_STATUS Context::read(NvU32 offset, NvU32 width, NvU32 &value) {
    value = 0;
    if (authenticate(this) != this || !ordinaryThread()) return NV_ERR_INVALID_STATE;
    if (!validAccess(offset, width)) return NV_ERR_INVALID_ARGUMENT;
    return rawRead(offset, width, value) ? NV_OK : NV_ERR_OPERATING_SYSTEM;
}

Inventory Context::inventory() {
    Inventory out = {};
    out.reason = "pci-context-unbound";
    if (authenticate(this) != this) return out;
    const NvU32 initialReads = reads_;
    NvU32 commandStatus = 0, header = 0, pointer = 0;
    if (read(4, 4, commandStatus) != NV_OK || read(0x0c, 4, header) != NV_OK ||
        read(0x34, 1, pointer) != NV_OK) { out.reason = "pci-config-unavailable"; return out; }
    out.command = static_cast<NvU16>(commandStatus);
    if (((header >> 16) & 0x7fU) != 0 || (commandStatus & 0x00100000U) == 0) {
        out.reason = "pci-capability-list-unavailable"; return out;
    }
    NvU64 visited = 0;
    NvU64 identifiers[4] = {};
    NvU32 occupied[48] = {};
    NvU32 offset = pointer;
    for (NvU32 links = 0; offset != 0 && links < kMaximumCapabilities; ++links) {
        if (!validCapabilityOffset(offset)) { out.reason = "pci-capability-offset-invalid"; return out; }
        const NvU64 bit = NvU64{1} << ((offset - 0x40) / 4);
        if (visited & bit) { out.reason = "pci-capability-cycle"; return out; }
        visited |= bit;
        NvU32 capability = 0;
        if (read(offset, 4, capability) != NV_OK || capability == 0xffffffffU) {
            out.reason = "pci-capability-unavailable"; return out;
        }
        const NvU32 id = capability & 0xffU;
        if (id == 0 || id == 0xffU) { out.reason = "pci-capability-id-invalid"; return out; }
        const NvU64 idBit = NvU64{1} << (id & 63U);
        // PM/MSI/MSI-X are single-instance capabilities. Vendor-specific
        // capabilities may legitimately repeat their ID; their linked
        // headers remain subject to the independent offset/cycle bound.
        if ((id == 1 || id == 5 || id == 0x11) &&
            (identifiers[id / 64] & idBit)) { out.reason = "pci-capability-id-duplicate"; return out; }
        identifiers[id / 64] |= idBit;
        ++out.capabilityCount;
        const NvU32 control = capability >> 16;
        NvU32 capabilityLength = 4;
        if (id == 1) {
            if (!withinCapabilitySpace(offset, 8) || (control & 7U) == 0 ||
                (control & 7U) > 3) { out.reason = "pci-pm-capability-invalid"; return out; }
            capabilityLength = 8;
            NvU32 pmcsr = 0;
            if (read(offset + 4, 2, pmcsr) != NV_OK) { out.reason = "pci-pm-unavailable"; return out; }
            out.pmOffset = static_cast<NvU8>(offset);
            out.powerState = static_cast<NvU8>(pmcsr & 3U);
        } else if (id == 5) {
            const NvU32 maximum = (control >> 1) & 7U;
            const NvU32 enabled = (control >> 4) & 7U;
            const NvU32 length = (control & 0x100U)
                ? ((control & 0x80U) ? 24U : 20U)
                : ((control & 0x80U) ? 14U : 10U);
            if (maximum > 5 || enabled > maximum || !withinCapabilitySpace(offset, length)) {
                out.reason = "pci-msi-capability-invalid"; return out;
            }
            capabilityLength = length;
            out.msiOffset = static_cast<NvU8>(offset);
            out.msiVectors = static_cast<NvU16>(1U << maximum);
            out.msiEnabledVectors = static_cast<NvU16>(1U << enabled);
            out.msiEnabled = (control & 1U) != 0;
        } else if (id == 0x11) {
            NvU32 table = 0, pba = 0;
            if (!withinCapabilitySpace(offset, 12) || read(offset + 4, 4, table) != NV_OK ||
                read(offset + 8, 4, pba) != NV_OK) { out.reason = "pci-msix-capability-invalid"; return out; }
            if ((table & 7U) > 5 || (pba & 7U) > 5) { out.reason = "pci-msix-bar-invalid"; return out; }
            capabilityLength = 12;
            out.msixOffset = static_cast<NvU8>(offset);
            out.msixVectors = static_cast<NvU16>((control & 0x7ffU) + 1);
            out.msixTableBar = static_cast<NvU8>(table & 7U);
            out.msixPbaBar = static_cast<NvU8>(pba & 7U);
            out.msixTableOffset = table & 0xfffffff8U;
            out.msixPbaOffset = pba & 0xfffffff8U;
            out.msixEnabled = (control & 0x8000U) != 0;
            out.msixFunctionMasked = (control & 0x4000U) != 0;
        }
        // Reject linked headers that overlap any known capability body. This
        // catches both forward- and backward-pointing partial overlaps.
        for (NvU32 previous = 0; previous + 1 < out.capabilityCount; ++previous) {
            const NvU32 begin = occupied[previous] & 0xffffU;
            const NvU32 end = occupied[previous] >> 16;
            if (offset < end && begin < offset + capabilityLength) {
                out.reason = "pci-capability-overlap"; return out;
            }
        }
        occupied[out.capabilityCount - 1] = offset | ((offset + capabilityLength) << 16);
        offset = (capability >> 8) & 0xffU;
    }
    if (offset != 0) { out.reason = "pci-capability-list-exhausted"; return out; }
    out.reads = reads_ - initialReads;
    if (!out.pmOffset || out.powerState != 0) { out.reason = "pci-not-d0"; return out; }
    out.reason = "pci-read-only-inventory-complete";
    out.valid = true;
    return out;
}

bool msixGeometry(const Inventory &inventory, NvU8 bar, NvU64 length) {
    if (!inventory.valid || !inventory.msixOffset || inventory.msixVectors == 0 ||
        inventory.msixVectors > 2048 || bar > 5 || length == 0) return false;
    const NvU64 tableBytes = NvU64{inventory.msixVectors} * 16;
    const NvU64 pbaBytes = ((NvU64{inventory.msixVectors} + 63) / 64) * 8;
    if (inventory.msixTableBar == inventory.msixPbaBar) {
        const NvU64 tableStart = inventory.msixTableOffset;
        const NvU64 pbaStart = inventory.msixPbaOffset;
        if (tableStart < pbaStart + pbaBytes && pbaStart < tableStart + tableBytes) return false;
    }
    bool relevant = false;
    if (inventory.msixTableBar == bar) {
        relevant = true;
        const NvU64 bytes = tableBytes;
        if (inventory.msixTableOffset >= length || bytes > length - inventory.msixTableOffset) return false;
    }
    if (inventory.msixPbaBar == bar) {
        relevant = true;
        const NvU64 bytes = pbaBytes;
        if (inventory.msixPbaOffset >= length || bytes > length - inventory.msixPbaOffset) return false;
    }
    return relevant;
}
}

extern "C" NV_STATUS NV_API_CALL os_pci_read_byte(void *handle, NvU32 offset, NvU8 *output) {
    if (!output) return NV_ERR_INVALID_POINTER;
    *output = 0;
    auto *context = S540NvidiaPci::Context::authenticate(handle);
    if (!context) return NV_ERR_INVALID_STATE;
    NvU32 value = 0; const NV_STATUS status = context->read(offset, 1, value);
    if (status == NV_OK) *output = static_cast<NvU8>(value);
    return status;
}
extern "C" NV_STATUS NV_API_CALL os_pci_read_word(void *handle, NvU32 offset, NvU16 *output) {
    if (!output) return NV_ERR_INVALID_POINTER;
    *output = 0;
    auto *context = S540NvidiaPci::Context::authenticate(handle);
    if (!context) return NV_ERR_INVALID_STATE;
    NvU32 value = 0; const NV_STATUS status = context->read(offset, 2, value);
    if (status == NV_OK) *output = static_cast<NvU16>(value);
    return status;
}
extern "C" NV_STATUS NV_API_CALL os_pci_read_dword(void *handle, NvU32 offset, NvU32 *output) {
    if (!output) return NV_ERR_INVALID_POINTER;
    *output = 0;
    auto *context = S540NvidiaPci::Context::authenticate(handle);
    if (!context) return NV_ERR_INVALID_STATE;
    NvU32 value = 0; const NV_STATUS status = context->read(offset, 4, value);
    if (status == NV_OK) *output = value;
    return status;
}
