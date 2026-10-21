// SPDX-License-Identifier: MIT
// Read only the audited VoodooPS2Keyboard RELEASE trace format. No driver code is copied.
#import <Foundation/Foundation.h>
#import <IOKit/IOKitLib.h>
#import <IOKit/kext/KextManager.h>
#include <sys/stat.h>
#include <sys/poll.h>
#include <sys/utsname.h>
#include <sys/file.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <mach/mach_time.h>
#include <mach/machine.h>
#include <limits.h>
#include <math.h>
#include <float.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static NSString *const BundleID = @"as.acidanthera.voodoo.driver.PS2Keyboard";
static NSString *const DriverSHA = @"b55758219af1b12b1c0e5e116ff1ee65dc5d8484086e5231103c242a5858a1e5";
static const unsigned char DriverUUID[] = {0xef,0xa8,0x83,0xf4,0x75,0x58,0x3e,0x98,0xa3,0x52,0xe2,0x02,0xcb,0x3d,0xfa,0xaf};
static volatile sig_atomic_t Interrupted = 0;
static const double WindowSeconds = 3.0;
static const double GuardianSeconds = 540.0;
static const double FailsafeSeconds = 600.0;
static const NSUInteger MaximumRecords = 128;
static void SignalHandler(int number) { (void)number; Interrupted = 1; }
static double Now(void) {
    static mach_timebase_info_data_t scale;
    if (!scale.denom) mach_timebase_info(&scale);
    return (double)mach_continuous_time() * scale.numer / scale.denom / 1e9;
}
static void Signals(void) {
    struct sigaction action; memset(&action, 0, sizeof(action));
    action.sa_handler = SignalHandler; sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL); sigaction(SIGTERM, &action, NULL);
    sigaction(SIGHUP, &action, NULL); signal(SIGPIPE, SIG_IGN);
}
static BOOL WriteAll(int fd, const void *bytes, size_t length) {
    const unsigned char *cursor = bytes;
    while (length) { ssize_t done = write(fd, cursor, length);
        if (done < 0 && errno == EINTR) continue;
        if (done <= 0) return NO;
        cursor += done; length -= (size_t)done;
    } return YES;
}
static BOOL Send(int fd, NSDictionary *value) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:value options:0 error:NULL];
    return data && WriteAll(fd, data.bytes, data.length) && WriteAll(fd, "\n", 1);
}
static NSPipe *PrivatePipe(void) {
    NSPipe *pipe = [NSPipe pipe];
    for (NSFileHandle *handle in @[pipe.fileHandleForReading, pipe.fileHandleForWriting]) {
        int fd = handle.fileDescriptor, flags = fcntl(fd, F_GETFD);
        if (flags < 0 || fcntl(fd, F_SETFD, flags | FD_CLOEXEC) < 0) {
            [pipe.fileHandleForReading closeFile]; [pipe.fileHandleForWriting closeFile]; return nil;
        }
    } return pipe;
}
static NSString *Line(int fd, double deadline) {
    NSMutableData *data = [NSMutableData data];
    while (!Interrupted && Now() < deadline && data.length < 65536) {
        struct pollfd p = {fd, POLLIN | POLLHUP, 0};
        int result = poll(&p, 1, 100);
        if (result < 0 && errno == EINTR) continue;
        if (result < 0) return nil;
        if (!result) continue;
        unsigned char byte; ssize_t amount = read(fd, &byte, 1);
        if (amount <= 0) return nil;
        if (byte == '\n') return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        [data appendBytes:&byte length:1];
    } return nil;
}
static NSDictionary *Message(int fd, double deadline) {
    NSString *line = Line(fd, deadline);
    if (!line) return nil;
    id value = [NSJSONSerialization JSONObjectWithData:[line dataUsingEncoding:NSUTF8StringEncoding] options:0 error:NULL];
    return [value isKindOfClass:[NSDictionary class]] ? value : nil;
}
static BOOL Integer(id value, long long expected) {
    return value && CFGetTypeID((__bridge CFTypeRef)value) == CFNumberGetTypeID() &&
        !CFNumberIsFloatType((__bridge CFNumberRef)value) && [value longLongValue] == expected;
}
static BOOL LoadedIdentity(NSDictionary *info) {
    return [info isKindOfClass:[NSDictionary class]] && [info[@"CFBundleIdentifier"] isEqual:BundleID] &&
        [info[@"CFBundleVersion"] isEqual:@"2.3.7"] && info[@"OSBundleStarted"] == (__bridge id)kCFBooleanTrue &&
        Integer(info[@"OSBundleCPUType"], CPU_TYPE_X86_64) &&
        [info[@"OSBundleUUID"] isKindOfClass:[NSData class]] &&
        [info[@"OSBundleUUID"] isEqual:[NSData dataWithBytes:DriverUUID length:sizeof(DriverUUID)]];
}
static io_service_t Driver(BOOL requireZero) {
    NSArray *keys = @[@"CFBundleIdentifier", @"CFBundleVersion", @"OSBundleUUID", @"OSBundleStarted", @"OSBundleCPUType"];
    CFDictionaryRef loaded = KextManagerCopyLoadedKextInfo((__bridge CFArrayRef)@[BundleID], (__bridge CFArrayRef)keys);
    NSDictionary *dictionary = CFBridgingRelease(loaded);
    if (!LoadedIdentity(dictionary[BundleID])) return IO_OBJECT_NULL;
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("ApplePS2Keyboard"), &iterator)) return IO_OBJECT_NULL;
    io_service_t service = IOIteratorNext(iterator), second = IOIteratorNext(iterator);
    IOObjectRelease(iterator);
    if (!service || second) { if(service) IOObjectRelease(service); if(second) IOObjectRelease(second); return IO_OBJECT_NULL; }
    io_name_t serviceClass;
    if(IOObjectGetClass(service, serviceClass) || strcmp(serviceClass, "ApplePS2Keyboard")) { IOObjectRelease(service); return IO_OBJECT_NULL; }
    CFTypeRef publisher = IORegistryEntryCreateCFProperty(service, CFSTR("CFBundleIdentifier"), kCFAllocatorDefault, 0);
    if (!publisher || !CFEqual(publisher, (__bridge CFStringRef)BundleID)) {
        if (publisher) CFRelease(publisher); IOObjectRelease(service); return IO_OBJECT_NULL;
    } CFRelease(publisher);
    CFTypeRef original = IORegistryEntryCreateCFProperty(service, CFSTR("LogScanCodes"), kCFAllocatorDefault, 0);
    BOOL valid = Integer((__bridge id)original, 0) || (!requireZero && Integer((__bridge id)original, 2));
    if (original) CFRelease(original);
    if (!valid) { IOObjectRelease(service); return IO_OBJECT_NULL; }
    return service;
}
static NSNumber *Value(io_service_t service) {
    CFTypeRef value = IORegistryEntryCreateCFProperty(service, CFSTR("LogScanCodes"), kCFAllocatorDefault, 0);
    if (!value) return nil;
    return CFBridgingRelease(value);
}
static BOOL VerifiedWriteOutcome(kern_return_t result, id current, NSNumber *requested) {
    (void)result; // A superclass failure cannot undo a command-gated mutation.
    return [current isEqual:requested] && Integer(current, requested.longLongValue);
}
static BOOL SetValue(io_service_t service, NSNumber *value) {
    // The superclass may return failure after the command-gated change. Readback is decisive.
    kern_return_t result = IORegistryEntrySetCFProperties(service, (__bridge CFDictionaryRef)@{@"LogScanCodes": value});
    return VerifiedWriteOutcome(result, Value(service), value);
}
typedef enum { RestorationVerified, RestorationRequired, RestorationConflict } Restoration;
static Restoration RestoreDecision(id current, NSNumber *original) {
    if ([current isEqual:original] && Integer(current, 0)) return RestorationVerified;
    return Integer(current, 2) ? RestorationRequired : RestorationConflict;
}
static BOOL Restore(io_service_t service, NSNumber *original) {
    Restoration action = RestoreDecision(Value(service), original);
    if(action == RestorationVerified) return YES;
    if(action == RestorationConflict) return NO; // Never overwrite a separate operator's unexpected value.
    return SetValue(service, original);
}
static BOOL EndWindow(double now, double deadline, BOOL signal, BOOL controlReady, BOOL loggerRunning, BOOL failsafeRunning) {
    return signal || now >= deadline || controlReady || !loggerRunning || !failsafeRunning;
}
static BOOL ExpectedCommand(NSString *command, NSUInteger index) {
    return [command isEqual:[NSString stringWithFormat:@"START %lu", (unsigned long)index]];
}
static NSDictionary *Trace(NSString *text) {
    if (![text isKindOfClass:[NSString class]] || text.length > 128) return nil;
    static NSRegularExpression *expression;
    if (!expression) expression = [NSRegularExpression regularExpressionWithPattern:
        @"^ApplePS2Keyboard: sending key ([0-9a-f]{1,4})=([0-9a-f]{1,4})(?:, ([0-9a-f]{1,4})=([0-9a-f]{1,4}))? (down|up)\\n?$" options:0 error:NULL];
    NSTextCheckingResult *match = [expression firstMatchInString:text options:0 range:NSMakeRange(0, text.length)];
    if (!match || match.range.length != text.length) return nil;
    unsigned values[4] = {0};
    for (NSUInteger index = 1; index <= 4; index++) {
        NSRange range = [match rangeAtIndex:index];
        if (range.location != NSNotFound) values[index-1] = (unsigned)strtoul([[text substringWithRange:range] UTF8String], NULL, 16);
    }
    BOOL remapped = [match rangeAtIndex:3].location != NSNotFound;
    unsigned raw = values[0], mapped = remapped ? values[1] : raw, adb = remapped ? values[3] : values[1];
    if ((raw > 0x80 && !(raw >= 0xe000 && raw <= 0xe0ff)) ||
        (mapped > 0x80 && !(mapped >= 0xe000 && mapped <= 0xe0ff)) || adb > 255 ||
        (remapped && values[1] != values[2])) return nil;
    return @{@"raw_scan": @(raw), @"mapped_scan": @(mapped), @"adb_code": @(adb),
             @"direction": [text substringWithRange:[match rangeAtIndex:5]]};
}
static double SourceTime(id timestamp) {
    if (![timestamp isKindOfClass:[NSString class]] || [timestamp length] > 64) return NAN;
    NSMutableString *text = [timestamp mutableCopy];
    if (text.length > 10 && [text characterAtIndex:10] == ' ') [text replaceCharactersInRange:NSMakeRange(10,1) withString:@"T"];
    if (text.length >= 5) { NSUInteger pos = text.length - 5; unichar sign = [text characterAtIndex:pos];
        if ((sign == '+' || sign == '-') && [text characterAtIndex:pos+3] != ':') [text insertString:@":" atIndex:pos+3]; }
    NSISO8601DateFormatter *formatter = [[NSISO8601DateFormatter alloc] init];
    formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime | NSISO8601DateFormatWithFractionalSeconds;
    NSDate *date = [formatter dateFromString:text];
    if (!date) { formatter.formatOptions = NSISO8601DateFormatWithInternetDateTime; date = [formatter dateFromString:text]; }
    return date ? date.timeIntervalSince1970 : NAN;
}
static void ParseLines(NSMutableData *buffer, NSMutableArray *records, BOOL *truncated, double sourceStart, NSUInteger *unattributed) {
    while (buffer.length) {
        const unsigned char *bytes = buffer.bytes; NSUInteger length = buffer.length, newline = 0;
        while (newline < length && bytes[newline] != '\n') newline++;
        if (newline == length) { if (length > 131072) [buffer setLength:0]; return; }
        NSData *line = [buffer subdataWithRange:NSMakeRange(0, newline)];
        [buffer replaceBytesInRange:NSMakeRange(0, newline + 1) withBytes:NULL length:0];
        NSDictionary *object = [NSJSONSerialization JSONObjectWithData:line options:0 error:NULL];
        NSDictionary *trace = [object isKindOfClass:[NSDictionary class]] ? Trace(object[@"eventMessage"]) : nil;
        if (trace) {
            double source = SourceTime(object[@"timestamp"]);
            if (!isfinite(source)) { (*unattributed)++; continue; }
            if (source < sourceStart) continue;
            if(records.count < MaximumRecords) { NSMutableDictionary *record = [trace mutableCopy];
                record[@"source_offset_ms"] = @((source-sourceStart)*1000); [records addObject:record]; }
            else *truncated = YES;
        }
    }
}
static NSTask *Task(NSString *executable, NSArray *arguments, NSPipe *input, NSPipe *output) {
    NSTask *task = [[NSTask alloc] init]; task.executableURL = [NSURL fileURLWithPath:executable]; task.arguments = arguments;
    task.environment = @{@"PATH": @"/usr/bin:/bin:/usr/sbin:/sbin", @"LC_ALL": @"C"};
    task.standardInput = input ?: [NSFileHandle fileHandleWithNullDevice];
    task.standardOutput = output ?: [NSFileHandle fileHandleWithNullDevice];
    task.standardError = [NSFileHandle fileHandleWithNullDevice];
    if (![task launchAndReturnError:NULL]) return nil;
    return task;
}
static void StopTask(NSTask *task) {
    if (!task) return;
    if (task.running) [task terminate];
    double end = Now() + 1;
    while (task.running && Now() < end) { struct pollfd dummy = {-1, 0, 0}; (void)poll(&dummy, 0, 20); }
    if (task.running) kill(task.processIdentifier, SIGKILL);
    [task waitUntilExit];
}
static NSString *SelfPath(void) {
    char path[PATH_MAX];
    NSString *argument = NSProcessInfo.processInfo.arguments[0];
    if (!realpath(argument.fileSystemRepresentation, path)) return nil;
    return [[NSFileManager defaultManager] stringWithFileSystemRepresentation:path length:strlen(path)];
}
static int Failsafe(void) {
    if (geteuid() != 0 || isatty(STDIN_FILENO)) return 77;
    // The failsafe owns the session lock, including after the guardian dies.
    int lock = open("/var/run/org.s540.function-key-scancodes.lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    struct stat lockInfo;
    if(lock < 0 || fstat(lock, &lockInfo) || !S_ISREG(lockInfo.st_mode) || lockInfo.st_uid != 0 ||
        lockInfo.st_nlink != 1 || (lockInfo.st_mode & 0777) != 0600 || flock(lock, LOCK_EX | LOCK_NB)) {
        if(lock >= 0) close(lock); return 78;
    }
    io_service_t service = Driver(YES); if(!service) { close(lock); return 78; }
    NSNumber *original = Value(service);
    uint64_t registryID = 0; if(IORegistryEntryGetRegistryEntryID(service, &registryID)) { IOObjectRelease(service); close(lock); return 1; }
    if (!Send(STDOUT_FILENO, @{@"state": @"failsafe-ready", @"registry_id": @(registryID)})) { IOObjectRelease(service); close(lock); return 1; }
    double deadline = Now() + FailsafeSeconds;
    NSUInteger windowsCompleted = 0;
    // Sole logging owner: a paused or dead guardian cannot extend or re-enable a window.
    for (NSUInteger index = 0; index < 10 && !Interrupted && Now() < deadline; index++) {
        NSString *command = Line(STDIN_FILENO, deadline);
        if (![command isEqual:[NSString stringWithFormat:@"ARM %lu", (unsigned long)index]] || !Integer(Value(service), 0)) break;
        double sourceStart = NSDate.date.timeIntervalSince1970;
        BOOL enabled = SetValue(service, @2);
        double started = Now(), activeDeadline = fmin(started + WindowSeconds, deadline);
        if (!enabled || !Send(STDOUT_FILENO, @{@"state": @"armed", @"trial": @(index), @"source_start": @(sourceStart),
            @"deadline": @(activeDeadline)})) break;
        BOOL stopped = NO;
        while (!EndWindow(Now(), activeDeadline, Interrupted, NO, YES, YES)) {
            struct pollfd control = {STDIN_FILENO, POLLIN | POLLHUP, 0};
            int result = poll(&control, 1, 25);
            if (result < 0 && errno == EINTR) continue;
            if(result != 0) { stopped = YES; break; } // Any byte or EOF cancels the window.
        }
        BOOL restored = Restore(service, original);
        double sourceEnd = NSDate.date.timeIntervalSince1970;
        BOOL complete = enabled && restored && !stopped && !Interrupted && Now() >= activeDeadline;
        if(!Send(STDOUT_FILENO, @{@"state": @"window-off", @"trial": @(index), @"logging_restored": @(restored),
            @"window_complete": @(complete), @"source_end": @(sourceEnd), @"elapsed": @(Now()-started)}) || !complete) break;
        windowsCompleted++;
    }
    // Keep the logging owner and its lock alive through the guardian's last stream drain.
    // No eleventh ARM is accepted; only control EOF, a signal, or the hard TTL can finish.
    while(windowsCompleted == 10 && !Interrupted && Now() < deadline) {
        struct pollfd control = {STDIN_FILENO, POLLIN | POLLHUP, 0};
        int result = poll(&control, 1, 100);
        if(result < 0 && errno == EINTR) continue;
        if(result != 0) break;
    }
    BOOL restored = Restore(service, original);
    (void)Send(STDOUT_FILENO, @{@"state": restored ? @"failsafe-restored" : @"restore-failed", @"logging_restored": @(restored)});
    IOObjectRelease(service); close(lock); return restored ? 0 : 1;
}
static NSArray *Trials(void) {
    return @[@{@"id": @"direct-F4", @"prompt": @"Press and release F4 without Fn."},
      @{@"id": @"direct-F5", @"prompt": @"Press and release F5 without Fn."},
      @{@"id": @"Fn-F5", @"prompt": @"After NOW, press Fn, then F5, release F5, then release Fn."},
      @{@"id": @"direct-F7", @"prompt": @"Press and release F7 without Fn."},
      @{@"id": @"direct-F8", @"prompt": @"Press and release F8 without Fn."},
      @{@"id": @"direct-F9", @"prompt": @"Press and release F9 without Fn."},
      @{@"id": @"direct-F10", @"prompt": @"Press and release F10 without Fn."},
      @{@"id": @"ordinary-Command-L", @"prompt": @"After NOW, press Command, then L, release L, then release Command."},
      @{@"id": @"ordinary-Command-P", @"prompt": @"After NOW, press Command, then P, release P, then release Command."},
      @{@"id": @"Fn-alone", @"prompt": @"After NOW, press and release Fn alone."}];
}
static BOOL PositiveF5Control(NSDictionary *capture) {
    if (![capture[@"capture_complete"] boolValue] || ![capture[@"source_time_attribution_verified"] boolValue] ||
        [capture[@"record_limit_reached"] boolValue]) return NO;
    BOOL down = NO, up = NO;
    for (NSDictionary *record in capture[@"records"]) if (Integer(record[@"adb_code"], 0x60)) {
        down |= [record[@"direction"] isEqual:@"down"]; up |= [record[@"direction"] isEqual:@"up"];
    } return down && up;
}
static NSDictionary *Capture(io_service_t service, NSNumber *original, NSUInteger index, double guardianDeadline, NSTask *failsafe, int failsafeWrite, int failsafeRead) {
    if (Interrupted || Now() >= guardianDeadline || !failsafe.running || !Integer(Value(service), 0)) return nil;
    NSPipe *stream = PrivatePipe(); if(!stream) return nil;
    NSTask *logger = Task(@"/usr/bin/log", @[@"stream", @"--style", @"ndjson", @"--level", @"debug", @"--predicate",
        @"process == 'kernel' AND eventMessage BEGINSWITH 'ApplePS2Keyboard: sending key '"], nil, stream);
    if (!logger) return nil;
    [stream.fileHandleForWriting closeFile];
    int logFD = stream.fileHandleForReading.fileDescriptor; fcntl(logFD, F_SETFL, O_NONBLOCK);
    // Settle startup before enabling any keyboard trace. No inherited control writer exists in log.
    struct pollfd dummy = {-1, 0, 0}; (void)poll(&dummy, 0, 250);
    if (!logger.running || Interrupted || !failsafe.running || Now() >= guardianDeadline) { StopTask(logger); return nil; }
    NSData *request = [[NSString stringWithFormat:@"ARM %lu\n", (unsigned long)index] dataUsingEncoding:NSASCIIStringEncoding];
    BOOL requested = WriteAll(failsafeWrite, request.bytes, request.length);
    NSDictionary *armed = requested ? Message(failsafeRead, Now()+3) : nil;
    BOOL enabled = [armed[@"state"] isEqual:@"armed"] && Integer(armed[@"trial"], index) && Integer(Value(service), 2);
    double sourceStart = [armed[@"source_start"] doubleValue], deadline = [armed[@"deadline"] doubleValue];
    if(!enabled || !isfinite(sourceStart) || sourceStart <= 0 || deadline <= Now() || deadline > Now()+WindowSeconds+0.2) {
        (void)WriteAll(failsafeWrite, "STOP\n", 5); Restore(service, original); StopTask(logger); return nil;
    }
    NSMutableData *buffer = [NSMutableData data]; NSMutableArray *records = [NSMutableArray array];
    BOOL truncated = NO, aborted = !enabled; NSUInteger unattributed = 0;
    if (enabled && !Send(STDOUT_FILENO, @{@"state": @"active", @"trial": @(index), @"seconds": @(WindowSeconds)})) aborted = YES;
    while (!aborted && !EndWindow(Now(), deadline, Interrupted, NO, logger.running, failsafe.running)) {
        if (!logger.running || !failsafe.running) { aborted = YES; break; }
        struct pollfd descriptors[] = {{STDIN_FILENO, POLLIN | POLLHUP, 0}, {logFD, POLLIN | POLLHUP, 0}, {failsafeRead, POLLIN | POLLHUP, 0}};
        (void)poll(descriptors, 3, 25);
        if (EndWindow(Now(), deadline, Interrupted, descriptors[0].revents != 0, logger.running, failsafe.running)) {
            if (descriptors[0].revents || Interrupted || !logger.running || !failsafe.running) aborted = YES;
            break;
        } // An overdue deadline is checked before processing any more control or trace bytes.
        if(descriptors[2].revents) break;
        if (descriptors[1].revents & POLLIN) { unsigned char bytes[4096]; ssize_t length = read(logFD, bytes, sizeof(bytes));
            if (length > 0) { [buffer appendBytes:bytes length:(NSUInteger)length]; ParseLines(buffer, records, &truncated, sourceStart, &unattributed); }
        }
    }
    if(aborted || Interrupted) (void)WriteAll(failsafeWrite, "STOP\n", 5);
    NSDictionary *off = Message(failsafeRead, Now()+3);
    BOOL validOff = [off[@"state"] isEqual:@"window-off"] && Integer(off[@"trial"], index);
    BOOL restored = validOff && [off[@"logging_restored"] boolValue] && Integer(Value(service), 0);
    if(!restored) restored = Restore(service, original);
    double sourceEnd = [off[@"source_end"] doubleValue], elapsed = [off[@"elapsed"] doubleValue];
    // Drain only already-emitted trace lines while logging is off. Parent cannot type until OFF.
    double drainEnd = Now() + 0.5;
    while (restored && Now() < drainEnd && !Interrupted) {
        struct pollfd input = {logFD, POLLIN, 0}; (void)poll(&input, 1, 25);
        unsigned char bytes[4096]; ssize_t length = read(logFD, bytes, sizeof(bytes));
        if (length > 0) { [buffer appendBytes:bytes length:(NSUInteger)length]; ParseLines(buffer, records, &truncated, sourceStart, &unattributed); }
    }
    BOOL loggerRunning = logger.running;
    StopTask(logger); [stream.fileHandleForReading closeFile];
    NSIndexSet *late = [records indexesOfObjectsPassingTest:^BOOL(NSDictionary *record, NSUInteger position, BOOL *stop) {
        (void)position; (void)stop; return [record[@"source_offset_ms"] doubleValue] > (sourceEnd-sourceStart)*1000;
    }];
    [records removeObjectsAtIndexes:late];
    BOOL clockStable = isfinite(sourceEnd) && sourceEnd >= sourceStart && fabs((sourceEnd-sourceStart)-elapsed) < 0.5;
    return @{@"state": restored ? @"off" : @"restore-failed", @"trial": @(index), @"logging_restored": @(restored),
        @"capture_complete": @(!aborted && !Interrupted && enabled && loggerRunning && restored && validOff && [off[@"window_complete"] boolValue]),
        @"source_time_attribution_verified": @(clockStable && unattributed == 0),
        @"unattributed_trace_count": @(unattributed), @"record_limit_reached": @(truncated), @"records": records};
}
static int Guardian(void) {
    if (geteuid() != 0 || isatty(STDIN_FILENO)) return 77;
    io_service_t service = Driver(YES); if(!service) { Send(STDOUT_FILENO, @{@"state": @"identity-unavailable"}); return 78; }
    NSNumber *original = Value(service);
    NSPipe *backupInput = PrivatePipe(), *backupOutput = PrivatePipe();
    if(!backupInput || !backupOutput) { IOObjectRelease(service); return 1; }
    NSTask *backup = Task(SelfPath(), @[@"--failsafe"], backupInput, backupOutput);
    [backupInput.fileHandleForReading closeFile]; [backupOutput.fileHandleForWriting closeFile];
    NSDictionary *ready = backup ? Message(backupOutput.fileHandleForReading.fileDescriptor, Now()+8) : nil;
    uint64_t registryID = 0; (void)IORegistryEntryGetRegistryEntryID(service, &registryID);
    if (![ready[@"state"] isEqual:@"failsafe-ready"] || !Integer(ready[@"registry_id"], (long long)registryID)) {
        [backupInput.fileHandleForWriting closeFile]; StopTask(backup); IOObjectRelease(service); return 1;
    }
    double deadline = Now() + GuardianSeconds; int result = 0;
    if (!Send(STDOUT_FILENO, @{@"state": @"ready", @"trials": @(Trials().count)})) result = 1;
    for (NSUInteger index = 0; !result && index < Trials().count; index++) {
        NSString *command = Line(STDIN_FILENO, deadline);
        if (!ExpectedCommand(command, index) || Interrupted || Now() >= deadline || !backup.running) { result = 1; break; }
        NSDictionary *capture = Capture(service, original, index, deadline, backup,
            backupInput.fileHandleForWriting.fileDescriptor, backupOutput.fileHandleForReading.fileDescriptor);
        if (!capture || !Send(STDOUT_FILENO, capture) || ![capture[@"capture_complete"] boolValue]) { result = 1; break; }
    }
    BOOL restored = Restore(service, original);
    [backupInput.fileHandleForWriting closeFile];
    // Let the independent failsafe confirm restoration before ending the privileged guardian.
    NSDictionary *finish = Message(backupOutput.fileHandleForReading.fileDescriptor, Now()+4);
    restored = restored && [finish[@"state"] isEqual:@"failsafe-restored"];
    if (!restored) result = 1;
    StopTask(backup); [backupOutput.fileHandleForReading closeFile];
    Send(STDOUT_FILENO, @{@"state": restored ? @"finished" : @"restore-failed", @"logging_restored": @(restored), @"success": @(!result && restored)});
    IOObjectRelease(service); return restored ? result : 1;
}
static BOOL ConsoleEnter(int guardianFD) {
    while (!Interrupted) {
        struct pollfd descriptors[] = {{STDIN_FILENO, POLLIN | POLLHUP, 0}, {guardianFD, POLLIN | POLLHUP, 0}};
        int result = poll(descriptors, 2, 100);
        if (result < 0 && errno == EINTR) continue;
        if (result < 0 || descriptors[1].revents) return NO;
        if (descriptors[0].revents) { unsigned char byte; if(read(STDIN_FILENO, &byte, 1) != 1) return NO; if(byte == '\n') return YES; }
    } return NO;
}
static BOOL SafeDirectory(NSString *directory) {
    struct stat st;
    return directory.isAbsolutePath && lstat(directory.fileSystemRepresentation, &st) == 0 && S_ISDIR(st.st_mode) &&
        !S_ISLNK(st.st_mode) && st.st_uid == getuid() && (st.st_mode & 0777) == 0700;
}
static BOOL WriteReport(NSString *directory, NSArray *trials, BOOL restored, BOOL success) {
    BOOL transport = NO;
    for (NSDictionary *trial in trials) if ([trial[@"id"] isEqual:@"direct-F5"] || [trial[@"id"] isEqual:@"Fn-F5"])
        transport |= PositiveF5Control(trial);
    NSDictionary *report = @{@"schema": @1, @"probe_version": @"1.0.0", @"driver_bundle": BundleID, @"driver_version": @"2.3.7",
      @"driver_release_uuid": @"efa883f4-7558-3e98-a352-e202cb3dfaaf", @"reference_binary_sha256": DriverSHA,
      @"logging_restored": @(restored), @"collection_complete": @(success), @"window_seconds": @(WindowSeconds),
      @"trace_transport_confirmed": @(transport),
      @"trace_limitations": @"Driver logging follows macro inversion and special handling. Empty traces do not prove absent firmware or PS/2 events.",
      @"privacy_note": @"Kernel scan traces also enter the unified system log during each window. Only requested keys should be pressed.", @"trials": trials};
    NSData *json = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:NULL];
    NSString *path = [directory stringByAppendingPathComponent:@"scancodes.json"];
    int fd = open(path.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (fd < 0) return NO;
    BOOL written = json && WriteAll(fd, json.bytes, json.length) && WriteAll(fd, "\n", 1); close(fd); return written;
}
static int Collect(NSString *directory) {
    if(geteuid() == 0 || getuid() != geteuid() || !isatty(STDIN_FILENO) || !SafeDirectory(directory)) return 77;
    struct stat console; if(stat("/dev/console", &console) || console.st_uid != getuid()) return 77;
    NSPipe *control = PrivatePipe(), *output = PrivatePipe(); if(!control || !output) return 1;
    NSTask *guardian = Task(@"/usr/bin/sudo", @[@"-n", @"--", SelfPath(), @"--guardian"], control, output);
    [control.fileHandleForReading closeFile]; [output.fileHandleForWriting closeFile];
    NSDictionary *ready = guardian ? Message(output.fileHandleForReading.fileDescriptor, Now()+15) : nil;
    if (![ready[@"state"] isEqual:@"ready"]) {
        fprintf(stderr, "Scan-code collection: The exact loaded RELEASE driver and numeric logging state could not be verified. No capture started.\n");
        [control.fileHandleForWriting closeFile]; StopTask(guardian); return 78;
    }
    NSMutableArray *captures = [NSMutableArray array]; BOOL success = YES, restored = YES;
    for (NSUInteger index = 0; index < Trials().count; index++) {
        NSDictionary *trial = Trials()[index];
        printf("\n%lu/%lu: %s\nRelease every key. Press ENTER to prepare, then wait for NOW.\n", (unsigned long)index+1,
            (unsigned long)Trials().count, [trial[@"prompt"] UTF8String]); fflush(stdout);
        if (!ConsoleEnter(output.fileHandleForReading.fileDescriptor)) { success = NO; break; }
        NSData *command = [[NSString stringWithFormat:@"START %lu\n", (unsigned long)index] dataUsingEncoding:NSASCIIStringEncoding];
        if (!WriteAll(control.fileHandleForWriting.fileDescriptor, command.bytes, command.length)) { success = NO; break; }
        NSDictionary *active = Message(output.fileHandleForReading.fileDescriptor, Now()+8);
        if (![active[@"state"] isEqual:@"active"] || !Integer(active[@"trial"], index)) { success = NO; break; }
        printf("NOW: requested keys only. Release all keys within 3 seconds. Do not type anything else.\n"); fflush(stdout);
        NSDictionary *capture = Message(output.fileHandleForReading.fileDescriptor, Now()+8);
        if (!capture || !Integer(capture[@"trial"], index)) { success = NO; break; }
        NSMutableDictionary *record = [capture mutableCopy]; [record removeObjectForKey:@"state"];
        record[@"id"] = trial[@"id"]; [captures addObject:record];
        restored = [capture[@"logging_restored"] boolValue];
        if (![capture[@"capture_complete"] boolValue] || !restored) { success = NO; break; }
        printf("OFF: logging restored. %lu numeric transitions retained.\n", (unsigned long)[capture[@"records"] count]); fflush(stdout);
        if(index == 2 && !PositiveF5Control(captures[1]) && !PositiveF5Control(captures[2])) {
            fprintf(stderr, "The F5 positive controls did not verify timestamped driver trace visibility. Remaining prompts are skipped.\n");
            success = NO; break;
        }
    }
    [control.fileHandleForWriting closeFile];
    NSDictionary *finish = Message(output.fileHandleForReading.fileDescriptor, Now()+8);
    restored = restored && [finish[@"logging_restored"] boolValue];
    success = success && [finish[@"success"] boolValue];
    StopTask(guardian); [output.fileHandleForReading closeFile];
    if (!WriteReport(directory, captures, restored, success)) return 1;
    fprintf(stdout, "\nCollection %s. Logging restoration: %s.\n", success ? "completed" : "interrupted", restored ? "verified" : "not verified");
    return success && restored ? 0 : 1;
}
static int SelfTest(void) {
    NSUInteger checks = 0;
#define CHECK(condition) do { checks++; if (!(condition)) { fprintf(stderr, "Scan fixture failed: %lu\n", (unsigned long)checks); return 1; } } while(0)
    CHECK(Integer(@0, 0)); CHECK(!Integer(@NO, 0)); CHECK(!Integer(@0.0, 0)); CHECK(!Integer(@"0", 0)); CHECK(!Integer(@1, 0));
    NSDictionary *plain = Trace(@"ApplePS2Keyboard: sending key 3f=60 down");
    CHECK([plain[@"raw_scan"] isEqual:@63]); CHECK([plain[@"mapped_scan"] isEqual:@63]); CHECK([plain[@"adb_code"] isEqual:@96]);
    CHECK([plain[@"direction"] isEqual:@"down"]); CHECK(Trace(@"ApplePS2Keyboard: sending key e063=80 up\n"));
    CHECK(Trace(@"ApplePS2Keyboard: sending key e067=3f, 3f=60 down"));
    CHECK(!Trace(@"ApplePS2Keyboard: sending key e067=3f, 40=60 down"));
    CHECK(!Trace(@"ApplePS2Keyboard: sending key e067=100 down"));
    CHECK(!Trace(@"ApplePS2Keyboard: sending key 99=60 down"));
    CHECK(!Trace(@"ApplePS2Keyboard: sending key e167=60 down"));
    CHECK(!Trace(@"other: ApplePS2Keyboard: sending key 3f=60 down"));
    CHECK(!Trace(@"ApplePS2Keyboard: sending key 3f=60 down password"));
    CHECK(!Trace(@"ApplePS2Keyboard: sending key 3f=60 down\nsecret")); CHECK(!Trace((id)@2));
    NSMutableDictionary *identity = [@{@"CFBundleIdentifier": BundleID, @"CFBundleVersion": @"2.3.7", @"OSBundleStarted": @YES,
        @"OSBundleCPUType": @(CPU_TYPE_X86_64), @"OSBundleUUID": [NSData dataWithBytes:DriverUUID length:sizeof(DriverUUID)]} mutableCopy];
    CHECK(LoadedIdentity(identity)); identity[@"CFBundleVersion"] = @"2.3.8"; CHECK(!LoadedIdentity(identity));
    identity[@"CFBundleVersion"] = @"2.3.7"; identity[@"OSBundleStarted"] = @1; CHECK(!LoadedIdentity(identity));
    identity[@"OSBundleStarted"] = @YES; identity[@"OSBundleUUID"] = [NSMutableData dataWithLength:16]; CHECK(!LoadedIdentity(identity));
    CHECK(!LoadedIdentity(@{}));
    CHECK(VerifiedWriteOutcome(kIOReturnError, @2, @2)); CHECK(!VerifiedWriteOutcome(kIOReturnSuccess, @0, @2));
    CHECK(!VerifiedWriteOutcome(kIOReturnSuccess, @YES, @1));
    CHECK(RestoreDecision(@0, @0) == RestorationVerified); CHECK(RestoreDecision(@2, @0) == RestorationRequired);
    CHECK(RestoreDecision(@1, @0) == RestorationConflict); CHECK(RestoreDecision(nil, @0) == RestorationConflict);
    CHECK(RestoreDecision(@NO, @0) == RestorationConflict); CHECK(RestoreDecision(@0.0, @0) == RestorationConflict);
    CHECK(!EndWindow(10, 13, NO, NO, YES, YES)); CHECK(EndWindow(13, 13, NO, NO, YES, YES));
    CHECK(EndWindow(12, 13, YES, NO, YES, YES)); CHECK(EndWindow(12, 13, NO, YES, YES, YES));
    CHECK(EndWindow(12, 13, NO, NO, NO, YES)); CHECK(EndWindow(12, 13, NO, NO, YES, NO));
    CHECK(ExpectedCommand(@"START 0", 0)); CHECK(!ExpectedCommand(@"START 0", 1));
    CHECK(!ExpectedCommand(@"START 1 anything", 1)); CHECK(!ExpectedCommand(@"START 01", 1));
    CHECK(isfinite(SourceTime(@"2026-10-14 18:00:00.123456+0200"))); CHECK(!isfinite(SourceTime(@"invalid")));
    NSMutableData *buffer = [NSMutableData data]; NSMutableArray *records = [NSMutableArray array]; BOOL truncated = NO; NSUInteger unattributed = 0;
    double sourceStart = SourceTime(@"2026-10-14 18:00:00.000000+0200");
    for (NSUInteger index = 0; index < 130; index++) [buffer appendData:[@"{\"timestamp\":\"2026-10-14 18:00:00.123456+0200\",\"eventMessage\":\"ApplePS2Keyboard: sending key 3f=60 down\",\"processImagePath\":\"PRIVATE_PATH\"}\n" dataUsingEncoding:NSUTF8StringEncoding]];
    ParseLines(buffer, records, &truncated, sourceStart, &unattributed); CHECK(records.count == MaximumRecords); CHECK(truncated); CHECK(buffer.length == 0); CHECK(unattributed == 0);
    [buffer appendData:[@"{\"timestamp\":\"2026-10-14 17:59:58.999999+0200\",\"eventMessage\":\"ApplePS2Keyboard: sending key 3f=60 down\"}\n" dataUsingEncoding:NSUTF8StringEncoding]];
    NSMutableArray *old = [NSMutableArray array]; ParseLines(buffer, old, &truncated, sourceStart, &unattributed); CHECK(old.count == 0);
    [buffer appendData:[@"{\"eventMessage\":\"ApplePS2Keyboard: sending key 3f=60 down\"}\n" dataUsingEncoding:NSUTF8StringEncoding]];
    ParseLines(buffer, old, &truncated, sourceStart, &unattributed); CHECK(unattributed == 1); CHECK(old.count == 0);
    NSData *encoded = [NSJSONSerialization dataWithJSONObject:records options:0 error:NULL];
    NSString *output = [[NSString alloc] initWithData:encoded encoding:NSUTF8StringEncoding];
    CHECK(![output containsString:@"PRIVATE_PATH"]); CHECK(![output containsString:@"eventMessage"]);
    CHECK(Trials().count == 10); CHECK([Trials()[9][@"id"] isEqual:@"Fn-alone"]);
    NSDictionary *validControl = @{@"capture_complete": @YES, @"source_time_attribution_verified": @YES,
      @"record_limit_reached": @NO, @"records": @[Trace(@"ApplePS2Keyboard: sending key 3f=60 down"), Trace(@"ApplePS2Keyboard: sending key 3f=60 up")]};
    CHECK(PositiveF5Control(validControl));
    NSMutableDictionary *invalidControl = [validControl mutableCopy]; invalidControl[@"source_time_attribution_verified"] = @NO;
    CHECK(!PositiveF5Control(invalidControl)); invalidControl[@"source_time_attribution_verified"] = @YES;
    invalidControl[@"records"] = @[Trace(@"ApplePS2Keyboard: sending key 3f=60 down")]; CHECK(!PositiveF5Control(invalidControl));
    // Child must see EOF after the parent writer closes, not retain an inherited copy of that writer.
    NSPipe *fixtureInput = PrivatePipe(), *fixtureOutput = PrivatePipe(); CHECK(fixtureInput && fixtureOutput);
    NSTask *fixtureChild = Task(SelfPath(), @[@"--fixture-eof"], fixtureInput, fixtureOutput); CHECK(fixtureChild);
    [fixtureInput.fileHandleForReading closeFile]; [fixtureOutput.fileHandleForWriting closeFile];
    CHECK([Message(fixtureOutput.fileHandleForReading.fileDescriptor, Now()+3)[@"state"] isEqual:@"fixture-ready"]);
    [fixtureInput.fileHandleForWriting closeFile];
    CHECK([Message(fixtureOutput.fileHandleForReading.fileDescriptor, Now()+3)[@"state"] isEqual:@"fixture-eof"]);
    StopTask(fixtureChild); [fixtureOutput.fileHandleForReading closeFile]; CHECK(fixtureChild.terminationStatus == 0);
    printf("Pure scan-code, loaded-identity and privacy fixture checks passed: %lu\n", (unsigned long)checks);
    return 0;
#undef CHECK
}
int main(int argc, const char *argv[]) { @autoreleasepool {
    Signals();
    if (argc == 2 && !strcmp(argv[1], "--fixture-eof")) {
        if(isatty(STDIN_FILENO)) return 64;
        if(!Send(STDOUT_FILENO, @{@"state": @"fixture-ready"})) return 1;
        char byte; ssize_t count = read(STDIN_FILENO, &byte, 1);
        if(count != 0) return 1;
        return Send(STDOUT_FILENO, @{@"state": @"fixture-eof"}) ? 0 : 1;
    }
    if (argc == 2 && !strcmp(argv[1], "--self-test")) return SelfTest();
    struct utsname system; if(uname(&system) || strcmp(system.sysname,"Darwin") || strcmp(system.machine,"x86_64")) return 77;
    if (argc == 2 && !strcmp(argv[1], "--failsafe")) return Failsafe();
    if (argc == 2 && !strcmp(argv[1], "--guardian")) return Guardian();
    if (argc == 3 && !strcmp(argv[1], "--output")) return Collect([NSString stringWithUTF8String:argv[2]]);
    fprintf(stderr, "Use --self-test or --output PRIVATE_EXISTING_DIRECTORY.\n"); return 64;
} }
