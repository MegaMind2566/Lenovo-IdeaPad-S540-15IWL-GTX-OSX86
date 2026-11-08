#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <CoreImage/CoreImage.h>
#import <CoreGraphics/CoreGraphics.h>
#import <IOKit/IOKitLib.h>

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

static uint64_t hashBytes(const uint8_t *bytes, NSUInteger length) {
    uint64_t hash = 1469598103934665603ull;
    for (NSUInteger i = 0; i < length; ++i) {
        hash ^= bytes[i];
        hash *= 1099511628211ull;
    }
    return hash;
}

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = nvidiaDevice();
        if (!device) return 2;
        const NSUInteger width = 1024, height = 1024, rowBytes = width * 4;
        NSMutableData *input = [NSMutableData dataWithLength:rowBytes * height];
        NSMutableData *output = [NSMutableData dataWithLength:rowBytes * height];
        uint8_t *source = input.mutableBytes;
        for (NSUInteger y = 0; y < height; ++y) {
            for (NSUInteger x = 0; x < width; ++x) {
                NSUInteger offset = (y * width + x) * 4;
                source[offset] = (uint8_t)(x & 255);
                source[offset + 1] = (uint8_t)(y & 255);
                source[offset + 2] = (uint8_t)((x + y) & 255);
                source[offset + 3] = 255;
            }
        }
        CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
        CIImage *image = [CIImage imageWithBitmapData:input bytesPerRow:rowBytes
                                                 size:CGSizeMake(width, height)
                                               format:kCIFormatRGBA8 colorSpace:colorSpace];
        image = [[[image imageByClampingToExtent]
            imageByApplyingFilter:@"CIGaussianBlur"
              withInputParameters:@{kCIInputRadiusKey: @10}]
            imageByCroppingToRect:CGRectMake(0, 0, width, height)];
        CIContext *context = [CIContext contextWithMTLDevice:device
                                                    options:@{kCIContextCacheIntermediates: @NO,
                                                              kCIContextUseSoftwareRenderer: @NO}];
        if (!context || !image) return 3;
        uint64_t firstHash = 0;
        CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
        for (NSUInteger round = 0; round < 12; ++round) {
            memset(output.mutableBytes, 0, output.length);
            [context render:image toBitmap:output.mutableBytes rowBytes:rowBytes
                      bounds:CGRectMake(0, 0, width, height)
                      format:kCIFormatRGBA8 colorSpace:colorSpace];
            const uint8_t *pixels = output.bytes;
            for (NSUInteger i = 3; i < output.length; i += 4) {
                if (pixels[i] != 255) {
                    fprintf(stderr, "FAIL_COREIMAGE_ALPHA round=%lu index=%lu value=%u\n",
                            (unsigned long)round, (unsigned long)i, pixels[i]);
                    CGColorSpaceRelease(colorSpace);
                    return 4;
                }
            }
            uint64_t hash = hashBytes(pixels, output.length);
            if (!round) firstHash = hash;
            else if (hash != firstHash) {
                fprintf(stderr, "FAIL_COREIMAGE_HASH round=%lu expected=%016llx got=%016llx\n",
                        (unsigned long)round, firstHash, hash);
                CGColorSpaceRelease(colorSpace);
                return 5;
            }
        }
        double seconds = CFAbsoluteTimeGetCurrent() - start;
        CGColorSpaceRelease(colorSpace);
        printf("PASS_COREIMAGE_NVIDIA device=\"%s\" rounds=12 pixels=%lu hash=%016llx seconds=%.3f\n",
               device.name.UTF8String, (unsigned long)(width * height * 12), firstHash, seconds);
        return 0;
    }
}
