// SPDX-License-Identifier: MIT
#include "S540NvidiaProviderSession.hpp"
#if defined(KERNEL)
#include <IOKit/pci/IOPCIDevice.h>
#endif
namespace S540NvidiaRmPci {
namespace {
#if defined(KERNEL)
class ProviderArbitration {
    IOPCIDevice *provider_;
    bool locked_;
public:
    explicit ProviderArbitration(IOPCIDevice *provider) : provider_(provider),
        locked_(provider && provider->lockForArbitration(false)) {}
    ~ProviderArbitration() { if (locked_) provider_->unlockForArbitration(); }
    bool acquired() const { return locked_; }
};
#endif
struct Checks {
    Result &result;
    bool current;
    explicit Checks(Result &value) : result(value), current(true) {}
    void operator()(bool passed) { ++result.checks; if (!passed) { ++result.failures; current = false; } }
    bool finish() { const bool value = current; current = true; return value; }
};
#if !defined(KERNEL)
// Explicit backend fixture for the same production check. No fixture address
// or a userspace read is presented as an actual PCI or kernel result.
struct StartupFixture {
    NvU32 references;
    static bool retain(void *value) { ++static_cast<StartupFixture *>(value)->references; return true; }
    static void release(void *value) { --static_cast<StartupFixture *>(value)->references; }
    static bool inactive(void *) { return false; }
    static bool bdf(void *, NvU8 &bus, NvU8 &device, NvU8 &function) { bus = 1; device = 0; function = 0; return true; }
    static bool read(void *, NvU32 offset, NvU32 width, NvU32 &value) {
        if (!validConfigurationAccess(offset, width)) return false;
        const NvU32 base = offset & ~NvU32{3};
        const NvU32 word = base == 0 ? 0x1f9110deU : base == 8 ? 0x030000a1U :
                           base == 0x2c ? 0x380617aaU : 0;
        value = word >> ((offset & 3U) * 8);
        if (width == 1) value &= 0xffU;
        if (width == 2) value &= 0xffffU;
        return true;
    }
};
#endif
}
#if defined(KERNEL)
Result check(IOPCIDevice *provider) {
#else
Result check() {
    StartupFixture fixture = {};
#endif
    Result result = {};
    Checks expect(result);
#if defined(KERNEL)
    // Framework arbitration is recursive for the calling thread and may wait
    // for another owner. false permits refusal; it is not a try-lock.
    ProviderArbitration providerGuard(provider);
    expect(providerGuard.acquired());
    if (!providerGuard.acquired()) return result;
#endif
    ProviderSession owner;
    expect(owner.ready());
    if (!owner.ready()) return result;
#if defined(KERNEL)
    const NV_STATUS started = owner.start(provider);
#else
    ProviderSession::Backend backend = {&fixture, StartupFixture::retain, StartupFixture::release,
        StartupFixture::read, StartupFixture::inactive, StartupFixture::bdf, false, 0};
    const NV_STATUS started = owner.startNative(backend);
#endif
    expect(started == NV_OK);
    if (started != NV_OK) {
        result.session = expect.finish();
        expect(owner.stop() == NV_OK && !owner.active() && owner.inFlight() == 0);
        result.cleanup = expect.finish();
        return result;
    }
    Metadata metadata = {};
    void *token = owner.handle();
    expect(token != nullptr && owner.active());
    expect(owner.metadata(metadata) == NV_OK);
    expect(metadata.identityVerified && metadata.readOnly && !metadata.providerOpened && !metadata.segmentKnown);
    expect(metadata.vendorDevice == 0x1f9110deU && metadata.revisionClass == 0x030000a1U && metadata.subsystem == 0x380617aaU);
    result.session = expect.finish();
    NvU8 byte = 0; NvU16 word = 0; NvU32 dword = 0;
    expect(owner.readByte(token, 0, &byte) == NV_OK && byte == 0xde);
    expect(owner.readWord(token, 0, &word) == NV_OK && word == 0x10de);
    expect(owner.readDword(token, 0, &dword) == NV_OK && dword == 0x1f9110deU);
    // This reads PCI extended configuration metadata, not GPU BAR MMIO.
    // Any returned value is acceptable: no AER/VC capability is fabricated.
    expect(owner.readDword(token, 0x100, &dword) == NV_OK);
    result.reads = expect.finish();
    word = 9; dword = 9;
    expect(owner.readWord(token, 1, &word) == NV_ERR_INVALID_ARGUMENT && word == 0);
    expect(owner.readDword(reinterpret_cast<void *>(~NvUPtr{0}), 0, &dword) == NV_ERR_INVALID_STATE && dword == 0);
    expect(owner.readDword(token, 4096, &dword) == NV_ERR_INVALID_ARGUMENT && dword == 0);
    void *lookup = reinterpret_cast<void *>(NvUPtr{1});
    NvU16 vendor = 0, device = 0;
    expect(owner.lookup(0, metadata.bus, metadata.device, metadata.function, &lookup, &vendor, &device) == NV_ERR_NOT_SUPPORTED && lookup == nullptr && vendor == 0xffffU && device == 0xffffU);
    result.handles = expect.finish();
    expect(owner.inFlight() == 0);
    expect(owner.stop() == NV_OK);
    expect(!owner.active() && owner.handle() == nullptr);
    result.lifecycle = expect.finish();
    expect(owner.readDword(token, 0, &dword) == NV_ERR_INVALID_STATE && dword == 0);
    expect(owner.stop() == NV_OK && owner.inFlight() == 0);
#if !defined(KERNEL)
    expect(fixture.references == 0);
#endif
    result.cleanup = expect.finish();
    return result;
}
} // namespace S540NvidiaRmPci
