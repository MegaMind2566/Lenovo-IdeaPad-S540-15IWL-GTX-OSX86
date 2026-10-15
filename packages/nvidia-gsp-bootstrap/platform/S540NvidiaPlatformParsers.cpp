// SPDX-License-Identifier: MIT
#include "S540NvidiaGspPlatform.hpp"

namespace {
NvU32 little32(const NvU8 *p) {
    return NvU32(p[0]) | (NvU32(p[1]) << 8) | (NvU32(p[2]) << 16) |
           (NvU32(p[3]) << 24);
}
}

bool S540NvidiaGspPlatform::decodeChassis(const void *table, NvU64 bytes,
                                         bool &notebook) {
    if (!table || bytes < 6 || bytes > 1024U * 1024U) return false;
    const auto *p = static_cast<const NvU8 *>(table);
    NvU64 offset = 0;
    bool found = false, value = false;
    NvU32 records = 0;
    while (offset < bytes) {
        if (++records > 4096 || bytes - offset < 4) return false;
        const NvU8 type = p[offset], length = p[offset + 1];
        if (length < 4 || length > bytes - offset) return false;
        if (type == 3) {
            if (length < 9) return false;
            // SMBIOS Type 3 byte 5: bit 7 is the chassis lock flag.
            const NvU8 chassis = p[offset + 5] & 0x7fU;
            if (!chassis || chassis == 2) return false; // unspecified/unknown
            const bool current = chassis == 9 || chassis == 10;
            if (found && value != current) return false;
            found = true; value = current;
        }
        NvU64 next = offset + length;
        while (next + 1 < bytes && (p[next] || p[next + 1])) ++next;
        if (next + 1 >= bytes) return false;
        offset = next + 2;
        if (type == 127) break;
    }
    if (!found) return false;
    notebook = value;
    return true;
}

bool S540NvidiaGspPlatform::decodeFadt(const void *table, NvU64 bytes,
                                      bool &lowPowerS0) {
    if (!table || bytes < 116 || bytes > 1024U * 1024U) return false;
    const auto *p = static_cast<const NvU8 *>(table);
    if (p[0] != 'F' || p[1] != 'A' || p[2] != 'C' || p[3] != 'P') return false;
    const NvU32 length = little32(p + 4);
    if (length < 116 || length > bytes) return false;
    NvU8 checksum = 0;
    for (NvU32 i = 0; i < length; ++i) checksum = NvU8(checksum + p[i]);
    if (checksum) return false;
    // ACPI FADT Flags, offset 112, LOW_POWER_S0_IDLE_CAPABLE bit 21.
    lowPowerS0 = (little32(p + 112) & (1U << 21)) != 0;
    return true;
}

bool S540NvidiaGspPlatform::romRequestValid(NvU32 offset, NvU32 bytes) {
    return bytes && bytes <= kMaximumRomChunk && offset < kMaximumRomBytes &&
           bytes <= kMaximumRomBytes - offset;
}

void S540NvidiaGspPlatform::observeConsoleOwner(ConsoleOwnership &state,
    bool ownerKnown, NvU32 vendor, NvU32 classCode, bool boundTarget) {
    if (state.frames == ~NvU32(0)) { state.overflow = true; return; }
    ++state.frames;
    if (!ownerKnown || (classCode & 0xff0000U) != 0x030000U) ++state.unknownOwners;
    else if (boundTarget) ++state.targetOwners;
    else if (vendor == 0x8086) ++state.intelOwners;
}

bool S540NvidiaGspPlatform::consoleExcludesTarget(const ConsoleOwnership &state,
    bool complete) {
    return complete && !state.overflow && state.frames != 0 &&
        state.intelOwners != 0 && state.targetOwners == 0 && state.unknownOwners == 0;
}
