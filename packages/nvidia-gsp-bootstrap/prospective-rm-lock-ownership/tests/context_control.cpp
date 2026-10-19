/* SPDX-License-Identifier: MIT */
#if defined(KERNEL)
#error "Native context controls must never enter a kernel candidate"
#endif
#include "../../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
extern "C" void s540ProspectiveControlContext(NvU32 value) {
    S540NvidiaDarwinServicesNative::setContext(value==2,value==0);
}
