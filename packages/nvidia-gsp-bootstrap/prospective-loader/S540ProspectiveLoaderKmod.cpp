// SPDX-License-Identifier: MIT
#include <mach/kmod.h>
#include "S540ProspectiveLoaderKernel.hpp"
extern "C" {
// Link only the pinned SDK libkmod.a C wrappers. The obsolete libkmodc++
// wrapper's OSRuntimeInitializeCPP(kmod_info_t *,void *) is not used.
kern_return_t _start(kmod_info_t *,void *);
kern_return_t _stop(kmod_info_t *,void *);
kern_return_t s540_prospective_start(kmod_info_t *info,void *) {
    return s540ProspectiveModuleStartBackend(info);
}
kern_return_t s540_prospective_stop(kmod_info_t *,void *) {
    return s540ProspectiveModuleStopBackend();
}
KMOD_EXPLICIT_DECL(org.osx86.S540ProspectiveLoader,"0.0.1",_start,_stop)
__attribute__((visibility("hidden"))) kmod_start_func_t *_realmain = s540_prospective_start;
__attribute__((visibility("hidden"))) kmod_stop_func_t *_antimain = s540_prospective_stop;
__attribute__((visibility("hidden"))) int _kext_apple_cc = __APPLE_CC__;
}
