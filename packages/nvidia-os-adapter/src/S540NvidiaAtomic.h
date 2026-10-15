// SPDX-License-Identifier: MIT
// Configure the unchanged NVIDIA atomic header for the Intel Clang port.
#ifndef S540_NVIDIA_ATOMIC_H
#define S540_NVIDIA_ATOMIC_H

#if !defined(__clang__) || !defined(__x86_64__)
#error "The current atomic integration requires Intel x86_64 Clang."
#endif

#if defined(PORT_IS_KERNEL_BUILD) && PORT_IS_KERNEL_BUILD != 1
#error "This integration checks NVIDIA's kernel-build atomic interface."
#endif
#ifndef PORT_IS_KERNEL_BUILD
#define PORT_IS_KERNEL_BUILD 1
#endif
#ifndef PORT_IS_CHECKED_BUILD
#define PORT_IS_CHECKED_BUILD 0
#endif
#if defined(PORT_MODULE_atomic) && PORT_MODULE_atomic != 1
#error "The atomic module must be enabled."
#endif
#ifndef PORT_MODULE_atomic
#define PORT_MODULE_atomic 1
#endif

#include "nvport/nvport.h"

#if !NVCPU_IS_X86_64 || !NVCPU_IS_64_BITS || !PORT_COMPILER_IS_CLANG
#error "Unexpected upstream CPU/compiler selection."
#endif
#if defined(__cplusplus)
#if NVPORT_HAS_C11_ATOMICS || !defined(_NVPORT_ATOMIC_CLANG_H_)
#error "C++ must select the original Clang intrinsic implementation."
#endif
#else
#if !NVPORT_HAS_C11_ATOMICS || !defined(NVPORT_ATOMIC_C11_H)
#error "C must select the original C11 implementation."
#endif
#if __STDC_HOSTED__
#error "Compile the C integration freestanding to use the pinned atomic header closure."
#endif
#endif

#endif
