/* SPDX-License-Identifier: MIT */
/* Typed original-entry tripwires, compiled against the pinned full nv.h. The
 * bootstrap preparation/refusal harness must never execute any of these. */
#include "nv.h"
#include "os-interface.h"
#include "../../nvidia-global-rm/src/S540NvidiaGlobalRm.h"
#include <stdlib.h>
void *NV_API_CALL os_mem_set(void *out, NvU8 value, NvU32 bytes) {
    volatile NvU8 *p = out;
    while (bytes--) *p++ = value;
    return out;
}
void *NV_API_CALL os_mem_copy(void *out, const void *in, NvU32 bytes) {
    volatile NvU8 *to = out;
    const volatile NvU8 *from = in;
    while (bytes--) *to++ = *from++;
    return out;
}
NvBool s540GlobalRmIsInitialized(void) { return NV_FALSE; }
NV_STATUS s540GlobalRmInitialize(S540NvidiaGlobalRmResult *out) {
    (void)out; abort();
}
void s540GlobalRmShutdown(S540NvidiaGlobalRmResult *out) { (void)out; abort(); }
void NV_API_CALL rm_execute_work_item(nvidia_stack_t *stack, void *item) {
    (void)stack; (void)item; abort();
}
NvBool NV_API_CALL rm_init_event_locks(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NV_STATUS NV_API_CALL rm_is_supported_device(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NvBool NV_API_CALL rm_init_private_state(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NvBool NV_API_CALL rm_init_adapter(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
void NV_API_CALL rm_disable_adapter(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
void NV_API_CALL rm_shutdown_adapter(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
void NV_API_CALL rm_free_private_state(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
void NV_API_CALL rm_destroy_event_locks(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NV_STATUS NV_API_CALL rm_run_rc_callback(nvidia_stack_t *stack, nv_state_t *nv) {
    (void)stack; (void)nv; abort();
}
NV_STATUS NV_API_CALL rm_run_nano_timer_callback(nvidia_stack_t *stack,
    nv_state_t *nv, void *event) { (void)stack; (void)nv; (void)event; abort(); }
