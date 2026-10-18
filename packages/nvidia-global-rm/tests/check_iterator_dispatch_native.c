// SPDX-License-Identifier: MIT
// Actual checked container type/tag/iterator definitions with explicit typed
// callback fixtures. Complete original RM controls separately exercise real
// multimap iteration through construction and ResourceServer cleanup.
#include "containers/vector.h"
#include <stdio.h>
MAKE_VECTOR(NativeDispatchVector, NvU32);
static NativeDispatchVector container;
static NvU32 containerEvaluations, calls;
static Vector *observedBase;
static void *observedFirst, *observedLast;
static NvU64 observedFirstIndex, observedLastIndex;
static NativeDispatchVector *containerExpression(void)
{
    ++containerEvaluations;
    return &container;
}
static VectorIterBase pointerRange(Vector *base, void *first, void *last)
{
    VectorIterBase result = {0};
    ++calls;
    observedBase = base;
    observedFirst = first;
    observedLast = last;
    result.pValue = first;
    result.pVector = base;
    result.firstIndex = 17;
    result.lastIndex = 29;
    return result;
}
static VectorIterBase indexRange(Vector *base, NvU64 first, NvU64 last)
{
    VectorIterBase result = {0};
    ++calls;
    observedBase = base;
    observedFirstIndex = first;
    observedLastIndex = last;
    result.pVector = base;
    result.firstIndex = 37;
    result.lastIndex = 43;
    return result;
}
int main(void)
{
    NvU32 checks = 0, values[2] = {1, 2};
    NativeDispatchVectorIter result;
#define EXPECT(condition) do { ++checks; if (!(condition)) return 1; } while (0)
    result = CONT_ITER_RANGE(containerExpression(), pointerRange,
                             &values[0], &values[1], vectIsValid_IMPL);
    EXPECT(calls == 1);
    EXPECT(containerEvaluations == 1);
    EXPECT(observedBase == &container.real.base);
    EXPECT(observedFirst == &values[0] && observedLast == &values[1]);
    EXPECT(result.iter.pVector == &container.real.base);
    EXPECT(result.pValue == &values[0]);
    EXPECT(result.iter.firstIndex == 17 && result.iter.lastIndex == 29);
    calls = containerEvaluations = 0;
    result = CONT_ITER_RANGE_INDEX(containerExpression(), indexRange,
                                   0x100000001ULL, 0x200000003ULL, vectIsValid_IMPL);
    EXPECT(calls == 1);
    EXPECT(containerEvaluations == 1);
    EXPECT(observedBase == &container.real.base);
    EXPECT(observedFirstIndex == 0x100000001ULL && observedLastIndex == 0x200000003ULL);
    EXPECT(result.iter.pVector == &container.real.base);
    EXPECT(result.iter.firstIndex == 37 && result.iter.lastIndex == 43);
    printf("{\"format\":1,\"component\":\"nvidia-iterator-dispatch-native\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"actual_container_headers\":true,\"typed_callback_fixture\":true,"
           "\"pointer_and_index_ranges\":true,\"single_container_evaluation\":true,"
           "\"gpu_access\":false,\"kernel_executed\":false}\n", checks);
    return 0;
#undef EXPECT
}
