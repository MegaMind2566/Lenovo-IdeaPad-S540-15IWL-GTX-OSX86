// SPDX-License-Identifier: MIT
#include "../src/nv_device_services.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
using namespace S540NvidiaDeviceTransport;
namespace {
unsigned checks;
void expect(bool condition, const char *message) {
    ++checks;
    if (!condition) { std::fprintf(stderr, "PCI PDI assertion failed: %s\n",message); std::exit(1); }
}
struct Configuration {
    NvU32 words[1024]{};
    NvU32 failedOffset = ~NvU32(0);
    NvU32 reads = 0;
    NvU32 lastOffset = 0;
};
NV_STATUS readDword(void *opaque, NvU32 offset, NvU32 &value) {
    auto &configuration = *static_cast<Configuration *>(opaque);
    ++configuration.reads;
    configuration.lastOffset = offset;
    if (offset == configuration.failedOffset || offset > 4092 || (offset & 3))
        return NV_ERR_INVALID_READ;
    value = configuration.words[offset / 4];
    return NV_OK;
}
void dvsec(Configuration &configuration, NvU32 offset, NvU32 next = 0,
           NvU32 vendor = 0x10de, NvU32 id = 3, NvU32 bytes = 0x14) {
    configuration.words[offset / 4] = (next << 20) | (1 << 16) | 0x23;
    if (offset <= 4084) {
        configuration.words[offset / 4 + 1] = (bytes << 20) | vendor;
        configuration.words[offset / 4 + 2] = id;
    }
}
void result(Configuration &configuration, NV_STATUS expected, const char *message) {
    NvU64 pdi = 0x87654321;
    expect(Detail::readPciPdi(Detail::PciDwordReader{&configuration,readDword},pdi) == expected,message);
    expect(pdi == 0x87654321,"failed PDI discovery preserves output");
}
}
int main() {
    NvU64 pdi = 7;
    expect(Detail::readPciPdi(Detail::PciDwordReader{},pdi) == NV_ERR_INVALID_ARGUMENT,
           "incomplete config reader refused");
    expect(s540Global_nv_pci_read_gpu_pdi_from_dvsec(nullptr,&pdi) == NV_ERR_INVALID_ARGUMENT,
           "null original state refused");
    auto *state = reinterpret_cast<nv_state_t *>(NvUPtr(0x540));
    expect(s540Global_nv_pci_read_gpu_pdi_from_dvsec(state,nullptr) == NV_ERR_INVALID_ARGUMENT,
           "null original output refused");
    expect(s540Global_nv_pci_read_gpu_pdi_from_dvsec(state,&pdi) == NV_ERR_INVALID_STATE && pdi == 7,
           "foreign/unbound state cannot cause PCI reads or publish fallback");
    Configuration empty;
    result(empty,NV_ERR_NOT_SUPPORTED,"actual empty extended-cap list permits original PBI fallback");
    expect(empty.reads == 1,"empty chain makes exactly one actual config read");
    Configuration other;
    dvsec(other,0x100,0,0x1234);
    result(other,NV_ERR_NOT_SUPPORTED,"foreign vendor DVSEC is not NVIDIA PDI");
    Configuration otherId;
    dvsec(otherId,0x100,0,0x10de,4);
    result(otherId,NV_ERR_NOT_SUPPORTED,"different NVIDIA DVSEC is not PDI");
    Configuration success;
    success.words[0x100 / 4] = (0x180 << 20) | 1;
    dvsec(success,0x180);
    success.words[0x18c / 4] = 0x12345678;
    success.words[0x190 / 4] = 0x9abcdef0;
    expect(Detail::readPciPdi(Detail::PciDwordReader{&success,readDword},pdi) == NV_OK &&
           pdi == 0x9abcdef012345678ULL,"real matching DVSEC3 combines both dwords");
    expect(success.reads == 6 && success.lastOffset == 0x190,"PDI reads use exact original offsets");
    Configuration zero;
    dvsec(zero,0x100);
    result(zero,NV_ERR_NOT_SUPPORTED,"actual zero PDI is unsupported as original");
    zero.words[0x10c / 4] = zero.words[0x110 / 4] = ~NvU32(0);
    result(zero,NV_ERR_NOT_SUPPORTED,"actual all-ones PDI is unsupported as original");
    Configuration shortCap;
    dvsec(shortCap,0x100,0,0x10de,3,0x10);
    result(shortCap,NV_ERR_INVALID_DATA,"short PDI capability is malformed, never absent");
    for (NvU32 next : {NvU32(0xfc),NvU32(0x101)}) {
        Configuration malformed;
        malformed.words[0x100 / 4] = (next << 20) | 1;
        result(malformed,NV_ERR_INVALID_OFFSET,"invalid capability pointer does not permit PBI fallback");
    }
    Configuration tail;
    tail.words[0x100 / 4] = (0xff0U << 20) | 1;
    dvsec(tail,0xff0);
    result(tail,NV_ERR_INVALID_OFFSET,"fixed PDI fields must fit config space");
    Configuration unreadableTail;
    unreadableTail.words[0x100 / 4] = (0xffcU << 20) | 1;
    dvsec(unreadableTail,0xffc);
    result(unreadableTail,NV_ERR_INVALID_READ,"DVSEC headers beyond config space are read failures");
    for (NvU32 offset : {NvU32(0x100),NvU32(0x104),NvU32(0x108),NvU32(0x10c),NvU32(0x110)}) {
        Configuration failed;
        dvsec(failed,0x100);
        failed.words[0x10c / 4] = 0x1234;
        failed.failedOffset = offset;
        result(failed,NV_ERR_INVALID_READ,"every header/PDI read failure preserves error distinction");
    }
    Configuration cycle;
    cycle.words[0x100 / 4] = (0x100 << 20) | 1;
    result(cycle,NV_ERR_CYCLE_DETECTED,"cycle exhausts the exact original bounded traversal");
    expect(cycle.reads == 480,"capability chain traversal is bounded to480 actual reads");
    std::printf("{\"format\":1,\"component\":\"nvidia-pci-pdi\",\"status\":\"passed\","
                "\"failures\":0,\"execution\":\"native-user-space\","
                "\"checks\":%u,\"maximum_capability_iterations\":480,\"kernel_execution\":\"not_tested\","
                "\"gpu_access\":false,\"hardware_pdi_read\":false}\n",checks);
}
