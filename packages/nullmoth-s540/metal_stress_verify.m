#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <IOKit/IOKitLib.h>
#import <dispatch/dispatch.h>

static BOOL pciWord(io_registry_entry_t entry, CFStringRef key, uint16_t *value) {
    CFTypeRef property = IORegistryEntryCreateCFProperty(entry, key, kCFAllocatorDefault, 0);
    if (!property || CFGetTypeID(property) != CFDataGetTypeID() || CFDataGetLength(property) < 2) {
        if (property) CFRelease(property);
        return NO;
    }
    const UInt8 *bytes = CFDataGetBytePtr(property);
    *value = (uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8);
    CFRelease(property);
    return YES;
}

static id<MTLDevice> nvidiaDevice(void) {
    id<MTLDevice> found = nil;
    for (id<MTLDevice> candidate in MTLCopyAllDevices()) {
        io_registry_entry_t current = IOServiceGetMatchingService(kIOMainPortDefault,
                                                                   IORegistryEntryIDMatching(candidate.registryID));
        for (unsigned depth = 0; depth < 16 && current; ++depth) {
            io_name_t className = {0};
            if (IOObjectGetClass(current, className) == KERN_SUCCESS && strcmp(className, "IOPCIDevice") == 0) {
                uint16_t vendor = 0, device = 0;
                BOOL match = pciWord(current, CFSTR("vendor-id"), &vendor) &&
                             pciWord(current, CFSTR("device-id"), &device) &&
                             vendor == 0x10de && device == 0x1f91;
                IOObjectRelease(current);
                current = IO_OBJECT_NULL;
                if (match) {
                    if (found) return nil;
                    found = candidate;
                }
                break;
            }
            io_registry_entry_t parent = IO_OBJECT_NULL;
            kern_return_t status = IORegistryEntryGetParentEntry(current, kIOServicePlane, &parent);
            IOObjectRelease(current);
            current = status == KERN_SUCCESS ? parent : IO_OBJECT_NULL;
        }
        if (current) IOObjectRelease(current);
    }
    return found;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        id<MTLDevice> device = nvidiaDevice();
        if (!device) return 2;
        NSError *error = nil;
        NSString *source =
            @"#include <metal_stdlib>\n"
             "using namespace metal;\n"
             "kernel void stress(device const uint *input [[buffer(0)]],\n"
             "                   device uint *output [[buffer(1)]],\n"
             "                   constant uint &salt [[buffer(2)]],\n"
             "                   uint id [[thread_position_in_grid]]) {\n"
             "  uint v = input[id] ^ salt;\n"
             "  for (uint j = 0; j < 64; ++j) { v ^= v >> 13; v = v * 1664525u + 1013904223u; }\n"
             "  output[id] = v + id;\n"
             "}\n";
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        id<MTLFunction> function = [library newFunctionWithName:@"stress"];
        id<MTLComputePipelineState> pipeline =
            [device newComputePipelineStateWithFunction:function error:&error];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!library || !function || !pipeline || !queue) {
            fprintf(stderr, "FAIL_STRESS_SETUP: %s\n", error.localizedDescription.UTF8String ?: "unknown");
            return 3;
        }

        const NSUInteger count = 1024 * 1024;
        const NSUInteger bytes = count * sizeof(uint32_t);
        uint32_t rounds = 12;
        if (argc == 2) {
            unsigned long requested = strtoul(argv[1], NULL, 10);
            if (requested < 1 || requested > 1000) return 8;
            rounds = (uint32_t)requested;
        }
        id<MTLBuffer> input = [device newBufferWithLength:bytes options:MTLResourceStorageModeManaged];
        id<MTLBuffer> output = [device newBufferWithLength:bytes options:MTLResourceStorageModeManaged];
        if (!input || !output) return 4;
        uint32_t *in = input.contents;
        uint32_t *out = output.contents;
        CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();

        for (uint32_t round = 0; round < rounds; ++round) {
            uint32_t salt = 0x9e3779b9u ^ (round * 0x10203u);
            for (NSUInteger i = 0; i < count; ++i) {
                in[i] = (uint32_t)i * 2654435761u + round;
                out[i] = 0xdeadbeefu;
            }
            [input didModifyRange:NSMakeRange(0, bytes)];
            [output didModifyRange:NSMakeRange(0, bytes)];
            id<MTLCommandBuffer> command = [queue commandBuffer];
            id<MTLComputeCommandEncoder> compute = [command computeCommandEncoder];
            [compute setComputePipelineState:pipeline];
            [compute setBuffer:input offset:0 atIndex:0];
            [compute setBuffer:output offset:0 atIndex:1];
            [compute setBytes:&salt length:sizeof(salt) atIndex:2];
            NSUInteger width = MIN((NSUInteger)256, pipeline.maxTotalThreadsPerThreadgroup);
            [compute dispatchThreads:MTLSizeMake(count, 1, 1)
                 threadsPerThreadgroup:MTLSizeMake(width, 1, 1)];
            [compute endEncoding];
            id<MTLBlitCommandEncoder> blit = [command blitCommandEncoder];
            [blit synchronizeResource:output];
            [blit endEncoding];
            dispatch_semaphore_t done = dispatch_semaphore_create(0);
            [command addCompletedHandler:^(__unused id<MTLCommandBuffer> completed) {
                dispatch_semaphore_signal(done);
            }];
            [command commit];
            if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 20 * NSEC_PER_SEC)) != 0)
                return 5;
            if (command.status != MTLCommandBufferStatusCompleted) {
                fprintf(stderr, "FAIL_STRESS_COMMAND round=%u error=%s\n", round,
                        command.error.localizedDescription.UTF8String ?: "none");
                return 6;
            }
            for (NSUInteger i = 0; i < count; ++i) {
                uint32_t expected = in[i] ^ salt;
                for (uint32_t j = 0; j < 64; ++j) {
                    expected ^= expected >> 13;
                    expected = expected * 1664525u + 1013904223u;
                }
                expected += (uint32_t)i;
                if (out[i] != expected) {
                    fprintf(stderr, "FAIL_STRESS_VALUE round=%u index=%lu expected=%08x got=%08x\n",
                            round, (unsigned long)i, expected, out[i]);
                    return 7;
                }
            }
        }
        double seconds = CFAbsoluteTimeGetCurrent() - start;
        printf("PASS_STRESS_NVIDIA device=\"%s\" rounds=%u values=%lu bytes_per_round=%lu seconds=%.3f\n",
               device.name.UTF8String, rounds, (unsigned long)(count * rounds),
               (unsigned long)(bytes * 2), seconds);
        return 0;
    }
}
