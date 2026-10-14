// SPDX-License-Identifier: MIT
// A bounded, passive function-key probe. No key text is requested or retained.
#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreAudio/CoreAudio.h>
#include <unistd.h>
#include <termios.h>
#include <sys/stat.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>

static const double CaptureSeconds = 3.0;
static const NSUInteger MaximumEventsPerTrial = 64;
static const CGEventType SystemDefinedType = (CGEventType)14;
static const int MediaButtonsSubtype = 8;
static const unsigned short FunctionCodes[] = {
    122, 120, 99, 118, 96, 97, 98, 100, 101, 109,
    103, 111, 105, 107, 113, 106, 64, 79, 80, 90
};
static const unsigned short ModifierCodes[] = {54, 55, 56, 57, 58, 59, 60, 61, 62, 63};

@interface CaptureState : NSObject
@property(nonatomic) BOOL active;
@property(nonatomic) NSUInteger directKey;
@property(nonatomic) BOOL tapInterrupted;
@property(nonatomic) BOOL overflow;
@property(nonatomic) CFAbsoluteTime started;
@property(nonatomic, strong) NSMutableArray<NSDictionary *> *events;
@property(nonatomic, strong) NSMutableArray<NSDictionary *> *interruptions;
@end
@implementation CaptureState
@end

static double MonotonicTime(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return 0;
    return (double)now.tv_sec + (double)now.tv_nsec / 1000000000.0;
}

static NSString *FunctionName(unsigned short code) {
    for (NSUInteger i = 0; i < sizeof(FunctionCodes) / sizeof(FunctionCodes[0]); i++) {
        if (FunctionCodes[i] == code) return [NSString stringWithFormat:@"F%lu", (unsigned long)i + 1];
    }
    return nil;
}

static BOOL ModifierCode(unsigned short code) {
    for (NSUInteger i = 0; i < sizeof(ModifierCodes) / sizeof(ModifierCodes[0]); i++) {
        if (ModifierCodes[i] == code) return YES;
    }
    return NO;
}

static NSArray<NSString *> *ModifierNames(CGEventFlags flags) {
    NSMutableArray *names = [NSMutableArray array];
    const CGEventFlags masks[] = {
        kCGEventFlagMaskAlphaShift, kCGEventFlagMaskShift, kCGEventFlagMaskControl,
        kCGEventFlagMaskAlternate, kCGEventFlagMaskCommand, kCGEventFlagMaskNumericPad,
        kCGEventFlagMaskHelp, kCGEventFlagMaskSecondaryFn
    };
    NSArray *labels = @[@"caps_lock", @"shift", @"control", @"option", @"command",
                        @"numeric_pad", @"help", @"secondary_fn_flag"];
    for (NSUInteger i = 0; i < sizeof(masks) / sizeof(masks[0]); i++) {
        if (flags & masks[i]) [names addObject:labels[i]];
    }
    return names;
}

// Printable-key positions are accepted only as these exact chords in their own direct trial.
// No character text is read. Other trials, unmodified letters, and extra chord modifiers are rejected.
static NSString *AllowedShortcut(unsigned short code, CGEventFlags flags, NSUInteger directKey) {
    CGEventFlags chord = flags & (kCGEventFlagMaskShift | kCGEventFlagMaskControl |
                                 kCGEventFlagMaskAlternate | kCGEventFlagMaskCommand);
    if (directKey == 5 && code == 15) { // ANSI R position.
        if (chord == kCGEventFlagMaskCommand) return @"command_r";
        if (chord == kCGEventFlagMaskControl) return @"control_r";
    }
    if (directKey == 9 && code == 37 && chord == kCGEventFlagMaskCommand) return @"command_l";
    if (directKey == 10 && code == 35 && chord == kCGEventFlagMaskCommand) return @"command_p";
    return nil;
}

static NSDictionary *DecodeKey(CGEventType type, unsigned short code, CGEventFlags flags,
                               BOOL repeat, NSUInteger directKey) {
    NSString *function = FunctionName(code);
    NSString *shortcut = AllowedShortcut(code, flags, directKey);
    if (type == kCGEventFlagsChanged) {
        if (!ModifierCode(code)) return nil;
        return @{@"kind": @"modifier_change", @"keycode": @(code),
                 @"modifiers": ModifierNames(flags)};
    }
    if (type != kCGEventKeyDown && type != kCGEventKeyUp) return nil;
    if (!function && !shortcut) return nil;
    NSMutableDictionary *decoded = [@{@"kind": type == kCGEventKeyDown ? @"key_down" : @"key_up",
                                     @"keycode": @(code), @"modifiers": ModifierNames(flags),
                                     @"repeat": @(repeat)} mutableCopy];
    if (function) decoded[@"function_key"] = function;
    if (shortcut) {
        decoded[@"shortcut"] = shortcut;
        if (directKey == 5) decoded[@"refresh_shortcut"] = shortcut;
    }
    return decoded;
}

static NSDictionary *DecodeMedia(int subtype, uint32_t data1, CGEventFlags flags) {
    if (subtype != MediaButtonsSubtype) return nil;
    uint16_t key = (uint16_t)(data1 >> 16);
    uint8_t state = (uint8_t)((data1 >> 8) & 0xff);
    uint8_t low = (uint8_t)(data1 & 0xff);
    // AUX_CONTROL_BUTTONS packs a non-text media key ID, key state, and repeat bit.
    // Do not retain data2 or other system-defined subtypes, which can contain unrelated data.
    return @{@"kind": @"media_button", @"subtype": @(subtype), @"media_key_code": @(key),
             @"state": state == 0x0a ? @"down" : state == 0x0b ? @"up" : @"other",
             @"state_code": @(state), @"repeat": @((low & 1) != 0),
             @"modifiers": ModifierNames(flags)};
}

static void RecordTapInterruption(CaptureState *capture, CGEventType type, double now) {
    if (!capture.active) return;
    NSString *reason = type == kCGEventTapDisabledByTimeout ? @"timeout" :
                       type == kCGEventTapDisabledByUserInput ? @"user_disabled" : nil;
    if (!reason) return;
    capture.tapInterrupted = YES;
    if (capture.interruptions.count < 4) {
        [capture.interruptions addObject:@{@"reason": reason,
            @"elapsed_ms": @(MAX(0, (NSInteger)((now - capture.started) * 1000)))}];
    }
}

static CGEventRef ListenCallback(CGEventTapProxy proxy, CGEventType type, CGEventRef event,
                                void *context) {
    (void)proxy;
    @autoreleasepool {
        CaptureState *capture = (__bridge CaptureState *)context;
        if (type == kCGEventTapDisabledByTimeout || type == kCGEventTapDisabledByUserInput) {
            RecordTapInterruption(capture, type, MonotonicTime());
            return event;
        }
        if (!capture.active) return event;
        NSDictionary *decoded = nil;
        CGEventFlags flags = CGEventGetFlags(event);
        if (type == SystemDefinedType) {
            NSEvent *native = [NSEvent eventWithCGEvent:event];
            if (native && native.type == NSEventTypeSystemDefined) {
                decoded = DecodeMedia(native.subtype, (uint32_t)native.data1, flags);
            }
        } else if (type == kCGEventKeyDown || type == kCGEventKeyUp || type == kCGEventFlagsChanged) {
            unsigned short code = (unsigned short)CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode);
            BOOL repeat = CGEventGetIntegerValueField(event, kCGKeyboardEventAutorepeat) != 0;
            decoded = DecodeKey(type, code, flags, repeat, capture.directKey);
        }
        if (decoded) {
            if (capture.events.count < MaximumEventsPerTrial) {
                NSMutableDictionary *record = [decoded mutableCopy];
                record[@"elapsed_ms"] = @(MAX(0, (NSInteger)((MonotonicTime() - capture.started) * 1000)));
                [capture.events addObject:record];
            } else capture.overflow = YES;
        }
        // A listen-only tap cannot suppress or alter events. Return the original event.
        return event;
    }
}

static NSDictionary *InputMuteControl(AudioDeviceID device, UInt32 element) {
    AudioObjectPropertyAddress address = {kAudioDevicePropertyMute, kAudioObjectPropertyScopeInput, element};
    Boolean available = AudioObjectHasProperty(device, &address);
    NSMutableDictionary *result = [@{@"element": @(element), @"available": @(available != 0)} mutableCopy];
    if (!available) return result;
    Boolean settable = false;
    OSStatus status = AudioObjectIsPropertySettable(device, &address, &settable);
    result[@"settable_query_status"] = @(status);
    result[@"settable"] = status == noErr ? @(settable != 0) : (id)[NSNull null];
    UInt32 muted = 0, size = sizeof(muted);
    status = AudioObjectGetPropertyData(device, &address, 0, NULL, &size, &muted);
    result[@"read_status"] = @(status);
    result[@"muted"] = status == noErr && size == sizeof(muted) ? @(muted != 0) : (id)[NSNull null];
    return result;
}

static NSDictionary *InputAudioCapabilities(void) {
    AudioObjectPropertyAddress address = {kAudioHardwarePropertyDefaultInputDevice,
                                         kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    AudioDeviceID device = kAudioObjectUnknown;
    UInt32 size = sizeof(device);
    OSStatus status = AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, NULL, &size, &device);
    BOOL exists = status == noErr && size == sizeof(device) && device != kAudioObjectUnknown;
    NSMutableDictionary *result = [@{@"default_input_exists": @(exists), @"device_query_status": @(status),
                                     @"read_only": @YES} mutableCopy];
    if (!exists) return result;
    address = (AudioObjectPropertyAddress){kAudioDevicePropertyStreamConfiguration,
                                          kAudioObjectPropertyScopeInput, kAudioObjectPropertyElementMain};
    size = 0;
    status = AudioObjectGetPropertyDataSize(device, &address, 0, NULL, &size);
    UInt32 channels = 0;
    if (status == noErr && size >= sizeof(AudioBufferList) && size <= 1024 * 1024) {
        AudioBufferList *buffers = calloc(1, size);
        if (buffers) {
            UInt32 allocated = size;
            status = AudioObjectGetPropertyData(device, &address, 0, NULL, &size, buffers);
            size_t header = offsetof(AudioBufferList, mBuffers);
            size_t capacity = allocated >= header ? (allocated - header) / sizeof(AudioBuffer) : 0;
            if (status == noErr && size <= allocated && buffers->mNumberBuffers <= capacity) {
                for (UInt32 i = 0; i < buffers->mNumberBuffers; i++) {
                    if (buffers->mBuffers[i].mNumberChannels <= 1024 &&
                        channels <= 1024 - buffers->mBuffers[i].mNumberChannels) {
                        channels += buffers->mBuffers[i].mNumberChannels;
                    } else { status = kAudioHardwareUnspecifiedError; break; }
                }
            } else if (status == noErr) status = kAudioHardwareUnspecifiedError;
            free(buffers);
        } else status = kAudioHardwareUnspecifiedError;
    } else if (status == noErr) status = kAudioHardwareUnspecifiedError;
    result[@"channel_query_status"] = @(status);
    result[@"input_channels"] = status == noErr ? @(channels) : (id)[NSNull null];
    NSMutableArray *controls = [NSMutableArray arrayWithObject:InputMuteControl(device, kAudioObjectPropertyElementMain)];
    if (status == noErr) {
        for (UInt32 channel = 1; channel <= MIN(channels, 16); channel++) {
            [controls addObject:InputMuteControl(device, channel)];
        }
    }
    result[@"mute_controls"] = controls;
    result[@"channel_controls_truncated"] = @(channels > 16);
    return result;
}

static BOOL IntegerValue(id object, int64_t minimum, int64_t maximum, int64_t *result) {
    if (![object isKindOfClass:[NSNumber class]]) return NO;
    CFTypeRef value = (__bridge CFTypeRef)object;
    if (CFGetTypeID(value) != CFNumberGetTypeID() || CFNumberIsFloatType((CFNumberRef)value)) return NO;
    int64_t parsed = 0;
    if (!CFNumberGetValue((CFNumberRef)value, kCFNumberSInt64Type, &parsed) ||
        parsed < minimum || parsed > maximum) return NO;
    *result = parsed;
    return YES;
}

static BOOL NumericPreferenceID(id object, uint32_t *result) {
    if (![object isKindOfClass:[NSString class]]) return NO;
    NSString *string = object;
    if (string.length == 0 || string.length > 10) return NO;
    uint64_t parsed = 0;
    for (NSUInteger i = 0; i < string.length; i++) {
        unichar character = [string characterAtIndex:i];
        if (character < '0' || character > '9') return NO;
        parsed = parsed * 10 + (uint64_t)(character - '0');
    }
    if (parsed > UINT32_MAX) return NO;
    *result = (uint32_t)parsed;
    return YES;
}

static NSDictionary *FilterSymbolicHotKeys(id raw) {
    // Read only the existing preference. Do not infer absent macOS default bindings.
    if (!raw) return @{@"status": @"MISSING_OR_UNAVAILABLE", @"bindings": @[], @"defaults_inferred": @NO};
    if (![raw isKindOfClass:[NSDictionary class]]) {
        return @{@"status": @"UNEXPECTED_VALUE_TYPE", @"bindings": @[], @"defaults_inferred": @NO};
    }
    NSMutableArray *bindings = [NSMutableArray array];
    NSUInteger malformed = 0;
    for (id identifier in (NSDictionary *)raw) {
        uint32_t numericID = 0;
        id entry = ((NSDictionary *)raw)[identifier];
        if (!NumericPreferenceID(identifier, &numericID) || ![entry isKindOfClass:[NSDictionary class]]) {
            malformed++; continue;
        }
        id enabled = ((NSDictionary *)entry)[@"enabled"];
        BOOL enabledFlag = NO;
        int64_t enabledInteger = 0;
        if ([enabled isKindOfClass:[NSNumber class]] &&
            CFGetTypeID((__bridge CFTypeRef)enabled) == CFBooleanGetTypeID()) {
            enabledFlag = [enabled boolValue];
        } else if (IntegerValue(enabled, 0, 1, &enabledInteger)) {
            enabledFlag = enabledInteger == 1;
        } else { malformed++; continue; }
        id value = ((NSDictionary *)entry)[@"value"];
        if (![value isKindOfClass:[NSDictionary class]]) { malformed++; continue; }
        id parameters = ((NSDictionary *)value)[@"parameters"];
        if (![parameters isKindOfClass:[NSArray class]] || [(NSArray *)parameters count] != 3) {
            malformed++; continue;
        }
        int64_t ignoredCharacter = 0, keycode = 0, flags = 0;
        NSArray *triplet = parameters;
        if (!IntegerValue(triplet[0], -1, UINT32_MAX, &ignoredCharacter) ||
            !IntegerValue(triplet[1], 0, UINT16_MAX, &keycode) ||
            !IntegerValue(triplet[2], 0, UINT32_MAX, &flags)) { malformed++; continue; }
        NSString *function = FunctionName((unsigned short)keycode);
        if (!function) continue;
        [bindings addObject:@{@"id": @(numericID), @"enabled": @(enabledFlag),
                             @"function_key": function, @"keycode": @(keycode),
                             @"modifier_flags": @(flags)}];
    }
    [bindings sortUsingDescriptors:@[[NSSortDescriptor sortDescriptorWithKey:@"id" ascending:YES]]];
    return @{@"status": @"AVAILABLE", @"bindings": bindings,
             @"malformed_entries_ignored": @(malformed), @"defaults_inferred": @NO};
}

static NSDictionary *ExistingSymbolicHotKeys(void) {
    CFPropertyListRef value = CFPreferencesCopyAppValue(CFSTR("AppleSymbolicHotKeys"),
                                                       CFSTR("com.apple.symbolichotkeys"));
    // Transfer only this immutable preference to ARC; no other application data is read.
    id existing = CFBridgingRelease(value);
    return FilterSymbolicHotKeys(existing);
}

static BOOL WaitForEnter(void) {
    // No typed input is stored. Consume and discard stdin until newline or EOF.
    int byte;
    while ((byte = getchar()) != EOF) if (byte == '\n') return YES;
    return NO;
}

static NSArray<NSDictionary *> *RequestedTrials(BOOL targeted) {
    NSMutableArray *trials = [NSMutableArray array];
    if (targeted) {
        for (NSNumber *key in @[@4, @5, @7, @8, @9, @10]) {
            [trials addObject:@{@"key": key, @"fn_layer": @NO}];
        }
        [trials addObject:@{@"key": @5, @"fn_layer": @YES}];
    } else {
        for (NSUInteger layer = 0; layer < 2; layer++) {
            for (NSUInteger key = 1; key <= 12; key++) {
                [trials addObject:@{@"key": @(key), @"fn_layer": @(layer == 1)}];
            }
        }
    }
    return trials;
}

static BOOL WriteReport(NSDictionary *report, NSString *directory) {
    NSError *error = nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:report
                                                 options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
    if (!json) return NO;
    NSString *jsonPath = [directory stringByAppendingPathComponent:@"events.json"];
    if (![[NSFileManager defaultManager] createFileAtPath:jsonPath contents:json
                                             attributes:@{NSFilePosixPermissions: @0600}]) return NO;
    NSMutableString *text = [NSMutableString stringWithString:@"Function-key event probe\n\n"];
    [text appendString:@"Passive Input Monitoring only. No key text, device identities, or personal paths are collected.\n"];
    [text appendString:@"The secondary_fn_flag is an event modifier, not proof that physical Fn was pressed.\n"];
    [text appendString:@"No matching event does not prove that firmware or ACPI produced no event.\n\n"];
    for (NSDictionary *trial in report[@"trials"]) {
        [text appendFormat:@"%@: %@\n", trial[@"label"], trial[@"status"]];
        if ([trial[@"tap_interrupted"] boolValue]) [text appendString:@"  Event tap interrupted; do not infer a missing key.\n"];
        for (NSDictionary *interruption in trial[@"interruptions"]) {
            [text appendFormat:@"  Interruption: %@ at %@ ms\n", interruption[@"reason"], interruption[@"elapsed_ms"]];
        }
        for (NSDictionary *record in trial[@"events"]) {
            NSData *line = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:NULL];
            if (line) [text appendFormat:@"  %@\n", [[NSString alloc] initWithData:line encoding:NSUTF8StringEncoding]];
        }
    }
    NSString *textPath = [directory stringByAppendingPathComponent:@"events.txt"];
    return [[NSFileManager defaultManager] createFileAtPath:textPath
        contents:[text dataUsingEncoding:NSUTF8StringEncoding] attributes:@{NSFilePosixPermissions: @0600}];
}

static int SelfTest(void) {
    // Pure decoder tests: no event tap, synthetic event posting, permission request, or device queries.
    for (unsigned short code = 0; code < 256; code++) {
        BOOL expected = FunctionName(code) != nil;
        if ((DecodeKey(kCGEventKeyDown, code, 0, NO, NO) != nil) != expected) return 1;
        if ((DecodeKey(kCGEventKeyUp, code, kCGEventFlagMaskSecondaryFn, NO, NO) != nil) != expected) return 1;
        if (DecodeKey(kCGEventKeyDown, code, kCGEventFlagMaskCommand, NO, NO) && !expected) return 1;
    }
    if (!DecodeKey(kCGEventKeyDown, 15, kCGEventFlagMaskCommand, NO, 5)) return 1;
    if (!DecodeKey(kCGEventKeyDown, 15, kCGEventFlagMaskControl, NO, 5)) return 1;
    if (DecodeKey(kCGEventKeyDown, 15, 0, NO, 5)) return 1;
    if (DecodeKey(kCGEventKeyDown, 15, kCGEventFlagMaskCommand | kCGEventFlagMaskShift, NO, 5)) return 1;
    if (DecodeKey(kCGEventKeyDown, 37, kCGEventFlagMaskCommand, NO, 5)) return 1;
    if (![DecodeKey(kCGEventKeyDown, 37, kCGEventFlagMaskCommand, NO, 9)[@"shortcut"] isEqual:@"command_l"]) return 1;
    if (![DecodeKey(kCGEventKeyUp, 35, kCGEventFlagMaskCommand, NO, 10)[@"shortcut"] isEqual:@"command_p"]) return 1;
    for (NSUInteger trialKey = 0; trialKey <= 12; trialKey++) {
        if ((DecodeKey(kCGEventKeyDown, 37, kCGEventFlagMaskCommand, NO, trialKey) != nil) != (trialKey == 9)) return 1;
        if ((DecodeKey(kCGEventKeyDown, 35, kCGEventFlagMaskCommand, NO, trialKey) != nil) != (trialKey == 10)) return 1;
        if (DecodeKey(kCGEventKeyDown, 37, kCGEventFlagMaskControl, NO, trialKey)) return 1;
        if (DecodeKey(kCGEventKeyDown, 35, kCGEventFlagMaskCommand | kCGEventFlagMaskAlternate, NO, trialKey)) return 1;
        if (DecodeKey(kCGEventKeyDown, 0, kCGEventFlagMaskCommand, NO, trialKey)) return 1;
    }
    if (!DecodeKey(kCGEventFlagsChanged, 63, kCGEventFlagMaskSecondaryFn, NO, NO)) return 1;
    if (DecodeKey(kCGEventFlagsChanged, 0, 0, NO, NO)) return 1;
    NSDictionary *media = DecodeMedia(8, (7U << 16) | (0x0aU << 8) | 1U, kCGEventFlagMaskSecondaryFn);
    if (!media || ![media[@"media_key_code"] isEqual:@7] || ![media[@"state"] isEqual:@"down"] ||
        ![media[@"repeat"] boolValue] || DecodeMedia(7, 0, 0)) return 1;
    if (![ModifierNames(kCGEventFlagMaskCommand | kCGEventFlagMaskSecondaryFn)
          isEqual:@[@"command", @"secondary_fn_flag"]]) return 1;
    NSData *data = [NSJSONSerialization dataWithJSONObject:@[media] options:0 error:NULL];
    NSString *serialized = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    if (!serialized || [serialized containsString:@"characters"] || [serialized containsString:@"data2"]) return 1;
    NSDictionary *fixture = @{
        @"36": @{@"enabled": @YES, @"value": @{@"parameters": @[@65535, @103, @8388608]}},
        @"37": @{@"enabled": @0, @"value": @{@"parameters": @[@65535, @111, @0]}},
        @"38": @{@"enabled": @YES, @"value": @{@"parameters": @[@97, @0, @0]}},
        @"39": @{@"enabled": @YES, @"value": @{@"parameters": @[@65535, @103]}},
        @"40": @{@"enabled": @YES, @"value": @{@"parameters": @[@65535, @103, @1.5]}},
        @"private_text": @{@"enabled": @YES, @"value": @{@"parameters": @[@65535, @103, @0]}},
        @"41": @{@"enabled": @"personal_text", @"value": @{@"parameters": @[@65535, @103, @0]}}
    };
    NSDictionary *filtered = FilterSymbolicHotKeys(fixture);
    NSArray *bindings = filtered[@"bindings"];
    if (bindings.count != 2 || ![bindings[0][@"id"] isEqual:@36] ||
        ![bindings[0][@"function_key"] isEqual:@"F11"] || ![bindings[0][@"enabled"] boolValue] ||
        ![bindings[1][@"function_key"] isEqual:@"F12"] || [bindings[1][@"enabled"] boolValue] ||
        ![filtered[@"malformed_entries_ignored"] isEqual:@4]) return 1;
    if (![FilterSymbolicHotKeys(nil)[@"status"] isEqual:@"MISSING_OR_UNAVAILABLE"] ||
        ![FilterSymbolicHotKeys(@[])[@"status"] isEqual:@"UNEXPECTED_VALUE_TYPE"]) return 1;
    data = [NSJSONSerialization dataWithJSONObject:filtered options:0 error:NULL];
    serialized = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    if ([serialized containsString:@"65535"] || [serialized containsString:@"private_text"] ||
        [serialized containsString:@"personal_text"] || [serialized containsString:@"parameters"]) return 1;
    CaptureState *capture = [CaptureState new];
    capture.interruptions = [NSMutableArray array];
    capture.started = 10.0;
    RecordTapInterruption(capture, kCGEventTapDisabledByUserInput, 10.1);
    if (capture.tapInterrupted || capture.interruptions.count != 0) return 1;
    capture.active = YES;
    RecordTapInterruption(capture, kCGEventTapDisabledByTimeout, 10.2);
    RecordTapInterruption(capture, kCGEventTapDisabledByUserInput, 10.3);
    if (!capture.tapInterrupted || capture.interruptions.count != 2 ||
        ![capture.interruptions[0][@"reason"] isEqual:@"timeout"] ||
        ![capture.interruptions[1][@"reason"] isEqual:@"user_disabled"]) return 1;
    capture.active = NO;
    capture.events = [NSMutableArray array];
    // Exercise the callback's early privacy guard without creating any event or event tap.
    if (ListenCallback(NULL, kCGEventKeyDown, NULL, (__bridge void *)capture) != NULL ||
        capture.events.count != 0) return 1;
    NSArray *targeted = RequestedTrials(YES);
    if (targeted.count != 7 || RequestedTrials(NO).count != 24 ||
        ![targeted[0][@"key"] isEqual:@4] || ![targeted[5][@"key"] isEqual:@10] ||
        ![targeted[6][@"key"] isEqual:@5] || ![targeted[6][@"fn_layer"] boolValue]) return 1;
    puts("Function-key decoder and privacy self-test passed.");
    return 0;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 2 && strcmp(argv[1], "--self-test") == 0) return SelfTest();
        BOOL targeted = argc == 4 && strcmp(argv[1], "--targeted") == 0 && strcmp(argv[2], "--output") == 0;
        int outputIndex = targeted ? 3 : 2;
        if (!targeted && (argc != 3 || strcmp(argv[1], "--output") != 0)) {
            fputs("Usage: function-key-events [--targeted] --output EXISTING_PRIVATE_DIRECTORY\n", stderr);
            return 64;
        }
        if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO)) {
            fputs("Run the probe interactively in Terminal. No report was written.\n", stderr);
            return 64;
        }
        NSString *directory = [[NSFileManager defaultManager] stringWithFileSystemRepresentation:argv[outputIndex]
                                                                                         length:strlen(argv[outputIndex])];
        struct stat metadata;
        if (!directory || lstat(argv[outputIndex], &metadata) != 0 || !S_ISDIR(metadata.st_mode) ||
            metadata.st_uid != getuid() || (metadata.st_mode & 077) != 0) {
            fputs("The output must be an existing private directory owned by the current user.\n", stderr);
            return 73;
        }
        for (NSString *file in @[@"events.json", @"events.txt"]) {
            NSString *path = [directory stringByAppendingPathComponent:file];
            if ([[NSFileManager defaultManager] fileExistsAtPath:path]) {
                fputs("The output directory already contains a report. No files were overwritten.\n", stderr);
                return 73;
            }
        }
        if (!CGPreflightListenEventAccess()) {
            CGRequestListenEventAccess();
            fputs("Input Monitoring permission is required.\n"
                  "Open System Settings > Privacy & Security > Input Monitoring.\n"
                  "Enable the requested Terminal/probe entry, then quit and reopen Terminal and rerun this command.\n"
                  "Accessibility permission is not requested. No report was written.\n", stderr);
            return 77;
        }
        NSArray<NSDictionary *> *requested = RequestedTrials(targeted);
        printf("Function-key event probe: %lu short, intentional tests.\n", (unsigned long)requested.count);
        puts("Save your work first. The real keys keep their current actions.\n"
             "F7 can change connectivity; F8 can affect the camera; F9 can lock the screen.\n"
             "After a lock, unlock normally and return to Terminal. Close any dialog before the next test.\n"
             "Do not type passwords or other text during a capture window.\n"
             "Press only the requested key once after CAPTURE appears, then release it.\n"
             "The probe does not change keyboard shortcuts, EFI, or any driver.\n");
        NSMutableArray *trials = [NSMutableArray array];
        BOOL stopped = NO;
        NSString *stopReason = @"none";
        for (NSUInteger index = 0; index < requested.count; index++) {
            NSUInteger key = [requested[index][@"key"] unsignedIntegerValue];
            BOOL fnLayer = [requested[index][@"fn_layer"] boolValue];
            NSString *label = fnLayer ? [NSString stringWithFormat:@"Fn+F%lu", (unsigned long)key]
                                     : [NSString stringWithFormat:@"F%lu direct", (unsigned long)key];
            printf("\n[%lu/%lu] %s. Press ENTER when ready.\n", (unsigned long)index + 1,
                   (unsigned long)requested.count, label.UTF8String);
            fflush(stdout);
            if (!WaitForEnter()) { stopped = YES; stopReason = @"stdin_closed"; break; }

            // A new tap is created only after the user starts this trial. Never manually disable a tap:
            // disabled notifications can otherwise stay queued and contaminate the next trial.
            CaptureState *capture = [CaptureState new];
            capture.directKey = fnLayer ? 0 : key;
            capture.events = [NSMutableArray array];
            capture.interruptions = [NSMutableArray array];
            CGEventMask mask = CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp) |
                               CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(SystemDefinedType);
            CFMachPortRef tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap,
                kCGEventTapOptionListenOnly, mask, ListenCallback, (__bridge void *)capture);
            if (!tap) {
                fputs("The passive event tap could not start. Check Input Monitoring and rerun from Terminal.\n", stderr);
                stopped = YES; stopReason = @"event_tap_creation_failed"; break;
            }
            CFRunLoopSourceRef source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0);
            if (!source) {
                CFMachPortInvalidate(tap); CFRelease(tap);
                stopped = YES; stopReason = @"run_loop_source_creation_failed"; break;
            }
            CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopDefaultMode);
            printf("CAPTURE: press and release %s now (3 seconds).\n", label.UTF8String);
            fflush(stdout);
            capture.started = MonotonicTime();
            capture.active = YES;
            double deadline = capture.started + CaptureSeconds;
            while (MonotonicTime() < deadline) {
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, MAX(0, MIN(0.05, deadline - MonotonicTime())), true);
            }
            capture.active = NO;
            CFRunLoopRemoveSource(CFRunLoopGetCurrent(), source, kCFRunLoopDefaultMode);
            CFMachPortInvalidate(tap);
            CFRelease(source);
            CFRelease(tap);
            tcflush(STDIN_FILENO, TCIFLUSH); // Discard terminal input generated by the intentional key.
            NSUInteger keyEvents = 0;
            for (NSDictionary *event in capture.events) if (![event[@"kind"] isEqual:@"modifier_change"]) keyEvents++;
            NSString *status = capture.tapInterrupted ? @"CAPTURE INTERRUPTED" :
                               keyEvents ? @"MATCHING KEY EVENT" : @"NO MATCHING KEY EVENT";
            [trials addObject:@{@"number": @(index + 1), @"label": label,
                @"requested_function_key": [NSString stringWithFormat:@"F%lu", (unsigned long)key],
                @"user_requested_fn_layer": @(fnLayer), @"window_seconds": @(CaptureSeconds),
                @"status": status, @"tap_interrupted": @(capture.tapInterrupted),
                @"matching_key_event_count": @(keyEvents), @"interruptions": [capture.interruptions copy],
                @"event_limit_reached": @(capture.overflow), @"events": [capture.events copy]}];
            printf("%s (%lu matching key events)\n", status.UTF8String, (unsigned long)keyEvents);
        }
        NSDictionary *report = @{@"schema": @"s540-function-key-events-v1", @"probe_version": @"1.1.0",
            @"capture_mode": @"session_listen_only", @"trial_mode": targeted ? @"targeted" : @"full",
            @"requested_trial_count": @(requested.count), @"stop_reason": stopReason,
            @"completed": @(!stopped && trials.count == requested.count),
            @"privacy": @{@"typed_text_recorded": @NO, @"personal_paths_recorded": @NO,
                           @"device_identity_recorded": @NO, @"background_installation": @NO},
            @"limitations": @[@"The secondary_fn_flag does not establish physical Fn state.",
                @"No matching event does not establish that firmware or ACPI produced no event.",
                @"Secure Input, lock transitions, permission limits, and routing can hide events.",
                @"Only F1-F20, modifier changes, AUX_CONTROL_BUTTONS, direct-F5 Command/Control+R, direct-F9 Command+L, and direct-F10 Command+P are retained."],
            @"audio_input_capabilities": InputAudioCapabilities(),
            @"existing_symbolic_hotkeys": ExistingSymbolicHotKeys(), @"trials": trials};
        if (!WriteReport(report, directory)) { fputs("The report could not be saved.\n", stderr); return 74; }
        puts("Report saved. The passive event tap is closed.");
        if (stopped) puts("Collection ended early. The report contains only completed trials.");
        return 0;
    }
}
