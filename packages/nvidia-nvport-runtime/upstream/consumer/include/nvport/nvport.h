// SPDX-License-Identifier: MIT
// Narrow CPU-only release profile for unmodified NVIDIA containers.
#ifndef S540_CONTAINER_NVPORT_H
#define S540_CONTAINER_NVPORT_H
#include "../../../../../nvidia-nvport-lifecycle/upstream/nvport_lifecycle.h"
#define PORT_IS_CHECKED_BUILD 0
#define PORT_BREAKPOINT() s540NvidiaCallerAssertionFailed("unreachable container dispatch", __FILE__, __LINE__)
#define PORT_DUMP_STACK() s540NvidiaCallerAssertionFailed("invalid container iterator", __FILE__, __LINE__)
#endif
