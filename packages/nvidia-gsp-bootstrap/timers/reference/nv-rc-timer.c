/*
 * SPDX-FileCopyrightText: Copyright (c) 1999-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 */

#include <linux/module.h>  // for MODULE_FIRMWARE

// must precede "nv.h" and "nv-firmware.h" includes
#define NV_FIRMWARE_FOR_NAME(name)  "nvidia/" NV_VERSION_STRING "/" name ".bin"
#define NV_FIRMWARE_DECLARE_GSP(name) \
static void
nvidia_rc_timer_callback(
    struct nv_timer *nv_timer
)
{
    nv_linux_state_t *nvl = container_of(nv_timer, nv_linux_state_t, rc_timer);
    nv_state_t *nv = NV_STATE_PTR(nvl);
    nvidia_stack_t *sp = nvl->sp[NV_DEV_STACK_TIMER];
    NV_STATUS status;

    status = nv_check_gpu_state(nv);
    if (status == NV_ERR_GPU_IS_LOST)
    {
        nv_printf(NV_DBG_INFO,
            "NVRM: GPU is lost, skipping device timer callbacks\n");
        return;
    }

    if (rm_run_rc_callback(sp, nv) == NV_OK)
    {
        // set another timeout 1 sec in the future:
        mod_timer(&nvl->rc_timer.kernel_timer, jiffies + HZ);
    }
}
int NV_API_CALL nv_start_rc_timer(
    nv_state_t *nv
)
{
    nv_linux_state_t *nvl = NV_GET_NVL_FROM_NV_STATE(nv);

    if (nv->rc_timer_enabled)
        return -1;

    nv_printf(NV_DBG_INFO, "NVRM: initializing rc timer\n");

    nv_timer_setup(&nvl->rc_timer, nvidia_rc_timer_callback);

    nv->rc_timer_enabled = 1;

    // set the timeout for 1 second in the future:
    mod_timer(&nvl->rc_timer.kernel_timer, jiffies + HZ);

    nv_printf(NV_DBG_INFO, "NVRM: rc timer initialized\n");

    return 0;
}

int NV_API_CALL nv_stop_rc_timer(
    nv_state_t *nv
)
{
    nv_linux_state_t *nvl = NV_GET_NVL_FROM_NV_STATE(nv);

    if (!nv->rc_timer_enabled)
        return -1;

    nv_printf(NV_DBG_INFO, "NVRM: stopping rc timer\n");
    nv->rc_timer_enabled = 0;
    nv_timer_delete_sync(&nvl->rc_timer.kernel_timer);
    nv_printf(NV_DBG_INFO, "NVRM: rc timer stopped\n");

    return 0;
}
