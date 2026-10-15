// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_ATOMIC_NATIVE_CHECK_H
#define S540_NVIDIA_ATOMIC_NATIVE_CHECK_H

#include "../src/S540NvidiaAtomic.h"
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <unistd.h>

#ifdef __cplusplus
#define STATIC_ASSERT(c, m) static_assert(c, m)
#define ALIGNOF(t) alignof(t)
#define CHECK_MODE "c++clang"
#else
#define STATIC_ASSERT(c, m) _Static_assert(c, m)
#define ALIGNOF(t) _Alignof(t)
#define CHECK_MODE "c11"
#endif

STATIC_ASSERT(sizeof(NvU32) == 4 && sizeof(NvS32) == 4, "32-bit NVIDIA ABI");
STATIC_ASSERT(sizeof(NvU64) == 8 && sizeof(NvS64) == 8, "64-bit NVIDIA ABI");
STATIC_ASSERT(sizeof(NvSPtr) == sizeof(void *), "pointer-sized NVIDIA ABI");
STATIC_ASSERT(ALIGNOF(PORT_ATOMIC NvU32) >= 4, "32-bit atomic alignment");
STATIC_ASSERT(ALIGNOF(PORT_ATOMIC NvU64) >= 8, "64-bit atomic alignment");
STATIC_ASSERT(sizeof(PORT_ATOMIC NvU32) == 4, "32-bit atomic size");
STATIC_ASSERT(sizeof(PORT_ATOMIC NvU64) == 8, "64-bit atomic size");
STATIC_ASSERT(__atomic_always_lock_free(4, 0), "32-bit atomics must be lock-free");
STATIC_ASSERT(__atomic_always_lock_free(8, 0), "64-bit atomics must be lock-free");

static unsigned checks;
#define CHECK(c) do { ++checks; if (!(c)) { \
    fprintf(stderr, "Atomic check failed at line %d: %s\n", __LINE__, #c); \
    return 1; } } while (0)

#if NVPORT_HAS_C11_ATOMICS
#define LOAD32(p) portAtomicGet(p)
#define LOAD64(p) portAtomicGet(p)
#define PUBLISH(p, v) portAtomicSet(p, v, memory_order_release)
#define OBSERVE(p) portAtomicGet(p, memory_order_acquire)
#else
// The unchanged Clang API has no separate load function. Its zero OR is an
// atomic read-modify-write, including the upstream sequentially consistent fence.
#define LOAD32(p) portAtomicOrU32(p, 0U)
#define LOAD64(p) portAtomicExOrU64(p, 0ULL)
#define PUBLISH(p, v) portAtomicSetU32(p, v)
#define OBSERVE(p) LOAD32(p)
#endif

#define CHECK_FAMILY(type, set, add, sub, inc, dec, xorop, orop, andop, cas) do { \
    PORT_ATOMIC type value = 0; \
    set(&value, (type)5); \
    CHECK(add(&value, (type)3) == (type)8); \
    CHECK(sub(&value, (type)2) == (type)6); \
    CHECK(inc(&value) == (type)7); \
    CHECK(dec(&value) == (type)6); \
    CHECK(xorop(&value, (type)3) == (type)5); \
    CHECK(orop(&value, (type)8) == (type)13); \
    CHECK(andop(&value, (type)7) == (type)5); \
    CHECK(!cas(&value, (type)9, (type)4)); \
    CHECK(orop(&value, (type)0) == (type)5); \
    CHECK(cas(&value, (type)12, (type)5)); \
    CHECK(orop(&value, (type)0) == (type)12); \
} while (0)

static int check_values(void)
{
    CHECK_FAMILY(NvU32, portAtomicSetU32, portAtomicAddU32, portAtomicSubU32,
                 portAtomicIncrementU32, portAtomicDecrementU32, portAtomicXorU32,
                 portAtomicOrU32, portAtomicAndU32, portAtomicCompareAndSwapU32);
    CHECK_FAMILY(NvS32, portAtomicSetS32, portAtomicAddS32, portAtomicSubS32,
                 portAtomicIncrementS32, portAtomicDecrementS32, portAtomicXorS32,
                 portAtomicOrS32, portAtomicAndS32, portAtomicCompareAndSwapS32);
    CHECK_FAMILY(NvU64, portAtomicExSetU64, portAtomicExAddU64, portAtomicExSubU64,
                 portAtomicExIncrementU64, portAtomicExDecrementU64, portAtomicExXorU64,
                 portAtomicExOrU64, portAtomicExAndU64, portAtomicExCompareAndSwapU64);
    CHECK_FAMILY(NvS64, portAtomicExSetS64, portAtomicExAddS64, portAtomicExSubS64,
                 portAtomicExIncrementS64, portAtomicExDecrementS64, portAtomicExXorS64,
                 portAtomicExOrS64, portAtomicExAndS64, portAtomicExCompareAndSwapS64);

    PORT_ATOMIC NvU32 u32 = 0;
    PORT_ATOMIC NvU64 u64 = 0;
    PORT_ATOMIC NvS32 s32 = 0;
    PORT_ATOMIC NvS64 s64 = 0;
    PORT_ATOMIC NvSPtr size = 0;
    portAtomicSetU32(&u32, 0xffffffffU);
    CHECK(portAtomicAddU32(&u32, 1U) == 0U);
    CHECK(portAtomicSubU32(&u32, 1U) == 0xffffffffU);
    CHECK(portAtomicIncrementU32(&u32) == 0U);
    CHECK(portAtomicDecrementU32(&u32) == 0xffffffffU);
    portAtomicExSetU64(&u64, 0xffffffffffffffffULL);
    CHECK(portAtomicExAddU64(&u64, 1ULL) == 0ULL);
    CHECK(portAtomicExSubU64(&u64, 1ULL) == 0xffffffffffffffffULL);
    CHECK(portAtomicExIncrementU64(&u64) == 0ULL);
    CHECK(portAtomicExDecrementU64(&u64) == 0xffffffffffffffffULL);
    // Signed checks stay within range: upstream fetch-add's return expression
    // is ordinary signed arithmetic and is not an overflow contract.
    portAtomicSetS32(&s32, 0x7ffffffe);
    CHECK(portAtomicIncrementS32(&s32) == 0x7fffffff);
    portAtomicSetS32(&s32, -0x7fffffff);
    CHECK(portAtomicDecrementS32(&s32) == (-0x7fffffff - 1));
    portAtomicExSetS64(&s64, 0x7ffffffffffffffeLL);
    CHECK(portAtomicExIncrementS64(&s64) == 0x7fffffffffffffffLL);
    portAtomicExSetS64(&s64, -0x7fffffffffffffffLL);
    CHECK(portAtomicExDecrementS64(&s64) == (-0x7fffffffffffffffLL - 1));
    portAtomicSetSize(&size, (NvSPtr)4);
    CHECK(portAtomicAddSize(&size, (NvSPtr)3) == 7);
    CHECK(portAtomicSubSize(&size, (NvSPtr)2) == 5);
    CHECK(portAtomicCompareAndSwapSize(&size, (NvSPtr)9, (NvSPtr)5));
    CHECK(!portAtomicCompareAndSwapSize(&size, (NvSPtr)1, (NvSPtr)5));
    CHECK(portAtomicGetSize(&size) == 9);
    portAtomicMemoryFenceLoad();
    portAtomicMemoryFenceStore();
    portAtomicMemoryFenceFull();
    portAtomicTimerBarrier();
    CHECK(1);
    return 0;
}

enum { THREAD_COUNT = 4, ITERATIONS = 8192, PUBLICATIONS = 4096 };
static PORT_ATOMIC NvU32 count32;
static PORT_ATOMIC NvU64 count64;
static PORT_ATOMIC NvU64 cas_count;
static PORT_ATOMIC NvU32 published;
static NvU64 payload;
static unsigned publication_errors;

static void *increment_worker(void *unused)
{
    (void)unused;
    for (unsigned i = 0; i < ITERATIONS; ++i)
    {
        portAtomicIncrementU32(&count32);
        portAtomicExIncrementU64(&count64);
        NvU64 current = LOAD64(&cas_count);
        while (!portAtomicExCompareAndSwapU64(&cas_count, current + 1ULL, current))
            current = LOAD64(&cas_count);
    }
    return NULL;
}

static void *publish_worker(void *unused)
{
    (void)unused;
    for (NvU64 i = 1; i <= PUBLICATIONS; ++i)
    {
        while (OBSERVE(&published) != 0U)
            sched_yield();
        payload = i * 17ULL;
        portAtomicMemoryFenceStore();
        PUBLISH(&published, 1U);
    }
    return NULL;
}

static void *observe_worker(void *unused)
{
    (void)unused;
    for (NvU64 i = 1; i <= PUBLICATIONS; ++i)
    {
        while (OBSERVE(&published) != 1U)
            sched_yield();
        portAtomicMemoryFenceLoad();
        if (payload != i * 17ULL)
            ++publication_errors;
        PUBLISH(&published, 0U);
    }
    return NULL;
}

static int check_threads(void)
{
    pthread_t workers[THREAD_COUNT];
    for (unsigned i = 0; i < THREAD_COUNT; ++i)
        CHECK(pthread_create(&workers[i], NULL, increment_worker, NULL) == 0);
    for (unsigned i = 0; i < THREAD_COUNT; ++i)
        CHECK(pthread_join(workers[i], NULL) == 0);
    CHECK(LOAD32(&count32) == THREAD_COUNT * ITERATIONS);
    CHECK(LOAD64(&count64) == THREAD_COUNT * ITERATIONS);
    CHECK(LOAD64(&cas_count) == THREAD_COUNT * ITERATIONS);
    pthread_t writer, reader;
    CHECK(pthread_create(&writer, NULL, publish_worker, NULL) == 0);
    CHECK(pthread_create(&reader, NULL, observe_worker, NULL) == 0);
    CHECK(pthread_join(writer, NULL) == 0);
    CHECK(pthread_join(reader, NULL) == 0);
    CHECK(publication_errors == 0);
    CHECK(OBSERVE(&published) == 0U);
    return 0;
}

int main(void)
{
    // A broken synchronization implementation must fail this process rather
    // than leaving the native CI job waiting indefinitely.
    alarm(20);
    if (check_values() || check_threads())
        return 1;
    alarm(0);
    printf("{\"format\":1,\"status\":\"passed\",\"mode\":\"%s\",\"checks\":%u,"
           "\"threads\":%u,\"increments_per_thread\":%u,\"publications\":%u,"
           "\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\","
           "\"gpu_access\":false}\n", CHECK_MODE, checks, THREAD_COUNT, ITERATIONS, PUBLICATIONS);
    return 0;
}

#endif
