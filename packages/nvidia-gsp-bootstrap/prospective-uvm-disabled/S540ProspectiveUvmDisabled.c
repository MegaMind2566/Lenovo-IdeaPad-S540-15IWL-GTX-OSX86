/* SPDX-License-Identifier: MIT */
/* Isolated selected-backend candidate. Not in the production source list. */
#include "nv.h"

#if !defined(S540_NVIDIA_NO_UVM_BACKEND) || S540_NVIDIA_NO_UVM_BACKEND != 1
#error "This candidate requires an explicit selected no-UVM backend."
#endif
#if defined(NV_UVM_ENABLE)
#error "The official disabled-UVM branches cannot serve an enabled UVM backend."
#endif

/* Exact effects of pinned nv.c's !defined(NV_UVM_ENABLE) branches. These
 * functions do not represent a delivered interrupt or a completed P2P drain.
 */
void NV_API_CALL nv_schedule_uvm_isr(nv_state_t *nv)
{
    (void)nv;
}

NV_STATUS NV_API_CALL nv_schedule_uvm_drain_p2p(NvU8 *uuid)
{
    (void)uuid;
    return NV_ERR_NOT_SUPPORTED;
}

void NV_API_CALL nv_schedule_uvm_resume_p2p(NvU8 *uuid)
{
    (void)uuid;
}
