/* SPDX-License-Identifier: MIT */
/* Source-only prospective loader evidence; this file does not enable RM. */
#include "nv.h"
#include "osapi.h"
#include "core/core.h"
#include "S540NvidiaGspOriginalRoots.h"

#if !defined(RmShutdownRm) || !defined(coreInitializeRm) || !defined(rm_init_adapter)
#error "Compile with the reviewed original RM private namespace header."
#endif

/*
 * Keep the exact 25 roots derived from the original execution closure. Every
 * pointer obtains its full type from its actual upstream declaration. There
 * are no replacement prototypes, erased callback types, or function calls.
 */
#define S540_PROSPECTIVE_ORIGINAL_ROOTS(X) \
    X(RmDestroyRegistry) \
    X(RmPackageRegistry) \
    X(RmReadRegistryDword) \
    X(RmShutdownRm) \
    X(RmWriteRegistryDword) \
    X(coreInitializeRm) \
    X(rm_acquire_api_lock) \
    X(rm_acquire_gpu_lock) \
    X(rm_destroy_event_locks) \
    X(rm_disable_adapter) \
    X(rm_execute_work_item) \
    X(rm_free_private_state) \
    X(rm_gpu_handle_mmu_faults) \
    X(rm_init_adapter) \
    X(rm_init_event_locks) \
    X(rm_init_private_state) \
    X(rm_is_supported_device) \
    X(rm_isr) \
    X(rm_isr_bh) \
    X(rm_isr_bh_unlocked) \
    X(rm_release_api_lock) \
    X(rm_release_gpu_lock) \
    X(rm_run_nano_timer_callback) \
    X(rm_run_rc_callback) \
    X(rm_shutdown_adapter)

#define S540_ROOT_FIELD(name) __typeof__(&name) name;
typedef struct {
    S540_PROSPECTIVE_ORIGINAL_ROOTS(S540_ROOT_FIELD)
} S540ProspectiveOriginalRootReferences;
#undef S540_ROOT_FIELD

/*
 * Clang's Mach-O 'used' lowering sets N_NO_DEAD_STRIP on this static object.
 * The object checker verifies that flag and each actual pointer relocation.
 * Volatile reads below keep a caller's metadata test dependent on this table.
 */
static const volatile S540ProspectiveOriginalRootReferences
    s540ProspectiveOriginalRoots __attribute__((used)) = {
#define S540_ROOT_ADDRESS(name) .name = &name,
    S540_PROSPECTIVE_ORIGINAL_ROOTS(S540_ROOT_ADDRESS)
#undef S540_ROOT_ADDRESS
};

#define S540_ROOT_ONE(name) + 1
enum {
    S540_PROSPECTIVE_ORIGINAL_ROOT_COUNT =
        0 S540_PROSPECTIVE_ORIGINAL_ROOTS(S540_ROOT_ONE)
};
#undef S540_ROOT_ONE
_Static_assert(S540_PROSPECTIVE_ORIGINAL_ROOT_COUNT == 25,
               "The reviewed original execution root inventory must have 25 entries.");

NvU32 s540ProspectiveRetainedRootCount(void)
{
    return S540_PROSPECTIVE_ORIGINAL_ROOT_COUNT;
}

NvBool s540ProspectiveRetainedRootsPresent(void)
{
    NvU32 present = 0;
#define S540_ROOT_PRESENT(name) present += s540ProspectiveOriginalRoots.name != 0;
    S540_PROSPECTIVE_ORIGINAL_ROOTS(S540_ROOT_PRESENT)
#undef S540_ROOT_PRESENT
    return present == S540_PROSPECTIVE_ORIGINAL_ROOT_COUNT;
}

#undef S540_PROSPECTIVE_ORIGINAL_ROOTS
