// SPDX-License-Identifier: MIT
#include "S540NvidiaDma.hpp"

#if defined(KERNEL)
// SDK API contract: acidanthera/MacKernelSDK
// 3f750085caa17ec3a7880f11c11bf4f48cd6a164. Lifecycle semantics cross-checked
// against apple-oss-distributions/xnu f6217f891ac0bb64f3d375211650a4c1ff8ca1ea.
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IODMACommand.h>
#include <IOKit/IOMapper.h>
#include <IOKit/IOService.h>
#include <machine/machine_routines.h>
#else
#include <cstdlib>
#endif

namespace {
using namespace S540NvidiaDma;

struct Segment {
    NvU64 address;
    NvU64 length;
};

#if !defined(KERNEL)
Fault nativeFault = Fault::None;
MapperMode nativeMapperMode = MapperMode::Provider;
NvU32 liveResources = 0;
NvU32 illegalOperations = 0;
#endif

// The kernel and native backends expose the same operations to the single
// state machine. Their only difference is the OS resource implementation.
class Backend {
public:
#if defined(KERNEL)
    IOBufferMemoryDescriptor *buffer = nullptr;
    IODMACommand *command = nullptr;
    IOMapper *mapper = nullptr;
#else
    NvU8 *buffer = nullptr;
    bool command = false;
    bool mapper = false;
    bool descriptorPrepared = false;
    bool attached = false;
    bool commandPrepared = false;
#endif

    bool allowed(IOService *provider) {
#if defined(KERNEL)
        return provider && !ml_at_interrupt_context() &&
               ml_get_interrupts_enabled();
#else
        return provider && nativeFault != Fault::Context;
#endif
    }

    bool selectMapper(IOService *provider, MapperMode &mode) {
#if defined(KERNEL)
        // copyMapperForDevice() can wait without a deadline when iommu-parent
        // is an unresolved registry identifier. Do not enter that path from a
        // bounded startup check. A published IOMapper object is retained here.
        OSObject *property = provider->copyProperty("iommu-parent");
        if (!property) {
            mode = MapperMode::DirectUntranslated;
            return true;
        }
        mapper = OSDynamicCast(IOMapper, property);
        if (mapper)
            mapper->retain();
        property->release();
        mode = mapper ? MapperMode::Provider : MapperMode::Unavailable;
        return mapper != nullptr;
#else
        (void)provider;
        mode = nativeFault == Fault::MapperUnresolved ?
                   MapperMode::Unavailable : nativeMapperMode;
        if (mode == MapperMode::Unavailable)
            return false;
        mapper = mode == MapperMode::Provider;
        if (mapper)
            ++liveResources;
        return true;
#endif
    }

    bool allocate() {
#if defined(KERNEL)
        // Default kernel memory is wired. No physically-contiguous request,
        // pageable buffer, GPU memory, low-address constraint or cache override.
        buffer = IOBufferMemoryDescriptor::withOptions(
                                                       kIODirectionOut | kIOMemoryMapperNone,
                                                       kBytes, 4096);
#else
        if (nativeFault != Fault::BufferAllocation) {
            void *memory = nullptr;
            if (posix_memalign(&memory, 4096, kBytes) == 0)
                buffer = static_cast<NvU8 *>(memory);
        }
        if (buffer)
            ++liveResources;
#endif
        return buffer != nullptr;
    }

    NvU8 *contents() {
#if defined(KERNEL)
        if (!buffer || buffer->getLength() != kBytes)
            return nullptr;
        return static_cast<NvU8 *>(buffer->getBytesNoCopy());
#else
        return nativeFault == Fault::BufferContents ? nullptr : buffer;
#endif
    }

    bool prepareBuffer() {
#if defined(KERNEL)
        return buffer->prepare(kIODirectionOut) == kIOReturnSuccess;
#else
        if (!buffer || descriptorPrepared) {
            ++illegalOperations;
            return false;
        }
        descriptorPrepared = nativeFault != Fault::BufferPrepare;
        return descriptorPrepared;
#endif
    }

    bool allocateCommand(MapperMode mode) {
#if defined(KERNEL)
        // A null mapper with kMapped silently selects/waits for gSystem. Use
        // kUnmapped explicitly for the separately reported direct-only path.
        const auto mapping = mode == MapperMode::Provider ?
                                 IODMACommand::kMapped : IODMACommand::kUnmapped;
        command = IODMACommand::withSpecification(
            kIODMACommandOutputHost64, 64, kMaxSegmentBytes, mapping,
            kBytes, 16, mapper, nullptr);
#else
        (void)mode;
        command = nativeFault != Fault::CommandAllocation;
        if (command)
            ++liveResources;
#endif
        return command != 0;
    }

    bool attach() {
#if defined(KERNEL)
        return command->setMemoryDescriptor(buffer, false) == kIOReturnSuccess;
#else
        if (!command || !descriptorPrepared || attached) {
            ++illegalOperations;
            return false;
        }
        attached = nativeFault != Fault::Attach;
        return attached;
#endif
    }

    bool prepareCommand() {
#if defined(KERNEL)
        return command->prepare(0, kBytes, true, true) == kIOReturnSuccess;
#else
        if (!attached || commandPrepared) {
            ++illegalOperations;
            return false;
        }
        // XNU increments its prepare counter before mapping can fail.
        commandPrepared = true;
        return nativeFault != Fault::CommandPrepare;
#endif
    }

    bool next(NvU64 &offset, Segment &segment, NvU32 &count) {
#if defined(KERNEL)
        IODMACommand::Segment64 current{};
        UInt64 currentOffset = offset;
        UInt32 currentCount = 1;
        const IOReturn status = command->gen64IOVMSegments(
            &currentOffset, &current, &currentCount);
        offset = currentOffset;
        count = currentCount;
        segment.address = current.fIOVMAddr;
        segment.length = current.fLength;
        return status == kIOReturnSuccess;
#else
        if (!commandPrepared) {
            ++illegalOperations;
            return false;
        }
        if (nativeFault == Fault::SegmentsError)
            return false;
        count = nativeFault == Fault::SegmentsZero ? 0 :
                (nativeFault == Fault::SegmentsCount ? 2 : 1);
        segment.address = 0x100000ULL + offset;
        segment.length = nativeFault == Fault::SegmentLength ?
                             kMaxSegmentBytes + 1 : kMaxSegmentBytes;
        if (nativeFault == Fault::SegmentsExhaustion)
            segment.length = 512;
        if (nativeFault == Fault::SegmentAlignment)
            ++segment.address;
        if (nativeFault == Fault::SegmentAddressOverflow)
            segment.address = ~NvU64(0) - 1;
        if (nativeFault != Fault::SegmentsNoProgress)
            offset += segment.length;
        if (nativeFault == Fault::SegmentsOvershoot)
            offset = kBytes + 1;
        return true;
#endif
    }

    void maybeCorruptPattern(NvU8 *bytes) {
#if !defined(KERNEL)
        if (nativeFault == Fault::PatternCorruption)
            bytes[kBytes / 2] ^= 1;
#else
        (void)bytes;
#endif
    }

    bool completeCommand(bool prepareFailed) {
#if defined(KERNEL)
        const IOReturn status = command->complete(true, true);
        return status == kIOReturnSuccess ||
               (prepareFailed && status == kIOReturnNotReady);
#else
        (void)prepareFailed;
        if (!commandPrepared) {
            ++illegalOperations;
            return false;
        }
        commandPrepared = false;
        return nativeFault != Fault::CommandComplete;
#endif
    }

    bool clear() {
#if defined(KERNEL)
        // Explicitly refuse implicit repeated completion. complete() decrements
        // the single prepare count even when its unmap operation reports error.
        return command->clearMemoryDescriptor(false) == kIOReturnSuccess;
#else
        if (!attached || commandPrepared) {
            ++illegalOperations;
            return false;
        }
        attached = false;
        // Inject a failed returned status after the modeled detach operation;
        // this tests error reporting, not an arbitrary kernel clear failure.
        return nativeFault != Fault::Clear;
#endif
    }

    bool completeBuffer() {
#if defined(KERNEL)
        return buffer->complete(kIODirectionOut) == kIOReturnSuccess;
#else
        if (!descriptorPrepared || commandPrepared || attached) {
            ++illegalOperations;
            return false;
        }
        descriptorPrepared = false;
        return nativeFault != Fault::BufferComplete;
#endif
    }

    void releaseCommand() {
#if defined(KERNEL)
        if (command)
            command->release();
        command = nullptr;
#else
        if (command) {
            if (attached || commandPrepared)
                ++illegalOperations;
            --liveResources;
        }
        command = false;
#endif
    }

    void releaseBuffer() {
#if defined(KERNEL)
        if (buffer)
            buffer->release();
        buffer = nullptr;
#else
        if (buffer) {
            if (descriptorPrepared || attached || commandPrepared)
                ++illegalOperations;
            std::free(buffer);
            --liveResources;
        }
        buffer = nullptr;
#endif
    }

    void releaseMapper() {
#if defined(KERNEL)
        if (mapper)
            mapper->release();
        mapper = nullptr;
#else
        if (mapper)
            --liveResources;
        mapper = false;
#endif
    }
};

void require(Result &result, bool &field, bool passed,
             Reason reason = Reason::SegmentsInvalid)
{
    ++result.checks;
    field = passed;
    if (!passed) {
        ++result.failures;
        if (result.reason == Reason::None)
            result.reason = reason;
    }
}

NvU8 patternAt(NvU32 offset)
{
    return static_cast<NvU8>((offset * 37U) ^ (offset >> 8) ^ 0xa5U);
}

} // namespace

S540NvidiaDma::Result S540NvidiaDma::check(IOService *provider)
{
    Result result{};
    result.mapperMode = MapperMode::Unavailable;
    result.cleanup = true;
    Backend backend;
    bool bufferPrepared = false;
    bool attached = false;
    bool commandPrepared = false;
    bool commandPrepareAttempted = false;
    NvU8 *bytes = nullptr;

    require(result, result.context, backend.allowed(provider), Reason::InvalidContext);
    if (!result.context)
        return result;
    require(result, result.supported,
            backend.selectMapper(provider, result.mapperMode), Reason::MapperUnavailable);
    if (!result.supported)
        goto cleanup;
    require(result, result.allocation, backend.allocate(), Reason::AllocationFailed);
    if (!result.allocation)
        goto cleanup;
    bytes = backend.contents();
    require(result, result.allocation, bytes != nullptr, Reason::ContentsUnavailable);
    if (!result.allocation)
        goto cleanup;
    for (NvU32 i = 0; i < kBytes; ++i)
        bytes[i] = patternAt(i);
    require(result, result.descriptorPrepared, backend.prepareBuffer(),
            Reason::DescriptorPrepareFailed);
    if (!result.descriptorPrepared)
        goto cleanup;
    bufferPrepared = true;
    require(result, result.commandPrepared,
            backend.allocateCommand(result.mapperMode), Reason::CommandAllocationFailed);
    if (!result.commandPrepared)
        goto cleanup;
    require(result, result.commandPrepared, backend.attach(), Reason::AttachFailed);
    if (!result.commandPrepared)
        goto cleanup;
    attached = true;
    commandPrepareAttempted = true;
    require(result, result.commandPrepared, backend.prepareCommand(),
            Reason::CommandPrepareFailed);
    if (!result.commandPrepared)
        goto cleanup;
    commandPrepared = true;
    {
        NvU64 offset = 0;
        NvU64 total = 0;
        result.segmentsValid = true;
        for (NvU32 i = 0; offset < kBytes && i < kMaxSegments; ++i) {
            const NvU64 previous = offset;
            Segment segment{};
            NvU32 count = 1;
            const bool generated = backend.next(offset, segment, count);
            const bool valid = generated && count == 1 &&
                segment.length != 0 && segment.length <= kMaxSegmentBytes &&
                segment.length <= kBytes - total && offset > previous &&
                offset <= kBytes && offset - previous == segment.length &&
                (segment.address & 15U) == 0 &&
                segment.address <= ~NvU64(0) - (segment.length - 1);
            bool current;
            require(result, current, valid);
            if (!current) {
                result.segmentsValid = false;
                break;
            }
            total += segment.length;
            ++result.segments;
        }
        bool covered;
        require(result, covered, result.segmentsValid && offset == kBytes &&
                                 total == kBytes && result.segments != 0);
        result.segmentsValid = covered;
        result.bytes = total;
    }
    if (!result.segmentsValid)
        goto cleanup;
    backend.maybeCorruptPattern(bytes);
    {
        bool intact = true;
        for (NvU32 i = 0; i < kBytes; ++i)
            intact = (bytes[i] == patternAt(i)) && intact;
        require(result, result.pattern, intact, Reason::PatternMismatch);
    }

cleanup:
    // Every operation below corresponds to one successful transition above.
    // Cleanup continues after a reported completion error, without retries.
    result.completion = commandPrepared;
    if (commandPrepareAttempted) {
        bool completed;
        // Exactly one attempt was made. A failed prepare may have incremented
        // fActive; one complete unwinds it. NotReady is harmless only when
        // prepare itself failed before incrementing. No implicit completion loop.
        require(result, completed, backend.completeCommand(!commandPrepared),
                Reason::CommandCompleteFailed);
        result.completion = completed && commandPrepared;
        result.cleanup = completed && result.cleanup;
    }
    if (attached) {
        bool cleared;
        require(result, cleared, backend.clear(), Reason::ClearFailed);
        result.cleanup = cleared && result.cleanup;
    }
    backend.releaseCommand();
    if (bufferPrepared) {
        bool completed;
        require(result, completed, backend.completeBuffer(), Reason::DescriptorCompleteFailed);
        result.completion = completed && result.completion;
        result.cleanup = completed && result.cleanup;
    }
    backend.releaseBuffer();
    backend.releaseMapper();
    bool cleaned;
    require(result, cleaned, result.cleanup);
    result.cleanup = cleaned;
    result.providerMappingVerified = result.passed() &&
                                    result.mapperMode == MapperMode::Provider;
    return result;
}

#if !defined(KERNEL)
void S540NvidiaDma::setNativeFault(Fault fault) { nativeFault = fault; }
void S540NvidiaDma::setNativeMapperMode(MapperMode mode) { nativeMapperMode = mode; }
NvU32 S540NvidiaDma::nativeLiveResources() { return liveResources; }
NvU32 S540NvidiaDma::nativeIllegalOperations() { return illegalOperations; }
#endif
