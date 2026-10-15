// SPDX-License-Identifier: MIT
#include "S540NvidiaDarwinInternal.hpp"
#if defined(KERNEL)
#include <sys/kauth.h>
#include <sys/proc.h>
#include <kern/task.h>
// Exact Apple XNU declaration/export evidence is included under reference/.
// Deliberately explicit: this requires com.apple.kpi.unsupported on Intel.
extern "C" int cpu_number(void);
#else
#include <unistd.h>
#if !defined(__APPLE__)
#include <sched.h>
#endif
#endif
namespace {
struct PidInfo {
#if defined(KERNEL)
    proc_t process;
#else
    pid_t process;
#endif
};
#if !defined(KERNEL)
alignas(NvU32) NvU32 nativeCpuFixture = ~NvU32{0};
#endif
}
extern "C" NvU32 NV_API_CALL s540Darwin_os_get_cpu_number(void) {
#if defined(KERNEL)
    const int number = cpu_number();
    if (number < 0) S540DarwinInternal::violation("negative kernel CPU index");
    return static_cast<NvU32>(number);
#else
    const NvU32 fixture = __atomic_load_n(&nativeCpuFixture, __ATOMIC_RELAXED);
    if (fixture != ~NvU32{0}) return fixture;
#if defined(__APPLE__)
    S540DarwinInternal::violation("native Darwin current-CPU query requires an explicit test fixture");
#else
    const int number = sched_getcpu();
    if (number < 0) S540DarwinInternal::violation("native CPU query");
    return static_cast<NvU32>(number);
#endif
#endif
}
#if !defined(KERNEL)
void S540NvidiaDarwinServicesNative::setCpuFixture(NvU32 number) {
    __atomic_store_n(&nativeCpuFixture, number, __ATOMIC_RELAXED);
}
#endif
extern "C" NvU32 NV_API_CALL s540Darwin_os_get_current_process(void) {
#if defined(KERNEL)
    return static_cast<NvU32>(proc_selfpid());
#else
    return static_cast<NvU32>(getpid());
#endif
}
extern "C" void NV_API_CALL s540Darwin_os_get_current_process_name(char *output, NvU32 size) {
    if (output == nullptr || size == 0) return;
    output[0] = '\0';
#if defined(KERNEL)
    // The public KPI uses signed int. A smaller bound is sufficient for a
    // process name and avoids truncating an untrusted unsigned size to int.
    const NvU32 limit = size > 1024 ? 1024 : size;
    proc_selfname(output, static_cast<int>(limit));
    output[limit - 1] = '\0';
#else
#if defined(__APPLE__)
    const char *name = getprogname();
#else
    extern char *program_invocation_short_name;
    const char *name = program_invocation_short_name;
#endif
    if (name == nullptr) return;
    NvU32 i = 0;
    while (i + 1 < size && name[i] != '\0') { output[i] = name[i]; ++i; }
    output[i] = '\0';
#endif
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_get_euid(NvU32 *output) {
    if (output == nullptr) return NV_ERR_INVALID_ARGUMENT;
    if (!S540DarwinInternal::ordinary()) return NV_ERR_INVALID_REQUEST;
#if defined(KERNEL)
    *output = static_cast<NvU32>(kauth_cred_getuid(kauth_cred_get()));
#else
    *output = static_cast<NvU32>(geteuid());
#endif
    return NV_OK;
}
extern "C" NvBool NV_API_CALL s540Darwin_os_is_administrator(void) {
    NvU32 uid = ~NvU32{0};
    return s540Darwin_os_get_euid(&uid) == NV_OK && uid == 0 ? NV_TRUE : NV_FALSE;
}
extern "C" NvBool NV_API_CALL s540Darwin_os_check_access(NvU16 accessRight) {
    // Explicit conservative Darwin policy. The pinned Linux implementation
    // accepts CAP_SYS_NICE / CAP_PERFMON; Darwin has no equivalent Linux
    // capability bitset. Only current root credentials grant those two
    // rights. Other RS rights remain denied, matching the original switch.
    if (accessRight != 1U && accessRight != 3U) return NV_FALSE;
    return s540Darwin_os_is_administrator();
}
extern "C" NvU32 NV_API_CALL s540Darwin_os_get_current_process_flags(void) {
#if defined(KERNEL)
    NvU32 flags = current_task() == kernel_task ? 1U : 0U;
    const auto process = proc_self();
    if (process != nullptr) {
        if (proc_exiting(process)) flags |= 2U;
        (void)proc_rele(process);
    }
    return flags;
#else
    // Native code is executing in a live POSIX userspace process, never in a
    // kernel task or its process-exit path. No kernel-context claim is made.
    return 0;
#endif
}
extern "C" void *NV_API_CALL s540Darwin_os_get_pid_info(void) {
    if (!S540DarwinInternal::ordinary()) return nullptr;
    auto *info = static_cast<PidInfo *>(S540DarwinInternal::allocate(sizeof(PidInfo)));
    if (info == nullptr) return nullptr;
#if defined(KERNEL)
    info->process = proc_self();
    if (info->process == nullptr) {
        S540DarwinInternal::deallocate(info, sizeof(PidInfo));
        return nullptr;
    }
#else
    info->process = getpid();
#endif
    S540DarwinInternal::account(1);
    return info;
}
extern "C" void NV_API_CALL s540Darwin_os_put_pid_info(void *handle) {
    if (handle == nullptr) return; // Explicitly permitted by NVIDIA's ABI.
    if (!S540DarwinInternal::ordinary()) S540DarwinInternal::violation("PID reference release context");
    auto *info = static_cast<PidInfo *>(handle);
#if defined(KERNEL)
    (void)proc_rele(info->process);
#endif
    S540DarwinInternal::deallocate(info, sizeof(PidInfo));
    S540DarwinInternal::account(-1);
}
extern "C" NV_STATUS NV_API_CALL s540Darwin_os_find_ns_pid(void *handle, NvU32 *output) {
    if (handle == nullptr || output == nullptr) return NV_ERR_INVALID_ARGUMENT;
    if (!S540DarwinInternal::ordinary()) return NV_ERR_INVALID_REQUEST;
    const auto *info = static_cast<const PidInfo *>(handle);
#if defined(KERNEL)
    const auto pid = proc_pid(info->process);
#else
    const auto pid = info->process;
#endif
    *output = static_cast<NvU32>(pid);
    return pid > 0 ? NV_OK : NV_ERR_OBJECT_NOT_FOUND;
}
extern "C" NvBool NV_API_CALL s540Darwin_os_is_init_ns(void) {
    // Darwin has a single kernel PID namespace. It has no Linux-style
    // per-process PID namespaces whose numeric PIDs need translation.
    return NV_TRUE;
}
