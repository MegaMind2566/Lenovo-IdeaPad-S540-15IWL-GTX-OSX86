#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#import <IOKit/graphics/IOGraphicsLib.h>
#import <unistd.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        io_iterator_t iterator = IO_OBJECT_NULL;
        kern_return_t status = IOServiceGetMatchingServices(kIOMainPortDefault,
                                                             IOServiceMatching("AppleBacklightDisplay"),
                                                             &iterator);
        if (status != KERN_SUCCESS) {
            fprintf(stderr, "FAIL_MATCH 0x%x\n", status);
            return 2;
        }
        io_service_t display = IOIteratorNext(iterator);
        IOObjectRelease(iterator);
        if (!display) {
            fprintf(stderr, "FAIL_NO_APPLE_BACKLIGHT_DISPLAY\n");
            return 3;
        }

        io_string_t path = {0};
        IORegistryEntryGetPath(display, kIOServicePlane, path);
        float original = 0.0f;
        status = IODisplayGetFloatParameter(display, 0, CFSTR(kIODisplayBrightnessKey), &original);
        printf("BACKLIGHT_PATH=%s\nFLOAT_BRIGHTNESS_STATUS=0x%x\n", path, status);
        SInt32 integerValue = 0, integerMin = 0, integerMax = 0;
        kern_return_t integerStatus = IODisplayGetIntegerRangeParameter(
            display, 0, CFSTR("bklt"), &integerValue, &integerMin, &integerMax);
        printf("BKLT_STATUS=0x%x\nBKLT_VALUE=%d\nBKLT_MIN=%d\nBKLT_MAX=%d\n",
               integerStatus, integerValue, integerMin, integerMax);
        if (status != KERN_SUCCESS && integerStatus != KERN_SUCCESS) {
            fprintf(stderr, "FAIL_READ_BRIGHTNESS float=0x%x bklt=0x%x path=%s\n",
                    status, integerStatus, path);
            IOObjectRelease(display);
            return 4;
        }
        if (status == KERN_SUCCESS) printf("BRIGHTNESS_ORIGINAL=%.6f\n", original);

        if (argc == 2 && strcmp(argv[1], "--pulse") == 0) {
            BOOL useInteger = status != KERN_SUCCESS;
            float trial = original > 0.80f ? 0.70f : MIN(1.0f, original + 0.15f);
            SInt32 integerTrial = integerValue > integerMin + (integerMax - integerMin) / 2
                ? integerMin + (integerMax - integerMin) * 7 / 10
                : integerMin + (integerMax - integerMin) * 9 / 10;
            status = useInteger
                ? IODisplaySetIntegerParameter(display, 0, CFSTR("bklt"), integerTrial)
                : IODisplaySetFloatParameter(display, 0, CFSTR(kIODisplayBrightnessKey), trial);
            if (status == KERN_SUCCESS) status = IODisplayCommitParameters(display, 0);
            if (status != KERN_SUCCESS) {
                fprintf(stderr, "FAIL_SET_BRIGHTNESS 0x%x mode=%s\n", status,
                        useInteger ? "bklt" : "float");
                IOObjectRelease(display);
                return 5;
            }
            usleep(800000);
            float observed = -1.0f;
            SInt32 integerObserved = -1, ignoredMin = 0, ignoredMax = 0;
            kern_return_t readStatus = useInteger
                ? IODisplayGetIntegerRangeParameter(display, 0, CFSTR("bklt"), &integerObserved,
                                                    &ignoredMin, &ignoredMax)
                : IODisplayGetFloatParameter(display, 0, CFSTR(kIODisplayBrightnessKey), &observed);
            kern_return_t restoreStatus = useInteger
                ? IODisplaySetIntegerParameter(display, 0, CFSTR("bklt"), integerValue)
                : IODisplaySetFloatParameter(display, 0, CFSTR(kIODisplayBrightnessKey), original);
            if (restoreStatus == KERN_SUCCESS) restoreStatus = IODisplayCommitParameters(display, 0);
            printf("BRIGHTNESS_TRIAL=%.6f\nBRIGHTNESS_OBSERVED=%.6f\nBKLT_TRIAL=%d\n"
                   "BKLT_OBSERVED=%d\nRESTORE_STATUS=0x%x\n",
                   trial, observed, integerTrial, integerObserved, restoreStatus);
            BOOL wrongValue = useInteger ? integerObserved != integerTrial : fabsf(observed - trial) > 0.02f;
            if (readStatus != KERN_SUCCESS || restoreStatus != KERN_SUCCESS || wrongValue) {
                fprintf(stderr, "FAIL_BRIGHTNESS_PULSE read=0x%x restore=0x%x\n",
                        readStatus, restoreStatus);
                IOObjectRelease(display);
                return 6;
            }
            printf("PASS_BRIGHTNESS_PULSE\n");
        }
        IOObjectRelease(display);
        return 0;
    }
}
