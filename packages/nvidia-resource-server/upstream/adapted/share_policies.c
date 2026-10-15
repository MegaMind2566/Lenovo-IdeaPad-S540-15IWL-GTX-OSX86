/*
 * SPDX-FileCopyrightText: Copyright (c) 1993-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
#include "resserv/rs_server.h"

NV_STATUS
serverInitGlobalSharePolicies
(
    RsServer *pServer
)
{
    RS_SHARE_POLICY sharePolicy;

    // Global default policies, these can be overridden by clients/objects
    portMemSet(&sharePolicy, 0, sizeof(sharePolicy));
    RS_ACCESS_MASK_ADD(&sharePolicy.accessMask, RS_ACCESS_DUP_OBJECT);
    sharePolicy.type = RS_SHARE_TYPE_PID;

    if (listAppendValue(&pServer->defaultInheritedSharePolicyList,
                        &sharePolicy) == NULL)
        return NV_ERR_NO_MEMORY;

    // Internal share policies, these can't be overridden

    // SMC dup policy: Do not allow duping across different SMC partition
    portMemSet(&sharePolicy, 0, sizeof(sharePolicy));
    sharePolicy.type = RS_SHARE_TYPE_SMC_PARTITION;
    sharePolicy.action = RS_SHARE_ACTION_FLAG_REQUIRE;
    RS_ACCESS_MASK_ADD(&sharePolicy.accessMask, RS_ACCESS_DUP_OBJECT);

    if (listAppendValue(&pServer->globalInternalSharePolicyList,
                        &sharePolicy) == NULL)
        return NV_ERR_NO_MEMORY;

    // FM dup policy: Allow FM to dup any user-mode client's resource.
    portMemSet(&sharePolicy, 0, sizeof(sharePolicy));
    sharePolicy.type = RS_SHARE_TYPE_FM_CLIENT;
    RS_ACCESS_MASK_ADD(&sharePolicy.accessMask, RS_ACCESS_DUP_OBJECT);

    if (listAppendValue(&pServer->globalInternalSharePolicyList,
                        &sharePolicy) == NULL)
        return NV_ERR_NO_MEMORY;

    return NV_OK;
}
