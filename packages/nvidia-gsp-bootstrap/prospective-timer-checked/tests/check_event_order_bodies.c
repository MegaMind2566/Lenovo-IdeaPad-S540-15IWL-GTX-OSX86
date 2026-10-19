/* SPDX-License-Identifier: MIT */
/* Complete source-extracted bodies, actual pinned generated types, explicit
 * CPU fixtures only for backend cancellation/destruction, IRQ and allocator.
 * An NV_OK backend fixture is NOT an accepted-work borrower drain receipt. */
#include "nv.h"
#include "gpu/gpu.h"
#include "gpu/timer/objtmr.h"

static OBJGPU gpu;
static OBJTMR timer;
static TMR_EVENT_PVT events[3];
static TMR_EVENT_PVT before[3];
static TMR_EVENT_PVT *target;
static NvU64 userData[3];
static NvU32 callCount, destroyCalls, freeCount, eventFreeCount, userFreeCount;
static NvU32 phaseErrors, identityErrors, sequence, backendSequence, eventFreeSequence, userFreeSequence;
static NV_STATUS backendStatus;

static void copyBytes(void *out, const void *in, NvU64 size) {
    NvU8 *d = out; const NvU8 *s = in;
    for (NvU64 i = 0; i < size; ++i) d[i] = s[i];
}
static NvBool sameBytes(const void *a, const void *b, NvU64 size) {
    const NvU8 *x = a, *y = b;
    for (NvU64 i = 0; i < size; ++i) if (x[i] != y[i]) return NV_FALSE;
    return NV_TRUE;
}
static OBJGPU *fixtureGetGpu(OBJTMR *object) {
    if (object != &timer) ++identityErrors;
    return &gpu;
}
static OBJTMR *fixtureGetTimer(OBJGPU *object) {
    if (object != &gpu) ++identityErrors;
    return &timer;
}
static NV_STATUS fixtureBackend(OS_GPU_INFO *info, void *handle, NvBool destroying) {
    ++callCount; destroyCalls += destroying; backendSequence = ++sequence;
    if (info != gpu.pOsGpuInfo || handle != before[target - events].super.pOSTmrCBdata)
        ++identityErrors;
    /* The full original list/event storage must still be intact when the
     * cancellation service is first asked to relinquish its callback. */
    if (timer.pRmActiveOSTimerEventList != events ||
        !sameBytes(events, before, sizeof(events)) || eventFreeCount || userFreeCount)
        ++phaseErrors;
    return backendStatus;
}
static NV_STATUS fixtureCancel(OS_GPU_INFO *info, void *handle) {
    return fixtureBackend(info, handle, NV_FALSE);
}
static NV_STATUS fixtureDestroy(OS_GPU_INFO *info, void *handle) {
    return fixtureBackend(info, handle, NV_TRUE);
}
static void fixtureFree(void *pointer) {
    if (!pointer) return;
    ++freeCount;
    if (pointer == target) { ++eventFreeCount; eventFreeSequence = ++sequence; }
    else if (pointer == target->super.pUserData) { ++userFreeCount; userFreeSequence = ++sequence; }
    else ++identityErrors;
}
static void fixtureLog(int level, const char *format, ...) { (void)level; (void)format; }
static void fixtureSchedule(OBJGPU *g, OBJTMR *t, NvU64 value) {
    (void)value; if (g != &gpu || t != &timer) ++identityErrors;
}
static void fixtureInterrupt(OBJTMR *t, OBJGPU *g) {
    if (g != &gpu || t != &timer) ++identityErrors;
}

#undef ENG_GET_GPU
#define ENG_GET_GPU(t) fixtureGetGpu(t)
#undef GPU_GET_TIMER
#define GPU_GET_TIMER(g) fixtureGetTimer(g)
#undef osCancelNanoTimer
#define osCancelNanoTimer fixtureCancel
#undef osDestroyNanoTimer
#define osDestroyNanoTimer fixtureDestroy
#undef tmrEventCancelOSTimer_HAL
#define tmrEventCancelOSTimer_HAL tmrEventCancelOSTimer_OSTIMER
#undef tmrEventDestroyOSTimer_HAL
#define tmrEventDestroyOSTimer_HAL tmrEventDestroyOSTimer_OSTIMER
#undef tmrEventCancel
#define tmrEventCancel tmrEventCancel_IMPL
#undef tmrEventDestroy
#define tmrEventDestroy tmrEventDestroy_IMPL
#undef tmrRmCallbackIntrDisable
#define tmrRmCallbackIntrDisable fixtureInterrupt
#undef portMemFree
#define portMemFree fixtureFree
#undef NV_PRINTF
#define NV_PRINTF(...) fixtureLog(__VA_ARGS__)
#undef NV_ASSERT
#define NV_ASSERT(expression) do { if (!(expression)) ++phaseErrors; } while (0)
#define _tmrScheduleCallbackInterrupt fixtureSchedule
#if S540_TIMER_ORDER_BASELINE
#include "baseline-bodies.inc"
#else
#include "candidate-bodies.inc"
#endif

/* operation: void cancel, void destroy, statusful ctrl cancel, ctrl destroy. */
NV_STATUS s540TimerOrderRun(NvU32 operation, NvU32 position, NV_STATUS failure) {
    TMR_EVENT_GENERAL_PARAMS parameters;
    NvU8 *bytes = (NvU8 *)&timer;
    for (NvU64 i = 0; i < sizeof(timer); ++i) bytes[i] = 0;
    bytes = (NvU8 *)events;
    for (NvU64 i = 0; i < sizeof(events); ++i) bytes[i] = 0;
    callCount = destroyCalls = freeCount = eventFreeCount = userFreeCount = 0;
    phaseErrors = identityErrors = sequence = backendSequence = eventFreeSequence = userFreeSequence = 0;
    backendStatus = failure;
    for (NvU32 i = 0; i < 3; ++i) {
        events[i].super.flags = TMR_FLAG_OS_TIMER_QUEUED | TMR_FLAG_USE_OS_TIMER | 0x80000000U;
        events[i].super.pOSTmrCBdata = (void *)(NvUPtr)(0x1000U + i);
        events[i].super.pUserData = &userData[i];
        events[i].pNext = i + 1 < 3 ? &events[i + 1] : NULL;
        events[i].bInUse = NV_TRUE;
        events[i].timens = 12345U + i;
        events[i].startTimeNs = 678U + i;
    }
    timer.pRmActiveOSTimerEventList = events;
    gpu.pOsGpuInfo = (OS_GPU_INFO *)(NvUPtr)0x12345678U;
    target = &events[position];
    copyBytes(before, events, sizeof(events));
    parameters.pEvent = NV_PTR_TO_NvP64(target);
    parameters.returnVal = NV_PTR_TO_NvP64(NULL);
    if (operation == 0) { tmrEventCancel_IMPL(&timer, &target->super); return NV_OK; }
    if (operation == 1) { tmrEventDestroy_IMPL(&timer, &target->super); return NV_OK; }
    if (operation == 2) return tmrCtrlCmdEventCancel(&gpu, &parameters);
    return tmrCtrlCmdEventDestroy(&gpu, &parameters);
}
NvU32 s540TimerOrderCalls(void) { return callCount; }
NvU32 s540TimerOrderDestroyCalls(void) { return destroyCalls; }
NvU32 s540TimerOrderPhaseErrors(void) { return phaseErrors; }
NvU32 s540TimerOrderIdentityErrors(void) { return identityErrors; }
NvU32 s540TimerOrderEventFrees(void) { return eventFreeCount; }
NvU32 s540TimerOrderUserFrees(void) { return userFreeCount; }
NvU32 s540TimerOrderProspectiveHelpers(void) { return S540_TIMER_ORDER_BASELINE ? 0U : 2U; }
NvBool s540TimerOrderFailureRetained(void) {
    return timer.pRmActiveOSTimerEventList == events && sameBytes(events, before, sizeof(events)) && !freeCount;
}
NvBool s540TimerOrderSuccessList(void) {
    NvU32 position = (NvU32)(target - events);
    TMR_EVENT_PVT *head = position == 0 ? &events[1] : &events[0];
    if (timer.pRmActiveOSTimerEventList != head || target->pNext || target->bInUse) return NV_FALSE;
    if (position == 1 && events[0].pNext != &events[2]) return NV_FALSE;
    if (position == 2 && events[1].pNext != NULL) return NV_FALSE;
    return NV_TRUE;
}
NvBool s540TimerOrderSuccessFlags(NvBool destroying) {
    const NvU32 expected = TMR_FLAG_USE_OS_TIMER | 0x80000000U;
    return target->super.flags == expected &&
        target->super.pOSTmrCBdata == (destroying ? NULL : before[target - events].super.pOSTmrCBdata);
}
NvBool s540TimerOrderSuccessFreeSequence(NvBool destroy, NvBool ctrl) {
    return !destroy ? !freeCount :
        eventFreeSequence > backendSequence && (!ctrl || userFreeSequence > eventFreeSequence);
}
