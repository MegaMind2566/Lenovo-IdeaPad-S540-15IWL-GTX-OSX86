// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaPciPolicy.hpp"
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <initializer_list>
using namespace S540NvidiaPci;
namespace {
unsigned checks = 0, failures = 0;
void check(bool value) { ++checks; if (!value) { ++failures; std::fprintf(stderr, "PCI check %u failed\n", checks); } }
struct Fixture {
    unsigned char bytes[256]; unsigned reads; unsigned badReads; bool fail;
    static bool reader(void *opaque, NvU32 offset, NvU32 width, NvU32 &value) {
        auto *f = static_cast<Fixture *>(opaque);
        ++f->reads;
        if (!validAccess(offset, width)) { ++f->badReads; return false; }
        if (f->fail) return false;
        value = 0;
        for (NvU32 i = 0; i < width; ++i) value |= NvU32{f->bytes[offset + i]} << (8 * i);
        return true;
    }
    void put(unsigned offset, NvU32 value, unsigned width = 4) {
        for (unsigned i = 0; i < width; ++i) bytes[offset + i] = static_cast<unsigned char>(value >> (8 * i));
    }
    Fixture() : bytes{}, reads(0), badReads(0), fail(false) {
        put(0, 0x1f9110de); put(8, 0x030000a1); put(0x2c, 0x380617aa);
        put(4, 0x00100002); put(0x34, 0x40); put(0x40, 0x00035001); put(0x44, 0);
        // MSI supports 32 vectors, 64-bit address and a per-vector mask.
        put(0x50, 0x018a7015); bytes[0x50] = 5;
        put(0x70, 0x40070011); put(0x74, 0x1000); put(0x78, 0x2000);
    }
};
bool inspect(Fixture &fixture, const char *reason) {
    Context context; check(context.bindNative(Fixture::reader, &fixture));
    Inventory inventory = context.inventory();
    const bool matched = !inventory.valid && std::strcmp(inventory.reason, reason) == 0;
    check(fixture.badReads == 0); return matched;
}
}
int main() {
    check(validAccess(255, 1)); check(validAccess(254, 2)); check(validAccess(252, 4));
    check(!validAccess(256, 1)); check(!validAccess(255, 2)); check(!validAccess(254, 4));
    check(!validAccess(UINT32_MAX, 4)); check(!validAccess(0, 0)); check(!validAccess(0, 8));
    check(!validCapabilityOffset(0x3c)); check(!validCapabilityOffset(0x41)); check(validCapabilityOffset(0xfc));
    NvU32 bars[6] = {0x10000000U, 0x2000000cU, 0x00000001U,
                     0x30000000U, 0x40000000U, 0x50000000U};
    check(memoryBarType(bars, 0) == 0);
    check(memoryBarType(bars, 1) == 2); // prefetchable 64-bit base
    check(memoryBarType(bars, 2) == -1); // address high word resembles I/O
    check(memoryBarType(bars, 3) == 0); // skip the earlier high word
    check(memoryBarType(bars, 5) == 0);
    check(memoryBarType(bars, 6) == -1);
    check(memoryBarType(nullptr, 0) == -1);
    bars[1] = 0x20000004U; bars[2] = 0x10000004U;
    check(memoryBarType(bars, 2) == -1); // high word resembles another 64-bit base
    check(memoryBarType(bars, 3) == 0);
    bars[0] = 0x10000001U; check(memoryBarType(bars, 0) == -1);
    bars[0] = 0x10000002U; check(memoryBarType(bars, 0) == -1);
    bars[0] = 0x10000006U; check(memoryBarType(bars, 0) == -1);
    bars[0] = 0; check(memoryBarType(bars, 0) == -1);
    bars[0] = 8; check(memoryBarType(bars, 0) == -1);
    bars[0] = UINT32_MAX; check(memoryBarType(bars, 0) == -1);
    bars[0] = 4; bars[1] = 0; check(memoryBarType(bars, 0) == -1);
    bars[1] = 1; check(memoryBarType(bars, 0) == 2); // valid base above 4 GiB
    bars[5] = 0x50000004U; check(memoryBarType(bars, 5) == -1);
    check(descriptorTagMatches(0x02000010U, 0, 0));
    check(descriptorTagMatches(0x42000010U, 0, 0));
    check(descriptorTagMatches(0x03000014U, 1, 2));
    check(descriptorTagMatches(0x43000014U, 1, 2));
    check(!descriptorTagMatches(0x02000014U, 1, 2));
    check(!descriptorTagMatches(0x03000010U, 0, 0));
    check(!descriptorTagMatches(0x01000010U, 0, 0));
    check(!descriptorTagMatches(0x02000014U, 0, 0));
    check(!descriptorTagMatches(0x02000010U, 6, 0));
    check(!descriptorTagMatches(0x02000010U, 0, -1));
    check(!descriptorTagMatches(0x02000010U, 0, 1));
    NvU8 byte = 9; NvU16 word = 9; NvU32 dword = 9;
    check(os_pci_read_byte(nullptr, 0, &byte) != NV_OK && byte == 0);
    check(os_pci_read_word(reinterpret_cast<void *>(1), 0, &word) != NV_OK && word == 0);
    check(os_pci_read_dword(reinterpret_cast<void *>(~uintptr_t{0}), 0, &dword) != NV_OK && dword == 0);
    check(os_pci_read_byte(nullptr, 0, nullptr) == NV_ERR_INVALID_POINTER);
    check(os_pci_read_word(nullptr, 0, nullptr) == NV_ERR_INVALID_POINTER);
    check(os_pci_read_dword(nullptr, 0, nullptr) == NV_ERR_INVALID_POINTER);
    Fixture f; Context c; check(c.handle() == nullptr); check(c.bindNative(Fixture::reader, &f));
    check(c.bound()); check(c.handle() == &c); check(!c.bindNative(Fixture::reader, &f));
    Context second; check(!second.bindNative(Fixture::reader, &f)); check(!second.bound());
    check(os_pci_read_byte(c.handle(), 0, &byte) == NV_OK && byte == 0xde);
    check(os_pci_read_word(c.handle(), 0, &word) == NV_OK && word == 0x10de);
    check(os_pci_read_dword(c.handle(), 0, &dword) == NV_OK && dword == 0x1f9110de);
    check(os_pci_read_word(c.handle(), 1, &word) == NV_ERR_INVALID_ARGUMENT && word == 0);
    check(os_pci_read_dword(c.handle(), 2, &dword) == NV_ERR_INVALID_ARGUMENT && dword == 0);
    check(os_pci_read_dword(c.handle(), 256, &dword) == NV_ERR_INVALID_ARGUMENT && dword == 0);
    check(os_pci_read_byte(c.handle(), UINT32_MAX, &byte) == NV_ERR_INVALID_ARGUMENT && byte == 0);
    check(os_pci_read_byte(c.handle(), 255, &byte) == NV_OK);
    check(os_pci_read_word(c.handle(), 254, &word) == NV_OK);
    check(os_pci_read_dword(c.handle(), 252, &dword) == NV_OK);
    f.put(0xfc, 0xffffffff); check(os_pci_read_dword(c.handle(), 252, &dword) == NV_OK && dword == 0xffffffff);
    f.fail = true; check(os_pci_read_dword(c.handle(), 0, &dword) == NV_ERR_OPERATING_SYSTEM && dword == 0); f.fail = false;
    Inventory inventory = c.inventory();
    check(inventory.valid); check(inventory.capabilityCount == 3); check(inventory.reads == 9);
    check(inventory.pmOffset == 0x40 && inventory.powerState == 0);
    check(inventory.msiOffset == 0x50 && inventory.msiVectors == 32 && inventory.msiEnabledVectors == 1);
    check(inventory.msixOffset == 0x70 && inventory.msixVectors == 8);
    check(!inventory.msiEnabled && !inventory.msixEnabled && inventory.msixFunctionMasked);
    check(!inventory.interruptsArmed); check(msixGeometry(inventory, 0, 0x3000));
    check(!msixGeometry(inventory, 0, 0x107f)); check(!msixGeometry(inventory, 0, 0x2007));
    check(msixGeometry(inventory, 0, 0x2008)); check(!msixGeometry(inventory, 1, UINT64_MAX));
    check(!msixGeometry(inventory, 6, UINT64_MAX)); check(!msixGeometry(inventory, 0, 0));
    inventory.msixPbaOffset = 0x1078; check(!msixGeometry(inventory, 0, UINT64_MAX));
    inventory.msixPbaOffset = 0x1080; check(msixGeometry(inventory, 0, UINT64_MAX));
    inventory.msixPbaOffset = 0x2000;
    inventory.msixVectors = 2048; inventory.msixPbaOffset = 0x20000; check(msixGeometry(inventory, 0, UINT64_MAX));
    inventory.msixVectors = 2049; check(!msixGeometry(inventory, 0, UINT64_MAX));
    c.unbind(); check(!c.bound()); check(c.handle() == nullptr);
    check(os_pci_read_dword(&c, 0, &dword) != NV_OK && dword == 0);
    check(!c.inventory().valid); c.unbind(); check(second.bindNative(Fixture::reader, &f)); second.unbind();
    for (unsigned index : {0U, 8U, 0x2cU}) {
        Fixture wrong; wrong.bytes[index] ^= 1; Context target;
        check(!target.bindNative(Fixture::reader, &wrong)); check(!target.bound());
        check(target.bindNative(Fixture::reader, &f)); target.unbind();
    }
    Fixture failed; failed.fail = true; Context bad;
    check(!bad.bindNative(Fixture::reader, &failed)); check(!bad.bindNative(nullptr, nullptr));
    { Fixture x; x.put(0x34, 0); check(inspect(x, "pci-not-d0")); }
    { Fixture x; x.put(4, 2); check(inspect(x, "pci-capability-list-unavailable")); }
    { Fixture x; x.put(0x0c, 0x00010000); check(inspect(x, "pci-capability-list-unavailable")); }
    for (unsigned offset : {1U, 0x3cU, 0x41U, 0xffU}) { Fixture x; x.put(0x34, offset); check(inspect(x, "pci-capability-offset-invalid")); }
    { Fixture x; x.bytes[0x41] = 0x40; check(inspect(x, "pci-capability-cycle")); }
    { Fixture x; x.bytes[0x71] = 0x40; check(inspect(x, "pci-capability-cycle")); }
    { Fixture x; x.bytes[0x70] = 5; check(inspect(x, "pci-capability-id-duplicate")); }
    { Fixture x; x.bytes[0x40] = 0; check(inspect(x, "pci-capability-id-invalid")); }
    { Fixture x; x.put(0x40, 0xffffffff); check(inspect(x, "pci-capability-unavailable")); }
    { Fixture x; x.bytes[0x42] = 0; check(inspect(x, "pci-pm-capability-invalid")); }
    { Fixture x; x.bytes[0x44] = 3; check(inspect(x, "pci-not-d0")); }
    { Fixture x; x.bytes[0x52] = 0x0c; check(inspect(x, "pci-msi-capability-invalid")); }
    { Fixture x; x.bytes[0x52] = 0x10; check(inspect(x, "pci-msi-capability-invalid")); }
    { Fixture x; x.put(0x34, 0xfc); x.put(0xfc, 0x00030001); check(inspect(x, "pci-pm-capability-invalid")); }
    { Fixture x; x.put(0x34, 0xfc); x.put(0xfc, 0x00800005); check(inspect(x, "pci-msi-capability-invalid")); }
    { Fixture x; x.put(0x34, 0xf8); x.put(0xf8, 0x00000011); check(inspect(x, "pci-msix-capability-invalid")); }
    { Fixture x; x.put(0x74, 0x1006); check(inspect(x, "pci-msix-bar-invalid")); }
    { Fixture x; x.put(0x78, 0x2007); check(inspect(x, "pci-msix-bar-invalid")); }
    { Fixture x; x.bytes[0x51] = 0x54; x.put(0x54, 0x00000010); check(inspect(x, "pci-capability-overlap")); }
    { Fixture x; x.bytes[0x41] = 0; Context target; check(target.bindNative(Fixture::reader, &x)); const auto v = target.inventory(); check(v.valid && !v.msiOffset && !v.msixOffset && !v.interruptsArmed); }
    { Fixture x; x.bytes[0x71] = 0x80; x.put(0x80, 0x00009009); x.put(0x90, 0x00000009); Context target; check(target.bindNative(Fixture::reader, &x)); const auto v = target.inventory(); check(v.valid && v.capabilityCount == 5); }
    check(f.badReads == 0);
    std::printf("{\"format\":1,\"component\":\"nvidia-pci-transport\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\",\"gpu_access\":false,\"malformed_capabilities\":true,\"invalid_handles\":true,\"bounded_config_reads\":true,\"msix_geometry\":true,\"interrupts_armed\":false}\n", failures ? "failed" : "passed", checks, failures);
    return failures ? 1 : 0;
}
