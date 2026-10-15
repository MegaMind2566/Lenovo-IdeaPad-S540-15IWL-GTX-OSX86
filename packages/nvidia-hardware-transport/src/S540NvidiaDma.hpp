// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_DMA_HPP
#define S540_NVIDIA_DMA_HPP

#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"

class IOService;

namespace S540NvidiaDma {

constexpr NvU32 kBytes = 64U * 1024U;
constexpr NvU32 kMaxSegmentBytes = 4096;
constexpr NvU32 kMaxSegments = 32;

enum class MapperMode : NvU32 {
    Unavailable = 0,
    Provider = 1,
    DirectUntranslated = 2
};

enum class Reason : NvU32 {
    None, InvalidContext, MapperUnavailable, AllocationFailed,
    ContentsUnavailable, DescriptorPrepareFailed, CommandAllocationFailed,
    AttachFailed, CommandPrepareFailed, SegmentsInvalid, PatternMismatch,
    CommandCompleteFailed, ClearFailed, DescriptorCompleteFailed
};

struct Result {
    NvU32 checks;
    NvU32 failures;
    NvU32 segments;
    NvU64 bytes;
    bool context;
    bool supported;
    bool allocation;
    bool descriptorPrepared;
    bool commandPrepared;
    bool segmentsValid;
    bool pattern;
    bool completion;
    bool cleanup;
    bool providerMappingVerified;
    MapperMode mapperMode;
    Reason reason;

    bool passed() const {
        return checks != 0 && failures == 0 && context && supported &&
               allocation && descriptorPrepared && commandPrepared &&
               segmentsValid && pattern && completion && cleanup;
    }
};

// Ordinary-thread, single-owner, finite host-memory preparation only. No GPU
// command is issued and no returned DMA address escapes this operation. A
// direct-untranslated result does not establish device DMA compatibility.
Result check(IOService *provider);

#if !defined(KERNEL)
enum class Fault : NvU32 {
    None, Context, MapperUnresolved, BufferAllocation, BufferContents,
    BufferPrepare, CommandAllocation, Attach, CommandPrepare, SegmentsError,
    SegmentsZero, SegmentsNoProgress, SegmentsExhaustion, SegmentsOvershoot,
    SegmentsCount, SegmentAlignment, SegmentLength, SegmentAddressOverflow,
    PatternCorruption, CommandComplete, Clear, BufferComplete
};

// Deterministic native-only backend controls. The production state machine
// below is shared; none of these hooks are present in the kernel object.
void setNativeFault(Fault fault);
void setNativeMapperMode(MapperMode mode);
NvU32 nativeLiveResources();
NvU32 nativeIllegalOperations();
#endif

} // namespace S540NvidiaDma
#endif
