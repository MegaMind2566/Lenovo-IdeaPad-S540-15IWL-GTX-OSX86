// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_FIRMWARE_HPP
#define S540_NVIDIA_FIRMWARE_HPP

#include "nvtypes.h"

// CPU-only preflight. The buffers are borrowed, immutable CPU memory, never MMIO.
// No firmware binary or approved firmware-image hash is included in this build.
namespace S540NvidiaFirmware {
enum class Error : NvU32 { Ok, MissingImage, Header, Range, Alignment, Names,
    Duplicate, MissingSection, Version, BuildId, UnapprovedImage,
    TransportNotReady, RpcHeader, RpcLength, RpcSequence, Stale, Busy, Timeout };
struct Span { NvU64 offset, size; };
struct Image { Span version, image, signature, buildId; NvU64 size; };
struct Layout { NvU64 commandHeader, commandData, statusHeader, statusData, total; };
struct RpcWindow { bool pending; NvU32 sequence; NvU64 deadline; };
struct Result {
    NvU32 checks, failures;
    bool parser, rpc, layout, cleanup, realImageReady;
    bool passed() const { return failures == 0 && parser && rpc && layout && cleanup; }
};

Error inspect(const void *bytes, NvU64 size, Image *out);
// SHA256 is calculated from bytes, never accepted as a caller assertion.
bool sha256(const void *bytes, NvU64 size, NvU8 digest[32]);
Error readiness(const void *bytes, NvU64 size, bool transportReady);
bool planLayout(NvU64 commandBytes, NvU64 statusBytes, NvU64 maxBytes, Layout *out);
Error validateRpc(const void *bytes, NvU64 size, NvU32 expectedSequence);
Error begin(RpcWindow *window, NvU32 sequence, NvU64 now, NvU64 timeout);
Error complete(RpcWindow *window, const void *bytes, NvU64 size, NvU64 now);
void cancel(RpcWindow *window);
Result selfCheck();
}

#endif
