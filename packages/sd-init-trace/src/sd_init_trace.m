// SPDX-License-Identifier: MIT
// Bounded, redacted SD initialization trace. Never loads a driver or edits EFI.
#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#import <IOKit/kext/KextManager.h>
#include <CoreFoundation/CoreFoundation.h>
#include <sys/sysctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint32_t magic, operation; uint64_t flags; } DebugPacket;
_Static_assert(sizeof(DebugPacket) == 16, "debug.SDXC protocol is exactly 16 bytes");
static const uint32_t Magic = UINT32_C(0x53445843);
static const uint64_t TraceBit = UINT64_C(2);
static const NSUInteger MaximumInput = 4 * 1024 * 1024, MaximumLine = 65536, MaximumEvents = 4096;
static volatile sig_atomic_t Interrupted;
static pid_t ChildPID = -1;
static int TraceFD = -1, ErrorFD = -1;
static BOOL ChildExited;

typedef int (*FlagExchange)(const DebugPacket *, DebugPacket *, size_t *, void *);
typedef struct { uint64_t original, enabled; BOOL saved, armed, restored; } FlagState;
static FlagState Flags;

static double Now(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) { Interrupted = SIGTERM; return 0; }
    return (double)value.tv_sec + (double)value.tv_nsec / 1000000000.0;
}
static void SignalHandler(int number) { Interrupted = number; }
static int SystemExchange(const DebugPacket *input, DebugPacket *output, size_t *length, void *context) {
    (void)context;
    return sysctlbyname("debug.SDXC", output, length, (void *)input, sizeof(*input));
}
static BOOL GetFlags(FlagExchange exchange, void *context, uint64_t *value) {
    DebugPacket input = {Magic, 0, 0}, output = {0, 0, 0};
    size_t length = sizeof(output);
    if (exchange(&input, &output, &length, context) || length != sizeof(output) ||
        output.magic != Magic || output.operation != 0) return NO;
    *value = output.flags;
    return YES;
}
static BOOL SetFlags(FlagExchange exchange, void *context, uint64_t value) {
    DebugPacket input = {Magic, 1, value};
    // The driver SET handler has no old/output operation. Verification is a GET.
    return exchange(&input, NULL, NULL, context) == 0;
}
static BOOL BeginFlags(FlagState *state, FlagExchange exchange, void *context) {
    if (!GetFlags(exchange, context, &state->original)) return NO;
    state->saved = YES;
    state->enabled = state->original | TraceBit;
    state->armed = YES; // arm before SET, including a failed/ambiguous syscall
    uint64_t actual = 0;
    return SetFlags(exchange, context, state->enabled) && GetFlags(exchange, context, &actual) && actual == state->enabled;
}
static BOOL RestoreFlags(FlagState *state, FlagExchange exchange, void *context) {
    if (!state->armed) return state->restored || !state->saved;
    state->armed = NO; // one bounded cleanup attempt, including the atexit path
    uint64_t actual = 0;
    state->restored = SetFlags(exchange, context, state->original) &&
        GetFlags(exchange, context, &actual) && actual == state->original;
    return state->restored;
}
static void ExitRestore(void) { (void)RestoreFlags(&Flags, SystemExchange, NULL); }

static BOOL Unsigned(id object, uint64_t *value) {
    if ([object isKindOfClass:[NSNumber class]]) {
        if (CFGetTypeID((__bridge CFTypeRef)object) == CFBooleanGetTypeID() ||
            CFNumberIsFloatType((__bridge CFNumberRef)object)) return NO;
        const char *type = [object objCType];
        if (strchr("CSILQ", type[0])) { *value = [object unsignedLongLongValue]; return YES; }
        long long number = [object longLongValue];
        if (number < 0) return NO;
        *value = (uint64_t)number; return YES;
    }
    if (![object isKindOfClass:[NSString class]]) return NO;
    NSString *string = object;
    if (!string.length || string.length > 20) return NO;
    const char *text = string.UTF8String;
    if (!text || text[0] == '-' || text[0] == '+' || text[0] == ' ') return NO;
    BOOL hex = string.length > 2 && text[0] == '0' && (text[1] == 'x' || text[1] == 'X');
    const char *digits = text + (hex ? 2 : 0);
    if (!*digits) return NO;
    for (const char *p = digits; *p; ++p)
        if (!strchr(hex ? "0123456789abcdefABCDEF" : "0123456789", *p)) return NO;
    errno = 0; char *end = NULL;
    unsigned long long number = strtoull(digits, &end, hex ? 16 : 10);
    if (errno || !end || *end) return NO;
    *value = number; return YES;
}
static BOOL Scalar32(uint64_t value, uint32_t *result) {
    if (value <= UINT32_MAX || ((value >> 32) == UINT32_MAX && (uint32_t)value >= UINT32_C(0x80000000))) { *result = (uint32_t)value; return YES; }
    return NO;
}

@interface Capture : NSObject
@property(nonatomic, strong) NSMutableArray<NSDictionary *> *events;
@property(nonatomic, strong) NSMutableArray<NSArray<NSString *> *> *unknownKeys;
@property(nonatomic, strong) NSMutableData *pending;
@property(nonatomic) NSUInteger inputBytes, errorBytes, ignoredEvents;
@property(nonatomic) BOOL unknownSchema, limitReached, streamFailed, removeEvent, insertEvent;
@property(nonatomic) double started;
@end
@implementation Capture
- (instancetype)init {
    self = [super init];
    if (self) { _events = [NSMutableArray array]; _unknownKeys = [NSMutableArray array]; _pending = [NSMutableData data]; _started = Now(); }
    return self;
}
@end

static void UnknownSchema(Capture *capture, id object) {
    capture.unknownSchema = YES;
    if (capture.unknownKeys.count >= 8) return;
    NSMutableArray *keys = [NSMutableArray array];
    if ([object isKindOfClass:[NSDictionary class]]) {
        for (id key in [(NSDictionary *)object allKeys]) {
            if (keys.count == 24) break;
            BOOL safe = [key isKindOfClass:[NSString class]] && [key length] <= 64;
            if (safe) for (NSUInteger i = 0; i < [key length]; ++i) {
                unichar c = [key characterAtIndex:i];
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                      (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '-')) { safe = NO; break; }
            }
            [keys addObject:safe ? key : @"nonstandard_key"];
        }
        [keys sortUsingSelector:@selector(compare:)];
    }
    if (![capture.unknownKeys containsObject:keys]) [capture.unknownKeys addObject:keys];
}
static BOOL Wanted(uint32_t debugid) {
    switch (debugid) {
        case 0x06134080: case 0x06134035: case 0x06134036: case 0x0613401C:
        case 0x06134018: case 0x06134078: case 0x06134068: case 0x06134064: return YES;
        default: return NO;
    }
}
static void ParseLine(Capture *capture, NSData *line, NSString *phase) {
    if (!line.length) return;
    if (line.length > MaximumLine) { capture.limitReached = YES; return; }
    id object = [NSJSONSerialization JSONObjectWithData:line options:0 error:NULL];
    if (![object isKindOfClass:[NSDictionary class]]) { UnknownSchema(capture, object); return; }
    NSDictionary *record = object;
    uint64_t rawID = 0;
    if (!Unsigned(record[@"debugid"], &rawID) || rawID > UINT32_MAX) { UnknownSchema(capture, record); return; }
    uint32_t debugid = (uint32_t)rawID;
    if (!Wanted(debugid)) { capture.ignoredEvents++; return; }
    uint64_t arguments[4] = {0, 0, 0, 0};
    id array = record[@"args"];
    if ([array isKindOfClass:[NSArray class]] && [array count] == 4) {
        for (NSUInteger i = 0; i < 4; ++i) if (!Unsigned(array[i], &arguments[i])) { UnknownSchema(capture, record); return; }
    } else {
        NSArray *names = record[@"arg1"] ? @[@"arg1", @"arg2", @"arg3", @"arg4"] :
            @[@"argument_1", @"argument_2", @"argument_3", @"argument_4"];
        for (NSUInteger i = 0; i < 4; ++i) if (!Unsigned(record[names[i]], &arguments[i])) { UnknownSchema(capture, record); return; }
    }
    NSMutableDictionary *fields = [NSMutableDictionary dictionary];
    NSString *kind = nil;
    if (debugid == 0x06134018) {
        // arg2 is the SD command argument: never include it or any responses.
        kind = @"command"; fields[@"command_index"] = @((arguments[0] >> 8) & 63);
    } else if (debugid == 0x06134080) {
        if (arguments[0] > 1) { UnknownSchema(capture, record); return; }
        kind = @"card_presence"; fields[@"present"] = @(arguments[0] == 1);
        if ([phase isEqual:@"remove"] && arguments[0] == 0) capture.removeEvent = YES;
        if ([phase isEqual:@"insert"] && arguments[0] == 1) capture.insertEvent = YES;
    } else {
        NSUInteger count = debugid == 0x06134035 || debugid == 0x06134064 ? 2 :
            debugid == 0x06134068 ? 1 : debugid == 0x06134078 ? 4 : 3;
        kind = debugid == 0x06134035 ? @"clock_start" : debugid == 0x06134036 ? @"clock_end" :
            debugid == 0x0613401C ? @"reset" : debugid == 0x06134078 ? @"wait_interrupt" :
            debugid == 0x06134068 ? @"configure_sd_media_return" : @"configure_card_return";
        for (NSUInteger i = 0; i < count; ++i) {
            uint32_t value = 0;
            if (!Scalar32(arguments[i], &value)) { UnknownSchema(capture, record); return; }
            fields[[NSString stringWithFormat:@"arg%lu", (unsigned long)i + 1]] = @(value);
        }
    }
    if (capture.events.count >= MaximumEvents) { capture.limitReached = YES; return; }
    [capture.events addObject:@{@"sequence":@(capture.events.count + 1), @"debugid":[NSString stringWithFormat:@"0x%08x", debugid],
        @"kind":kind, @"phase":phase, @"elapsed_ms":@((uint64_t)((Now() - capture.started) * 1000)), @"fields":fields}];
}
static void Feed(Capture *capture, const void *bytes, NSUInteger length, NSString *phase) {
    if (length > MaximumInput - MIN(capture.inputBytes, MaximumInput)) { capture.limitReached = YES; return; }
    capture.inputBytes += length;
    [capture.pending appendBytes:bytes length:length];
    NSData *newline = [NSData dataWithBytes:"\n" length:1];
    for (;;) {
        NSRange found = [capture.pending rangeOfData:newline options:0 range:NSMakeRange(0, capture.pending.length)];
        if (found.location == NSNotFound) break;
        ParseLine(capture, [capture.pending subdataWithRange:NSMakeRange(0, found.location)], phase);
        [capture.pending replaceBytesInRange:NSMakeRange(0, found.location + 1) withBytes:NULL length:0];
        if (capture.unknownSchema || capture.limitReached) return;
    }
    if (capture.pending.length > MaximumLine) capture.limitReached = YES;
}
static BOOL ChildAlive(void) {
    if (ChildPID <= 0 || ChildExited) return NO;
    int status = 0; pid_t result = waitpid(ChildPID, &status, WNOHANG);
    if (result == ChildPID || (result < 0 && errno == ECHILD)) { ChildExited = YES; ChildPID = -1; return NO; }
    return result == 0 || (result < 0 && errno == EINTR);
}
static void StopChild(void) {
    if (ChildAlive()) {
        (void)kill(ChildPID, SIGINT);
        for (unsigned i = 0; i < 200 && ChildAlive(); ++i) usleep(10000);
        if (ChildAlive()) {
            (void)kill(ChildPID, SIGKILL);
            for (unsigned i = 0; i < 100 && ChildAlive(); ++i) usleep(10000);
        }
    }
    if (TraceFD >= 0) { close(TraceFD); TraceFD = -1; }
    if (ErrorFD >= 0) { close(ErrorFD); ErrorFD = -1; }
}
static BOOL TraceState(uint32_t *state, int *owner) {
    size_t length = sizeof(*state);
    if (sysctlbyname("ktrace.state", state, &length, NULL, 0) || length != sizeof(*state)) return NO;
    length = sizeof(*owner);
    return !sysctlbyname("ktrace.owning_pid", owner, &length, NULL, 0) && length == sizeof(*owner) && *state <= 2;
}
static BOOL StartChild(void) {
    int output[2] = {-1,-1}, errors[2] = {-1,-1};
    if (pipe(output)) return NO;
    if (pipe(errors)) { close(output[0]); close(output[1]); return NO; }
    ChildExited = NO; ChildPID = fork();
    if (ChildPID == 0) {
        (void)dup2(output[1], STDOUT_FILENO); (void)dup2(errors[1], STDERR_FILENO);
        close(output[0]); close(output[1]); close(errors[0]); close(errors[1]);
        execl("/usr/bin/ktrace", "ktrace", "trace", "-f", "S0x0613", "-T", "60", "--ndjson", "--no-default-codes-files", (char *)NULL);
        _exit(127);
    }
    close(output[1]); close(errors[1]);
    if (ChildPID < 0) { close(output[0]); close(errors[0]); return NO; }
    TraceFD = output[0]; ErrorFD = errors[0];
    if (fcntl(TraceFD, F_SETFL, O_NONBLOCK) || fcntl(ErrorFD, F_SETFL, O_NONBLOCK)) { StopChild(); return NO; }
    return YES;
}
static void ReadPipes(Capture *capture, NSString *phase) {
    uint8_t bytes[4096];
    if (TraceFD >= 0) for (;;) {
        ssize_t count = read(TraceFD, bytes, sizeof(bytes));
        if (count > 0) { Feed(capture, bytes, (NSUInteger)count, phase); if (capture.unknownSchema || capture.limitReached) break; }
        else {
            if (count == 0) {
                if (capture.pending.length && !capture.unknownSchema && !capture.limitReached) {
                    ParseLine(capture, capture.pending, phase); [capture.pending setLength:0];
                }
                close(TraceFD); TraceFD = -1;
            } else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
                capture.streamFailed = YES;
            }
            break;
        }
    }
    if (ErrorFD >= 0) for (;;) {
        ssize_t count = read(ErrorFD, bytes, sizeof(bytes));
        if (count > 0) { capture.errorBytes += (NSUInteger)count; if (capture.errorBytes > 131072) { capture.limitReached = YES; break; } }
        else {
            if (count == 0) { close(ErrorFD); ErrorFD = -1; }
            else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) { capture.streamFailed = YES; }
            break;
        }
    }
}

static BOOL IsDescendant(io_registry_entry_t slot, io_registry_entry_t controller) {
    io_registry_entry_t cursor = slot; IOObjectRetain(cursor);
    BOOL found = NO;
    for (unsigned depth = 0; depth < 32 && cursor; ++depth) {
        if (IOObjectIsEqualTo(cursor, controller)) { found = YES; break; }
        io_registry_entry_t parent = IO_OBJECT_NULL;
        kern_return_t result = IORegistryEntryGetParentEntry(cursor, kIOServicePlane, &parent);
        IOObjectRelease(cursor); cursor = result == KERN_SUCCESS ? parent : IO_OBJECT_NULL;
    }
    if (cursor) IOObjectRelease(cursor);
    return found;
}
static BOOL CardPresent(io_registry_entry_t slot, BOOL *present) {
    CFTypeRef value = IORegistryEntryCreateCFProperty(slot, CFSTR("Card Present"), kCFAllocatorDefault, 0);
    BOOL valid = value && CFGetTypeID(value) == CFBooleanGetTypeID();
    if (valid) *present = CFBooleanGetValue((CFBooleanRef)value);
    if (value) CFRelease(value);
    return valid;
}
static BOOL PCIProperty(io_registry_entry_t entry, CFStringRef key, uint32_t expected) {
    CFTypeRef value = IORegistryEntryCreateCFProperty(entry, key, kCFAllocatorDefault, 0);
    BOOL valid = value && CFGetTypeID(value) == CFDataGetTypeID() && CFDataGetLength((CFDataRef)value) == 4;
    if (valid) {
        const UInt8 *bytes = CFDataGetBytePtr((CFDataRef)value);
        uint32_t actual = bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
        valid = actual == expected;
    }
    if (value) CFRelease(value);
    return valid;
}
static io_registry_entry_t FindSlot(BOOL *appleSDXCLoaded) {
    CFDictionaryRef loadedRef = KextManagerCopyLoadedKextInfo(NULL, NULL);
    if (!loadedRef) return IO_OBJECT_NULL;
    NSDictionary *loaded = CFBridgingRelease(loadedRef);
    NSUInteger matches = 0;
    for (NSString *identifier in @[@"com.apple.driver.BigSurSDXC"]) {
        NSDictionary *info = loaded[identifier];
        if ([info isKindOfClass:[NSDictionary class]] && [info[@"CFBundleVersion"] isEqual:@"1.9.0"] &&
            [info[@"OSBundleStarted"] boolValue]) matches++;
    }
    *appleSDXCLoaded = loaded[@"com.apple.driver.AppleSDXC"] != nil;
    if (matches != 1) return IO_OBJECT_NULL;
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(0, IOServiceMatching("BgSurSDXC"), &iterator)) return IO_OBJECT_NULL;
    io_registry_entry_t controller = IO_OBJECT_NULL, entry;
    NSUInteger count = 0;
    while ((entry = IOIteratorNext(iterator))) {
        CFTypeRef name = IORegistryEntryCreateCFProperty(entry, CFSTR("IONameMatched"), kCFAllocatorDefault, 0);
        CFTypeRef bundle = IORegistryEntryCreateCFProperty(entry, CFSTR("CFBundleIdentifier"), kCFAllocatorDefault, 0);
        io_registry_entry_t parent = IO_OBJECT_NULL;
        if (name && CFGetTypeID(name) == CFStringGetTypeID() && CFEqual(name, CFSTR("pci1217,8621")) &&
            bundle && CFGetTypeID(bundle) == CFStringGetTypeID() && CFEqual(bundle, CFSTR("com.apple.driver.BigSurSDXC")) &&
            IORegistryEntryGetParentEntry(entry, kIOServicePlane, &parent) == KERN_SUCCESS &&
            IOObjectConformsTo(parent, "IOPCIDevice") && PCIProperty(parent, CFSTR("vendor-id"), 0x1217) &&
            PCIProperty(parent, CFSTR("device-id"), 0x8621) && PCIProperty(parent, CFSTR("subsystem-vendor-id"), 0x17AA) &&
            PCIProperty(parent, CFSTR("subsystem-id"), 0x3803)) {
            count++; if (!controller) { controller = parent; IOObjectRetain(controller); }
        }
        if (parent) IOObjectRelease(parent);
        if (name) CFRelease(name);
        if (bundle) CFRelease(bundle);
        IOObjectRelease(entry);
    }
    IOObjectRelease(iterator);
    if (count != 1) { if (controller) IOObjectRelease(controller); return IO_OBJECT_NULL; }
    iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(0, IOServiceMatching("BgSurSDXCSlot"), &iterator)) {
        IOObjectRelease(controller); return IO_OBJECT_NULL;
    }
    io_registry_entry_t slot = IO_OBJECT_NULL;
    count = 0;
    while ((entry = IOIteratorNext(iterator))) {
        count++;
        if (IsDescendant(entry, controller) && !slot) { slot = entry; IOObjectRetain(slot); }
        IOObjectRelease(entry);
    }
    IOObjectRelease(iterator); IOObjectRelease(controller);
    if (count != 1 && slot) { IOObjectRelease(slot); slot = IO_OBJECT_NULL; }
    return slot;
}

static NSMutableDictionary *Report(Capture *capture, NSString *mode, NSString *result, NSString *reason) {
    return [@{@"schema":@1, @"mode":mode, @"result":result, @"reason":reason,
        @"events":capture.events, @"unknown_schema_keys":capture.unknownKeys,
        @"ignored_nonwhitelisted_events":@(capture.ignoredEvents), @"input_limit_reached":@(capture.limitReached),
        @"interpretation":@"Sequenza osservata; nessun esito dimostra da solo il guasto o il funzionamento della scheda. I codici possono essere condivisi con AppleSDXC."} mutableCopy];
}
static int PrintReport(NSDictionary *report) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:NULL];
    if (!data) return 1;
    return fwrite(data.bytes, 1, data.length, stdout) == data.length && fputc('\n', stdout) != EOF ? 0 : 1;
}
static int Run(void) {
    Capture *capture = [Capture new];
    NSString *result = @"REFUSED", *reason = @"preflight";
    io_registry_entry_t slot = IO_OBJECT_NULL;
    BOOL absent = NO, reinserted = NO, appleLoaded = NO;
    uint32_t initialTraceState = UINT32_MAX;
    memset(&Flags, 0, sizeof(Flags));
    struct sigaction action; memset(&action, 0, sizeof(action)); action.sa_handler = SignalHandler;
    sigemptyset(&action.sa_mask);
    (void)sigaction(SIGINT, &action, NULL); (void)sigaction(SIGTERM, &action, NULL); (void)sigaction(SIGHUP, &action, NULL);
    (void)sigaction(SIGQUIT, &action, NULL); (void)sigaction(SIGPIPE, &action, NULL);
    (void)atexit(ExitRestore);
    @try {
        do {
            if (geteuid() != 0) { reason = @"root_required"; break; }
            char release[64] = {0}; size_t releaseLength = sizeof(release);
            if (sysctlbyname("kern.osrelease", release, &releaseLength, NULL, 0) || strncmp(release, "25.", 3)) { reason = @"darwin_25_required"; break; }
            if (access("/usr/bin/ktrace", X_OK)) { reason = @"ktrace_cli_missing"; break; }
            uint32_t state = 0; int owner = 0;
            if (!TraceState(&state, &owner)) { reason = @"ktrace_state_unknown"; break; }
            initialTraceState = state; // OFF=0 or OS-managed BG=2; never report an owner PID.
            if (state == 1) { reason = @"another_foreground_trace_active"; break; }
            slot = FindSlot(&appleLoaded);
            if (!slot) { reason = @"driver_version_or_unique_controller_slot_not_confirmed"; break; }
            BOOL present = NO;
            if (!CardPresent(slot, &present) || !present) { reason = @"insert_sd_before_start"; break; }
            uint64_t unused = 0;
            if (!GetFlags(SystemExchange, NULL, &unused)) { reason = @"binary_debug_protocol_unavailable"; break; }
            result = @"INCONCLUSIVE";
            if (!StartChild()) { reason = @"owned_trace_start_failed"; break; }
            double deadline = Now() + 3;
            BOOL owned = NO;
            while (!Interrupted && ChildAlive() && Now() < deadline) {
                ReadPipes(capture, @"starting");
                if (!TraceState(&state, &owner)) break;
                if (state == 1 && owner == ChildPID) { owned = YES; break; }
                if (state == 1 && owner != ChildPID) break;
                usleep(20000);
            }
            if (!owned) { reason = @"owned_foreground_trace_not_confirmed"; break; }
            if (capture.unknownSchema || capture.limitReached || capture.streamFailed || Interrupted) {
                reason = @"trace_unusable_before_card_action"; break;
            }
            if (!BeginFlags(&Flags, SystemExchange, NULL)) { reason = @"enable_trace_bit_not_verified"; break; }
            fprintf(stderr, "Traccia avviata. Togli ora la SD: attendo al massimo 15 secondi.\n");
            deadline = Now() + 15;
            while (!Interrupted && ChildAlive() && !capture.unknownSchema && !capture.limitReached && !capture.streamFailed && Now() < deadline) {
                ReadPipes(capture, @"remove");
                if (!CardPresent(slot, &present)) { reason = @"card_property_lost"; break; }
                absent = !present;
                if (absent && capture.removeEvent) break;
                usleep(20000);
            }
            if (!(absent && capture.removeEvent)) { reason = @"removal_positive_control_missing"; break; }
            if (capture.unknownSchema || capture.limitReached || capture.streamFailed || Interrupted || !ChildAlive()) { reason = @"trace_interrupted_after_removal"; break; }
            fprintf(stderr, "Rimozione confermata da IORegistry e traccia. Reinserisci ora la SD entro 15 secondi.\n");
            deadline = Now() + 15;
            while (!Interrupted && ChildAlive() && !capture.unknownSchema && !capture.limitReached && !capture.streamFailed && Now() < deadline) {
                ReadPipes(capture, @"insert");
                if (!CardPresent(slot, &present)) { reason = @"card_property_lost"; break; }
                reinserted = present;
                if (reinserted && capture.insertEvent) break;
                usleep(20000);
            }
            if (!(reinserted && capture.insertEvent)) { reason = @"reinsertion_not_confirmed"; break; }
            if (capture.unknownSchema || capture.limitReached || capture.streamFailed || Interrupted || !ChildAlive()) {
                reason = @"trace_interrupted_after_reinsertion"; break;
            }
            fprintf(stderr, "Reinserimento rilevato. Raccolgo la sequenza per un massimo di 20 secondi.\n");
            deadline = Now() + 20;
            while (!Interrupted && ChildAlive() && !capture.unknownSchema && !capture.limitReached && !capture.streamFailed && Now() < deadline) {
                ReadPipes(capture, @"collect"); usleep(20000);
            }
            ReadPipes(capture, @"collect");
            if (Interrupted) reason = @"signal_received";
            else if (capture.unknownSchema) reason = @"unknown_ndjson_schema";
            else if (capture.limitReached) reason = @"bounded_capture_limit";
            else if (capture.streamFailed) reason = @"trace_pipe_read_error";
            else if (capture.pending.length) reason = @"partial_ndjson_record";
            else if (Now() < deadline) reason = @"trace_ended_before_collection_deadline";
            else { result = @"TRACE_CAPTURED"; reason = @"bounded_initialization_sequence_captured"; }
        } while (0);
    } @catch (__unused NSException *exception) { result = @"INCONCLUSIVE"; reason = @"internal_exception_redacted"; }
    @finally { StopChild(); if (!RestoreFlags(&Flags, SystemExchange, NULL)) { result = @"INCONCLUSIVE"; reason = @"debug_flags_restore_not_verified"; } if (slot) IOObjectRelease(slot); }
    if (capture.unknownSchema) { result = @"INCONCLUSIVE"; reason = @"unknown_ndjson_schema"; }
    if (capture.streamFailed) { result = @"INCONCLUSIVE"; reason = @"trace_pipe_read_error"; }
    if (Interrupted) { result = @"INCONCLUSIVE"; reason = @"signal_received"; }
    if (Flags.saved && !Flags.restored) { result = @"INCONCLUSIVE"; reason = @"debug_flags_restore_not_verified"; }
    NSMutableDictionary *report = Report(capture, @"sd_initialization", result, reason);
    report[@"ktrace_initial_state"] = initialTraceState == UINT32_MAX ? (id)[NSNull null] : @(initialTraceState);
    report[@"positive_control"] = @{@"ioreg_card_absent":@(absent), @"trace_card_absent":@(capture.removeEvent), @"passed":@(absent && capture.removeEvent)};
    report[@"reinsertion"] = @{@"ioreg_card_present":@(reinserted), @"trace_card_present":@(capture.insertEvent)};
    report[@"apple_sdxc_also_loaded"] = @(appleLoaded);
    report[@"debug_flags"] = @{@"saved":@(Flags.saved), @"restored_verified":@(Flags.restored || !Flags.saved),
        @"original_hex":[NSString stringWithFormat:@"0x%016llx", (unsigned long long)Flags.original], @"added_mask_hex":@"0x2"};
    if (Flags.saved && !Flags.restored) fprintf(stderr, "ATTENZIONE: ripristino dei flag non verificato; conserva questo report.\n");
    return PrintReport(report);
}

static int DecodeFixture(NSString *path) {
    Capture *capture = [Capture new];
    int descriptor = open(path.fileSystemRepresentation, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    struct stat info;
    if (descriptor < 0 || fstat(descriptor, &info) || !S_ISREG(info.st_mode) || info.st_size < 0 || (uint64_t)info.st_size > MaximumInput) {
        if (descriptor >= 0) close(descriptor);
        return PrintReport(Report(capture, @"fixture_decode", @"REFUSED", @"fixture_not_a_bounded_regular_file"));
    }
    uint8_t bytes[4096]; ssize_t count;
    while ((count = read(descriptor, bytes, sizeof(bytes))) > 0 && !capture.unknownSchema && !capture.limitReached)
        Feed(capture, bytes, (NSUInteger)count, @"fixture");
    close(descriptor);
    if (capture.pending.length && !capture.unknownSchema && !capture.limitReached) ParseLine(capture, capture.pending, @"fixture");
    NSString *result = !capture.unknownSchema && !capture.limitReached && capture.events.count ? @"TRACE_CAPTURED" : @"INCONCLUSIVE";
    return PrintReport(Report(capture, @"fixture_decode", result, capture.unknownSchema ? @"unknown_ndjson_schema" : @"sanitized_fixture_projection"));
}

typedef struct { uint64_t flags; unsigned calls, corruption; BOOL failEnable; } FakeFlags;
static int FakeExchange(const DebugPacket *input, DebugPacket *output, size_t *length, void *context) {
    FakeFlags *fake = context; fake->calls++;
    if (input->magic != Magic || input->operation > 1) return -1;
    if (input->operation == 1) {
        if (output || length) return -1;
        fake->flags = input->flags;
        if (fake->failEnable && (input->flags & 2)) return -1;
        return 0;
    }
    if (!output || !length || *length != 16 || input->flags != 0) return -1;
    *output = *input; output->flags = fake->flags;
    if (fake->corruption == 1) *length = 15;
    if (fake->corruption == 2) output->magic ^= 1;
    if (fake->corruption == 3) output->operation = 1;
    return 0;
}
static int SelfTest(void) {
    unsigned checks = 0;
#define CHECK(condition) do { checks++; if (!(condition)) { (void)PrintReport(@{@"result":@"SELF_TEST_FAILED", @"check":@(checks)}); return 1; } } while (0)
    CHECK(sizeof(DebugPacket) == 16);
    FakeFlags fake = {UINT64_C(0xa5c3f01712345678), 0, NO, NO}; FlagState state = {0};
    uint64_t original = fake.flags;
    CHECK(BeginFlags(&state, FakeExchange, &fake)); CHECK(fake.flags == (original | 2));
    CHECK((fake.flags >> 32) == (original >> 32)); CHECK(RestoreFlags(&state, FakeExchange, &fake)); CHECK(fake.flags == original);
    unsigned calls = fake.calls; CHECK(RestoreFlags(&state, FakeExchange, &fake) && fake.calls == calls);
    for (unsigned corruption = 1; corruption <= 3; ++corruption) {
        fake.corruption = corruption; FlagState malformed = {0};
        CHECK(!BeginFlags(&malformed, FakeExchange, &fake) && !malformed.armed);
    }
    fake.corruption = 0; fake.failEnable = YES; fake.flags = UINT64_C(0x8765432100000000); FlagState failed = {0};
    CHECK(!BeginFlags(&failed, FakeExchange, &fake) && failed.armed); fake.failEnable = NO;
    CHECK(RestoreFlags(&failed, FakeExchange, &fake) && fake.flags == UINT64_C(0x8765432100000000));
    Capture *capture = [Capture new];
    NSDictionary *record = @{@"debugid":@"0x06134018", @"args":@[@(17 << 8), @"0xdeadbeefcafebabe", @0, @0],
        @"thread":@"PRIVATE_THREAD", @"process":@"PRIVATE_PROCESS", @"serial":@"PRIVATE_SERIAL"};
    ParseLine(capture, [NSJSONSerialization dataWithJSONObject:record options:0 error:NULL], @"fixture");
    CHECK(capture.events.count == 1 && [capture.events[0][@"fields"] isEqual:@{@"command_index":@17}]);
    NSString *projected = [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:capture.events options:0 error:NULL] encoding:NSUTF8StringEncoding];
    CHECK(![projected containsString:@"deadbeef"] && ![projected containsString:@"PRIVATE"] && ![projected containsString:@"serial"]);
    ParseLine(capture, [@"{\"debugid\":101924992,\"arg1\":0,\"arg2\":0,\"arg3\":0,\"arg4\":0}" dataUsingEncoding:NSUTF8StringEncoding], @"remove");
    CHECK(capture.removeEvent);
    Capture *alternative = [Capture new];
    ParseLine(alternative, [@"{\"debugid\":\"0x06134080\",\"argument_1\":1,\"argument_2\":0,\"argument_3\":0,\"argument_4\":0}" dataUsingEncoding:NSUTF8StringEncoding], @"insert");
    CHECK(alternative.insertEvent);
    Capture *unknown = [Capture new];
    ParseLine(unknown, [@"{\"new_schema\":\"PRIVATE_VALUE\"}" dataUsingEncoding:NSUTF8StringEncoding], @"fixture");
    CHECK(unknown.unknownSchema && unknown.events.count == 0 && [unknown.unknownKeys[0] isEqual:@[@"new_schema"]]);
    Capture *redacted = [Capture new];
    ParseLine(redacted, [@"{\"debugid\":\"0x061340b0\",\"args\":[1,2,3,4]}" dataUsingEncoding:NSUTF8StringEncoding], @"fixture");
    CHECK(redacted.events.count == 0);
    uint64_t number = 0; CHECK(!Unsigned(@YES, &number) && !Unsigned(@1.5, &number) && !Unsigned(@-1, &number));
    CHECK(Unsigned(@"0xffffffffffffffff", &number) && number == UINT64_MAX);
    uint32_t scalar = 0; CHECK(!Scalar32(UINT64_C(0xffff123456789abc), &scalar));
    return PrintReport(@{@"result":@"SELF_TEST_PASSED", @"checks":@(checks), @"hardware_accessed":@NO});
#undef CHECK
}
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 2 && !strcmp(argv[1], "--self-test")) return SelfTest();
        if (argc == 3 && (!strcmp(argv[1], "--decode-fixture") || !strcmp(argv[1], "--parse-fixture")))
            return DecodeFixture([NSString stringWithUTF8String:argv[2]]);
        if (argc == 2 && !strcmp(argv[1], "--emit-probe")) {
            execl("/usr/bin/ktrace", "ktrace", "emit", "0xfeff0010", "1", "2", "3", "4", (char *)NULL);
            fprintf(stderr, "Impossibile avviare il probe sintetico tramite ktrace emit.\n");
            return 127;
        }
        if (argc == 2 && !strcmp(argv[1], "--run")) return Run();
        fprintf(stderr, "Uso: sd_init_trace --self-test | --run | --decode-fixture FILE | --emit-probe\n");
        return 64;
    }
}
