// SPDX-License-Identifier: MIT
#include <mach/kmod.h>

// This binary includes Apple Covered Code from MacKernelSDK's libkmod.
// Copyright (c) 2000 Apple Computer, Inc. All rights reserved.
// Its Source Code is available under the Apple Public Source License 2.0 at:
// https://github.com/acidanthera/MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Library/kmod
__attribute__((used)) static const char S540ThirdPartySourceNotice[] =
	"Copyright (c) 2000 Apple Computer, Inc. All rights reserved. "
	"S540Sensors includes Apple Covered Code; Source Code is available under "
	"the Apple Public Source License 2.0 at https://github.com/acidanthera/"
	"MacKernelSDK/tree/3f750085caa17ec3a7880f11c11bf4f48cd6a164/Library/kmod";

extern "C" {
kern_return_t _start(kmod_info_t *, void *);
kern_return_t _stop(kmod_info_t *, void *);

kern_return_t s540_sensors_start(kmod_info_t *, void *) {
	return KMOD_RETURN_SUCCESS;
}

kern_return_t s540_sensors_stop(kmod_info_t *, void *) {
	return KMOD_RETURN_SUCCESS;
}

KMOD_EXPLICIT_DECL(org.s540.S540Sensors, "1.0.0", _start, _stop)
__attribute__((visibility("hidden"))) kmod_start_func_t *_realmain = s540_sensors_start;
__attribute__((visibility("hidden"))) kmod_stop_func_t *_antimain = s540_sensors_stop;
__attribute__((visibility("hidden"))) int _kext_apple_cc = __APPLE_CC__;
}
