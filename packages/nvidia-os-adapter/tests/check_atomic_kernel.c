// SPDX-License-Identifier: MIT
// Compile this same consumer as GNU C11 and C++17. It is a compile check,
// not a new NVIDIA ABI or a loaded kernel driver.
#include "../src/S540NvidiaAtomic.h"

#ifdef __cplusplus
extern "C" {
#endif

NvU64 S540NvidiaAtomicCompileCheck(PORT_ATOMIC NvU32 *p32,
                                 PORT_ATOMIC NvU64 *p64,
                                 PORT_ATOMIC NvS32 *ps32,
                                 PORT_ATOMIC NvS64 *ps64)
{
    NvU64 result = 0;
    portAtomicSetU32(p32, 7U);
    result += portAtomicAddU32(p32, 3U);
    result += portAtomicSubU32(p32, 2U);
    result += portAtomicIncrementU32(p32);
    result += portAtomicDecrementU32(p32);
    result += portAtomicXorU32(p32, 1U);
    result += portAtomicOrU32(p32, 2U);
    result += portAtomicAndU32(p32, 15U);
    result += portAtomicCompareAndSwapU32(p32, 3U, 11U);
    portAtomicExSetU64(p64, 7ULL);
    result += portAtomicExAddU64(p64, 3ULL);
    result += portAtomicExSubU64(p64, 2ULL);
    result += portAtomicExIncrementU64(p64);
    result += portAtomicExDecrementU64(p64);
    result += portAtomicExXorU64(p64, 1ULL);
    result += portAtomicExOrU64(p64, 2ULL);
    result += portAtomicExAndU64(p64, 15ULL);
    result += portAtomicExCompareAndSwapU64(p64, 3ULL, 11ULL);
    portAtomicSetS32(ps32, -7);
    result += (NvU32)portAtomicAddS32(ps32, 3);
    result += (NvU32)portAtomicSubS32(ps32, 2);
    result += (NvU32)portAtomicIncrementS32(ps32);
    result += (NvU32)portAtomicDecrementS32(ps32);
    result += (NvU32)portAtomicXorS32(ps32, 1);
    result += (NvU32)portAtomicOrS32(ps32, 2);
    result += (NvU32)portAtomicAndS32(ps32, 15);
    result += portAtomicCompareAndSwapS32(ps32, 3, 11);
    portAtomicExSetS64(ps64, -7LL);
    result += (NvU64)portAtomicExAddS64(ps64, 3LL);
    result += (NvU64)portAtomicExSubS64(ps64, 2LL);
    result += (NvU64)portAtomicExIncrementS64(ps64);
    result += (NvU64)portAtomicExDecrementS64(ps64);
    result += (NvU64)portAtomicExXorS64(ps64, 1LL);
    result += (NvU64)portAtomicExOrS64(ps64, 2LL);
    result += (NvU64)portAtomicExAndS64(ps64, 15LL);
    result += portAtomicExCompareAndSwapS64(ps64, 3LL, 11LL);
    portAtomicMemoryFenceLoad();
    portAtomicMemoryFenceStore();
    portAtomicMemoryFenceFull();
    portAtomicTimerBarrier();
    return result;
}

#ifdef __cplusplus
}
#endif
