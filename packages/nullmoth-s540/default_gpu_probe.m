#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

int main(void) {
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        NSNumber *switching = NSBundle.mainBundle.infoDictionary[@"NSSupportsAutomaticGraphicsSwitching"];
        printf("bundle=%s automatic_switching=%s default_device=\"%s\"\n",
               NSBundle.mainBundle.bundleIdentifier.UTF8String ?: "none",
               switching ? switching.stringValue.UTF8String : "unset",
               device.name.UTF8String ?: "none");
        return device ? 0 : 2;
    }
}
