// SPDX-License-Identifier: MIT
#ifndef S540_NVIDIA_RESOURCE_EXERCISE_H
#define S540_NVIDIA_RESOURCE_EXERCISE_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct S540_RESOURCE_RESULT {
    NvU32 checks, failures;
    NvBool server, clients, resources, sharing, control, cleanup;
} S540_RESOURCE_RESULT;
// Internal, externally serialized entry. Requires the real NVPort core and
// backend TLS initialized. It constructs and destroys actual NVIDIA NVOC objects.
void s540ResourceExercise(S540_RESOURCE_RESULT *result);
// Exercise the adapted original constructor, then fully release any success.
NvBool s540ResourceConstructorProbe(void);
#ifdef __cplusplus
}
#endif
#endif
