// SPDX-License-Identifier: MIT
#pragma once
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
#include <cstdio>
#include <cstring>
#define NV_ASSERT_OK_OR_RETURN(e) do { NV_STATUS s = (e); if (s != NV_OK) return s; } while (0)
#define NV_ASSERT_OR_RETURN(c, e) do { if (!(c)) return (e); } while (0)
#define NV_ASSERT_OK(e) ((void)(e))
#define NV_PRINTF(...) ((void)0)
#define NV_PFALCON_FALCON_RM 0U
struct OBJGPU { NvU32 chipId0 = 0x1234; };
struct KernelFalcon {};
struct nv_cap_t { unsigned id; };
using OS_GPU_INFO = NvU32;
struct OS_RM_CAPS { nv_cap_t *caps[2]; };
enum { OS_RM_CAP_GPU_DIR = 0, OS_RM_CAP_GPU_MIG_DIR = 1, OS_RM_CAP_GPU_COUNT = 2,
       OS_RUGO = 1, OS_XUGO = 2 };
static nv_cap_t rootCap{0}, gpuCap{1}, migCap{2};
static nv_cap_t *nvidia_caps_root;
struct Fixture {
    NV_STATUS preWait = NV_OK, resetHw = NV_OK, resetWait = NV_OK, allocation = NV_OK;
    unsigned preCalls = 0, resetCalls = 0, waitCalls = 0, switches = 0, writes = 0;
    unsigned getters = 0, allocations = 0, directories = 0, unregisters = 0;
    unsigned directoryFailure = 0, order = 0, getterOrder = 0, allocationOrder = 0;
    char gpuName[16] = {}, migName[16] = {};
    OS_RM_CAPS caps{};
} f;
inline NV_STATUS kflcnPreResetWait_HAL(OBJGPU *, KernelFalcon *) { ++f.preCalls; return f.preWait; }
inline NV_STATUS kflcnResetHw(OBJGPU *, KernelFalcon *) { ++f.resetCalls; return f.resetHw; }
inline NV_STATUS kflcnWaitForResetToFinish_HAL(OBJGPU *, KernelFalcon *) { ++f.waitCalls; return f.resetWait; }
inline void kflcnSwitchToFalcon_HAL(OBJGPU *, KernelFalcon *) { ++f.switches; }
inline void kflcnRegWrite_HAL(OBJGPU *, KernelFalcon *, NvU32, NvU32) { ++f.writes; }
inline NvU32 nv_get_dev_minor(OS_GPU_INFO *p) { ++f.getters; f.getterOrder = ++f.order; return *p; }
inline NV_STATUS _allocOsRmCaps(OS_RM_CAPS **p, unsigned) { ++f.allocations; f.allocationOrder = ++f.order; if (f.allocation == NV_OK) *p = &f.caps; return f.allocation; }
#define os_snprintf std::snprintf
inline nv_cap_t *os_nv_cap_create_dir_entry(nv_cap_t *, const char *name, unsigned) {
    ++f.directories;
    std::snprintf(f.directories == 1 ? f.gpuName : f.migName, 16, "%s", name);
    if (f.directoryFailure == f.directories) return nullptr;
    return f.directories == 1 ? &gpuCap : &migCap;
}
inline void osRmCapUnregister(OS_RM_CAPS **p) { ++f.unregisters; *p = nullptr; }
