/* SPDX-License-Identifier: MIT; explicit CPU failure endpoint, never composed. */
#include "../../nvidia-darwin-services/src/S540NvidiaDarwinServices.h"
extern "C" void s540MappingTestFailAllocation(void)
{
    S540NvidiaDarwinServicesNative::failNext(
        S540NvidiaDarwinServicesNative::Failure::Storage);
}
