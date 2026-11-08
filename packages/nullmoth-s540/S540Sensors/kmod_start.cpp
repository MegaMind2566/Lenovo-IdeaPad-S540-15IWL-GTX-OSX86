// SPDX-License-Identifier: MIT
#include <mach/kmod.h>

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
