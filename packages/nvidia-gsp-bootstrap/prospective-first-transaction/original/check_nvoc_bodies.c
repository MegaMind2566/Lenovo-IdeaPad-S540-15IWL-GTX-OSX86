/* SPDX-License-Identifier: MIT */
/* Exact generic deletion/constructor bodies with actual NVOC types. Object
 * metadata/allocator/record endpoints are fixtures, not registered-owner proof. */
#include "nv.h"
#include "nvoc/object.h"
#include "nvoc/rtti.h"
#include "gpu/timer/objtmr.h"
#include "gpu/gsp/kernel_gsp.h"
#include "S540NvidiaGspFirstTransactionOriginal.h"
#include "control_types.h"

static Object parentObject, originalObject;
static OBJTMR timerObject;
static S540OriginalControlResult result;
static NvU32 mode, guardCalls;
static const struct NVOC_RTTI metadata = {0};
static void zeros(void *p, NvU64 n) { NvU8 *b=p; for(NvU64 i=0;i<n;++i)b[i]=0; }
NV_STATUS s540FirstTxnCheckBeforeDeleteObject(const void *object) {
    ++guardCalls;
    if (object == NULL) ++result.identityErrors;
    if (mode == 0 || mode == 4) return NV_ERR_NOT_READY;
    if (mode == 1 && guardCalls > 1) return NV_ERR_NOT_SUPPORTED;
    return NV_OK;
}
static void fixtureDestruct(Dynamic *object) { (void)object; ++result.originalDestructors; }
static void fixtureFree(void *pointer) { if(pointer != &originalObject) ++result.identityErrors; ++result.originalFrees; }
static Dynamic *fixtureFullyDerive(Dynamic *object) { return object; }
#undef dynamicCast
#define dynamicCast(p, type) ((type *)(p))
#undef __nvoc_destructFromBase
#define __nvoc_destructFromBase fixtureDestruct
#undef __nvoc_fullyDerive
#define __nvoc_fullyDerive fixtureFullyDerive
#undef objRemoveChild
#define objRemoveChild(p, c) do { ++result.originalUnlinks; objRemoveChild_IMPL((p), (c)); } while (0)
#undef objGetChild
#define objGetChild objGetChild_IMPL
#undef portMemFree
#define portMemFree fixtureFree
#undef NV_ASSERT
#define NV_ASSERT(v) do { if (!(v)) ++result.identityErrors; } while (0)
#undef NV_PRINTF_STRINGS_ALLOWED
#define NV_PRINTF_STRINGS_ALLOWED 0
#undef PORT_BREAKPOINT_CHECKED
#define PORT_BREAKPOINT_CHECKED() (++result.identityErrors)
#include "actual-nvoc-bodies.inc"

static NV_STATUS ctorBase(OBJENGSTATE *object) { (void)object; return mode == 3 ? NV_ERR_TIMEOUT : NV_OK; }
static NV_STATUS ctorIntr(IntrService *object) { (void)object; return mode == 4 ? NV_ERR_IN_USE : NV_OK; }
static void ctorData(OBJTMR *object, GpuHalspecOwner *g, RmHalspecOwner *r) { (void)object; (void)g; (void)r; }
static void dtorBase(Dynamic *object) { (void)object; ++result.constructorBaseDestructors; }
#undef __nvoc_ctor_OBJENGSTATE
#define __nvoc_ctor_OBJENGSTATE ctorBase
#undef __nvoc_ctor_IntrService
#define __nvoc_ctor_IntrService ctorIntr
#undef __nvoc_dtor_OBJENGSTATE
#define __nvoc_dtor_OBJENGSTATE dtorBase
#undef __nvoc_init_dataField_OBJTMR
#define __nvoc_init_dataField_OBJTMR ctorData
#include "actual-timer-ctor-body.inc"

void s540OriginalControlNvoc(NvU32 which, S540OriginalControlResult *out) {
    zeros(&result,sizeof(result)); zeros(&parentObject,sizeof(parentObject)); zeros(&originalObject,sizeof(originalObject));
    mode=which; guardCalls=0;
    originalObject.__nvoc_rtti = &metadata;
    originalObject.pParent=&parentObject; parentObject.childTree.pChild=&originalObject;
    result.guardStatus = s540FirstTxnObjDeleteChecked((Dynamic *)&originalObject);
    result.ownershipPreserved = originalObject.pParent == &parentObject && parentObject.childTree.pChild == &originalObject;
    *out=result;
}
void s540OriginalControlCtor(NvU32 which, S540OriginalControlResult *out) {
    zeros(&result,sizeof(result)); zeros(&timerObject,sizeof(timerObject)); guardCalls=0;
    mode=which;
    result.guardStatus=__nvoc_ctor_OBJTMR(&timerObject,NULL,NULL);
    *out=result;
}
