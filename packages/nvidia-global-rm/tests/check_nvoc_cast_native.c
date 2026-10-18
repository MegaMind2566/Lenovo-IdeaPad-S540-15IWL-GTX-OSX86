// SPDX-License-Identifier: MIT
// Actual checked NVOC generated headers, compiled as GNU C. The separate
// C++ control uses the exact macro with an explicit reduced layout fixture.
#include "core/system.h"
#include "nvoc/object.h"
#include <stdio.h>

static Object *nextObject;
static NvU32 evaluations;
static Object *sourceExpression(void)
{
    ++evaluations;
    return nextObject;
}

int main(void)
{
    NvU32 checks = 0;
    OBJSYS system = {};
    Object object = {};
#define EXPECT(condition) do { ++checks; if (!(condition)) return 1; } while (0)
    EXPECT(staticCast(NVOC_NULL_OBJECT, Dynamic) == NULL);
    EXPECT(staticCast((OBJSYS *)NULL, Object) == NULL);
    system.__nvoc_pbase_Object = &object;
    system.__nvoc_pbase_OBJSYS = &system;
    object.__nvoc_pbase_Object = &object;
    EXPECT(staticCast(&system, Object) == &object);
    EXPECT(staticCast(&system, OBJSYS) == &system);
    EXPECT(staticCast(&system, Dynamic) == (Dynamic *)&system.__nvoc_rtti);
    EXPECT(staticCast(&object, Object) == &object);
    nextObject = &object;
    evaluations = 0;
    EXPECT(staticCast(sourceExpression(), Dynamic) == (Dynamic *)&object.__nvoc_rtti);
    EXPECT(evaluations == 1);
    nextObject = NULL;
    evaluations = 0;
    EXPECT(staticCast(sourceExpression(), Dynamic) == NULL);
    EXPECT(evaluations == 1);
    const OBJSYS *qualified = &system;
    EXPECT(staticCast(qualified, Object) == &object);
    EXPECT(staticCast(qualified, Dynamic) == (Dynamic *)&system.__nvoc_rtti);
    printf("{\"format\":1,\"component\":\"nvidia-nvoc-cast-native\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"null_and_inheritance\":true,\"single_evaluation\":true,"
           "\"qualified_source\":true,\"gpu_access\":false,"
           "\"kernel_executed\":false}\n", checks);
    return 0;
#undef EXPECT
}
