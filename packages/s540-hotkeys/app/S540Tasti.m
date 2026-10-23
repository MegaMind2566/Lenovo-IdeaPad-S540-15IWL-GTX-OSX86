// SPDX-License-Identifier: MIT
// Numeric Lenovo hotkey events only. No audio capture or general keyboard logging.
#import <Cocoa/Cocoa.h>
#import <QuartzCore/QuartzCore.h>
#import <CoreAudio/CoreAudio.h>
#import <CoreWLAN/CoreWLAN.h>
#import <IOBluetooth/IOBluetooth.h>
#import <IOKit/IOKitLib.h>
#import <ApplicationServices/ApplicationServices.h>
#include <dispatch/dispatch.h>
#include <dlfcn.h>
#include <mach/mach_time.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include "HotkeyPolicy.h"

static NSString *const AppVersion = @"0.1.2";
static NSString *const DriverVersion = @"0.1.0";
static NSString *const DriverClass = @"S540HotkeysVPC";
static NSString *const DriverBundle = @"org.s540.HotkeysVPC";
static const uint32_t ExpectedCFG = 0xFE0D0014;
static atomic_bool CancelActions;
static atomic_bool Terminating;
static atomic_uint_fast64_t LifecycleEpoch;
static atomic_uint_fast64_t LockPreferenceEpoch;
static BOOL ActionsCancelled(void) { return atomic_load(&CancelActions) || atomic_load(&Terminating); }
static uint64_t NowNs(void) {
    static mach_timebase_info_data_t scale;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ mach_timebase_info(&scale); });
    return (uint64_t)((long double)mach_absolute_time() * scale.numer / scale.denom);
}
static BOOL Unsigned(id value, uint64_t *result) {
    if (!value || CFGetTypeID((__bridge CFTypeRef)value) != CFNumberGetTypeID() ||
        CFNumberIsFloatType((__bridge CFNumberRef)value) || [value longLongValue] < 0) return NO;
    *result = [value unsignedLongLongValue];
    return YES;
}
// IOKit decodes OSNumber32 as CFNumberSInt32, including high-bit bit patterns.
// Only fields whose driver contract is uint32 may use this reinterpretation.
static BOOL UInt32Bits(id value, uint32_t *result) {
    if (!value || CFGetTypeID((__bridge CFTypeRef)value) != CFNumberGetTypeID() ||
        CFNumberIsFloatType((__bridge CFNumberRef)value)) return NO;
    // NSNumber's unsigned bridge may convert UINT64_MAX to signed -1. Bound
    // the mathematical value before asking for any signed scalar conversion.
    NSNumber *number = value;
    if ([number compare:@(INT32_MIN)] == NSOrderedAscending ||
        [number compare:@(UINT32_MAX)] == NSOrderedDescending) return NO;
    int64_t signedValue = 0;
    if (!CFNumberGetValue((__bridge CFNumberRef)value, kCFNumberSInt64Type, &signedValue) ||
        signedValue < INT32_MIN || signedValue > UINT32_MAX) return NO;
    *result = (uint32_t)signedValue;
    return YES;
}
static BOOL IsBoolean(id value) {
    return value && CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID();
}
static BOOL LockKeysEnabled(void) {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    if ([defaults objectForKey:@"EnableF9"] != nil) return [defaults boolForKey:@"EnableF9"];
    return [defaults boolForKey:@"EnableFnF9"] || [defaults boolForKey:@"EnableLockKeys"];
}
static void MigrateLockPreference(void) {
    NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
    if ([defaults objectForKey:@"EnableF9"] == nil) [defaults setBool:LockKeysEnabled() forKey:@"EnableF9"];
    [defaults removeObjectForKey:@"EnableFnF9"];
    [defaults removeObjectForKey:@"EnableLockKeys"];
}
static NSString *PrivateDirectory(void) {
    return [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/S540Tasti"];
}
static NSDictionary *ReadPrivateDictionary(NSString *name) {
    NSURL *url = [NSURL fileURLWithPath:[PrivateDirectory() stringByAppendingPathComponent:name]];
    return [NSDictionary dictionaryWithContentsOfURL:url error:NULL];
}
static BOOL WritePrivateDictionary(NSDictionary *dictionary, NSString *name) {
    NSData *data = [NSPropertyListSerialization dataWithPropertyList:dictionary
        format:NSPropertyListBinaryFormat_v1_0 options:0 error:NULL];
    NSURL *url = [NSURL fileURLWithPath:[PrivateDirectory() stringByAppendingPathComponent:name]];
    return data && [data writeToURL:url options:NSDataWritingAtomic error:NULL];
}
static BOOL PrepareDirectory(void) {
    NSString *path = PrivateDirectory();
    if (![[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES
            attributes:@{NSFilePosixPermissions:@0700} error:NULL]) return NO;
    struct stat info;
    return lstat(path.fileSystemRepresentation, &info) == 0 && S_ISDIR(info.st_mode) &&
        info.st_uid == getuid() && (info.st_mode & 0077) == 0;
}
static NSString *DriverContractFailure(NSDictionary *snapshot) {
    uint64_t schema = 0, sequence = 0; uint32_t cfg = 0;
    if (!Unsigned(snapshot[@"Schema"], &schema) || schema != 1) return @"driver-contract-Schema-invalid";
    if (!UInt32Bits(snapshot[@"CFG"], &cfg)) return @"driver-contract-CFG-type-invalid";
    if (cfg != ExpectedCFG) return @"driver-contract-CFG-mismatch";
    if (!Unsigned(snapshot[@"EventSequence"], &sequence)) return @"driver-contract-EventSequence-invalid";
    if (![snapshot[@"Version"] isEqual:DriverVersion]) return @"driver-contract-Version-mismatch";
    if (!IsBoolean(snapshot[@"Ready"])) return @"driver-contract-Ready-invalid";
    if (!IsBoolean(snapshot[@"Awake"])) return @"driver-contract-Awake-invalid";
    if (![snapshot[@"State"] isKindOfClass:[NSString class]] ||
        ![@[@"Ready", @"Fault", @"Stopping"] containsObject:snapshot[@"State"]]) return @"driver-contract-State-invalid";
    if (![snapshot[@"EventRing"] isKindOfClass:[NSArray class]]) return @"driver-contract-EventRing-invalid";
    return nil;
}
static NSDictionary *DriverSnapshot(uint64_t *registryID, NSString **failure) {
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching(DriverClass.UTF8String), &iterator)) {
        *failure = @"driver-search-failed"; return nil;
    }
    io_service_t service = IOIteratorNext(iterator), other = IOIteratorNext(iterator);
    IOObjectRelease(iterator);
    if (!service || other) {
        if (service) IOObjectRelease(service);
        if (other) IOObjectRelease(other);
        *failure = other ? @"multiple-drivers" : @"driver-not-loaded"; return nil;
    }
    CFTypeRef bundle = IORegistryEntryCreateCFProperty(service, CFSTR("CFBundleIdentifier"), kCFAllocatorDefault, 0);
    BOOL identity = bundle && CFGetTypeID(bundle) == CFStringGetTypeID() &&
        [(__bridge NSString *)bundle isEqual:DriverBundle];
    if (bundle) CFRelease(bundle);
    CFTypeRef raw = identity ? IORegistryEntryCreateCFProperty(service, CFSTR("Snapshot"), kCFAllocatorDefault, 0) : NULL;
    uint64_t identifier = 0;
    kern_return_t foundID = IORegistryEntryGetRegistryEntryID(service, &identifier);
    IOObjectRelease(service);
    if (!identity || foundID || !identifier || !raw || CFGetTypeID(raw) != CFDictionaryGetTypeID()) {
        if (raw) CFRelease(raw);
        *failure = @"driver-identity-or-snapshot-invalid"; return nil;
    }
    NSDictionary *snapshot = CFBridgingRelease(raw);
    *failure = DriverContractFailure(snapshot);
    if (*failure) return nil;
    *registryID = identifier;
    return snapshot;
}
static BOOL ReadDefaultInput(AudioDeviceID *device) {
    AudioObjectPropertyAddress address = {kAudioHardwarePropertyDefaultInputDevice,
        kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    UInt32 bytes = sizeof(*device);
    return AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, NULL, &bytes, device) == noErr &&
        bytes == sizeof(*device) && *device != kAudioObjectUnknown;
}
static BOOL ReadMute(AudioDeviceID device, UInt32 *mute, BOOL *writable) {
    AudioObjectPropertyAddress address = {kAudioDevicePropertyMute,
        kAudioDevicePropertyScopeInput, kAudioObjectPropertyElementMain};
    if (!AudioObjectHasProperty(device, &address)) return NO;
    Boolean settable = false; UInt32 bytes = sizeof(*mute);
    if (AudioObjectIsPropertySettable(device, &address, &settable) != noErr ||
        AudioObjectGetPropertyData(device, &address, 0, NULL, &bytes, mute) != noErr ||
        bytes != sizeof(*mute) || *mute > 1) return NO;
    *writable = settable; return YES;
}
typedef NS_ENUM(NSInteger, HKFeedbackOutcome) { HKFeedbackError, HKFeedbackConfirmed, HKFeedbackRequest };
static NSDictionary *Feedback(HKFeedbackOutcome outcome, NSString *message, NSString *brief, NSString *symbol) {
    return @{@"outcome":@(outcome), @"message":message, @"brief":brief, @"symbol":symbol};
}
static NSDictionary *LockFeedback(HKFeedbackOutcome outcome, NSString *message, NSString *brief, uint64_t epoch) {
    NSMutableDictionary *feedback = [Feedback(outcome, message, brief, @"lock.fill") mutableCopy];
    feedback[@"lock_epoch"] = @(epoch); // Authorization belongs to the original key, not the display time.
    return feedback;
}
static NSDictionary *ToggleMicrophone(void) {
    if (ActionsCancelled()) return Feedback(HKFeedbackError, @"Microfono: operazione annullata", @"Operazione annullata", @"mic.slash.fill");
    AudioDeviceID device = kAudioObjectUnknown, current = kAudioObjectUnknown;
    UInt32 before = 0; BOOL writable = NO;
    if (!ReadDefaultInput(&device) || !ReadMute(device, &before, &writable) || !writable)
        return Feedback(HKFeedbackError, @"Microfono: controllo mute non disponibile", @"Mute microfono non disponibile", @"mic.slash.fill");
    if (!ReadDefaultInput(&current) || current != device)
        return Feedback(HKFeedbackError, @"Microfono: ingresso cambiato, ripremi F4", @"Ingresso microfono cambiato", @"mic.fill");
    AudioObjectPropertyAddress address = {kAudioDevicePropertyMute,
        kAudioDevicePropertyScopeInput, kAudioObjectPropertyElementMain};
    UInt32 desired = !before, actual = before;
    if (ActionsCancelled()) return Feedback(HKFeedbackError, @"Microfono: operazione annullata", @"Operazione annullata", @"mic.slash.fill");
    if (AudioObjectSetPropertyData(device, &address, 0, NULL, sizeof(desired), &desired) != noErr ||
        !ReadMute(device, &actual, &writable) || actual != desired)
        return Feedback(HKFeedbackError, @"Microfono: modifica non confermata", @"Mute non confermato", @"mic.slash.fill");
    if (!ReadDefaultInput(&current) || current != device)
        return Feedback(HKFeedbackError, @"Microfono: ingresso cambiato dopo F4", @"Ingresso microfono cambiato", @"mic.fill");
    return desired ? Feedback(HKFeedbackConfirmed, @"Microfono disattivato", @"Microfono disattivato", @"mic.slash.fill") :
        Feedback(HKFeedbackConfirmed, @"Microfono attivo", @"Microfono attivo", @"mic.fill");
}
typedef void (*BluetoothSetter)(int);
static BluetoothSetter BluetoothPowerSetter(void) {
    static BluetoothSetter setter;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ setter = (BluetoothSetter)dlsym(RTLD_DEFAULT, "IOBluetoothPreferenceSetControllerPowerState"); });
    return setter;
}
static BOOL BluetoothPower(BOOL *power) {
    IOBluetoothHostController *controller = [IOBluetoothHostController defaultController];
    if (!controller) return NO;
    BluetoothHCIPowerState actual = controller.powerState;
    if (actual != 0 && actual != 1) return NO;
    *power = actual == 1; return YES;
}
static BOOL SetBluetooth(BOOL desired, BOOL recovering, BOOL *uncertain) {
    *uncertain = NO;
    if (!recovering && ActionsCancelled()) return NO;
    BluetoothSetter setter = BluetoothPowerSetter(); BOOL before = NO;
    if (!setter || !BluetoothPower(&before)) return NO;
    if (before == desired) return YES;
    *uncertain = YES;
    setter(desired ? 1 : 0);
    for (unsigned i = 0; i < 50; i++) {
        BOOL actual = NO;
        if (BluetoothPower(&actual) && actual == desired) {
            *uncertain = NO;
            return recovering || !ActionsCancelled();
        }
        usleep(100000);
    }
    return NO;
}
static BOOL SetWiFi(CWInterface *interface, BOOL desired, BOOL recovering, BOOL *uncertain) {
    *uncertain = NO;
    if (!recovering && ActionsCancelled()) return NO;
    if (interface.powerOn == desired) return YES;
    NSError *error = nil;
    *uncertain = YES;
    if (![interface setPower:desired error:&error]) return NO;
    for (unsigned i = 0; i < 30; i++) {
        if (interface.powerOn == desired) {
            *uncertain = NO;
            return recovering || !ActionsCancelled();
        }
        usleep(100000);
    }
    return NO;
}
static BOOL ReadRadios(CWInterface **interfaceOut, HKRadioState *state) {
    CWInterface *interface = [[CWWiFiClient sharedWiFiClient] interface]; BOOL bluetooth = NO;
    if (!interface || !interface.interfaceName.length || !BluetoothPower(&bluetooth) || !BluetoothPowerSetter()) return NO;
    *interfaceOut = interface;
    *state = (HKRadioState){interface.powerOn, bluetooth}; return YES;
}
static HKRadioState LoadSavedRadios(BOOL *valid) {
    NSDictionary *saved = ReadPrivateDictionary(@"radio-snapshot.plist");
    *valid = IsBoolean(saved[@"WiFi"]) && IsBoolean(saved[@"Bluetooth"]);
    if (!*valid) return (HKRadioState){false, false};
    return (HKRadioState){[saved[@"WiFi"] boolValue], [saved[@"Bluetooth"] boolValue]};
}
static BOOL SaveRadios(HKRadioState state) {
    NSDictionary *snapshot = @{@"WiFi":@(state.wifi), @"Bluetooth":@(state.bluetooth)};
    return WritePrivateDictionary(snapshot, @"radio-snapshot.plist");
}
static NSDictionary *ToggleRadios(void) {
    if (ActionsCancelled()) return Feedback(HKFeedbackError, @"Radio: operazione annullata", @"Operazione annullata", @"airplane");
    CWInterface *interface = nil; HKRadioState before;
    if (!ReadRadios(&interface, &before)) return Feedback(HKFeedbackError, @"Radio: Wi-Fi o Bluetooth non controllabile", @"Controllo radio non disponibile", @"airplane");
    BOOL hasSaved = NO; HKRadioState saved = LoadSavedRadios(&hasSaved);
    HKRadioState target = HKRadioTarget(before, hasSaved, saved);
    // Save the user's original mix before switching both radios off.
    if ((before.wifi || before.bluetooth) && !SaveRadios(before))
        return Feedback(HKFeedbackError, @"Radio: impossibile salvare lo stato precedente, nessuna modifica", @"Radio non modificate", @"airplane");
    BOOL btChanged = before.bluetooth != target.bluetooth;
    BOOL wifiChanged = before.wifi != target.wifi;
    BOOL uncertainBT = NO, uncertainWiFi = NO;
    BOOL btOK = SetBluetooth(target.bluetooth, NO, &uncertainBT);
    BOOL wifiOK = btOK && !ActionsCancelled() && SetWiFi(interface, target.wifi, NO, &uncertainWiFi);
    CWInterface *afterInterface = nil; HKRadioState after;
    BOOL confirmed = wifiOK && !ActionsCancelled() && ReadRadios(&afterInterface, &after) &&
        [afterInterface.interfaceName isEqual:interface.interfaceName] && HKRadioEqual(after, target);
    if (!confirmed) {
        // Restore only changes belonging to this attempt, and only from the requested target state.
        BOOL rollbackAttempted = NO;
        if (wifiChanged && interface.powerOn == target.wifi) {
            rollbackAttempted = YES;
            BOOL pending = NO;
            BOOL recovered = SetWiFi(interface, before.wifi, YES, &pending);
            uncertainWiFi = !recovered || pending;
        }
        BOOL btActual = NO;
        if (btChanged && BluetoothPower(&btActual) && btActual == target.bluetooth) {
            rollbackAttempted = YES;
            BOOL pending = NO;
            BOOL recovered = SetBluetooth(before.bluetooth, YES, &pending);
            uncertainBT = !recovered || pending;
        }
        BOOL restored = !uncertainBT && !uncertainWiFi && ReadRadios(&afterInterface, &after) && HKRadioEqual(after, before);
        if (!restored) return Feedback(HKFeedbackError, @"Radio: operazione non confermata, controlla Wi-Fi e Bluetooth", @"Stato radio non confermato", @"airplane");
        return Feedback(HKFeedbackError, rollbackAttempted ? @"Radio: operazione interrotta, stato precedente ripristinato" : @"Radio: operazione interrotta, stato precedente confermato",
            @"Radio nello stato precedente", @"antenna.radiowaves.left.and.right");
    }
    if (!target.wifi && !target.bluetooth) return Feedback(HKFeedbackConfirmed, @"Modalità aereo: Wi-Fi e Bluetooth spenti", @"Wi-Fi e Bluetooth spenti", @"airplane");
    NSString *message = target.wifi && target.bluetooth ? @"Wi-Fi e Bluetooth attivi" : target.wifi ? @"Wi-Fi attivo; Bluetooth spento" : @"Bluetooth attivo; Wi-Fi spento";
    return Feedback(HKFeedbackConfirmed, message, message, target.wifi ? @"wifi" : @"antenna.radiowaves.left.and.right");
}
static NSString *CameraStatus(NSDictionary *snapshot) {
    uint64_t result = 0; uint32_t state = UINT32_MAX;
    if (!Unsigned(snapshot[@"LastCameraResult"], &result) || !UInt32Bits(snapshot[@"CameraState"], &state)) return @"Webcam: stato non disponibile";
    if (result == 0) return @"Webcam: pronta per F8";
    if (result == 1) return @"Webcam: comando non supportato dal firmware";
    if (result == 2 || result == 3 || result == 7) {
        if (state == 0) return @"Webcam disattivata: stato firmware confermato";
        if (state == 1) return @"Webcam attiva: stato firmware confermato";
    }
    return @"Webcam: modifica non confermata dal firmware";
}
static NSDictionary *CameraFeedback(NSDictionary *snapshot) {
    uint64_t result = 0; uint32_t state = UINT32_MAX;
    if (!Unsigned(snapshot[@"LastCameraResult"], &result) || !UInt32Bits(snapshot[@"CameraState"], &state))
        return Feedback(HKFeedbackError, @"Webcam: stato non disponibile", @"Stato webcam non disponibile", @"camera.slash.fill");
    if (result == 0 || result == 3) return nil; // Baseline or no new confirmed action.
    if ((result == 2 || result == 7) && state <= 1)
        return Feedback(HKFeedbackConfirmed, CameraStatus(snapshot), state ? @"Webcam attiva · firmware" : @"Webcam disattivata · firmware",
            state ? @"camera.fill" : @"camera.slash.fill");
    return Feedback(HKFeedbackError, CameraStatus(snapshot), result == 1 ? @"Comando webcam non supportato" : @"Webcam: modifica non confermata", @"camera.slash.fill");
}
static BOOL PostLockRequest(void) {
    if (!AXIsProcessTrusted()) return NO;
    CGEventRef down = CGEventCreateKeyboardEvent(NULL, (CGKeyCode)12, true);
    CGEventRef up = CGEventCreateKeyboardEvent(NULL, (CGKeyCode)12, false);
    if (!down || !up) { if (down) CFRelease(down); if (up) CFRelease(up); return NO; }
    CGEventFlags flags = kCGEventFlagMaskControl | kCGEventFlagMaskCommand;
    CGEventSetFlags(down, flags); CGEventSetFlags(up, flags);
    CGEventPost(kCGHIDEventTap, down); CGEventPost(kCGHIDEventTap, up);
    CFRelease(down); CFRelease(up); return YES;
}

@interface S540FeedbackPanel : NSPanel
@end
@implementation S540FeedbackPanel
- (BOOL)canBecomeKeyWindow { return NO; }
- (BOOL)canBecomeMainWindow { return NO; }
@end

@interface S540Delegate : NSObject <NSApplicationDelegate> {
    NSStatusItem *_item;
    S540FeedbackPanel *_hudPanel;
    NSImageView *_hudIcon;
    NSTextField *_hudLabel;
    uint64_t _hudToken;
    NSMenuItem *_driverItem, *_micItem, *_radioItem, *_cameraItem, *_lockItem;
    dispatch_queue_t _actions;
    dispatch_source_t _timer, _termSignal;
    NSMutableDictionary *_featureStatus;
    uint64_t _registryID, _sequence, _lastF4, _lastF7, _lastF9;
    bool _seenF4, _seenF7, _seenF9;
    BOOL _baselineNeeded, _suspended, _stopping;
    CFMachPortRef _lockTap;
    CFRunLoopSourceRef _lockTapSource;
    uint64_t _tapBaselineNs;
    bool _lockLDown;
    int _lockFD;
}
- (void)updateFeature:(NSString *)feature text:(NSString *)text;
- (void)applyFeedback:(NSDictionary *)feedback feature:(NSString *)feature;
- (void)showFeedback:(NSDictionary *)feedback;
- (void)dismissFeedback;
- (void)refreshLockTap;
- (void)closeLockTap;
- (CGEventRef)handleLockEvent:(CGEventRef)event type:(CGEventType)type;
@end

static CGEventRef LockTapCallback(CGEventTapProxy proxy, CGEventType type, CGEventRef event, void *context) {
    (void)proxy;
    return [(__bridge S540Delegate *)context handleLockEvent:event type:type];
}
@implementation S540Delegate
- (instancetype)init {
    self = [super init];
    if (self) _lockFD = -1;
    return self;
}
- (void)updateFeature:(NSString *)feature text:(NSString *)text {
    if ([_featureStatus[feature] isEqual:text]) return;
    _featureStatus[feature] = text;
    NSDictionary *saved = @{@"app_version":AppVersion, @"features":[_featureStatus copy], @"updated_at":[NSDate date]};
    (void)WritePrivateDictionary(saved, @"runtime.plist");
    dispatch_async(dispatch_get_main_queue(), ^{
        NSMenuItem *target = [feature isEqual:@"F4"] ? self->_micItem : [feature isEqual:@"F7"] ? self->_radioItem :
            [feature isEqual:@"F8"] ? self->_cameraItem : [feature isEqual:@"F9"] ? self->_lockItem : self->_driverItem;
        target.title = text;
        self->_item.button.toolTip = [NSString stringWithFormat:@"S540 Tasti — %@", text];
    });
}
- (void)dismissFeedback {
    // Called on the main queue; invalidates timers belonging to older panels.
    _hudToken++;
    [_hudPanel orderOut:nil];
}
- (void)showFeedback:(NSDictionary *)feedback {
    if (!feedback) return;
    uint64_t epoch = atomic_load(&LifecycleEpoch);
    BOOL lockRelated = feedback[@"lock_epoch"] != nil;
    uint64_t preferenceEpoch = lockRelated ? [feedback[@"lock_epoch"] unsignedLongLongValue] : atomic_load(&LockPreferenceEpoch);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (ActionsCancelled() || atomic_load(&LifecycleEpoch) != epoch ||
            atomic_load(&LockPreferenceEpoch) != preferenceEpoch || (lockRelated && !LockKeysEnabled())) return;
        if (!self->_hudPanel) {
            NSRect bounds = NSMakeRect(0, 0, 308, 86);
            self->_hudPanel = [[S540FeedbackPanel alloc] initWithContentRect:bounds
                styleMask:NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
                backing:NSBackingStoreBuffered defer:NO];
            self->_hudPanel.opaque = NO;
            self->_hudPanel.backgroundColor = NSColor.clearColor;
            self->_hudPanel.hasShadow = YES;
            self->_hudPanel.hidesOnDeactivate = NO;
            self->_hudPanel.ignoresMouseEvents = YES;
            self->_hudPanel.level = NSStatusWindowLevel;
            self->_hudPanel.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces |
                NSWindowCollectionBehaviorFullScreenAuxiliary | NSWindowCollectionBehaviorTransient |
                NSWindowCollectionBehaviorIgnoresCycle;
            NSVisualEffectView *surface = [[NSVisualEffectView alloc] initWithFrame:bounds];
            surface.material = NSVisualEffectMaterialHUDWindow;
            surface.blendingMode = NSVisualEffectBlendingModeBehindWindow;
            surface.state = NSVisualEffectStateActive;
            surface.maskImage = [NSImage imageWithSize:bounds.size flipped:NO drawingHandler:^BOOL(NSRect rect) {
                [NSColor.whiteColor setFill];
                [[NSBezierPath bezierPathWithRoundedRect:rect xRadius:18 yRadius:18] fill];
                return YES;
            }];
            self->_hudIcon = [[NSImageView alloc] initWithFrame:NSMakeRect(20, 25, 36, 36)];
            self->_hudIcon.imageScaling = NSImageScaleProportionallyUpOrDown;
            self->_hudLabel = [NSTextField wrappingLabelWithString:@""];
            self->_hudLabel.frame = NSMakeRect(72, 20, 216, 46);
            self->_hudLabel.font = [NSFont systemFontOfSize:14 weight:NSFontWeightSemibold];
            self->_hudLabel.maximumNumberOfLines = 2;
            self->_hudLabel.selectable = NO;
            [surface addSubview:self->_hudIcon];
            [surface addSubview:self->_hudLabel];
            self->_hudPanel.contentView = surface;
        }
        BOOL failed = [feedback[@"outcome"] integerValue] == HKFeedbackError;
        NSString *symbol = failed ? @"exclamationmark.triangle.fill" : feedback[@"symbol"];
        NSImage *icon = [NSImage imageWithSystemSymbolName:symbol accessibilityDescription:feedback[@"brief"]];
        if (!icon) icon = [NSImage imageWithSystemSymbolName:@"keyboard" accessibilityDescription:@"Tasti rapidi"];
        self->_hudIcon.image = [icon imageWithSymbolConfiguration:
            [NSImageSymbolConfiguration configurationWithPointSize:30 weight:NSFontWeightMedium]];
        self->_hudIcon.contentTintColor = failed ? NSColor.systemOrangeColor : NSColor.labelColor;
        self->_hudLabel.stringValue = feedback[@"brief"];
        self->_hudLabel.textColor = NSColor.labelColor;
        NSScreen *screen = NSScreen.mainScreen ?: NSScreen.screens.firstObject;
        if (!screen) return;
        NSRect visible = screen.visibleFrame;
        [self->_hudPanel setFrameOrigin:NSMakePoint(NSMidX(visible) - 154,
            NSMinY(visible) + MAX(30, visible.size.height * 0.16))];
        uint64_t token = ++self->_hudToken;
        [self->_hudPanel orderFrontRegardless];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 1400 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
            if (self->_hudToken == token) [self dismissFeedback];
        });
    });
}
- (void)applyFeedback:(NSDictionary *)feedback feature:(NSString *)feature {
    if (!feedback) return;
    [self updateFeature:feature text:feedback[@"message"]];
    [self showFeedback:feedback];
}
- (void)pollDriver {
    if (_stopping || _suspended || ActionsCancelled()) return;
    NSString *failure = nil; uint64_t identifier = 0;
    NSDictionary *snapshot = DriverSnapshot(&identifier, &failure);
    if (!snapshot) {
        _baselineNeeded = YES;
        NSString *text = [failure isEqual:@"driver-not-loaded"] ? @"Driver tasti in attesa: installazione o riavvio necessario" :
            [NSString stringWithFormat:@"Driver tasti: %@", failure ?: @"driver-state-invalid"];
        if (![_featureStatus[@"Driver"] isEqual:text]) [self updateFeature:@"Driver" text:text];
        return;
    }
    if (![snapshot[@"Ready"] boolValue] || ![snapshot[@"State"] isEqual:@"Ready"]) {
        _baselineNeeded = YES;
        if (![_featureStatus[@"Driver"] isEqual:@"Driver tasti fermo: controllare installazione"])
            [self updateFeature:@"Driver" text:@"Driver tasti fermo: controllare installazione"];
        return;
    }
    if (![snapshot[@"Awake"] boolValue]) { _baselineNeeded = YES; return; }
    uint64_t current = 0; (void)Unsigned(snapshot[@"EventSequence"], &current);
    if (_baselineNeeded || identifier != _registryID) {
        _registryID = identifier; _sequence = current; _baselineNeeded = NO;
        _seenF4 = _seenF7 = false;
        [self updateFeature:@"Driver" text:@"Tasti Lenovo collegati"];
        [self updateFeature:@"F8" text:CameraStatus(snapshot)];
        return;
    }
    NSArray *ring = snapshot[@"EventRing"];
    HKEvent events[32];
    BOOL parsed = ring.count <= 32;
    for (NSUInteger index = 0; parsed && index < ring.count; index++) {
        id entry = ring[index];
        parsed = [entry isKindOfClass:[NSDictionary class]] &&
            Unsigned(entry[@"seq"], &events[index].seq) && Unsigned(entry[@"mask"], &events[index].mask) &&
            Unsigned(entry[@"time_ns"], &events[index].timeNs);
    }
    HKRingResult validation = parsed ? HKValidateRing(events, ring.count, current, _sequence) : HKRingInvalid;
    if (validation != HKRingValid) {
        _sequence = current; _seenF4 = _seenF7 = false;
        [self updateFeature:@"Driver" text:@"Eventi tasti persi: sincronizzazione ripristinata, nessuna azione arretrata"];
        return;
    }
    uint64_t previous = _sequence;
    _sequence = current; // Commit before executing actions: no retries or replays after a failure.
    for (NSUInteger index = 0; index < ring.count; index++) {
        if (ActionsCancelled()) return;
        if (events[index].seq <= previous) continue;
        uint64_t mask = events[index].mask, time = events[index].timeNs;
        if ((mask & (UINT64_C(1) << 8)) && HKDebounce(time, &_lastF4, &_seenF4)) {
            if (HKEventFresh(NowNs(), time)) [self applyFeedback:ToggleMicrophone() feature:@"F4"];
            else [self updateFeature:@"F4" text:@"F4: evento scaduto, ripremi il tasto"];
        }
        if (ActionsCancelled()) return;
        if ((mask & (UINT64_C(1) << 13)) && HKDebounce(time, &_lastF7, &_seenF7)) {
            if (HKEventFresh(NowNs(), time)) [self applyFeedback:ToggleRadios() feature:@"F7"];
            else [self updateFeature:@"F7" text:@"F7: evento scaduto, ripremi il tasto"];
        }
    }
    NSString *camera = CameraStatus(snapshot);
    if (![_featureStatus[@"F8"] isEqual:camera]) [self updateFeature:@"F8" text:camera];
    // The snapshot owns only one final camera result. Show it once for the
    // newest camera event, never once per old ring entry or baseline/poll.
    uint64_t cameraTime = 0;
    for (NSUInteger index = 0; index < ring.count; index++)
        if (events[index].seq > previous && (events[index].mask & (UINT64_C(1) << 7)))
            cameraTime = events[index].timeNs;
    if (cameraTime && HKEventFresh(NowNs(), cameraTime)) [self showFeedback:CameraFeedback(snapshot)];
}
- (CGEventRef)handleLockEvent:(CGEventRef)event type:(CGEventType)type {
    if (type == kCGEventTapDisabledByTimeout || type == kCGEventTapDisabledByUserInput) {
        _lockLDown = false; _tapBaselineNs = NowNs();
        if (_lockTap && LockKeysEnabled() && !ActionsCancelled() && CGPreflightListenEventAccess() && AXIsProcessTrusted())
            CGEventTapEnable(_lockTap, true);
        else dispatch_async(_actions, ^{ [self updateFeature:@"F9" text:@"F9 / ⌘+L: filtro sospeso, rileggi i permessi"]; });
        return event;
    }
    if (!event || (type != kCGEventKeyDown && type != kCGEventKeyUp) || !LockKeysEnabled()) return event;
    uint64_t keyCode = (uint64_t)CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode);
    if (keyCode != 37) return event;
    CGEventFlags flags = CGEventGetFlags(event);
    BOOL command = (flags & kCGEventFlagMaskCommand) != 0;
    BOOL otherModifiers = (flags & (kCGEventFlagMaskControl | kCGEventFlagMaskAlternate | kCGEventFlagMaskShift)) != 0;
    HKLockDecision decision = HKDirectLock(&_lockLDown, type == kCGEventKeyDown, type == kCGEventKeyUp,
        keyCode, command, otherModifiers, CGEventGetIntegerValueField(event, kCGKeyboardEventAutorepeat) != 0);
    if (decision == HKLockPass) return event;
    if (decision == HKLockConsume) return NULL;
    uint64_t now = CGEventGetTimestamp(event), baseline = _tapBaselineNs;
    uint64_t epoch = atomic_load(&LifecycleEpoch);
    uint64_t lockEpoch = atomic_load(&LockPreferenceEpoch);
    dispatch_async(_actions, ^{
        if (self->_stopping || self->_suspended || ActionsCancelled() || !LockKeysEnabled() || atomic_load(&LifecycleEpoch) != epoch ||
            atomic_load(&LockPreferenceEpoch) != lockEpoch ||
            !HKDebounce(now, &self->_lastF9, &self->_seenF9)) return;
        if (now < baseline || !HKEventFresh(NowNs(), now)) {
            [self updateFeature:@"F9" text:@"F9 / ⌘+L: evento scaduto, ripremi il tasto"];
            return;
        }
        [self showFeedback:LockFeedback(HKFeedbackRequest, @"Richiesta blocco schermo", @"Blocco schermo…", lockEpoch)];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 180 * NSEC_PER_MSEC), self->_actions, ^{
            if (self->_stopping || self->_suspended || ActionsCancelled() || !LockKeysEnabled() ||
                atomic_load(&LifecycleEpoch) != epoch || atomic_load(&LockPreferenceEpoch) != lockEpoch ||
                !HKEventFresh(NowNs(), now)) return;
            BOOL sent = PostLockRequest();
            [self updateFeature:@"F9" text:sent ? @"F9 / ⌘+L: richiesta blocco schermo inviata" : @"F9 / ⌘+L: consenti Accessibilità"];
            if (!sent) [self showFeedback:LockFeedback(HKFeedbackError, @"Consenti Accessibilità", @"Consenti Accessibilità per F9", lockEpoch)];
        });
    });
    return NULL;
}
- (void)closeLockTap {
    (void)atomic_fetch_add(&LockPreferenceEpoch, 1);
    _lockLDown = false;
    if (_lockTapSource) {
        CFRunLoopRemoveSource(CFRunLoopGetMain(), _lockTapSource, kCFRunLoopCommonModes);
        CFRelease(_lockTapSource); _lockTapSource = NULL;
    }
    if (_lockTap) { CFMachPortInvalidate(_lockTap); CFRelease(_lockTap); _lockTap = NULL; }
}
- (void)refreshLockTap {
    _lockLDown = false; _tapBaselineNs = NowNs();
    BOOL enabled = LockKeysEnabled();
    if (!enabled || !CGPreflightListenEventAccess() || !AXIsProcessTrusted()) {
        [self closeLockTap];
        NSString *message = enabled ? @"F9 / ⌘+L: servono Monitoraggio input e Accessibilità" : @"F9 / ⌘+L: abilitalo dal menu S540";
        dispatch_async(_actions, ^{ [self updateFeature:@"F9" text:message]; });
        return;
    }
    if (!_lockTap) {
        CGEventMask mask = CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp);
        _lockTap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionDefault,
            mask, LockTapCallback, (__bridge void *)self);
        if (_lockTap) _lockTapSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, _lockTap, 0);
        if (!_lockTap || !_lockTapSource) {
            [self closeLockTap];
            dispatch_async(_actions, ^{ [self updateFeature:@"F9" text:@"F9 / ⌘+L: filtro non disponibile, rileggi i permessi"]; });
            return;
        }
        CFRunLoopAddSource(CFRunLoopGetMain(), _lockTapSource, kCFRunLoopCommonModes);
    }
    CGEventTapEnable(_lockTap, true);
    dispatch_async(_actions, ^{ [self updateFeature:@"F9" text:@"F9 / ⌘+L: blocco schermo pronto"]; });
}
- (void)enableF9:(id)sender {
    (void)sender;
    [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"EnableF9"];
    if (!CGPreflightListenEventAccess()) (void)CGRequestListenEventAccess();
    NSDictionary *options = @{(__bridge NSString *)kAXTrustedCheckOptionPrompt:@YES};
    (void)AXIsProcessTrustedWithOptions((__bridge CFDictionaryRef)options);
    [self refreshLockTap];
}
- (void)disableF9:(id)sender {
    (void)sender;
    [[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"EnableF9"];
    [self closeLockTap];
    [self dismissFeedback];
    dispatch_async(_actions, ^{
        self->_seenF9 = false;
        [self updateFeature:@"F9" text:@"F9 / ⌘+L: disabilitato dal menu S540"];
    });
}
- (void)refreshPermissions:(id)sender { (void)sender; [self refreshLockTap]; }
- (void)quit:(id)sender { (void)sender; [NSApp terminate:nil]; }
- (void)willSleep:(NSNotification *)notification {
    (void)notification;
    (void)atomic_fetch_add(&LifecycleEpoch, 1);
    atomic_store(&CancelActions, true);
    [self dismissFeedback];
    dispatch_async(_actions, ^{ self->_suspended = YES; self->_baselineNeeded = YES; });
}
- (void)didWake:(NSNotification *)notification {
    (void)notification;
    uint64_t epoch = atomic_fetch_add(&LifecycleEpoch, 1) + 1;
    dispatch_async(_actions, ^{
        self->_suspended = NO; self->_baselineNeeded = YES; self->_seenF9 = false;
        if (atomic_load(&LifecycleEpoch) == epoch && !atomic_load(&Terminating))
            atomic_store(&CancelActions, false);
    });
    [self refreshLockTap];
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    if (!PrepareDirectory()) { [NSApp terminate:nil]; return; }
    NSString *path = [PrivateDirectory() stringByAppendingPathComponent:@"session.lock"];
    _lockFD = open(path.fileSystemRepresentation, O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    struct stat info;
    if (_lockFD < 0 || fstat(_lockFD, &info) || !S_ISREG(info.st_mode) || info.st_uid != getuid() ||
        info.st_nlink != 1 || (info.st_mode & 0077) != 0 || flock(_lockFD, LOCK_EX | LOCK_NB)) {
        if (_lockFD >= 0) close(_lockFD);
        _lockFD = -1; [NSApp terminate:nil]; return;
    }
    MigrateLockPreference();
    _actions = dispatch_queue_create("org.s540.Hotkeys.actions", DISPATCH_QUEUE_SERIAL);
    _featureStatus = [@{@"Driver":@"Collegamento tasti Lenovo…", @"F4":@"F4: microfono pronto",
        @"F7":@"F7: Wi-Fi e Bluetooth pronti", @"F8":@"F8: webcam in attesa", @"F9":@"F9 / ⌘+L: abilitalo dal menu S540"} mutableCopy];
    _item = [[NSStatusBar systemStatusBar] statusItemWithLength:NSVariableStatusItemLength];
    NSString *menuIconPath = [[NSBundle mainBundle] pathForResource:@"MenuBarIconTemplate" ofType:@"png"];
    NSImage *menuIcon = menuIconPath ? [[NSImage alloc] initWithContentsOfFile:menuIconPath] : nil;
    if (menuIcon) {
        NSString *retinaPath = [[NSBundle mainBundle] pathForResource:@"MenuBarIconTemplate@2x" ofType:@"png"];
        NSData *retinaData = retinaPath ? [NSData dataWithContentsOfFile:retinaPath] : nil;
        NSBitmapImageRep *retina = retinaData ? [NSBitmapImageRep imageRepWithData:retinaData] : nil;
        if (retina) { retina.size = NSMakeSize(20, 18); [menuIcon addRepresentation:retina]; }
    }
    if (!menuIcon) menuIcon = [NSImage imageWithSystemSymbolName:@"keyboard" accessibilityDescription:@"S540 Tasti rapidi"];
    menuIcon.size = NSMakeSize(20, 18);
    menuIcon.template = YES;
    _item.button.image = menuIcon;
    _item.button.title = @"";
    _item.button.accessibilityLabel = @"S540 Tasti rapidi";
    _item.button.toolTip = @"S540 Tasti rapidi";
    NSMenu *menu = [[NSMenu alloc] initWithTitle:@"S540 Tasti"];
    NSArray *titles = @[_featureStatus[@"Driver"],_featureStatus[@"F4"],_featureStatus[@"F7"],_featureStatus[@"F8"],_featureStatus[@"F9"]];
    NSMutableArray *items = [NSMutableArray array];
    for (NSString *title in titles) { NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:title action:NULL keyEquivalent:@""]; item.enabled = NO; [menu addItem:item]; [items addObject:item]; }
    _driverItem=items[0]; _micItem=items[1]; _radioItem=items[2]; _cameraItem=items[3]; _lockItem=items[4];
    [menu addItem:[NSMenuItem separatorItem]];
    NSMenuItem *enable = [[NSMenuItem alloc] initWithTitle:@"Abilita F9 / ⌘+L per il blocco…" action:@selector(enableF9:) keyEquivalent:@""]; enable.target=self; [menu addItem:enable];
    NSMenuItem *disable = [[NSMenuItem alloc] initWithTitle:@"Disabilita F9 / ⌘+L per il blocco" action:@selector(disableF9:) keyEquivalent:@""]; disable.target=self; [menu addItem:disable];
    NSMenuItem *refresh = [[NSMenuItem alloc] initWithTitle:@"Rileggi permessi F9" action:@selector(refreshPermissions:) keyEquivalent:@""]; refresh.target=self; [menu addItem:refresh];
    [menu addItem:[NSMenuItem separatorItem]];
    NSMenuItem *quit = [[NSMenuItem alloc] initWithTitle:@"Esci da S540 Tasti" action:@selector(quit:) keyEquivalent:@""]; quit.target=self; [menu addItem:quit];
    _item.menu = menu;
    _baselineNeeded = YES;
    _timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, _actions);
    dispatch_source_set_timer(_timer, DISPATCH_TIME_NOW, 200 * NSEC_PER_MSEC, 30 * NSEC_PER_MSEC);
    dispatch_source_set_event_handler(_timer, ^{ [self pollDriver]; });
    dispatch_resume(_timer);
    signal(SIGTERM, SIG_IGN);
    _termSignal = dispatch_source_create(DISPATCH_SOURCE_TYPE_SIGNAL, SIGTERM, 0, dispatch_get_main_queue());
    dispatch_source_set_event_handler(_termSignal, ^{ [NSApp terminate:nil]; });
    dispatch_resume(_termSignal);
    NSNotificationCenter *workspace = [[NSWorkspace sharedWorkspace] notificationCenter];
    [workspace addObserver:self selector:@selector(willSleep:) name:NSWorkspaceWillSleepNotification object:nil];
    [workspace addObserver:self selector:@selector(didWake:) name:NSWorkspaceDidWakeNotification object:nil];
    [self refreshLockTap];
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    atomic_store(&Terminating, true);
    atomic_store(&CancelActions, true);
    if (_actions) dispatch_sync(_actions, ^{ self->_stopping = YES; if (self->_timer) dispatch_source_cancel(self->_timer); });
    [self closeLockTap];
    [self dismissFeedback];
    if (_termSignal) dispatch_source_cancel(_termSignal);
    [[[NSWorkspace sharedWorkspace] notificationCenter] removeObserver:self];
    if (_lockFD >= 0) { close(_lockFD); _lockFD = -1; }
    return NSTerminateNow;
}
@end

static NSDictionary *Status(void) {
    uint64_t identifier = 0; NSString *failure = nil;
    NSDictionary *snapshot = DriverSnapshot(&identifier, &failure);
    NSMutableDictionary *status = [@{@"schema":@1,@"app_version":AppVersion,@"expected_driver_version":DriverVersion,@"driver_found":@(snapshot != nil),
        @"driver_ready":@([snapshot[@"Ready"] boolValue] && [snapshot[@"State"] isEqual:@"Ready"]), @"driver_status":snapshot[@"State"] ?: failure ?: @"unknown",
        @"input_monitoring_granted":@(CGPreflightListenEventAccess()),
        @"accessibility_granted":@(AXIsProcessTrusted()), @"f9_enabled":@(LockKeysEnabled()), @"fn_f9_enabled":@NO,
        @"command_l_locks_screen":@(LockKeysEnabled())} mutableCopy];
    if (snapshot) status[@"driver_snapshot"] = snapshot;
    AudioDeviceID device = kAudioObjectUnknown; UInt32 mute = 0; BOOL writable = NO;
    BOOL mic = ReadDefaultInput(&device) && ReadMute(device, &mute, &writable);
    status[@"microphone_master_mute_available"] = @(mic && writable);
    if (mic) status[@"microphone_muted"] = @(mute != 0);
    CWInterface *interface = nil; HKRadioState state;
    BOOL radios = ReadRadios(&interface, &state);
    status[@"radio_controls_available"] = @(radios);
    if (radios) { status[@"wifi_powered"] = @(state.wifi); status[@"bluetooth_powered"] = @(state.bluetooth); }
    NSDictionary *runtime = ReadPrivateDictionary(@"runtime.plist");
    if ([runtime[@"app_version"] isEqual:AppVersion] && [runtime[@"features"] isKindOfClass:[NSDictionary class]])
        status[@"last_feature_status"] = runtime[@"features"];
    return status;
}
static int PrintJSON(NSDictionary *object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:NSJSONWritingPrettyPrinted error:NULL];
    if (!data) return 1;
    return fwrite(data.bytes, 1, data.length, stdout) == data.length && fputc('\n', stdout) != EOF ? 0 : 1;
}
// Diagnostics below are exclusively for fixed build-time fixtures. Never pass
// live keyboard, audio, radio, registry, or user data into this helper.
static NSDictionary *FixtureValueInfo(id value) {
    if (!value) return @{@"value":@"nil"};
    CFTypeID type = CFGetTypeID((__bridge CFTypeRef)value);
    NSMutableDictionary *info = [@{@"value":[value description], @"class":NSStringFromClass([value class]),
        @"cf_type":@(type)} mutableCopy];
    if (type == CFNumberGetTypeID()) {
        NSNumber *number = value; int64_t scalar = 0;
        info[@"cf_number_type"] = @(CFNumberGetType((__bridge CFNumberRef)value));
        info[@"is_float"] = @(CFNumberIsFloatType((__bridge CFNumberRef)value));
        info[@"objc_type"] = [NSString stringWithUTF8String:number.objCType] ?: @"unknown";
        info[@"scalar_conversion_ok"] = @(CFNumberGetValue((__bridge CFNumberRef)value, kCFNumberSInt64Type, &scalar));
        info[@"scalar_conversion_value"] = @(scalar);
        info[@"compare_min"] = @([number compare:@(INT32_MIN)]);
        info[@"compare_max"] = @([number compare:@(UINT32_MAX)]);
    }
    return info;
}
static void RecordCheck(NSMutableArray *checks, NSString *name, BOOL passed, NSDictionary *failureDetails) {
    NSMutableDictionary *check = [@{@"name":name, @"passed":@(passed)} mutableCopy];
    if (!passed && failureDetails) check[@"details"] = failureDetails;
    [checks addObject:check];
}
static void CheckUInt32(NSMutableArray *checks, NSString *name, id input, BOOL expectedAccepted, uint32_t expectedBits) {
    uint32_t bits = 0;
    BOOL accepted = UInt32Bits(input, &bits);
    BOOL passed = accepted == expectedAccepted && (!accepted || bits == expectedBits);
    NSDictionary *details = passed ? nil : @{@"input":FixtureValueInfo(input),
        @"expected_accepted":@(expectedAccepted), @"actual_accepted":@(accepted),
        @"expected_bits":@(expectedBits), @"actual_bits":@(bits)};
    RecordCheck(checks, name, passed, details);
}
static void CheckContract(NSMutableArray *checks, NSString *name, NSDictionary *snapshot, NSString *expectedFailure) {
    NSString *actual = DriverContractFailure(snapshot);
    BOOL passed = expectedFailure ? [actual isEqual:expectedFailure] : actual == nil;
    RecordCheck(checks, name, passed, passed ? nil : @{@"expected":expectedFailure ?: @"valid", @"actual":actual ?: @"valid"});
}
static void CheckLock(NSMutableArray *checks, NSString *name, bool *held, bool down, bool up,
                      uint64_t keyCode, bool command, bool otherModifiers, bool repeating,
                      HKLockDecision expected, bool expectedHeld) {
    HKLockDecision actual = HKDirectLock(held, down, up, keyCode, command, otherModifiers, repeating);
    BOOL passed = actual == expected && *held == expectedHeld;
    RecordCheck(checks, name, passed, passed ? nil : @{@"expected_decision":@(expected), @"actual_decision":@(actual),
        @"expected_held":@(expectedHeld), @"actual_held":@(*held)});
}
static void DecoderAndContractTests(NSMutableArray *checks) {
    uint32_t cfgRaw = ExpectedCFG;
    int32_t signedCFG = 0, signedUnknown = -1;
    memcpy(&signedCFG, &cfgRaw, sizeof(signedCFG));
    id cfg = CFBridgingRelease(CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &signedCFG));
    id unknown = CFBridgingRelease(CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, &signedUnknown));
    RecordCheck(checks, @"cf-sint32-fixtures-created", cfg != nil && unknown != nil, nil);
    if (!cfg || !unknown) return;
    uint64_t wide = 0;
    RecordCheck(checks, @"strict-unsigned-rejects-signed-cfg", !Unsigned(cfg, &wide), FixtureValueInfo(cfg));
    CheckUInt32(checks, @"u32-signed-cfg", cfg, YES, ExpectedCFG);
    CheckUInt32(checks, @"u32-signed-unknown-camera", unknown, YES, UINT32_MAX);
    CheckUInt32(checks, @"u32-positive-max", @(UINT32_MAX), YES, UINT32_MAX);
    CheckUInt32(checks, @"u32-negative-min", @(INT32_MIN), YES, UINT32_C(0x80000000));
    CheckUInt32(checks, @"u32-zero", @0, YES, 0);
    CheckUInt32(checks, @"u32-reject-bool", @YES, NO, 0);
    CheckUInt32(checks, @"u32-reject-float-one", @1.0, NO, 0);
    CheckUInt32(checks, @"u32-reject-float-fraction", @1.5, NO, 0);
    CheckUInt32(checks, @"u32-reject-string", @"1", NO, 0);
    CheckUInt32(checks, @"u32-reject-below-min", @(-INT64_C(2147483649)), NO, 0);
    CheckUInt32(checks, @"u32-reject-two-to-32", @(UINT64_C(4294967296)), NO, 0);
    CheckUInt32(checks, @"u32-reject-uint64-max", @(UINT64_MAX), NO, 0);
    NSMutableDictionary *snapshot = [@{@"Schema":@1, @"CFG":cfg, @"EventSequence":@0,
        @"Version":DriverVersion, @"Ready":@YES, @"Awake":@YES, @"State":@"Ready", @"EventRing":@[]} mutableCopy];
    CheckContract(checks, @"contract-signed-cfg-driver-010", snapshot, nil);
    snapshot[@"CFG"] = @YES;
    CheckContract(checks, @"contract-reject-bool-cfg", snapshot, @"driver-contract-CFG-type-invalid");
    snapshot[@"CFG"] = cfg; snapshot[@"Version"] = AppVersion;
    CheckContract(checks, @"contract-app-version-not-driver-version", snapshot, @"driver-contract-Version-mismatch");
    snapshot[@"Version"] = DriverVersion; snapshot[@"EventSequence"] = @(-1);
    CheckContract(checks, @"contract-strict-unsigned-sequence", snapshot, @"driver-contract-EventSequence-invalid");
    bool held = false;
    CheckLock(checks, @"lock-command-l-down", &held, true, false, 37, true, false, false, HKLockRequest, true);
    CheckLock(checks, @"lock-owned-repeat-consumed", &held, true, false, 37, true, false, true, HKLockConsume, true);
    CheckLock(checks, @"lock-owned-release-without-command", &held, false, true, 37, false, false, false, HKLockConsume, false);
    CheckLock(checks, @"lock-plain-l-passes", &held, true, false, 37, false, false, false, HKLockPass, false);
    CheckLock(checks, @"lock-unowned-command-repeat-passes", &held, true, false, 37, true, false, true, HKLockPass, false);
    CheckLock(checks, @"lock-unowned-release-passes", &held, false, true, 37, true, false, false, HKLockPass, false);
    CheckLock(checks, @"lock-other-modifiers-pass", &held, true, false, 37, true, true, false, HKLockPass, false);
    CheckLock(checks, @"lock-normal-f9-passes", &held, true, false, 101, false, false, false, HKLockPass, false);
}
static int SelfTest(void) {
    NSMutableArray *checks = [NSMutableArray array];
    HKRadioState off = {false,false}, wifi={true,false};
    HKEvent events[]={{1,0x100,1},{2,0x2000,2}};
    uint64_t last=0; bool seen=false;
    RecordCheck(checks, @"radio-off-target", HKRadioEqual(HKRadioTarget(wifi,false,off),off), nil);
    RecordCheck(checks, @"radio-restore-original-mix", HKRadioEqual(HKRadioTarget(off,true,wifi),wifi), nil);
    RecordCheck(checks, @"ring-contiguous", HKValidateRing(events,2,2,0)==HKRingValid, nil);
    RecordCheck(checks, @"ring-gap-rejected", HKValidateRing(events+1,1,2,0)==HKRingGap, nil);
    RecordCheck(checks, @"debounce-first", HKDebounce(1,&last,&seen), nil);
    RecordCheck(checks, @"debounce-repeat", !HKDebounce(1000,&last,&seen), nil);
    RecordCheck(checks, @"debounce-quiet-window", HKDebounce(300001000,&last,&seen), nil);
    RecordCheck(checks, @"unsigned-reject-bool", !Unsigned(@NO,&last), FixtureValueInfo(@NO));
    RecordCheck(checks, @"unsigned-reject-string", !Unsigned(@"0",&last), FixtureValueInfo(@"0"));
    RecordCheck(checks, @"unsigned-reject-float-zero", !Unsigned(@0.0,&last), FixtureValueInfo(@0.0));
    RecordCheck(checks, @"unsigned-accept-zero", Unsigned(@0,&last), FixtureValueInfo(@0));
    RecordCheck(checks, @"fresh-boundary-accepted", HKEventFresh(3000000001,1), nil);
    RecordCheck(checks, @"fresh-expired-rejected", !HKEventFresh(3000000002,1), nil);
    DecoderAndContractTests(checks);
    BOOL passed = YES; NSMutableArray *failures = [NSMutableArray array];
    for (NSDictionary *check in checks) if (![check[@"passed"] boolValue]) { passed = NO; [failures addObject:check]; }
    (void)PrintJSON(@{@"result":passed?@"SELF_TEST_PASSED":@"SELF_TEST_FAILED",@"app_version":AppVersion,
        @"hardware_actions_performed":@NO,@"checks_run":@(checks.count),@"checks":checks,@"failures":failures});
    return passed ? 0 : 1;
}
static S540Delegate *StrongDelegate;
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc==2 && !strcmp(argv[1],"--self-test")) return SelfTest();
        if (argc==2 && !strcmp(argv[1],"--status")) return PrintJSON(Status());
        if (argc!=1) { fprintf(stderr,"Usage: S540Tasti [--status | --self-test]\n"); return 64; }
        if (geteuid()==0 || geteuid()!=getuid()) { fprintf(stderr,"Run S540Tasti as the logged-in user, without sudo.\n"); return 77; }
        NSApplication *application = [NSApplication sharedApplication];
        [application setActivationPolicy:NSApplicationActivationPolicyAccessory];
        StrongDelegate = [[S540Delegate alloc] init];
        application.delegate = StrongDelegate;
        [application run];
    }
    return 0;
}
