#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <IOKit/IOKitLib.h>
#import <dispatch/dispatch.h>

static BOOL readPCIWord(io_registry_entry_t entry, CFStringRef key, uint16_t *value) {
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

static BOOL deviceHasExpectedPCIIdentity(id<MTLDevice> device, uint16_t *vendor, uint16_t *deviceID) {
    io_registry_entry_t current = IOServiceGetMatchingService(kIOMainPortDefault,
                                                               IORegistryEntryIDMatching(device.registryID));
    if (!current) return NO;
    BOOL matched = NO;
    for (unsigned depth = 0; depth < 16 && current; ++depth) {
        io_name_t className = {0};
        if (IOObjectGetClass(current, className) == KERN_SUCCESS && strcmp(className, "IOPCIDevice") == 0) {
            uint16_t v = 0, d = 0;
            if (readPCIWord(current, CFSTR("vendor-id"), &v) &&
                readPCIWord(current, CFSTR("device-id"), &d)) {
                *vendor = v;
                *deviceID = d;
                matched = (v == 0x10de && d == 0x1f91);
            }
            IOObjectRelease(current);
            return matched;
        }
        io_registry_entry_t parent = IO_OBJECT_NULL;
        kern_return_t status = IORegistryEntryGetParentEntry(current, kIOServicePlane, &parent);
        IOObjectRelease(current);
        current = status == KERN_SUCCESS ? parent : IO_OBJECT_NULL;
    }
    if (current) IOObjectRelease(current);
    return NO;
}

int main(void) {
    @autoreleasepool {
        NSArray<id<MTLDevice>> *devices = MTLCopyAllDevices();
        id<MTLDevice> target = nil;
        uint16_t vendor = 0, deviceID = 0;
        for (id<MTLDevice> candidate in devices) {
            uint16_t v = 0, d = 0;
            if (deviceHasExpectedPCIIdentity(candidate, &v, &d)) {
                if (target) {
                    fprintf(stderr, "FAIL_IDENTITA_AMBIGUA: piu dispositivi 10DE:1F91\n");
                    return 2;
                }
                target = candidate;
                vendor = v;
                deviceID = d;
            }
        }
        if (!target) {
            fprintf(stderr, "FAIL_NVIDIA_ASSENTE: nessun dispositivo Metal PCI 10DE:1F91\n");
            return 3;
        }

        NSError *error = nil;
        NSString *source =
            @"#include <metal_stdlib>\n"
             "using namespace metal;\n"
             "kernel void verify_values(device const uint *input [[buffer(0)]],\n"
             "                          device uint *output [[buffer(1)]],\n"
             "                          constant uint &salt [[buffer(2)]],\n"
             "                          uint id [[thread_position_in_grid]]) {\n"
             "    output[id] = input[id] * 3u + salt;\n"
             "}\n";
        id<MTLLibrary> library = [target newLibraryWithSource:source options:nil error:&error];
        if (!library) {
            fprintf(stderr, "FAIL_SHADER: %s\n", error.localizedDescription.UTF8String);
            return 4;
        }
        id<MTLFunction> function = [library newFunctionWithName:@"verify_values"];
        id<MTLComputePipelineState> pipeline =
            [target newComputePipelineStateWithFunction:function error:&error];
        if (!pipeline) {
            fprintf(stderr, "FAIL_PIPELINE: %s\n", error.localizedDescription.UTF8String);
            return 5;
        }
        id<MTLCommandQueue> queue = [target newCommandQueue];
        if (!queue) {
            fprintf(stderr, "FAIL_CODA: impossibile creare la command queue NVIDIA\n");
            return 6;
        }

        const NSUInteger count = 64;
        const NSUInteger byteCount = count * sizeof(uint32_t);
        id<MTLBuffer> input = [target newBufferWithLength:byteCount options:MTLResourceStorageModeManaged];
        id<MTLBuffer> output = [target newBufferWithLength:byteCount options:MTLResourceStorageModeManaged];
        if (!input || !output) {
            fprintf(stderr, "FAIL_BUFFER: allocazione managed rifiutata\n");
            return 7;
        }

        for (uint32_t round = 0; round < 20; ++round) {
            uint32_t *in = input.contents;
            uint32_t *out = output.contents;
            uint32_t salt = 0x13579u + round * 17u;
            for (uint32_t i = 0; i < count; ++i) {
                in[i] = (round + 1u) * 1009u + i * 37u;
                out[i] = 0xdeadbeefu;
            }
            [input didModifyRange:NSMakeRange(0, byteCount)];
            [output didModifyRange:NSMakeRange(0, byteCount)];

            id<MTLCommandBuffer> command = [queue commandBuffer];
            id<MTLComputeCommandEncoder> compute = [command computeCommandEncoder];
            [compute setComputePipelineState:pipeline];
            [compute setBuffer:input offset:0 atIndex:0];
            [compute setBuffer:output offset:0 atIndex:1];
            [compute setBytes:&salt length:sizeof(salt) atIndex:2];
            NSUInteger width = MIN((NSUInteger)64, pipeline.maxTotalThreadsPerThreadgroup);
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
            if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC)) != 0) {
                fprintf(stderr, "FAIL_TIMEOUT: round %u\n", round);
                return 8;
            }
            if (command.status != MTLCommandBufferStatusCompleted) {
                fprintf(stderr, "FAIL_COMMAND: round %u status %lu error %s\n", round,
                        (unsigned long)command.status,
                        command.error.localizedDescription.UTF8String ?: "nessuno");
                return 9;
            }
            for (uint32_t i = 0; i < count; ++i) {
                uint32_t expected = in[i] * 3u + salt;
                if (out[i] != expected) {
                    fprintf(stderr,
                            "FAIL_VALORE: round %u indice %u atteso 0x%08x ottenuto 0x%08x\n",
                            round, i, expected, out[i]);
                    return 10;
                }
            }
        }

        printf("PASS_CALCOLO_NVIDIA device=\"%s\" pci=%04x:%04x valori=1280\n",
               target.name.UTF8String, vendor, deviceID);
        return 0;
    }
}
