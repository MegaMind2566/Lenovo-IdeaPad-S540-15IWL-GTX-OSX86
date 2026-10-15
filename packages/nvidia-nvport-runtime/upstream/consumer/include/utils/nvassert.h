// SPDX-License-Identifier: MIT
// Explicit release-profile assertion bridge; not the full NVPort debug API.
// Fallible upstream ASSERT_OR_RETURN paths retain their diagnostic and return.
// Mandatory invariants terminate through the existing Darwin/native bridge.
#ifndef S540_CONTAINER_NVASSERT_H
#define S540_CONTAINER_NVASSERT_H
#include "nvport/nvport.h"
#define NV_CHECKED_ONLY(statement)
#define NV_ASSERT_CHECKED(expression) ((void)0)
#define NV_ASSERT(expression) do { if (!(expression)) s540NvidiaCallerAssertionFailed(#expression, __FILE__, __LINE__); } while (0)
#define NV_ASSERT_FAILED(message) s540NvidiaCallerAssertionFailed(message, __FILE__, __LINE__)
#define NV_ASSERT_OR_RETURN(expression, value) do { if (!(expression)) { portDbgPrintf("NVIDIA container: %s (%s:%d)\n", #expression, __FILE__, __LINE__); return (value); } } while (0)
#define NV_ASSERT_OR_RETURN_VOID(expression) do { if (!(expression)) { portDbgPrintf("NVIDIA container: %s (%s:%d)\n", #expression, __FILE__, __LINE__); return; } } while (0)
#endif
