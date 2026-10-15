// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_PCI_HPP
#define S540_NVIDIA_PCI_HPP

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include "../../nvidia-os-adapter/upstream/include/nv-kernel-interface-api.h"

#if defined(KERNEL)
class IOPCIDevice;
#endif

namespace S540NvidiaPci {
// A read-only, standard-configuration-space profile of the exact NVIDIA ABI.
// Bind only while the provider's arbitration lock and the integrated startup
// lease are held. The provider is borrowed, never retained or opened here.
// All accesses and unbinding must finish on that serialized ordinary thread.
// This does not implement bus discovery, config writes or extended config.
struct Inventory {
    bool valid;
    const char *reason;
    NvU32 reads;
    NvU32 capabilityCount;
    NvU16 command;
    NvU8 pmOffset;
    NvU8 msiOffset;
    NvU8 msixOffset;
    NvU8 powerState;
    NvU16 msiVectors;
    NvU16 msiEnabledVectors;
    NvU16 msixVectors;
    NvU8 msixTableBar;
    NvU8 msixPbaBar;
    NvU32 msixTableOffset;
    NvU32 msixPbaOffset;
    bool msiEnabled;
    bool msixEnabled;
    bool msixFunctionMasked;
    // This profile never registers or arms an interrupt source. The enabled
    // bits above are observed firmware configuration, not a driver action.
    bool interruptsArmed;
};

class Context {
public:
    Context();
    ~Context();
#if defined(KERNEL)
    bool bind(IOPCIDevice *device);
#else
    using Reader = bool (*)(void *, NvU32 offset, NvU32 width, NvU32 &value);
    bool bindNative(Reader reader, void *opaque);
#endif
    void unbind();
    bool bound() const;
    void *handle();
    Inventory inventory();
    // Used by the exact C ABI after opaque-handle authentication. A valid out
    // pointer is zeroed before every invalid-handle/offset/context failure.
    NV_STATUS read(NvU32 offset, NvU32 width, NvU32 &value);
    static Context *authenticate(void *handle);
private:
#if defined(KERNEL)
    IOPCIDevice *device_;
#else
    Reader reader_;
    void *opaque_;
#endif
    bool bound_;
    NvU32 reads_;
    bool rawRead(NvU32 offset, NvU32 width, NvU32 &value);
    bool bindValidated();
    Context(const Context &) = delete;
    Context &operator=(const Context &) = delete;
};

// CPU-only prospective MSI-X geometry checks against an already assigned BAR
// length. No table/PBA mapping or read occurs. Zero/oversized lengths and
// invalid BIRs are rejected. IRQ setup/delivery remains unimplemented.
bool msixGeometry(const Inventory &inventory, NvU8 bar, NvU64 length);
}

// ABI reference: NVIDIA/open-gpu-kernel-modules commit
// 1a82fbfda8f321b056eb3568850f9316c5e465c5,
// src/nvidia/arch/nvalloc/unix/include/os-interface.h, declarations 103-105.
// The implementation is a deliberately narrower Darwin adapter, not the
// upstream Linux implementation: no bus lookup, writes or extended space.
extern "C" {
NV_STATUS NV_API_CALL os_pci_read_byte(void *, NvU32, NvU8 *);
NV_STATUS NV_API_CALL os_pci_read_word(void *, NvU32, NvU16 *);
NV_STATUS NV_API_CALL os_pci_read_dword(void *, NvU32, NvU32 *);
}
#endif
