/* SPDX-License-Identifier: MIT */
/* Two full actual bodies with original generated types. Typed cancellation,
 * clock and interrupt endpoints are CPU fixtures, not real-drain receipts. */
#include "nv.h"
#include "gpu/gpu.h"
#include "gpu/timer/objtmr.h"
static OBJGPU gpu;
static OBJTMR timer;
static TMR_EVENT_PVT events[3];
static NvU32 calls, failAt, alarmDisable, countdownDisable, identityErrors;
static NV_STATUS failure;
static NvU64 now;
static NV_STATUS fixtureCancel(OS_GPU_INFO *info, void *handle) {
    ++calls;
    if (info != gpu.pOsGpuInfo || handle != (void *)(NvUPtr)calls) ++identityErrors;
    return calls == failAt ? failure : NV_OK;
}
static void fixtureLog(int level, const char *format, ...) { (void)level; (void)format; }
#undef ENG_GET_GPU
#define ENG_GET_GPU(...) (&gpu)
#undef tmrSetAlarmIntrDisable_HAL
#define tmrSetAlarmIntrDisable_HAL(...) ((void)++alarmDisable)
#undef tmrSetCountdownIntrDisable_HAL
#define tmrSetCountdownIntrDisable_HAL(...) ((void)++countdownDisable)
#undef osCancelNanoTimer
#define osCancelNanoTimer fixtureCancel
#undef portTimeGetUptimeNanoseconds
#define portTimeGetUptimeNanoseconds() now
#undef tmrEventCancelOSTimer_HAL
#define tmrEventCancelOSTimer_HAL tmrEventCancelOSTimer_OSTIMER
#undef NV_PRINTF
#define NV_PRINTF(...) fixtureLog(__VA_ARGS__)
#if S540_TIMER_BASELINE
#include "baseline-bodies.inc"
#else
#include "proposed-bodies.inc"
#endif
static void reset(NvU32 count, NvU32 fail, NV_STATUS status, NvU64 time) {
    NvU8 *d = (NvU8 *)events;
    for (NvU64 i = 0; i < sizeof(events); ++i) d[i] = 0;
    calls = alarmDisable = countdownDisable = identityErrors = 0;
    failAt = fail; failure = status; now = time;
    for (NvU32 i = 0; i < count; ++i) {
        events[i].super.flags = TMR_FLAG_OS_TIMER_QUEUED | 0x80000000U;
        events[i].super.pOSTmrCBdata = (void *)(NvUPtr)(i + 1);
        events[i].pNext = i + 1 < count ? &events[i + 1] : NULL;
        events[i].startTimeNs = 10; events[i].timens = 1000;
    }
    timer.pRmActiveOSTimerEventList = count ? events : NULL;
}
NV_STATUS s540TimerStatusCancel(NvU32 which) {
    reset(1, 0, NV_OK, 100);
    if (which == 0) return tmrEventCancelOSTimer_OSTIMER(&timer, NULL);
    if (which == 1) events[0].super.pOSTmrCBdata = NULL;
    if (which == 2) { failAt = 1; failure = NV_ERR_TIMEOUT; }
    if (which == 3) { failAt = 1; failure = NV_ERR_IN_USE; }
    if (which == 5 || which == 6) events[0].super.flags &= ~TMR_FLAG_OS_TIMER_QUEUED;
    if (which == 6) { failAt = 1; failure = NV_ERR_TIMEOUT; }
    return tmrEventCancelOSTimer_OSTIMER(&timer, (TMR_EVENT *)events);
}
NV_STATUS s540TimerStatusUnload(NvU32 count, NvU32 fail, NvU64 time) {
    reset(count, fail, NV_ERR_TIMEOUT, time);
    return tmrStateUnload_IMPL(&gpu, &timer, 0);
}
NvU32 s540TimerStatusCalls(void) { return calls; }
NvU32 s540TimerStatusFlag(NvU32 which) { return events[which].super.flags; }
NvU32 s540TimerStatusExpectedFlag(NvBool queued) { return 0x80000000U | (queued ? TMR_FLAG_OS_TIMER_QUEUED : 0); }
NvU64 s540TimerStatusRemaining(NvU32 which) { return events[which].timens; }
NvU32 s540TimerStatusInterrupts(void) { return alarmDisable + countdownDisable; }
NvU32 s540TimerStatusIdentityErrors(void) { return identityErrors; }
NvBool s540TimerStatusListPreserved(void) {
    return timer.pRmActiveOSTimerEventList == events && events[0].pNext == &events[1] &&
        events[1].pNext == &events[2] && !events[2].pNext;
}
