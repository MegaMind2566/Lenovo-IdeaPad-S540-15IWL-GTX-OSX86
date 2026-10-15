// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_FIRMWARE_ASSETS_HPP
#define S540_NVIDIA_FIRMWARE_ASSETS_HPP
#include "nvtypes.h"

// Borrowed immutable CPU image bytes. No API in this component uploads firmware
// or turns on bus mastering, interrupts, SEC2, GSP or any GPU engine.
namespace S540NvidiaFirmwareAssets {
enum class Error : NvU32 { Ok, Missing, Size, Hash, Elf, Header, Count,
    Fingerprint, Directory, Range, Overlap, Alignment };
struct Ucodes { NvU32 entries, present; NvU64 fingerprint, directoryBytes; };
struct Radix3 { NvU64 pages[4], tableBytes, dataBytes, allocationBytes; };
struct Result {
    NvU32 checks, failures;
    bool imageVerified, ucodesVerified, releaseMatched, signaturePresent;
    bool ucodesDirectory, radixLayout, cleanup;
    // An authenticity check of a signed GPU binary requires the GPU's secure
    // boot chain. Source/hash identification is deliberately reported separately.
    bool firmwareLoaded, gpuInitialized;
    bool passed() const { return failures==0 && imageVerified && ucodesVerified &&
        releaseMatched && signaturePresent && ucodesDirectory && radixLayout &&
        cleanup && !firmwareLoaded && !gpuInitialized; }
};
Error inspectUcodes(const void *bytes, NvU64 size, Ucodes *out);
bool planRadix3(NvU64 dataBytes, NvU64 maxAllocationBytes, Radix3 *out);
Result verifyPair(const void *gsp, NvU64 gspSize, const void *ucodes, NvU64 ucodesSize);
// Fixture validation is separate from verifyPair; never claims a real image.
struct CheckResult { NvU32 checks, failures; bool passed() const {return failures==0;} };
CheckResult selfCheck();
}
#endif
