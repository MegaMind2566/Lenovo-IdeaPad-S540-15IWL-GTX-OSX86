// SPDX-License-Identifier: MIT
#include <mach/kmod.h>

extern "C" {
__attribute__((used)) const char S540NvidiaPCIProbeRuntimeNotice[] =
    "Unmodified kernel module runtime: Portions Copyright (c) 2000, 2008-2012 Apple Inc. "
    "Source available under APSL 2.0: "
    "https://github.com/acidanthera/MacKernelSDK/tree/"
    "3f750085caa17ec3a7880f11c11bf4f48cd6a164/Library/kmod";

// The SDK's libkmod supplies the standard kernel-module entry wrappers.
kern_return_t _start(kmod_info_t *, void *);
kern_return_t _stop(kmod_info_t *, void *);

kern_return_t nvidia_transport_start(kmod_info_t *, void *) {
    return KMOD_RETURN_SUCCESS;
}

kern_return_t nvidia_transport_stop(kmod_info_t *, void *) {
    return KMOD_RETURN_SUCCESS;
}

KMOD_EXPLICIT_DECL(org.osx86.S540NvidiaPCIProbe, "0.5.0", _start, _stop)
__attribute__((visibility("hidden"))) kmod_start_func_t *_realmain = nvidia_transport_start;
__attribute__((visibility("hidden"))) kmod_stop_func_t *_antimain = nvidia_transport_stop;
__attribute__((visibility("hidden"))) int _kext_apple_cc = __APPLE_CC__;
}
