/* SPDX-License-Identifier: MIT
 * Disable only four function-key shortcuts proved by the S540 event report.
 * This helper never edits a preferences backing file, EFI, or global defaults.
 */
#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <pwd.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>

static NSString *const Domain = @"com.apple.symbolichotkeys";
static NSString *const PreferenceKey = @"AppleSymbolicHotKeys";
static NSString *const Profile = @"s540-plain-f9-f12-v1";
static NSString *const JournalName = @"shortcut-journal.plist";
static const NSUInteger JournalLimit = 1024 * 1024;

static NSArray<NSString *> *TargetIDs(void) { return @[@"32", @"33", @"36", @"62"]; }
static NSDictionary<NSString *, NSNumber *> *Keycodes(void) {
    return @{@"32": @101, @"33": @109, @"36": @103, @"62": @111};
}
static BOOL fail(NSString **error, NSString *message) {
    if (error) *error = message;
    return NO;
}
static BOOL integer(id value, long long expected) {
    return value && CFGetTypeID((__bridge CFTypeRef)value) == CFNumberGetTypeID()
        && !CFNumberIsFloatType((__bridge CFNumberRef)value)
        && [value longLongValue] == expected;
}
static BOOL enabledValue(id value, BOOL *enabled) {
    if (!value) return NO;
    CFTypeID kind = CFGetTypeID((__bridge CFTypeRef)value);
    if (kind != CFBooleanGetTypeID() && kind != CFNumberGetTypeID()) return NO;
    if (kind == CFNumberGetTypeID() && CFNumberIsFloatType((__bridge CFNumberRef)value)) return NO;
    long long number = [value longLongValue];
    if (number != 0 && number != 1) return NO;
    if (enabled) *enabled = number != 0;
    return YES;
}
/* CFEqual on whole dictionaries may treat Boolean and numeric values alike.
 * Preserve value types too; this avoids silently rewriting original fields. */
static BOOL exact(id first, id second) {
    if (!first || !second) return first == second;
    CFTypeID kind = CFGetTypeID((__bridge CFTypeRef)first);
    if (kind != CFGetTypeID((__bridge CFTypeRef)second)) return NO;
    if (kind == CFDictionaryGetTypeID()) {
        if ([first count] != [second count]) return NO;
        for (id key in first) if (!exact(first[key], second[key])) return NO;
        return YES;
    }
    if (kind == CFArrayGetTypeID()) {
        if ([first count] != [second count]) return NO;
        for (NSUInteger index = 0; index < [first count]; index++)
            if (!exact(first[index], second[index])) return NO;
        return YES;
    }
    if (kind == CFNumberGetTypeID() &&
        CFNumberIsFloatType((__bridge CFNumberRef)first) !=
        CFNumberIsFloatType((__bridge CFNumberRef)second)) return NO;
    return CFEqual((__bridge CFTypeRef)first, (__bridge CFTypeRef)second);
}
static NSDictionary *withoutEnabled(NSDictionary *entry) {
    NSMutableDictionary *copy = [entry mutableCopy];
    [copy removeObjectForKey:@"enabled"];
    return copy;
}
static BOOL validEntry(id entry, NSString *identifier, NSString **error) {
    if (![entry isKindOfClass:[NSDictionary class]] || !enabledValue(entry[@"enabled"], NULL))
        return fail(error, [NSString stringWithFormat:@"Shortcut %@ has an invalid enabled field.", identifier]);
    id value = entry[@"value"];
    if (![value isKindOfClass:[NSDictionary class]] || ![value[@"type"] isEqual:@"standard"])
        return fail(error, [NSString stringWithFormat:@"Shortcut %@ is not a standard keyboard binding.", identifier]);
    id parameters = value[@"parameters"];
    if (![parameters isKindOfClass:[NSArray class]] || [parameters count] != 3 ||
        !integer(parameters[1], [Keycodes()[identifier] longLongValue]) || !integer(parameters[2], 0))
        return fail(error, [NSString stringWithFormat:@"Shortcut %@ no longer matches the recorded plain function key.", identifier]);
    /* parameters[0] was not recorded by the event probe. Preserve it verbatim. */
    return YES;
}
static NSDictionary *originalEntries(NSDictionary *current, NSString **error) {
    NSMutableDictionary *entries = [NSMutableDictionary dictionary];
    for (NSString *identifier in TargetIDs()) {
        if (!validEntry(current[identifier], identifier, error)) return nil;
        entries[identifier] = current[identifier];
    }
    return entries;
}
static NSArray<NSString *> *changedIDs(NSDictionary *originals) {
    NSMutableArray *changed = [NSMutableArray array];
    for (NSString *identifier in TargetIDs()) {
        BOOL enabled = NO;
        enabledValue(originals[identifier][@"enabled"], &enabled);
        if (enabled) [changed addObject:identifier];
    }
    return changed;
}
typedef NS_ENUM(NSUInteger, ApplyState) { OriginalOnly, PendingEither, AppliedOnly };
static NSDictionary *applyCandidate(NSDictionary *current, NSDictionary *originals,
                                    NSArray<NSString *> *changed, ApplyState state,
                                    NSString **error) {
    NSMutableDictionary *candidate = [current mutableCopy];
    for (NSString *identifier in TargetIDs()) {
        NSDictionary *entry = current[identifier], *original = originals[identifier];
        if (!validEntry(entry, identifier, error)) return nil;
        if (!exact(withoutEnabled(entry), withoutEnabled(original))) {
            fail(error, [NSString stringWithFormat:@"Shortcut %@ was reassigned or changed. No settings were written.", identifier]);
            return nil;
        }
        BOOL enabled = NO, originalEnabled = NO;
        enabledValue(entry[@"enabled"], &enabled);
        enabledValue(original[@"enabled"], &originalEnabled);
        if (![changed containsObject:identifier]) {
            if (!exact(entry, original)) {
                fail(error, [NSString stringWithFormat:@"Unchanged target shortcut %@ no longer matches its journal.", identifier]);
                return nil;
            }
            continue;
        }
        if ((state == OriginalOnly && !exact(entry[@"enabled"], original[@"enabled"])) ||
            (state == AppliedOnly && enabled) || !originalEnabled) {
            fail(error, [NSString stringWithFormat:@"Shortcut %@ conflicts with the journal state.", identifier]);
            return nil;
        }
        if (enabled) {
            NSMutableDictionary *disabled = [entry mutableCopy];
            disabled[@"enabled"] = @NO;
            candidate[identifier] = disabled;
        }
    }
    return candidate;
}
static NSDictionary *restoreCandidate(NSDictionary *current, NSDictionary *originals,
                                      NSArray<NSString *> *changed, BOOL recovery,
                                      NSString **error) {
    NSMutableDictionary *candidate = [current mutableCopy];
    for (NSString *identifier in changed) {
        NSDictionary *entry = current[identifier], *original = originals[identifier];
        if (!validEntry(entry, identifier, error)) return nil;
        if (!exact(withoutEnabled(entry), withoutEnabled(original))) {
            fail(error, [NSString stringWithFormat:@"Shortcut %@ changed after application. Restore refused.", identifier]);
            return nil;
        }
        BOOL enabled = NO;
        enabledValue(entry[@"enabled"], &enabled);
        if (enabled && (!recovery || !exact(entry[@"enabled"], original[@"enabled"]))) {
            fail(error, [NSString stringWithFormat:@"Shortcut %@ was re-enabled outside this helper. Restore refused.", identifier]);
            return nil;
        }
        NSMutableDictionary *restored = [entry mutableCopy];
        restored[@"enabled"] = original[@"enabled"];
        candidate[identifier] = restored;
    }
    return candidate;
}
static BOOL runtimeGuard(NSString **home, NSString **error) {
    uid_t uid = getuid();
    if (uid == 0 || geteuid() != uid || getgid() != getegid() ||
        getenv("SUDO_UID") || getenv("SUDO_USER"))
        return fail(error, @"Run this helper as the logged-in user. Do not use sudo.");
    struct stat console;
    if (stat("/dev/console", &console) != 0 || console.st_uid != uid)
        return fail(error, @"Run this helper from the current desktop user account.");
    struct passwd *account = getpwuid(uid);
    if (!account || !account->pw_dir || account->pw_dir[0] != '/')
        return fail(error, @"The current account home directory could not be resolved.");
    NSString *resolved = [NSString stringWithUTF8String:account->pw_dir];
    struct stat info;
    if (lstat(resolved.fileSystemRepresentation, &info) != 0 || !S_ISDIR(info.st_mode) || info.st_uid != uid)
        return fail(error, @"The account home directory is missing, linked, or owned by another user.");
    if (home) *home = resolved;
    return YES;
}
static NSDictionary *readPreferences(NSString **error) {
    CFStringRef domain = (__bridge CFStringRef)Domain, key = (__bridge CFStringRef)PreferenceKey;
    if (CFPreferencesAppValueIsForced(key, domain)) {
        fail(error, @"The shortcut preference is managed. No settings were written.");
        return nil;
    }
    if (!CFPreferencesSynchronize(domain, kCFPreferencesCurrentUser, kCFPreferencesAnyHost) ||
        !CFPreferencesSynchronize(domain, kCFPreferencesCurrentUser, kCFPreferencesCurrentHost)) {
        fail(error, @"The shortcut preferences could not be refreshed.");
        return nil;
    }
    id override = CFBridgingRelease(CFPreferencesCopyValue(key, domain,
        kCFPreferencesCurrentUser, kCFPreferencesCurrentHost));
    if (override) {
        fail(error, @"A current-host shortcut override exists. No settings were written.");
        return nil;
    }
    id value = CFBridgingRelease(CFPreferencesCopyValue(key, domain,
        kCFPreferencesCurrentUser, kCFPreferencesAnyHost));
    id effective = CFBridgingRelease(CFPreferencesCopyAppValue(key, domain));
    if (![value isKindOfClass:[NSDictionary class]] || !exact(value, effective)) {
        fail(error, @"The active shortcuts do not match the current-user any-host preference domain.");
        return nil;
    }
    return value;
}
static BOOL writePreferences(NSDictionary *before, NSDictionary *candidate, NSString **error) {
    NSDictionary *fresh = readPreferences(error);
    if (!fresh) return NO;
    if (!exact(before, fresh))
        return fail(error, @"Shortcuts changed during preparation. Close Keyboard Shortcuts and retry.");
    if (exact(before, candidate)) return YES;
    CFPreferencesSetValue((__bridge CFStringRef)PreferenceKey, (__bridge CFPropertyListRef)candidate,
        (__bridge CFStringRef)Domain, kCFPreferencesCurrentUser, kCFPreferencesAnyHost);
    if (!CFPreferencesSynchronize((__bridge CFStringRef)Domain,
        kCFPreferencesCurrentUser, kCFPreferencesAnyHost))
        return fail(error, @"Preference persistence could not be confirmed. Keep the journal and rerun the same command.");
    NSDictionary *after = readPreferences(error);
    if (!after) return NO;
    if (!exact(after, candidate))
        return fail(error, @"The read-back differs from the prepared change. Keep the journal and rerun the same command.");
    return YES;
}
static BOOL ensureDirectory(NSString *path, BOOL create, BOOL private, NSString **error) {
    struct stat info;
    if (lstat(path.fileSystemRepresentation, &info) != 0) {
        if (errno != ENOENT || !create || mkdir(path.fileSystemRepresentation, private ? 0700 : 0755) != 0)
            return fail(error, @"The journal directory is unavailable.");
        if (lstat(path.fileSystemRepresentation, &info) != 0)
            return fail(error, @"The journal directory could not be checked.");
    }
    if (!S_ISDIR(info.st_mode) || info.st_uid != getuid() ||
        (private ? ((info.st_mode & 0777) != 0700) : ((info.st_mode & 0022) != 0)))
        return fail(error, @"The journal directory is linked, has unsafe permissions, or belongs to another user.");
    return YES;
}
static NSString *journalDirectory(NSString *home, BOOL create, NSString **error) {
    NSString *library = [home stringByAppendingPathComponent:@"Library"];
    NSString *support = [library stringByAppendingPathComponent:@"Application Support"];
    NSString *folder = [support stringByAppendingPathComponent:@"S540FunctionKeys"];
    struct stat info;
    if (!create && lstat(folder.fileSystemRepresentation, &info) != 0 && errno == ENOENT) return nil;
    if (!ensureDirectory(library, create, NO, error) || !ensureDirectory(support, create, NO, error) ||
        !ensureDirectory(folder, create, YES, error)) return nil;
    return folder;
}
static BOOL safeFileDescriptor(int descriptor, NSString **error) {
    struct stat info;
    if (fstat(descriptor, &info) != 0 || !S_ISREG(info.st_mode) || info.st_uid != getuid() ||
        info.st_nlink != 1 || (info.st_mode & 0777) != 0600)
        return fail(error, @"A journal or lock file has an unsafe owner, type, link count, or permissions.");
    return YES;
}
static int lockDirectory(NSString *folder, NSString **error) {
    NSString *path = [folder stringByAppendingPathComponent:@"shortcut.lock"];
    int descriptor = open(path.fileSystemRepresentation, O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (descriptor < 0) { fail(error, @"The journal lock could not be opened."); return -1; }
    if (!safeFileDescriptor(descriptor, error) || flock(descriptor, LOCK_EX | LOCK_NB) != 0) {
        if (!*error) fail(error, @"Another shortcut operation is running.");
        close(descriptor); return -1;
    }
    return descriptor;
}
static BOOL validJournal(NSDictionary *journal, NSString **error) {
    NSSet *keys = [NSSet setWithArray:@[@"schema", @"profile", @"uid", @"domain", @"key",
        @"user_scope", @"host_scope", @"original_entries", @"changed_ids", @"phase", @"operation",
        @"created", @"updated"]];
    if (![journal isKindOfClass:[NSDictionary class]] ||
        ![[NSSet setWithArray:journal.allKeys] isEqual:keys] || !integer(journal[@"schema"], 1) ||
        !integer(journal[@"uid"], getuid()) || ![journal[@"profile"] isEqual:Profile] ||
        ![journal[@"domain"] isEqual:Domain] || ![journal[@"key"] isEqual:PreferenceKey] ||
        ![journal[@"user_scope"] isEqual:@"current-user"] || ![journal[@"host_scope"] isEqual:@"any-host"] ||
        ![journal[@"created"] isKindOfClass:[NSDate class]] || ![journal[@"updated"] isKindOfClass:[NSDate class]])
        return fail(error, @"The shortcut journal has an unexpected schema, scope, or account.");
    NSString *phase = journal[@"phase"], *operation = journal[@"operation"];
    if (![@[@"prepared", @"applied", @"restored"] containsObject:phase] ||
        ![@[@"apply", @"restore"] containsObject:operation] ||
        ([phase isEqual:@"applied"] && ![operation isEqual:@"apply"]) ||
        ([phase isEqual:@"restored"] && ![operation isEqual:@"restore"]))
        return fail(error, @"The shortcut journal has an invalid operation state.");
    NSDictionary *originals = journal[@"original_entries"];
    if (![originals isKindOfClass:[NSDictionary class]] ||
        ![[NSSet setWithArray:originals.allKeys] isEqual:[NSSet setWithArray:TargetIDs()]] ||
        !originalEntries(originals, error)) return fail(error, @"The original shortcut entries are invalid.");
    if (![journal[@"changed_ids"] isKindOfClass:[NSArray class]] ||
        !exact(journal[@"changed_ids"], changedIDs(originals)) || [journal[@"changed_ids"] count] == 0)
        return fail(error, @"The journal change list does not match its original entries.");
    return YES;
}
static NSDictionary *loadJournal(NSString *folder, NSString **error) {
    if (!folder) return nil;
    NSString *path = [folder stringByAppendingPathComponent:JournalName];
    int descriptor = open(path.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (descriptor < 0) {
        if (errno != ENOENT) fail(error, @"The shortcut journal could not be opened safely.");
        return nil;
    }
    if (!safeFileDescriptor(descriptor, error)) { close(descriptor); return nil; }
    struct stat info;
    if (fstat(descriptor, &info) != 0 || info.st_size <= 0 || info.st_size > (off_t)JournalLimit) {
        close(descriptor); fail(error, @"The shortcut journal has an invalid size."); return nil;
    }
    NSMutableData *data = [NSMutableData dataWithLength:(NSUInteger)info.st_size];
    NSUInteger offset = 0;
    while (offset < data.length) {
        ssize_t result = read(descriptor, (char *)data.mutableBytes + offset, data.length - offset);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) { close(descriptor); fail(error, @"The shortcut journal could not be read completely."); return nil; }
        offset += (NSUInteger)result;
    }
    close(descriptor);
    NSDictionary *journal = [NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable
        format:NULL error:NULL];
    if (!validJournal(journal, error)) return nil;
    return journal;
}
static BOOL saveJournal(NSString *folder, NSDictionary *journal, NSString **error) {
    if (!validJournal(journal, error)) return NO;
    NSData *data = [NSPropertyListSerialization dataWithPropertyList:journal
        format:NSPropertyListBinaryFormat_v1_0 options:0 error:NULL];
    if (!data || data.length > JournalLimit) return fail(error, @"The shortcut journal could not be serialized.");
    NSString *path = [folder stringByAppendingPathComponent:JournalName];
    struct stat info;
    if (lstat(path.fileSystemRepresentation, &info) == 0) {
        int existing = open(path.fileSystemRepresentation, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
        if (existing < 0) return fail(error, @"The existing journal changed or could not be opened.");
        BOOL safe = safeFileDescriptor(existing, error); close(existing);
        if (!safe) return NO;
    } else if (errno != ENOENT) return fail(error, @"The existing journal could not be checked.");
    NSString *temporary = [folder stringByAppendingPathComponent:
        [NSString stringWithFormat:@"journal-%@.tmp", NSUUID.UUID.UUIDString]];
    int descriptor = open(temporary.fileSystemRepresentation,
        O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (descriptor < 0) return fail(error, @"A private journal staging file could not be created.");
    BOOL success = YES;
    NSUInteger offset = 0;
    while (offset < data.length) {
        ssize_t result = write(descriptor, (const char *)data.bytes + offset, data.length - offset);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) { success = NO; break; }
        offset += (NSUInteger)result;
    }
    if (success && fsync(descriptor) != 0) success = NO;
    if (close(descriptor) != 0) success = NO;
    if (success && rename(temporary.fileSystemRepresentation, path.fileSystemRepresentation) != 0) success = NO;
    if (!success) {
        unlink(temporary.fileSystemRepresentation);
        return fail(error, @"The journal update could not be saved durably. Keep it and rerun the same command.");
    }
    int directory = open(folder.fileSystemRepresentation, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (directory < 0) return fail(error, @"The journal directory could not be synchronized.");
    int result = fsync(directory), savedErrno = errno;
    close(directory);
    if (result != 0 && savedErrno != EINVAL && savedErrno != ENOTSUP)
        return fail(error, @"The journal directory could not be synchronized.");
    return YES;
}
static NSDictionary *newJournal(NSDictionary *originals, NSArray *changed) {
    NSDate *now = [NSDate date];
    return @{@"schema": @1, @"profile": Profile, @"uid": @(getuid()), @"domain": Domain,
        @"key": PreferenceKey, @"user_scope": @"current-user", @"host_scope": @"any-host",
        @"original_entries": originals, @"changed_ids": changed, @"phase": @"prepared",
        @"operation": @"apply", @"created": now, @"updated": now};
}
static NSDictionary *journalState(NSDictionary *journal, NSString *phase, NSString *operation) {
    NSMutableDictionary *copy = [journal mutableCopy];
    copy[@"phase"] = phase; copy[@"operation"] = operation; copy[@"updated"] = [NSDate date];
    return copy;
}
static void printStatus(NSDictionary *current, NSDictionary *journal) {
    puts("Current-user shortcut status:");
    for (NSString *identifier in TargetIDs()) {
        BOOL enabled = NO;
        if (!validEntry(current[identifier], identifier, NULL)) {
            printf("  Shortcut %s: CHANGED OR UNAVAILABLE\n", identifier.UTF8String); continue;
        }
        enabledValue(current[identifier][@"enabled"], &enabled);
        printf("  Shortcut %s: %s\n", identifier.UTF8String, enabled ? "ENABLED" : "DISABLED");
    }
    if (journal) printf("Journal: %s (%s)\n", [journal[@"phase"] UTF8String], [journal[@"operation"] UTF8String]);
    else puts("Journal: none");
}
static NSDictionary *fixtureEntry(NSInteger keycode, NSInteger modifiers, BOOL enabled) {
    return @{@"enabled": @(enabled), @"value": @{@"type": @"standard",
        @"parameters": @[@65535, @(keycode), @(modifiers)]}, @"extra": @{@"keep": @"verbatim"}};
}
static int selfTest(void) {
    NSMutableDictionary *fixture = [NSMutableDictionary dictionary];
    for (NSString *identifier in TargetIDs()) fixture[identifier] = fixtureEntry([Keycodes()[identifier] integerValue], 0, YES);
    fixture[@"34"] = fixtureEntry(101, 131072, YES);
    fixture[@"35"] = fixtureEntry(109, 131072, YES);
    fixture[@"37"] = fixtureEntry(103, 131072, YES);
    fixture[@"63"] = fixtureEntry(111, 131072, YES);
    fixture[@"53"] = fixtureEntry(107, 0, YES); fixture[@"54"] = fixtureEntry(113, 0, YES);
    fixture[@"10"] = fixtureEntry(96, 262144, YES); fixture[@"unrelated"] = @{@"untouched": @[@YES, @12, @"text"]};
    NSString *error = nil;
    NSDictionary *originals = originalEntries(fixture, &error);
    NSArray *changed = changedIDs(originals);
    NSDictionary *applied = applyCandidate(fixture, originals, changed, OriginalOnly, &error);
    NSUInteger checks = 0;
#define CHECK(condition) do { checks++; if (!(condition)) { fprintf(stderr, "Self-test failed at line %d.\n", __LINE__); return 1; } } while (0)
    CHECK(originals && applied && !error && changed.count == 4);
    for (NSString *identifier in fixture) {
        if ([changed containsObject:identifier]) {
            CHECK(exact(withoutEnabled(fixture[identifier]), withoutEnabled(applied[identifier])));
            CHECK([applied[identifier][@"enabled"] boolValue] == NO);
        } else CHECK(exact(fixture[identifier], applied[identifier]));
    }
    CHECK(exact(fixture, restoreCandidate(applied, originals, changed, NO, &error)));
    CHECK(exact(applied, applyCandidate(applied, originals, changed, AppliedOnly, &error)));
    CHECK(exact(applied, applyCandidate(applied, originals, changed, PendingEither, &error)));
    NSMutableDictionary *partial = [applied mutableCopy]; partial[@"32"] = fixture[@"32"];
    CHECK(exact(applied, applyCandidate(partial, originals, changed, PendingEither, &error)));
    CHECK(exact(fixture, restoreCandidate(partial, originals, changed, YES, &error)));
    error = nil; CHECK(!restoreCandidate(partial, originals, changed, NO, &error) && error);
    error = nil; CHECK(!applyCandidate(partial, originals, changed, AppliedOnly, &error) && error);
    NSMutableDictionary *modified = [applied mutableCopy]; modified[@"32"] = fixtureEntry(101, 131072, NO);
    error = nil; CHECK(!restoreCandidate(modified, originals, changed, NO, &error) && error);
    [modified removeObjectForKey:@"32"];
    error = nil; CHECK(!restoreCandidate(modified, originals, changed, NO, &error) && error);
    modified = [applied mutableCopy]; modified[@"34"] = fixtureEntry(101, 131072, NO); modified[@"new"] = @"preserve later edits";
    error = nil;
    NSDictionary *restored = restoreCandidate(modified, originals, changed, NO, &error);
    CHECK(restored && exact(restored[@"34"], modified[@"34"]) && exact(restored[@"new"], modified[@"new"]));
    for (NSString *identifier in changed) CHECK(exact(restored[identifier], fixture[identifier]));
    NSMutableDictionary *someDisabled = [fixture mutableCopy]; someDisabled[@"36"] = fixtureEntry(103, 0, NO);
    error = nil; NSDictionary *mixedOriginals = originalEntries(someDisabled, &error);
    NSArray *mixedChanged = changedIDs(mixedOriginals);
    CHECK(mixedChanged.count == 3 && ![mixedChanged containsObject:@"36"]);
    NSDictionary *mixedApplied = applyCandidate(someDisabled, mixedOriginals, mixedChanged, OriginalOnly, &error);
    CHECK(mixedApplied && exact(mixedApplied[@"36"], someDisabled[@"36"]));
    NSMutableDictionary *laterMixed = [mixedApplied mutableCopy]; laterMixed[@"36"] = fixtureEntry(103, 131072, YES);
    NSDictionary *mixedRestored = restoreCandidate(laterMixed, mixedOriginals, mixedChanged, NO, &error);
    CHECK(mixedRestored && exact(mixedRestored[@"36"], laterMixed[@"36"]));
    NSDictionary *journal = newJournal(originals, changed);
    error = nil; CHECK(validJournal(journal, &error));
    CHECK(validJournal(journalState(journal, @"prepared", @"restore"), &error));
    CHECK(validJournal(journalState(journal, @"restored", @"restore"), &error));
    NSMutableDictionary *badJournal = [journal mutableCopy]; badJournal[@"domain"] = @"foreign.domain";
    error = nil; CHECK(!validJournal(badJournal, &error));
    badJournal = [journal mutableCopy]; badJournal[@"changed_ids"] = @[@"32", @"32"];
    error = nil; CHECK(!validJournal(badJournal, &error));
    CHECK(!integer(@YES, 1) && !enabledValue(@2, NULL) && !enabledValue(@0.5, NULL));
    CHECK(!exact(@YES, @1));
    printf("Pure shortcut fixture checks passed: %lu. No preferences were read or written.\n", (unsigned long)checks);
    return 0;
#undef CHECK
}
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2 || ![@[@"--apply", @"--restore", @"--status", @"--self-test"]
            containsObject:[NSString stringWithUTF8String:argv[1]]]) {
            fputs("Usage: function-key-preferences --apply | --restore | --status | --self-test\n", stderr);
            return 2;
        }
        NSString *command = [NSString stringWithUTF8String:argv[1]];
        if ([command isEqual:@"--self-test"]) return selfTest();
        NSString *error = nil, *home = nil;
        if (!runtimeGuard(&home, &error)) { fprintf(stderr, "%s\n", error.UTF8String); return 1; }
        NSDictionary *current = readPreferences(&error);
        if (!current) { fprintf(stderr, "%s\n", error.UTF8String); return 1; }
        BOOL applying = [command isEqual:@"--apply"];
        NSString *folder = journalDirectory(home, applying, &error);
        if (error) { fprintf(stderr, "%s\n", error.UTF8String); return 1; }
        int lock = folder ? lockDirectory(folder, &error) : -1;
        if (folder && lock < 0) { fprintf(stderr, "%s\n", error.UTF8String); return 1; }
        NSDictionary *journal = loadJournal(folder, &error);
        if (error) { if (lock >= 0) close(lock); fprintf(stderr, "%s\n", error.UTF8String); return 1; }
        int result = 0;
        if ([command isEqual:@"--status"]) {
            printStatus(current, journal);
        } else if (applying) {
            NSDictionary *originals = nil;
            NSArray *changed = nil;
            ApplyState state = OriginalOnly;
            if (journal) {
                originals = journal[@"original_entries"]; changed = journal[@"changed_ids"];
                if ([journal[@"phase"] isEqual:@"prepared"] && [journal[@"operation"] isEqual:@"restore"])
                    fail(&error, @"A restore operation is pending. Rerun --restore first.");
                else if ([journal[@"phase"] isEqual:@"prepared"]) state = PendingEither;
                else if ([journal[@"phase"] isEqual:@"applied"]) state = AppliedOnly;
            } else {
                originals = originalEntries(current, &error);
                if (originals) changed = changedIDs(originals);
            }
            if (!error && changed.count == 0) puts("The four recorded plain function-key shortcuts are already disabled. No settings were written.");
            else if (!error) {
                NSDictionary *candidate = applyCandidate(current, originals, changed, state, &error);
                if (candidate) {
                    if (!journal) journal = newJournal(originals, changed);
                    NSDictionary *prepared = journalState(journal, @"prepared", @"apply");
                    if (saveJournal(folder, prepared, &error) && writePreferences(current, candidate, &error) &&
                        saveJournal(folder, journalState(prepared, @"applied", @"apply"), &error)) {
                        puts("The four plain F9-F12 macOS shortcuts are disabled. Other shortcuts and function-key settings were preserved.");
                        puts("Log out and sign in again, or restart, to refresh macOS shortcut handling.");
                    }
                }
            }
        } else {
            if (!journal) fail(&error, @"No shortcut journal exists. No settings were written.");
            else if ([journal[@"phase"] isEqual:@"restored"]) {
                NSDictionary *candidate = restoreCandidate(current, journal[@"original_entries"], journal[@"changed_ids"], YES, &error);
                if (candidate && exact(candidate, current)) puts("The journaled shortcuts are already restored. No settings were written.");
                else if (candidate) fail(&error, @"A restored shortcut was changed again. No settings were written.");
            } else {
                BOOL recovery = [journal[@"phase"] isEqual:@"prepared"];
                NSDictionary *candidate = restoreCandidate(current, journal[@"original_entries"], journal[@"changed_ids"], recovery, &error);
                if (candidate) {
                    NSDictionary *prepared = journalState(journal, @"prepared", @"restore");
                    if (saveJournal(folder, prepared, &error) && writePreferences(current, candidate, &error) &&
                        saveJournal(folder, journalState(prepared, @"restored", @"restore"), &error)) {
                        puts("The original enabled fields were restored. Unrelated shortcut changes were preserved.");
                        puts("Log out and sign in again, or restart, to refresh macOS shortcut handling.");
                    }
                }
            }
        }
        if (error) { fprintf(stderr, "%s\n", error.UTF8String); result = 1; }
        if (lock >= 0) close(lock);
        return result;
    }
}
