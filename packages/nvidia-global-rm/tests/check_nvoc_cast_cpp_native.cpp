// SPDX-License-Identifier: MIT
// Reduced C++ compatibility fixture. The builder force-includes the exact
// staticCast macro extracted from the checked original prelude.h. Full original
// NVOC headers are C-only (their qualified anonymous bit-field rejects C++).
#include "nvtypes.h"
#include <cstdio>
struct Dynamic { const void *__nvoc_rtti; };
struct Object {
    union { Dynamic base; const void *__nvoc_rtti; };
    Object *__nvoc_pbase_Object;
};
struct Derived {
    union { Object base; const void *__nvoc_rtti; };
    Object *__nvoc_pbase_Object;
    Derived *__nvoc_pbase_Derived;
};
#define __staticCast_Dynamic(pObj) ((Dynamic *) &(pObj)->__nvoc_rtti)
#define __staticCast_Object(pObj) ((pObj)->__nvoc_pbase_Object)
#define __staticCast_Derived(pObj) ((pObj)->__nvoc_pbase_Derived)
static Object *nextObject;
static NvU32 evaluations;
static Object *sourceExpression() { ++evaluations; return nextObject; }
extern "C" int main()
{
    NvU32 checks = 0;
    Derived derived{};
    Object object{};
#define EXPECT(condition) do { ++checks; if (!(condition)) return 1; } while (0)
    EXPECT(staticCast((Object *)nullptr, Dynamic) == nullptr);
    EXPECT(staticCast((Derived *)nullptr, Object) == nullptr);
    derived.__nvoc_pbase_Object = &object;
    derived.__nvoc_pbase_Derived = &derived;
    object.__nvoc_pbase_Object = &object;
    EXPECT(staticCast(&derived, Object) == &object);
    EXPECT(staticCast(&derived, Derived) == &derived);
    EXPECT(staticCast(&derived, Dynamic) == (Dynamic *)&derived.__nvoc_rtti);
    EXPECT(staticCast(&object, Object) == &object);
    nextObject = &object;
    evaluations = 0;
    EXPECT(staticCast(sourceExpression(), Dynamic) == (Dynamic *)&object.__nvoc_rtti);
    EXPECT(evaluations == 1);
    nextObject = nullptr;
    evaluations = 0;
    EXPECT(staticCast(sourceExpression(), Dynamic) == nullptr);
    EXPECT(evaluations == 1);
    const Derived *qualified = &derived;
    EXPECT(staticCast(qualified, Object) == &object);
    EXPECT(staticCast(qualified, Dynamic) == (Dynamic *)&derived.__nvoc_rtti);
    std::printf("{\"format\":1,\"component\":\"nvidia-nvoc-cast-native\","
           "\"status\":\"passed\",\"checks\":%u,\"failures\":0,"
           "\"null_and_inheritance\":true,\"single_evaluation\":true,"
           "\"qualified_source\":true,\"gpu_access\":false,"
           "\"kernel_executed\":false}\n", checks);
    return 0;
#undef EXPECT
}
