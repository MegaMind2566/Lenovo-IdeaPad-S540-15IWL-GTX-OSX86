// SPDX-License-Identifier: MIT
#ifndef S540_HOTKEY_POLICY_H
#define S540_HOTKEY_POLICY_H
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef struct { bool wifi, bluetooth; } HKRadioState;
typedef enum { HKLockPass, HKLockConsume, HKLockRequest } HKLockDecision;
static inline HKLockDecision HKDirectLock(bool *held, bool down, bool up,
                                         uint64_t keyCode, bool command,
                                         bool otherModifiers, bool repeating) {
    if (keyCode != 37 || (!down && !up)) return HKLockPass;
    bool matches = command && !otherModifiers;
    if (up) {
        bool consumed = *held;
        *held = false;
        return consumed ? HKLockConsume : HKLockPass;
    }
    if (*held) return HKLockConsume;
    if (repeating) return HKLockPass;
    if (!matches) return HKLockPass;
    *held = true;
    return HKLockRequest;
}
static inline bool HKEventFresh(uint64_t nowNs, uint64_t eventNs) {
    return eventNs != 0 && nowNs >= eventNs && nowNs - eventNs <= UINT64_C(3000000000);
}
static inline bool HKRadioEqual(HKRadioState a, HKRadioState b) {
    return a.wifi == b.wifi && a.bluetooth == b.bluetooth;
}
static inline HKRadioState HKRadioTarget(HKRadioState current, bool hasSaved, HKRadioState saved) {
    if (current.wifi || current.bluetooth) return (HKRadioState){false, false};
    return hasSaved && (saved.wifi || saved.bluetooth) ? saved : (HKRadioState){true, true};
}
static inline bool HKDebounce(uint64_t nowNs, uint64_t *lastSeen, bool *seen) {
    bool act = !*seen || nowNs < *lastSeen || nowNs - *lastSeen >= UINT64_C(300000000);
    *lastSeen = nowNs;
    *seen = true;
    return act;
}
typedef struct { uint64_t seq, mask, timeNs; } HKEvent;
typedef enum { HKRingValid, HKRingGap, HKRingInvalid } HKRingResult;
static inline HKRingResult HKValidateRing(const HKEvent *events, size_t count,
                                         uint64_t current, uint64_t previous) {
    if (count > 32 || (count && !events)) return HKRingInvalid;
    uint64_t prior = 0, expected = previous;
    for (size_t i = 0; i < count; i++) {
        if (!events[i].seq || events[i].seq <= prior || events[i].seq > current || events[i].mask > UINT64_C(0xffff))
            return HKRingInvalid;
        prior = events[i].seq;
        if (events[i].seq > previous) {
            if (expected == UINT64_MAX || events[i].seq != expected + 1) return HKRingGap;
            expected = events[i].seq;
        }
    }
    if (current < previous) return HKRingGap;
    return expected == current ? HKRingValid : HKRingGap;
}
#endif
