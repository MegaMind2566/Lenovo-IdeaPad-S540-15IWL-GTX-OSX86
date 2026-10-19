/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_GLOBAL_RM_CENTRAL_POLICY_H
#define S540_NVIDIA_GLOBAL_RM_CENTRAL_POLICY_H
/* These are deliberately selected services of this driver backend. They are
 * not observations that the kernel or physical hardware lacks a feature.
 */
#define S540_GLOBAL_RM_CENTRAL_POLICY_VERSION 1U
#define S540_GLOBAL_RM_RUNTIME_PM_BACKEND 0
#define S540_GLOBAL_RM_KERNEL_SUSPEND_NOTIFIERS 0
#define S540_GLOBAL_RM_PCI_HOT_REMOVE_SERVICE 0
#define S540_GLOBAL_RM_PCI_REQUEST_ATOMICS_SERVICE 0
#define S540_GLOBAL_RM_CXL_CACHE_SERVICE 0
#endif
