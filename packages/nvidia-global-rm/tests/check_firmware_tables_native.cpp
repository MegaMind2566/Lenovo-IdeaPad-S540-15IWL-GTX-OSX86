// SPDX-License-Identifier: MIT
#include "S540NvidiaGlobalRmFirmwareTables.h"
#include <cstdio>
#include <cstdlib>
using namespace S540NvidiaFirmwareTables;
extern "C" int s540RsdpOriginalAbiControl(void);
namespace {
unsigned checks;
void expect(bool value, const char *why) {
    ++checks; if (!value) { std::fprintf(stderr,"RSDP assertion: %s\n",why); std::exit(1); }
}
struct Firmware {
    NvU8 bytes[4096]{};
    NvU64 address = 0x1000;
    NvU32 reads = 0, maximum = 0, failRead = 0;
};
NV_STATUS read(void *opaque, NvU64 address, NvU8 *out, NvU32 count) {
    auto &fixture = *static_cast<Firmware *>(opaque);
    ++fixture.reads;
    if (fixture.failRead == fixture.reads) return NV_ERR_INVALID_READ;
    if (!out || address < fixture.address || address - fixture.address > sizeof(fixture.bytes) ||
        count > sizeof(fixture.bytes) - (address - fixture.address)) return NV_ERR_INVALID_READ;
    if (count > fixture.maximum) fixture.maximum = count;
    for (NvU32 i = 0; i < count; ++i) out[i] = fixture.bytes[address - fixture.address + i];
    return NV_OK;
}
void checksum(Firmware &f, NvU32 count, NvU32 offset) {
    f.bytes[offset] = 0;
    NvU8 sum = 0; for (NvU32 i = 0; i < count; ++i) sum = NvU8(sum + f.bytes[i]);
    f.bytes[offset] = NvU8(0 - sum);
}
void seed(Firmware &f, NvU8 revision = 0, NvU32 count = 36) {
    f = Firmware{};
    const char signature[] = "RSD PTR ";
    for (NvU32 i = 0; i < 8; ++i) f.bytes[i] = signature[i];
    f.bytes[15] = revision;
    f.bytes[17] = 0x20;
    if (revision >= 2) f.bytes[25] = 0x30;
    for (NvU32 i = 0; i < 4; ++i) f.bytes[20 + i] = NvU8(count >> (8 * i));
    checksum(f,20,8);
    if (revision >= 2 && count >= 36 && count <= 4096) checksum(f,count,32);
}
void failure(Firmware &f, NvU64 address, NV_STATUS status, const char *why) {
    NvU32 out = 0xabcdef;
    expect(validateRsdp(Reader{&f,read},address,out) == status,why);
    expect(out == 0xabcdef,"failure preserves output");
}
}
int main() {
    const int abi = s540RsdpOriginalAbiControl();
    if (abi != 3) return 1;
    checks += 3;
    Firmware f; NvU32 out = 7;
    NvU64 decoded = 0xaaaa;
    const NvU8 property[8] = {0x10,0x32,0x54,0x76,0x98,0xba,0xdc,0xfe};
    expect(decodeTableAddress(nullptr,8,decoded) == NV_ERR_INVALID_DATA && decoded == 0xaaaa,"null property preserves output");
    expect(decodeTableAddress(property,3,decoded) == NV_ERR_INVALID_DATA && decoded == 0xaaaa,"partial pointer refused");
    expect(decodeTableAddress(property,9,decoded) == NV_ERR_INVALID_DATA && decoded == 0xaaaa,"oversized pointer refused");
    expect(decodeTableAddress(property,4,decoded) == NV_OK && decoded == 0x76543210,"actual4-byte EFI pointer decoded");
    expect(decodeTableAddress(property,8,decoded) == NV_OK && decoded == 0xfedcba9876543210ULL,"actual8-byte EFI pointer never truncated");
    expect(validateRsdp(Reader{},0x1000,out) == NV_ERR_INVALID_ARGUMENT && out == 7,"absent reader refused");
    seed(f); failure(f,0,NV_ERR_INVALID_ARGUMENT,"zero physical pointer refused");
    failure(f,0x1001,NV_ERR_INVALID_ARGUMENT,"unaligned pointer refused");
    failure(f,0x100000000ULL,NV_ERR_INVALID_ARGUMENT,"address above original32-bitABI refused");
    failure(f,0xfffffff0ULL,NV_ERR_INVALID_ARGUMENT,"prefix cannot cross4GiB");
    expect(f.reads == 0,"invalid addresses perform no reads");
    expect(validateRsdp(Reader{&f,read},f.address,out) == NV_OK && out == f.address,"valid actual legacy payload accepted");
    expect(f.reads == 1 && f.maximum == 20,"legacy payload reads exact20 bytes");
    seed(f); f.bytes[0] = 'X'; failure(f,f.address,NV_ERR_INVALID_DATA,"bad signature rejected");
    seed(f); ++f.bytes[8]; failure(f,f.address,NV_ERR_INVALID_DATA,"bad legacy checksum rejected");
    seed(f); f.bytes[17] = 0; checksum(f,20,8); failure(f,f.address,NV_ERR_INVALID_DATA,"legacy RSDT address0 is unusable");
    seed(f,1); failure(f,f.address,NV_ERR_INVALID_DATA,"undefined revision1 rejected");
    seed(f); f.failRead = 1; failure(f,f.address,NV_ERR_INVALID_READ,"real prefix read failure preserved");
    seed(f,2);
    expect(validateRsdp(Reader{&f,read},f.address,out) == NV_OK && out == f.address,"valid extended payload accepted");
    expect(f.reads == 3 && f.maximum == 36,"extended header and checksum reads bounded");
    seed(f,2); f.bytes[25] = 0; checksum(f,36,32); failure(f,f.address,NV_ERR_INVALID_DATA,"extended XSDT address0 is unusable");
    seed(f,2); ++f.bytes[32]; failure(f,f.address,NV_ERR_INVALID_DATA,"bad extended checksum rejected");
    seed(f,2,35); failure(f,f.address,NV_ERR_INVALID_DATA,"short extended length rejected");
    seed(f,2,4097); failure(f,f.address,NV_ERR_NOT_SUPPORTED,"oversized extended length rejected");
    seed(f,2,0); failure(f,f.address,NV_ERR_INVALID_DATA,"zero extended length rejected");
    seed(f,2); f.address = 0xffffffe0ULL; failure(f,f.address,NV_ERR_INVALID_OFFSET,"extended prefix cannot cross4GiB");
    seed(f,2,64); f.address = 0xffffffe0ULL; failure(f,f.address,NV_ERR_INVALID_OFFSET,"extended map bound rejects before prefix");
    seed(f,2,4096);
    expect(validateRsdp(Reader{&f,read},f.address,out) == NV_OK && out == f.address,"bounded future extended payload checksum accepted");
    expect(f.reads == 66 && f.maximum == 64,"largest admitted payload uses64-byte chunks");
    seed(f,2); f.failRead = 2; failure(f,f.address,NV_ERR_INVALID_READ,"extended header read error preserved");
    seed(f,2); f.failRead = 3; failure(f,f.address,NV_ERR_INVALID_READ,"extended payload read error preserved");
    expect(s540GlobalRmReadFirmwareRsdp(nullptr) == NV_ERR_INVALID_ARGUMENT,"null platform output refused");
    out = 0x1234;
    expect(s540GlobalRmReadFirmwareRsdp(&out) == NV_ERR_NOT_SUPPORTED && out == 0x1234,"native control has no physical memory authority");
    std::printf("{\"format\":1,\"component\":\"nvidia-firmware-table-parser\",\"status\":\"passed\",\"failures\":0,\"checks\":%u,\"maximum_table_bytes\":4096,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false,\"physical_firmware_read\":false}\n",checks);
}
