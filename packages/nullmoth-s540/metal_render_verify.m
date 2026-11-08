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

static id<MTLDevice> expectedNvidia(void) {
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
        id<MTLDevice> device = expectedNvidia();
        if (!device) {
            fprintf(stderr, "FAIL_RENDER_IDENTITA: NVIDIA 10DE:1F91 assente o ambigua\n");
            return 2;
        }
        NSError *error = nil;
        NSString *source =
            @"#include <metal_stdlib>\n"
             "using namespace metal;\n"
             "struct VOut { float4 position [[position]]; };\n"
             "vertex VOut full_triangle(uint id [[vertex_id]]) {\n"
             "  float2 p[3] = { float2(-1.0,-1.0), float2(3.0,-1.0), float2(-1.0,3.0) };\n"
             "  VOut o; o.position=float4(p[id],0.0,1.0); return o;\n"
             "}\n"
             "fragment float4 fixed_color() { return float4(64.0/255.0,128.0/255.0,192.0/255.0,1.0); }\n";
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
        if (!library) {
            fprintf(stderr, "FAIL_RENDER_SHADER: %s\n", error.localizedDescription.UTF8String);
            return 3;
        }
        MTLRenderPipelineDescriptor *descriptor = [MTLRenderPipelineDescriptor new];
        descriptor.vertexFunction = [library newFunctionWithName:@"full_triangle"];
        descriptor.fragmentFunction = [library newFunctionWithName:@"fixed_color"];
        descriptor.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
        id<MTLRenderPipelineState> pipeline =
            [device newRenderPipelineStateWithDescriptor:descriptor error:&error];
        if (!pipeline) {
            fprintf(stderr, "FAIL_RENDER_PIPELINE: %s\n", error.localizedDescription.UTF8String);
            return 4;
        }

        const BOOL fullHD = argc == 2 && strcmp(argv[1], "--fullhd") == 0;
        const NSUInteger width = fullHD ? 1920 : 64;
        const NSUInteger height = fullHD ? 1080 : 64;
        const NSUInteger bytesPerRow = width * 4;
        MTLTextureDescriptor *textureDescriptor =
            [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm
                                                                width:width height:height mipmapped:NO];
        textureDescriptor.storageMode = MTLStorageModePrivate;
        textureDescriptor.usage = MTLTextureUsageRenderTarget;
        id<MTLTexture> texture = [device newTextureWithDescriptor:textureDescriptor];
        id<MTLBuffer> readback = [device newBufferWithLength:bytesPerRow * height
                                                     options:MTLResourceStorageModeManaged];
        id<MTLCommandQueue> queue = [device newCommandQueue];
        if (!texture || !readback || !queue) {
            fprintf(stderr, "FAIL_RENDER_RISORSE\n");
            return 5;
        }

        id<MTLCommandBuffer> command = [queue commandBuffer];
        MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
        pass.colorAttachments[0].texture = texture;
        pass.colorAttachments[0].loadAction = MTLLoadActionClear;
        pass.colorAttachments[0].storeAction = MTLStoreActionStore;
        pass.colorAttachments[0].clearColor = MTLClearColorMake(1.0, 0.0, 0.0, 1.0);
        id<MTLRenderCommandEncoder> render = [command renderCommandEncoderWithDescriptor:pass];
        [render setRenderPipelineState:pipeline];
        [render drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
        [render endEncoding];

        id<MTLBlitCommandEncoder> blit = [command blitCommandEncoder];
        [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0
                  sourceOrigin:MTLOriginMake(0, 0, 0)
                    sourceSize:MTLSizeMake(width, height, 1)
                      toBuffer:readback destinationOffset:0
             destinationBytesPerRow:bytesPerRow
           destinationBytesPerImage:bytesPerRow * height];
        [blit synchronizeResource:readback];
        [blit endEncoding];

        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        [command addCompletedHandler:^(__unused id<MTLCommandBuffer> completed) {
            dispatch_semaphore_signal(done);
        }];
        [command commit];
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC)) != 0) {
            fprintf(stderr, "FAIL_RENDER_TIMEOUT\n");
            return 6;
        }
        if (command.status != MTLCommandBufferStatusCompleted) {
            fprintf(stderr, "FAIL_RENDER_COMMAND: %s\n",
                    command.error.localizedDescription.UTF8String ?: "stato non completato");
            return 7;
        }

        const uint8_t *pixels = readback.contents;
        NSUInteger wrong = 0;
        for (NSUInteger i = 0; i < width * height; ++i) {
            const uint8_t *pixel = pixels + i * 4;
            if (labs((long)pixel[0] - 64) > 1 || labs((long)pixel[1] - 128) > 1 ||
                labs((long)pixel[2] - 192) > 1 || pixel[3] != 255) {
                if (wrong < 4) {
                    fprintf(stderr, "PIXEL_ERRATO[%lu]=%u,%u,%u,%u\n", (unsigned long)i,
                            pixel[0], pixel[1], pixel[2], pixel[3]);
                }
                ++wrong;
            }
        }
        if (wrong) {
            fprintf(stderr, "FAIL_RENDER_PIXEL: %lu/%lu errati\n", (unsigned long)wrong,
                    (unsigned long)(width * height));
            return 8;
        }
        printf("PASS_RENDER_NVIDIA device=\"%s\" width=%lu height=%lu pixels=%lu "
               "rgba=64,128,192,255\n", device.name.UTF8String, (unsigned long)width,
               (unsigned long)height, (unsigned long)(width * height));
        return 0;
    }
}
