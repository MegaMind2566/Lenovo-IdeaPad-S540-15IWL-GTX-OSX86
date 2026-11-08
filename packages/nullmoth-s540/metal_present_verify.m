#import <Cocoa/Cocoa.h>
#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>
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

@interface Presenter : NSObject <NSApplicationDelegate, MTKViewDelegate>
@property(nonatomic, strong) id<MTLDevice> device;
@property(nonatomic, strong) id<MTLCommandQueue> queue;
@property(nonatomic, strong) id<MTLRenderPipelineState> pipeline;
@property(nonatomic, strong) NSWindow *window;
@property(nonatomic) NSUInteger submitted;
@property(nonatomic) NSUInteger completed;
@property(nonatomic) NSUInteger failed;
@property(nonatomic) BOOL setupFailed;
@end

@implementation Presenter
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    self.device = nvidiaDevice();
    NSError *error = nil;
    NSString *source =
        @"#include <metal_stdlib>\n"
         "using namespace metal;\n"
         "struct VOut { float4 position [[position]]; float3 color; };\n"
         "vertex VOut present_v(uint id [[vertex_id]]) {\n"
         " float2 p[3]={float2(-0.8,-0.7),float2(0.8,-0.7),float2(0.0,0.8)};\n"
         " float3 c[3]={float3(1,0,0),float3(0,1,0),float3(0,0,1)};\n"
         " VOut o; o.position=float4(p[id],0,1); o.color=c[id]; return o; }\n"
         "fragment float4 present_f(VOut in [[stage_in]]) { return float4(in.color,1); }\n";
    id<MTLLibrary> library = [self.device newLibraryWithSource:source options:nil error:&error];
    MTLRenderPipelineDescriptor *descriptor = [MTLRenderPipelineDescriptor new];
    descriptor.vertexFunction = [library newFunctionWithName:@"present_v"];
    descriptor.fragmentFunction = [library newFunctionWithName:@"present_f"];
    descriptor.colorAttachments[0].pixelFormat = MTLPixelFormatBGRA8Unorm;
    self.pipeline = [self.device newRenderPipelineStateWithDescriptor:descriptor error:&error];
    self.queue = [self.device newCommandQueue];
    if (!self.device || !library || !self.pipeline || !self.queue) {
        fprintf(stderr, "FAIL_PRESENT_SETUP: %s\n", error.localizedDescription.UTF8String ?: "unknown");
        self.setupFailed = YES;
        [NSApp stop:nil];
        return;
    }

    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(120, 120, 640, 400)
                                              styleMask:NSWindowStyleMaskTitled |
                                                        NSWindowStyleMaskClosable |
                                                        NSWindowStyleMaskResizable
                                                backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"S540 NVIDIA Metal presentation test";
    MTKView *view = [[MTKView alloc] initWithFrame:self.window.contentView.bounds device:self.device];
    view.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    view.colorPixelFormat = MTLPixelFormatBGRA8Unorm;
    view.clearColor = MTLClearColorMake(0.04, 0.06, 0.10, 1.0);
    view.preferredFramesPerSecond = 30;
    view.enableSetNeedsDisplay = NO;
    view.paused = NO;
    view.delegate = self;
    self.window.contentView = view;
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 6 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        [NSApp stop:nil];
        [NSApp postEvent:[NSEvent otherEventWithType:NSEventTypeApplicationDefined
                                           location:NSZeroPoint modifierFlags:0 timestamp:0
                                        windowNumber:0 context:nil subtype:0 data1:0 data2:0]
                 atStart:NO];
    });
}

- (void)mtkView:(MTKView *)view drawableSizeWillChange:(CGSize)size { (void)view; (void)size; }

- (void)drawInMTKView:(MTKView *)view {
    id<CAMetalDrawable> drawable = view.currentDrawable;
    MTLRenderPassDescriptor *pass = view.currentRenderPassDescriptor;
    if (!drawable || !pass) return;
    id<MTLCommandBuffer> command = [self.queue commandBuffer];
    id<MTLRenderCommandEncoder> encoder = [command renderCommandEncoderWithDescriptor:pass];
    [encoder setRenderPipelineState:self.pipeline];
    [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [encoder endEncoding];
    [command presentDrawable:drawable];
    @synchronized (self) { self.submitted++; }
    [command addCompletedHandler:^(id<MTLCommandBuffer> completed) {
        @synchronized (self) {
            if (completed.status == MTLCommandBufferStatusCompleted) self.completed++;
            else self.failed++;
        }
    }];
    [command commit];
}
@end

int main(void) {
    @autoreleasepool {
        NSApplication *application = NSApplication.sharedApplication;
        application.activationPolicy = NSApplicationActivationPolicyRegular;
        Presenter *presenter = [Presenter new];
        application.delegate = presenter;
        [application run];
        [presenter.window orderOut:nil];
        if (presenter.setupFailed || presenter.submitted < 60 || presenter.completed < 60 || presenter.failed) {
            fprintf(stderr, "FAIL_PRESENT_NVIDIA submitted=%lu completed=%lu failed=%lu\n",
                    (unsigned long)presenter.submitted, (unsigned long)presenter.completed,
                    (unsigned long)presenter.failed);
            return 2;
        }
        printf("PASS_PRESENT_NVIDIA device=\"%s\" submitted=%lu completed=%lu failed=%lu\n",
               presenter.device.name.UTF8String, (unsigned long)presenter.submitted,
               (unsigned long)presenter.completed, (unsigned long)presenter.failed);
        return 0;
    }
}
