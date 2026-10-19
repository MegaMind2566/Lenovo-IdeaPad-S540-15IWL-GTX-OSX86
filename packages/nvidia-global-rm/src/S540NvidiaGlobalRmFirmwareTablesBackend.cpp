// SPDX-License-Identifier: MIT
#include "S540NvidiaGlobalRmFirmwareTables.h"
#if defined(KERNEL)
#include <IOKit/IORegistryEntry.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <libkern/c++/OSData.h>
#include <machine/machine_routines.h>
#endif

namespace {
NvU32 little32(const NvU8 *p) {
    return NvU32(p[0]) | (NvU32(p[1]) << 8) | (NvU32(p[2]) << 16) | (NvU32(p[3]) << 24);
}
NvU64 little64(const NvU8 *p) { return NvU64(little32(p)) | (NvU64(little32(p + 4)) << 32); }
bool signature(const NvU8 *p) {
    const NvU8 expected[] = {'R', 'S', 'D', ' ', 'P', 'T', 'R', ' '};
    for (unsigned i = 0; i < sizeof(expected); ++i) if (p[i] != expected[i]) return false;
    return true;
}
bool checksum(const NvU8 *p, NvU32 bytes) {
    NvU8 sum = 0;
    for (NvU32 i = 0; i < bytes; ++i) sum = NvU8(sum + p[i]);
    return sum == 0;
}
#if defined(KERNEL)
NV_STATUS physicalRead(void *, NvU64 address, NvU8 *out, NvU32 bytes) {
    if (!out || !bytes || bytes > 64 || !address || address > 0xFFFFFFFFULL ||
        address + bytes > 0x100000000ULL) return NV_ERR_INVALID_ARGUMENT;
    // AppleSMBIOS uses a physical withAddressRange descriptor with an explicit
    // no-mapper option for EFI table data. No DMA translation is involved.
    IOMemoryDescriptor *memory = IOMemoryDescriptor::withAddressRange(
        address, bytes, kIODirectionIn | kIOMemoryMapperNone, nullptr);
    if (!memory) return NV_ERR_NO_MEMORY;
    const IOReturn prepared = memory->prepare(kIODirectionIn);
    if (prepared != kIOReturnSuccess) { memory->release(); return NV_ERR_INVALID_READ; }
    NV_STATUS status = memory->readBytes(0, out, bytes) == bytes
        ? NV_STATUS(NV_OK) : NV_STATUS(NV_ERR_INVALID_READ);
    if (memory->complete(kIODirectionIn) != kIOReturnSuccess) status = NV_ERR_INVALID_READ;
    memory->release();
    return status;
}
NV_STATUS configurationAddress(const char *path, const NvU8 (&expectedGuid)[16], NvU64 &address) {
    IORegistryEntry *entry = IORegistryEntry::fromPath(path);
    if (!entry) return NV_ERR_OBJECT_NOT_FOUND;
    OSObject *guidObject = entry->copyProperty("guid");
    OSObject *tableObject = entry->copyProperty("table");
    OSData *guid = OSDynamicCast(OSData, guidObject);
    OSData *table = OSDynamicCast(OSData, tableObject);
    NV_STATUS status = NV_ERR_INVALID_DATA;
    bool matched = guidObject == nullptr;
    // The named GUID entry is Apple's original lookup convention. If the
    // optional binary GUID property is published, require its exact value too.
    if (guid && guid->getLength() == 16) {
        const auto *actualGuid = static_cast<const NvU8 *>(guid->getBytesNoCopy());
        matched = actualGuid != nullptr;
        for (unsigned i = 0; actualGuid && i < 16; ++i)
            if (actualGuid[i] != expectedGuid[i]) matched = false;
    }
    if (matched && table) {
        status = S540NvidiaFirmwareTables::decodeTableAddress(
            static_cast<const NvU8 *>(table->getBytesNoCopy()), table->getLength(), address);
    }
    if (guidObject) guidObject->release();
    if (tableObject) tableObject->release();
    entry->release();
    return status;
}
#endif
}

NV_STATUS S540NvidiaFirmwareTables::decodeTableAddress(const NvU8 *bytes, NvU32 length, NvU64 &result) {
    if (!bytes || (length != 4 && length != 8)) return NV_ERR_INVALID_DATA;
    result = little32(bytes);
    if (length == 8) result = little64(bytes);
    return NV_OK;
}

NV_STATUS S540NvidiaFirmwareTables::validateRsdp(const Reader &reader, NvU64 physical, NvU32 &result) {
    if (!reader.read || !physical || (physical & 15) || physical > 0xFFFFFFFFULL - 19)
        return NV_ERR_INVALID_ARGUMENT;
    NvU8 header[36] = {};
    NV_STATUS status = reader.read(reader.context, physical, header, 20);
    if (status != NV_OK) return status;
    if (!signature(header) || !checksum(header, 20) || header[15] == 1) return NV_ERR_INVALID_DATA;
    if (header[15] >= 2) {
        if (physical > 0xFFFFFFFFULL - 35) return NV_ERR_INVALID_OFFSET;
        status = reader.read(reader.context, physical, header, sizeof(header));
        if (status != NV_OK) return status;
        if (!signature(header) || !checksum(header, 20) || header[15] < 2)
            return NV_ERR_INVALID_DATA;
        const NvU32 length = little32(header + 20);
        if (length < sizeof(header)) return NV_ERR_INVALID_DATA;
        if (length > 4096) return NV_ERR_NOT_SUPPORTED;
        if (physical + length > 0x100000000ULL) return NV_ERR_INVALID_OFFSET;
        NvU8 sum = 0, bytes[64];
        for (NvU32 offset = 0; offset < length;) {
            const NvU32 count = length - offset < sizeof(bytes) ? length - offset : sizeof(bytes);
            status = reader.read(reader.context, physical + offset, bytes, count);
            if (status != NV_OK) return status;
            for (NvU32 i = 0; i < count; ++i) sum = NvU8(sum + bytes[i]);
            offset += count;
        }
        if (sum != 0 || little64(header + 24) == 0) return NV_ERR_INVALID_DATA;
    } else if (little32(header + 16) == 0) return NV_ERR_INVALID_DATA;
    result = static_cast<NvU32>(physical);
    return NV_OK;
}

extern "C" NV_STATUS s540GlobalRmReadFirmwareRsdp(NvU32 *physical) {
    if (!physical) return NV_ERR_INVALID_ARGUMENT;
#if defined(KERNEL)
    if (ml_at_interrupt_context() || !ml_get_interrupts_enabled()) return NV_ERR_INVALID_STATE;
    IORegistryEntry *configuration = IORegistryEntry::fromPath(
        "IODeviceTree:/efi/configuration-table");
    if (!configuration) return NV_ERR_NOT_SUPPORTED;
    configuration->release();
    // Device-tree properties only locate a candidate. Do not publish their
    // pointer until actual bounded physical reads validate the RSDP payload.
    static const NvU8 acpi20[] = {0x71,0xe8,0x68,0x88,0xf1,0xe4,0xd3,0x11,0xbc,0x22,0,0x80,0xc7,0x3c,0x88,0x81};
    static const NvU8 acpi10[] = {0x30,0x2d,0x9d,0xeb,0x88,0x2d,0xd3,0x11,0x9a,0x16,0,0x90,0x27,0x3f,0xc1,0x4d};
    NvU64 candidate = 0;
    NV_STATUS status = configurationAddress(
        "IODeviceTree:/efi/configuration-table/8868E871-E4F1-11D3-BC22-0080C73C8881", acpi20, candidate);
    if (status == NV_ERR_OBJECT_NOT_FOUND)
        status = configurationAddress(
            "IODeviceTree:/efi/configuration-table/8868e871-e4f1-11d3-bc22-0080c73c8881", acpi20, candidate);
    if (status == NV_ERR_OBJECT_NOT_FOUND)
        status = configurationAddress(
            "IODeviceTree:/efi/configuration-table/EB9D2D30-2D88-11D3-9A16-0090273FC14D", acpi10, candidate);
    if (status == NV_ERR_OBJECT_NOT_FOUND)
        status = configurationAddress(
            "IODeviceTree:/efi/configuration-table/eb9d2d30-2d88-11d3-9a16-0090273fc14d", acpi10, candidate);
    // An observed EFI configuration table with no ACPI entry is an operating
    // system lookup failure, as in the original CONFIG_EFI branch. An absent
    // supported publication was distinguished before looking up any entries.
    if (status != NV_OK) return status == NV_ERR_OBJECT_NOT_FOUND ? NV_STATUS(NV_ERR_OPERATING_SYSTEM) : status;
    NvU32 result = 0;
    status = S540NvidiaFirmwareTables::validateRsdp(
        S540NvidiaFirmwareTables::Reader{nullptr,physicalRead}, candidate, result);
    if (status == NV_OK) *physical = result;
    return status;
#else
    // A native userspace control has no authority to read physical firmware.
    return NV_ERR_NOT_SUPPORTED;
#endif
}
