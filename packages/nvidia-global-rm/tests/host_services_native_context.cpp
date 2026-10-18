// SPDX-License-Identifier: MIT
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
extern "C" void hostServicesNativeContext(NvBool interruptContext, NvBool enabled) {
    S540NvidiaDarwinServicesNative::setContext(interruptContext != 0, enabled != 0);
}
