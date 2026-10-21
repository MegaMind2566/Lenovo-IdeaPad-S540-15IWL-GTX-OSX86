#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#import <IOKit/hid/IOHIDLib.h>
#import <IOKit/hid/IOHIDManager.h>
#import <IOKit/hidsystem/IOHIDLib.h>
#include <mach/mach_time.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <termios.h>
#include <poll.h>

static NSString *const ProbeVersion = @"1.0.1";
static volatile sig_atomic_t StopSignal = 0;
static void StopHandler(int signalNumber) { StopSignal = signalNumber; }
static NSArray *Limitations(void) {
    return @[@"Passive userspace HID values after driver processing; not raw PS/2 bytes.",
             @"ACPI/VPC notifications not published as HID are outside this observer.",
             @"An empty target window does not prove absence of a physical or firmware event.",
             @"No key mapping, radio/camera setting, EFI component or driver is changed.",
             @"Numeric input values are retained only during prompted windows; pointer-axis and wheel usages are excluded."];
}

static NSString *UTCNow(void) {
    NSISO8601DateFormatter *formatter = [[NSISO8601DateFormatter alloc] init];
    formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
    return [formatter stringFromDate:[NSDate date]];
}

static BOOL InsideWindow(uint64_t timestamp, uint64_t start, uint64_t end) {
    return timestamp >= start && timestamp < end;
}

typedef struct {
    struct termios original;
    int fd;
    BOOL active;
} TerminalCapture;

static struct termios CaptureTerminalAttributes(struct termios original) {
    struct termios capture = original;
    // Keep signal handling (including Ctrl-C) and every unrelated attribute.
    capture.c_lflag &= (tcflag_t)~(ICANON | ECHO | ECHONL);
    capture.c_cc[VMIN] = 0;
    capture.c_cc[VTIME] = 0;
    return capture;
}

static int FlushTerminalInput(int fd) {
    int result;
    do { result = tcflush(fd, TCIFLUSH); } while (result < 0 && errno == EINTR);
    return result;
}

static BOOL BeginTerminalCapture(TerminalCapture *terminal, int fd, NSString **failure) {
    terminal->fd = fd;
    if (!isatty(fd) || tcgetattr(fd, &terminal->original) != 0) {
        *failure = @"An interactive Terminal is required; terminal attributes could not be read.";
        return NO;
    }
    struct termios attributes = CaptureTerminalAttributes(terminal->original);
    int changed;
    do { changed = tcsetattr(fd, TCSANOW, &attributes); } while (changed < 0 && errno == EINTR);
    if (changed != 0) {
        *failure = @"Terminal capture mode could not be prepared; no capture window was started.";
        return NO;
    }
    terminal->active = YES;
    if (FlushTerminalInput(fd) != 0) {
        *failure = @"Pending terminal input could not be cleared before the capture window.";
        return NO;
    }
    return YES;
}

static BOOL EndTerminalCapture(TerminalCapture *terminal) {
    if (!terminal->active) return YES;
    BOOL flushed = FlushTerminalInput(terminal->fd) == 0;
    int restored;
    // TCSAFLUSH also discards a key sequence arriving between flush and restore.
    do { restored = tcsetattr(terminal->fd, TCSAFLUSH, &terminal->original); } while (restored < 0 && errno == EINTR);
    if (restored == 0) terminal->active = NO;
    return flushed && restored == 0;
}

static BOOL TerminalAttributesEqual(struct termios a, struct termios b) {
    return a.c_iflag == b.c_iflag && a.c_oflag == b.c_oflag && a.c_cflag == b.c_cflag &&
        a.c_lflag == b.c_lflag && memcmp(a.c_cc, b.c_cc, sizeof(a.c_cc)) == 0 &&
        cfgetispeed(&a) == cfgetispeed(&b) && cfgetospeed(&a) == cfgetospeed(&b);
}

static BOOL WriteTerminalBytes(int fd, const char *bytes, size_t remaining) {
    while (remaining) {
        ssize_t written = write(fd, bytes, remaining);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) return NO;
        bytes += written; remaining -= (size_t)written;
    }
    return YES;
}

static BOOL TerminalPTYRegression(void) {
    // Exercise the production guard with an isolated PTY: no HID or user TTY.
    int master = posix_openpt(O_RDWR | O_NOCTTY);
    if (master < 0) return NO;
    int slave = -1;
    FILE *input = NULL;
    TerminalCapture terminal = {0};
    BOOL passed = NO;
    do {
        if (grantpt(master) != 0 || unlockpt(master) != 0) break;
        char *name = ptsname(master);
        if (!name) break;
        slave = open(name, O_RDWR | O_NOCTTY);
        if (slave < 0) break;
        NSString *failure = nil;
        if (!BeginTerminalCapture(&terminal, slave, &failure)) break;
        const char escape[] = "\033[15~";
        if (!WriteTerminalBytes(master, escape, sizeof(escape) - 1)) break;
        struct pollfd pending = {.fd = slave, .events = POLLIN, .revents = 0};
        if (poll(&pending, 1, 1000) != 1 || !(pending.revents & POLLIN)) break;
        // Do not read the escape: production cleanup must discard it.
        if (!EndTerminalCapture(&terminal)) break;
        struct termios restored;
        if (tcgetattr(slave, &restored) != 0 || !TerminalAttributesEqual(terminal.original, restored)) break;
        if (!WriteTerminalBytes(master, "\n", 1)) break;
        pending.revents = 0;
        if (poll(&pending, 1, 1000) != 1 || !(pending.revents & POLLIN)) break;
        int duplicate = dup(slave);
        if (duplicate < 0) break;
        input = fdopen(duplicate, "r");
        if (!input) { close(duplicate); break; }
        char *line = NULL; size_t capacity = 0;
        ssize_t length = getline(&line, &capacity, input);
        passed = length == 1 && line && line[0] == '\n';
        free(line);
    } while (0);
    if (!EndTerminalCapture(&terminal)) passed = NO;
    if (input) fclose(input);
    if (slave >= 0) close(slave);
    close(master);
    return passed;
}

static NSDictionary *ValidatePositive(NSArray<NSDictionary *> *events) {
    NSMutableArray<NSDictionary *> *keys = [NSMutableArray array];
    for (NSDictionary *event in events) {
        if ([event[@"usagePage"] unsignedIntValue] == 7 && [event[@"usage"] unsignedIntValue] == 0x3e)
            [keys addObject:event];
    }
    NSMutableDictionary *result = [@{@"requiredUsagePage": @7, @"requiredUsage": @62,
                                     @"requiredSequence": @[@1, @0], @"passed": @NO,
                                     @"matchingEventCount": @(keys.count)} mutableCopy];
    if (keys.count != 2) {
        result[@"reason"] = @"Exactly one F5 down/up pair is required; missing, repeated or duplicate presses are inconclusive.";
        return result;
    }
    NSDictionary *down = keys[0], *up = keys[1];
    if (![down[@"deviceRegistryID"] isEqual:up[@"deviceRegistryID"]] ||
        ![down[@"elementCookie"] isEqual:up[@"elementCookie"]]) {
        result[@"reason"] = @"F5 down and up came from different devices or elements.";
        return result;
    }
    if ([down[@"value"] longLongValue] != 1 || [up[@"value"] longLongValue] != 0) {
        result[@"reason"] = @"F5 sequence is not one down followed by one up.";
        return result;
    }
    result[@"passed"] = @YES;
    result[@"deviceRegistryID"] = down[@"deviceRegistryID"];
    result[@"elementCookie"] = down[@"elementCookie"];
    result[@"reason"] = @"One F5 down/up pair observed on the same device and element.";
    return result;
}

static NSArray *Sequence(NSArray<NSDictionary *> *events) {
    NSMutableArray *sequence = [NSMutableArray array];
    for (NSDictionary *event in events) {
        [sequence addObject:@[event[@"deviceRegistryID"], event[@"usagePage"], event[@"usage"], event[@"value"]]];
    }
    return sequence;
}

static NSMutableDictionary *NewReport(void) {
    return [@{@"protocolVersion": @1, @"toolVersion": ProbeVersion, @"startedAtUTC": UTCNow(),
              @"mode": @"Passive userspace HID value observation", @"result": @"INCONCLUSIVE",
              @"complete": @NO, @"devices": @[], @"trials": [NSMutableArray array],
              @"positiveValidation": @{@"passed": @NO, @"reason": @"Not yet tested."},
              @"limitations": Limitations()} mutableCopy];
}

static NSDictionary *TestEvent(NSString *device, NSNumber *cookie, NSNumber *value) {
    return @{@"deviceRegistryID": device, @"elementCookie": cookie, @"usagePage": @7,
             @"usage": @62, @"value": value, @"offsetMilliseconds": @1};
}

static BOOL RelevantUsage(uint32_t page, uint32_t usage) {
    // Keep telephony, system-control and vendor inputs as well as keyboard inputs.
    // Do not infer the key's usage page before observing it.
    return !(page == 1 && usage >= 0x30 && usage <= 0x38);
}

static int SelfTest(void) {
    NSMutableArray<NSDictionary *> *checks = [NSMutableArray array];
    void (^check)(NSString *, BOOL) = ^(NSString *name, BOOL passed) {
        [checks addObject:@{@"name": name, @"passed": @(passed)}];
    };
    NSDictionary *down = TestEvent(@"0x100", @12, @1), *up = TestEvent(@"0x100", @12, @0);
    check(@"same-device-element-down-up", [ValidatePositive(@[down, up])[@"passed"] boolValue]);
    check(@"different-device-rejected", ![ValidatePositive(@[down, TestEvent(@"0x200", @12, @0)])[@"passed"] boolValue]);
    check(@"different-element-rejected", ![ValidatePositive(@[down, TestEvent(@"0x100", @13, @0)])[@"passed"] boolValue]);
    check(@"missing-release-rejected", ![ValidatePositive(@[down])[@"passed"] boolValue]);
    check(@"repeat-press-rejected", ![ValidatePositive(@[down, down, up])[@"passed"] boolValue]);
    check(@"duplicate-cycle-rejected", ![ValidatePositive(@[down, up, down, up])[@"passed"] boolValue]);
    check(@"reverse-sequence-rejected", ![ValidatePositive(@[up, down])[@"passed"] boolValue]);
    check(@"empty-control-rejected", ![ValidatePositive(@[])[@"passed"] boolValue]);
    check(@"stale-timestamp-rejected", !InsideWindow(99, 100, 200));
    check(@"start-timestamp-accepted", InsideWindow(100, 100, 200));
    check(@"end-timestamp-rejected", !InsideWindow(200, 100, 200));
    check(@"future-timestamp-rejected", !InsideWindow(201, 100, 200));
    check(@"telephony-phone-mute-retained", RelevantUsage(0x0b, 0x2f));
    check(@"generic-system-control-retained", RelevantUsage(1, 0x81));
    check(@"pointer-axis-excluded", !RelevantUsage(1, 0x30));
    struct termios originalTerminal;
    memset(&originalTerminal, 0, sizeof(originalTerminal));
    originalTerminal.c_lflag = ICANON | ECHO | ECHONL | ISIG | IEXTEN;
    originalTerminal.c_iflag = ICRNL;
    originalTerminal.c_oflag = OPOST;
    originalTerminal.c_cflag = CREAD;
    originalTerminal.c_cc[VMIN] = 1;
    originalTerminal.c_cc[VTIME] = 9;
    originalTerminal.c_cc[VINTR] = 3;
    struct termios captureTerminal = CaptureTerminalAttributes(originalTerminal);
    check(@"capture-terminal-canonical-echo-off", (captureTerminal.c_lflag & (ICANON | ECHO | ECHONL)) == 0);
    check(@"capture-terminal-signals-preserved", (captureTerminal.c_lflag & ISIG) == (originalTerminal.c_lflag & ISIG));
    check(@"capture-terminal-read-nonblocking", captureTerminal.c_cc[VMIN] == 0 && captureTerminal.c_cc[VTIME] == 0);
    check(@"capture-terminal-unrelated-flags-preserved", captureTerminal.c_iflag == originalTerminal.c_iflag &&
          captureTerminal.c_oflag == originalTerminal.c_oflag && captureTerminal.c_cflag == originalTerminal.c_cflag &&
          (captureTerminal.c_lflag & (tcflag_t)~(ICANON | ECHO | ECHONL)) == (originalTerminal.c_lflag & (tcflag_t)~(ICANON | ECHO | ECHONL)) &&
          captureTerminal.c_cc[VINTR] == originalTerminal.c_cc[VINTR]);
    check(@"capture-terminal-original-retained", (originalTerminal.c_lflag & (ICANON | ECHO | ECHONL)) == (ICANON | ECHO | ECHONL) &&
          originalTerminal.c_cc[VMIN] == 1 && originalTerminal.c_cc[VTIME] == 9);
    check(@"pty-function-escape-does-not-contaminate-next-prompt", TerminalPTYRegression());
    check(@"different-device-sequences-distinct", ![Sequence(@[down]) isEqual:Sequence(@[TestEvent(@"0x200", @12, @1)])]);
    NSMutableDictionary *sample = NewReport();
    sample[@"devices"] = @[@{@"registryID": @"0x100", @"transport": @"PS2", @"class": @"IOHIDKeyboardEventDevice", @"product": @"Keyboard", @"relevantInputCollection": @YES}];
    sample[@"trials"] = @[@{@"label": @"CONTROL_FN_F5", @"durationSeconds": @3, @"events": @[down, up]}];
    sample[@"positiveValidation"] = ValidatePositive(@[down, up]);
    sample[@"result"] = @"CAPTURED";
    sample[@"complete"] = @YES;
    check(@"report-json-schema-serializable", [NSJSONSerialization isValidJSONObject:sample] &&
          [sample[@"protocolVersion"] isEqual:@1] && [sample[@"trials"] isKindOfClass:[NSArray class]]);
    BOOL passed = YES;
    for (NSDictionary *item in checks) passed = passed && [item[@"passed"] boolValue];
    NSDictionary *output = @{@"protocolVersion": @1, @"result": passed ? @"SELF_TEST_PASSED" : @"SELF_TEST_FAILED", @"checks": checks, @"sampleReport": sample};
    NSData *data = [NSJSONSerialization dataWithJSONObject:output options:NSJSONWritingPrettyPrinted error:NULL];
    fwrite(data.bytes, 1, data.length, stdout); fputc('\n', stdout);
    return passed ? 0 : 1;
}

static NSString *RegistryID(IOHIDDeviceRef device) {
    uint64_t entry = 0;
    if (!device) return nil;
    if (IORegistryEntryGetRegistryEntryID(IOHIDDeviceGetService(device), &entry) != KERN_SUCCESS || !entry)
        return nil;
    return [NSString stringWithFormat:@"0x%llx", (unsigned long long)entry];
}

static NSString *StringProperty(IOHIDDeviceRef device, CFStringRef key) {
    CFTypeRef value = IOHIDDeviceGetProperty(device, key);
    if (!value || CFGetTypeID(value) != CFStringGetTypeID()) return @"";
    NSString *text = (__bridge NSString *)value;
    text = [[text componentsSeparatedByCharactersInSet:[NSCharacterSet controlCharacterSet]] componentsJoinedByString:@" "];
    return text.length > 160 ? [text substringToIndex:160] : text;
}

static NSNumber *NumberProperty(IOHIDDeviceRef device, CFStringRef key) {
    CFTypeRef value = IOHIDDeviceGetProperty(device, key);
    return value && CFGetTypeID(value) == CFNumberGetTypeID() ? (__bridge NSNumber *)value : @0;
}

static BOOL InputElement(IOHIDElementRef element) {
    IOHIDElementType type = IOHIDElementGetType(element);
    return type >= kIOHIDElementTypeInput_Misc && type <= kIOHIDElementTypeInput_ScanCodes;
}

static BOOL RelevantElement(IOHIDElementRef element) {
    if (!InputElement(element)) return NO;
    return RelevantUsage(IOHIDElementGetUsagePage(element), IOHIDElementGetUsage(element));
}

static BOOL DeviceRelevant(IOHIDDeviceRef device) {
    CFArrayRef elements = IOHIDDeviceCopyMatchingElements(device, NULL, kIOHIDOptionsTypeNone);
    if (!elements) return NO;
    BOOL relevant = NO;
    for (CFIndex i = 0; i < CFArrayGetCount(elements); i++) {
        if (RelevantElement((IOHIDElementRef)CFArrayGetValueAtIndex(elements, i))) { relevant = YES; break; }
    }
    CFRelease(elements);
    return relevant;
}

static NSArray *DeviceMetadata(CFSetRef devices, BOOL *valid) {
    NSMutableArray *metadata = [NSMutableArray array];
    NSMutableSet *seen = [NSMutableSet set];
    *valid = YES;
    for (id object in (__bridge NSSet *)devices) {
        IOHIDDeviceRef device = (__bridge IOHIDDeviceRef)object;
        NSString *registry = RegistryID(device);
        if (!registry || [seen containsObject:registry]) { *valid = NO; continue; }
        [seen addObject:registry];
        io_name_t className = {0};
        IOObjectGetClass(IOHIDDeviceGetService(device), className);
        [metadata addObject:@{@"registryID": registry, @"transport": StringProperty(device, CFSTR(kIOHIDTransportKey)),
                              @"product": StringProperty(device, CFSTR(kIOHIDProductKey)),
                              @"class": [NSString stringWithUTF8String:className] ?: @"",
                              @"primaryUsagePage": NumberProperty(device, CFSTR(kIOHIDPrimaryUsagePageKey)),
                              @"primaryUsage": NumberProperty(device, CFSTR(kIOHIDPrimaryUsageKey)),
                              @"relevantInputCollection": @(DeviceRelevant(device))}];
    }
    [metadata sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        return [a[@"registryID"] compare:b[@"registryID"]];
    }];
    return metadata;
}

typedef struct {
    uint64_t start, end;
    mach_timebase_info_data_t timebase;
    __unsafe_unretained NSMutableArray *events;
    __unsafe_unretained NSSet *allowedDevices;
    NSUInteger nonNumericOmitted, staleOmitted;
    BOOL invalidDevice, callbackError, overflow;
} CaptureContext;

static void ValueCallback(void *context, IOReturn result, void *sender, IOHIDValueRef value) {
    (void)sender;
    CaptureContext *capture = context;
    if (result != kIOReturnSuccess) { capture->callbackError = YES; return; }
    uint64_t timestamp = IOHIDValueGetTimeStamp(value);
    if (!InsideWindow(timestamp, capture->start, capture->end)) { capture->staleOmitted++; return; }
    IOHIDElementRef element = IOHIDValueGetElement(value);
    if (!RelevantElement(element)) return;
    NSString *registry = RegistryID(IOHIDElementGetDevice(element));
    if (!registry || ![capture->allowedDevices containsObject:registry]) { capture->invalidDevice = YES; return; }
    if (IOHIDValueGetLength(value) > (CFIndex)sizeof(CFIndex)) { capture->nonNumericOmitted++; return; }
    if (capture->events.count >= 512) { capture->overflow = YES; return; }
    double offset = (double)(timestamp - capture->start) * capture->timebase.numer / capture->timebase.denom / 1000000.0;
    [capture->events addObject:@{@"deviceRegistryID": registry,
                                @"usagePage": @(IOHIDElementGetUsagePage(element)),
                                @"usage": @(IOHIDElementGetUsage(element)),
                                @"elementCookie": @((uint32_t)IOHIDElementGetCookie(element)),
                                @"elementType": @(IOHIDElementGetType(element)),
                                @"value": @((long long)IOHIDValueGetIntegerValue(value)),
                                @"offsetMilliseconds": @(offset)}];
}

static BOOL Prompt(NSString *label, NSString *instruction) {
    // A function key may also send terminal escape bytes after a HID window.
    if (isatty(STDIN_FILENO) && FlushTerminalInput(STDIN_FILENO) != 0) return NO;
    printf("\n%s\n%s\nPremi Invio per preparare la finestra; poi attendi VIA.\n", label.UTF8String, instruction.UTF8String);
    fflush(stdout);
    char *line = NULL; size_t capacity = 0;
    ssize_t length = getline(&line, &capacity, stdin);
    BOOL valid = length > 0;
    if (valid) for (ssize_t i = 0; i < length; i++) if (line[i] != '\n' && line[i] != '\r') valid = NO;
    free(line);
    return valid;
}

static NSDictionary *RunWindow(NSString *label, NSString *instruction, NSArray *expectedDevices,
                               NSArray **actualDevices, NSString **failure) {
    if (!Prompt(label, instruction)) { *failure = @"Input ended or a non-empty line was entered; no key-window data was collected."; return nil; }
    IOHIDManagerRef manager = IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone);
    if (!manager) { *failure = @"IOHIDManagerCreate failed."; return nil; }
    IOHIDManagerSetDeviceMatching(manager, NULL);
    IOHIDManagerScheduleWithRunLoop(manager, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);
    IOReturn opened = IOHIDManagerOpen(manager, kIOHIDOptionsTypeNone);
    CFSetRef devices = opened == kIOReturnSuccess ? IOHIDManagerCopyDevices(manager) : NULL;
    NSMutableArray *explicitlyOpened = [NSMutableArray array];
    NSDictionary *trial = nil;
    TerminalCapture terminal = {0};
    do {
        if (opened != kIOReturnSuccess || !devices || !CFSetGetCount(devices)) {
            *failure = [NSString stringWithFormat:@"HID manager open/enumeration failed (0x%08x); no target test is valid.", (unsigned int)opened]; break;
        }
        BOOL valid = NO;
        NSArray *metadata = DeviceMetadata(devices, &valid);
        *actualDevices = metadata;
        if (!valid) { *failure = @"Missing or duplicate HID registry identity."; break; }
        if (expectedDevices && ![expectedDevices isEqual:metadata]) { *failure = @"HID device topology changed after the positive control."; break; }
        __attribute__((objc_precise_lifetime)) NSMutableSet *allowed = [NSMutableSet set];
        BOOL allOpen = YES;
        for (id object in (__bridge NSSet *)devices) {
            IOHIDDeviceRef device = (__bridge IOHIDDeviceRef)object;
            if (!DeviceRelevant(device)) continue;
            IOReturn deviceResult = IOHIDDeviceOpen(device, kIOHIDOptionsTypeNone);
            if (deviceResult != kIOReturnSuccess) {
                *failure = [NSString stringWithFormat:@"Relevant HID device %@ could not be opened (0x%08x).", RegistryID(device), (unsigned int)deviceResult];
                allOpen = NO; break;
            }
            [explicitlyOpened addObject:object];
            [allowed addObject:RegistryID(device)];
        }
        if (!allOpen) break;
        if (!allowed.count) { *failure = @"No observable non-axis HID input collection is available."; break; }
        // New manager per window; drain pre-window reports and the prompt's Return release.
        printf("Preparazione: non premere tasti...\n"); fflush(stdout);
        CFAbsoluteTime drainUntil = CFAbsoluteTimeGetCurrent() + 0.75;
        while (!StopSignal && CFAbsoluteTimeGetCurrent() < drainUntil) CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.02, true);
        if (StopSignal) { *failure = @"Collection interrupted before the capture window."; break; }
        NSMutableArray *events = [NSMutableArray array];
        CaptureContext capture = {0};
        capture.events = events; capture.allowedDevices = allowed;
        if (mach_timebase_info(&capture.timebase) != KERN_SUCCESS || !capture.timebase.numer || !capture.timebase.denom) {
            *failure = @"Monotonic HID timebase is unavailable."; break;
        }
        if (!BeginTerminalCapture(&terminal, STDIN_FILENO, failure)) break;
        if (StopSignal) { *failure = @"Collection interrupted before the capture window."; break; }
        capture.start = mach_absolute_time();
        capture.end = capture.start + (uint64_t)(3000000000.0 * capture.timebase.denom / capture.timebase.numer);
        NSString *started = UTCNow();
        IOHIDManagerRegisterInputValueCallback(manager, ValueCallback, &capture);
        printf("VIA: premi e rilascia UNA volta il tasto indicato. Tre secondi.\n"); fflush(stdout);
        while (!StopSignal && mach_absolute_time() < capture.end) CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, true);
        IOHIDManagerRegisterInputValueCallback(manager, NULL, NULL);
        BOOL terminalRestored = EndTerminalCapture(&terminal);
        if (terminalRestored) { printf("FINE.\n"); fflush(stdout); }
        CFSetRef finalDevices = IOHIDManagerCopyDevices(manager);
        BOOL finalMetadataValid = NO;
        NSArray *finalMetadata = finalDevices ? DeviceMetadata(finalDevices, &finalMetadataValid) : @[];
        BOOL topologyChanged = !finalMetadataValid || ![metadata isEqual:finalMetadata];
        if (finalDevices) CFRelease(finalDevices);
        if (!terminalRestored) {
            *failure = @"Terminal input flush or attribute restoration failed; collection stopped.";
        } else if (StopSignal) {
            *failure = @"Collection interrupted; the current window is incomplete.";
        } else if (topologyChanged) {
            *failure = @"HID device topology changed during the capture window.";
        } else if (capture.invalidDevice || capture.callbackError || capture.overflow) {
            *failure = @"HID callback error, unexpected device or event-buffer limit; capture is inconclusive.";
        }
        trial = @{@"label": label, @"startedAtUTC": started, @"durationSeconds": @3,
                  @"events": events, @"nonNumericValuesOmitted": @(capture.nonNumericOmitted),
                  @"outsideWindowValuesOmitted": @(capture.staleOmitted),
                  @"valid": @(terminalRestored && !StopSignal && !topologyChanged && !capture.invalidDevice && !capture.callbackError && !capture.overflow)};
    } while (0);
    if (!EndTerminalCapture(&terminal)) {
        *failure = @"Terminal attribute restoration failed during cleanup; collection stopped.";
        fprintf(stderr, "Ripristino Terminale non riuscito. Interrompi la prova e riapri Terminale.\n");
    }
    for (id object in explicitlyOpened) IOHIDDeviceClose((__bridge IOHIDDeviceRef)object, kIOHIDOptionsTypeNone);
    if (devices) CFRelease(devices);
    IOHIDManagerClose(manager, kIOHIDOptionsTypeNone);
    IOHIDManagerUnscheduleFromRunLoop(manager, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);
    CFRelease(manager);
    return trial;
}

static BOOL WriteReport(NSDictionary *report, NSString *path) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
    if (!data) { fprintf(stderr, "JSON serialization failed: %s\n", error.localizedDescription.UTF8String); return NO; }
    int file = open(path.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (file < 0) { fprintf(stderr, "Cannot create a new report: %s\n", strerror(errno)); return NO; }
    const uint8_t *bytes = data.bytes; size_t remaining = data.length;
    BOOL success = YES;
    while (remaining) {
        ssize_t written = write(file, bytes, remaining);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) { success = NO; break; }
        bytes += written; remaining -= (size_t)written;
    }
    if (success && fsync(file) != 0) success = NO;
    if (close(file) != 0) success = NO;
    return success;
}

static NSString *AccessName(IOHIDAccessType access) {
    switch (access) {
        case kIOHIDAccessTypeGranted: return @"granted";
        case kIOHIDAccessTypeDenied: return @"denied";
        default: return @"unknown";
    }
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 2 && strcmp(argv[1], "--self-test") == 0) return SelfTest();
        if (argc != 3 || strcmp(argv[1], "--output") != 0) {
            fprintf(stderr, "Usage: hid-key-probe --output NEW-REPORT.json | --self-test\n"); return 64;
        }
        if (geteuid() == 0 || geteuid() != getuid()) { fprintf(stderr, "Run as your normal macOS user; do not use sudo.\n"); return 77; }
        NSString *output = [NSString stringWithUTF8String:argv[2]];
        if (!output.isAbsolutePath) { fprintf(stderr, "Report path must be absolute.\n"); return 64; }
        NSMutableDictionary *report = NewReport();
        NSString *lockDirectory = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/S540HIDKeys"];
        NSError *directoryError = nil;
        if (![[NSFileManager defaultManager] createDirectoryAtPath:lockDirectory withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions: @0700} error:&directoryError]) {
            fprintf(stderr, "Cannot prepare collection lock: %s\n", directoryError.localizedDescription.UTF8String); return 73;
        }
        NSString *lockPath = [lockDirectory stringByAppendingPathComponent:@"collection.lock"];
        int lock = open(lockPath.fileSystemRepresentation, O_RDWR | O_CREAT | O_NOFOLLOW, 0600);
        struct stat lockStat;
        if (lock < 0 || fstat(lock, &lockStat) != 0 || !S_ISREG(lockStat.st_mode) || lockStat.st_uid != getuid() || flock(lock, LOCK_EX | LOCK_NB) != 0) {
            if (lock >= 0) close(lock);
            fprintf(stderr, "Another collection is active, or its lock is not usable.\n"); return 75;
        }
        struct sigaction stopAction;
        memset(&stopAction, 0, sizeof(stopAction));
        stopAction.sa_handler = StopHandler;
        sigemptyset(&stopAction.sa_mask);
        sigaction(SIGINT, &stopAction, NULL);
        sigaction(SIGTERM, &stopAction, NULL);
        sigaction(SIGHUP, &stopAction, NULL);
        sigaction(SIGQUIT, &stopAction, NULL);
        int exitCode = 2;
        do {
            IOHIDAccessType access = IOHIDCheckAccess(kIOHIDRequestTypeListenEvent);
            BOOL requestResult = NO;
            if (access != kIOHIDAccessTypeGranted) {
                requestResult = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent);
                report[@"permission"] = @{@"before": AccessName(access), @"requestReturned": @(requestResult),
                                          @"after": AccessName(IOHIDCheckAccess(kIOHIDRequestTypeListenEvent))};
                report[@"reason"] = @"Input Monitoring was not granted at entry. Allow the entry macOS names, quit and reopen Terminal, then rerun; no key trials were started.";
                fprintf(stderr, "Consenti Monitoraggio input per la voce indicata da macOS. Chiudi e riapri Terminale, poi riesegui. Nessuna prova tasti avviata.\n");
                exitCode = 77; break;
            }
            report[@"permission"] = @{@"before": @"granted"};
            printf("Osservazione HID passiva: nessuna modifica a EFI, driver o mappature.\nDurante VIA usa soltanto il tasto richiesto; non digitare testo o password.\n");
            NSArray *devices = nil;
            NSString *failure = nil;
            NSDictionary *positive = RunWindow(@"CONTROL_FN_F5", @"Controllo: tieni Fn e premi/rilascia F5 UNA volta durante VIA.", nil, &devices, &failure);
            if (devices) report[@"devices"] = devices;
            NSMutableArray *trials = report[@"trials"];
            if (positive) [trials addObject:positive];
            if (failure) { report[@"reason"] = failure; break; }
            NSDictionary *validation = ValidatePositive(positive[@"events"]);
            report[@"positiveValidation"] = validation;
            if (![validation[@"passed"] boolValue]) { report[@"reason"] = @"Positive control failed; target trials were not requested."; break; }
            printf("Controllo positivo valido. Proseguo con le sole prove mirate.\n");
            NSArray *steps = @[@[@"DIRECT_F4", @"Premi e rilascia F4 SENZA Fn."],
                               @[@"DIRECT_F7", @"Premi e rilascia F7 SENZA Fn."],
                               @[@"DIRECT_F8", @"Premi e rilascia F8 SENZA Fn."],
                               @[@"DIRECT_F9", @"Premi e rilascia F9 SENZA Fn."],
                               @[@"ORDINARY_COMMAND_L", @"Premi e rilascia la normale combinazione Comando+L (non F9)."]];
            for (NSArray *step in steps) {
                NSArray *currentDevices = nil;
                NSDictionary *trial = RunWindow(step[0], step[1], devices, &currentDevices, &failure);
                if (trial) [trials addObject:trial];
                if (failure) break;
            }
            if (failure) { report[@"reason"] = failure; break; }
            NSDictionary *f9 = trials[4], *commandL = trials[5];
            NSArray *f9Events = f9[@"events"], *commandEvents = commandL[@"events"];
            NSString *comparison = !f9Events.count || !commandEvents.count ? @"insufficient-data" :
                ([Sequence(f9Events) isEqual:Sequence(commandEvents)] ? @"identical-HID-sequence" : @"different-HID-sequence");
            report[@"comparisons"] = @{@"directF9VersusOrdinaryCommandL": comparison};
            report[@"result"] = @"CAPTURED";
            report[@"complete"] = @YES;
            report[@"reason"] = @"Positive control passed and all requested HID windows completed; target behavior is not implemented by this diagnostic.";
            exitCode = 0;
        } while (0);
        report[@"finishedAtUTC"] = UTCNow();
        if (StopSignal) exitCode = 128 + StopSignal;
        BOOL saved = WriteReport(report, output);
        flock(lock, LOCK_UN); close(lock);
        if (!saved) return 74;
        printf("\nRisultato: %s\n%s\nReport: %s\n", [report[@"result"] UTF8String], [report[@"reason"] UTF8String], output.fileSystemRepresentation);
        return exitCode;
    }
}
