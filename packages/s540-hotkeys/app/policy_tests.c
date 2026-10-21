#include "HotkeyPolicy.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    unsigned checks = 0;
#define CHECK(x) do { assert(x); checks++; } while (0)
    HKRadioState off = {false, false}, wifi = {true, false}, bt = {false, true}, both = {true, true};
    CHECK(HKEventFresh(1, 1));
    CHECK(HKEventFresh(3000000001, 1));
    CHECK(!HKEventFresh(3000000002, 1));
    CHECK(!HKEventFresh(0, 0));
    CHECK(!HKEventFresh(1, 2));
    bool held = false;
    CHECK(HKDirectLock(&held, true, false, 37, true, false, false) == HKLockRequest && held);
    CHECK(HKDirectLock(&held, true, false, 37, true, false, true) == HKLockConsume && held);
    CHECK(HKDirectLock(&held, false, true, 37, false, false, false) == HKLockConsume && !held);
    CHECK(HKDirectLock(&held, true, false, 37, false, false, false) == HKLockPass && !held);
    CHECK(HKDirectLock(&held, true, false, 37, true, false, true) == HKLockPass && !held);
    CHECK(HKDirectLock(&held, false, true, 37, true, false, false) == HKLockPass && !held);
    CHECK(HKDirectLock(&held, true, false, 37, true, true, false) == HKLockPass && !held);
    CHECK(HKDirectLock(&held, false, true, 37, true, false, false) == HKLockPass && !held);
    CHECK(HKDirectLock(&held, true, false, 101, false, false, false) == HKLockPass && !held);
    CHECK(HKDirectLock(&held, false, false, 37, true, false, false) == HKLockPass && !held);
    CHECK(HKRadioEqual(HKRadioTarget(wifi, false, off), off));
    CHECK(HKRadioEqual(HKRadioTarget(bt, false, off), off));
    CHECK(HKRadioEqual(HKRadioTarget(both, false, off), off));
    CHECK(HKRadioEqual(HKRadioTarget(off, true, wifi), wifi));
    CHECK(HKRadioEqual(HKRadioTarget(off, true, bt), bt));
    CHECK(HKRadioEqual(HKRadioTarget(off, false, off), both));
    CHECK(HKRadioEqual(HKRadioTarget(off, true, off), both));
    uint64_t last = 0; bool seen = false;
    CHECK(HKDebounce(1000, &last, &seen));
    CHECK(!HKDebounce(100000000, &last, &seen));
    CHECK(!HKDebounce(200000000, &last, &seen));
    CHECK(!HKDebounce(400000000, &last, &seen));
    CHECK(HKDebounce(700000000, &last, &seen));
    HKEvent e[] = {{1, 0x100, 1}, {2, 0x2000, 2}, {3, 0x80, 3}};
    CHECK(HKValidateRing(e, 3, 3, 0) == HKRingValid);
    CHECK(HKValidateRing(e, 3, 3, 2) == HKRingValid);
    CHECK(HKValidateRing(e, 3, 3, 3) == HKRingValid);
    CHECK(HKValidateRing(e + 1, 2, 3, 0) == HKRingGap);
    CHECK(HKValidateRing(e, 2, 3, 0) == HKRingGap);
    CHECK(HKValidateRing(e, 3, 2, 0) == HKRingInvalid);
    CHECK(HKValidateRing(NULL, 0, 0, 0) == HKRingValid);
    CHECK(HKValidateRing(NULL, 0, 4, 0) == HKRingGap);
    CHECK(HKValidateRing(e, 33, 3, 0) == HKRingInvalid);
    HKEvent bad[] = {{1, 0x10000, 1}};
    CHECK(HKValidateRing(bad, 1, 1, 0) == HKRingInvalid);
    bad[0] = (HKEvent){0, 0, 1};
    CHECK(HKValidateRing(bad, 1, 1, 0) == HKRingInvalid);
    HKEvent duplicate[] = {{1, 1, 1}, {1, 2, 2}};
    CHECK(HKValidateRing(duplicate, 2, 2, 0) == HKRingInvalid);
    CHECK(HKValidateRing(NULL, 0, 0, 1) == HKRingGap);
    printf("S540 companion policy fixtures passed: %u\n", checks);
    return 0;
}
