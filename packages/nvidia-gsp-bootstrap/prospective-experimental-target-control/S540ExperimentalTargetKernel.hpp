// SPDX-License-Identifier: MIT
#ifndef S540_EXPERIMENTAL_TARGET_KERNEL_HPP
#define S540_EXPERIMENTAL_TARGET_KERNEL_HPP
#if !defined(KERNEL)
#error This backend requires the real kernel IOKit interface
#endif
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <mach/kmod.h>
#include "S540ExperimentalTargetState.h"
#include "../src/S540NvidiaGspBootstrap.hpp"
class S540ExperimentalTargetControl final : public IOService {
    OSDeclareDefaultStructors(S540ExperimentalTargetControl);
    bool counted = false, permanentPin = false;
    S540NvidiaGspBootstrap::Owner *owner = nullptr;
    IOPCIDevice *retainedProvider = nullptr;
    void publishOwnerObservation();
public:
    bool init(OSDictionary *properties = nullptr) override;
    void free() override;
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    IOReturn newUserClient(task_t task, void *security, UInt32 type,
        OSDictionary *properties, IOUserClient **handler) override;
    NV_STATUS runOnce(const S540ExperimentalRequest &,NvBool *actualCallingClientOwnsRequest);
    NV_STATUS requestStop();
};
class S540ExperimentalTargetClient final : public IOUserClient {
    OSDeclareDefaultStructors(S540ExperimentalTargetClient);
    S540ExperimentalTargetControl *control = nullptr;
    bool counted = false;
    NvBool requestOwned = NV_FALSE;
public:
    bool initWithTask(task_t task, void *security, UInt32 type,
        OSDictionary *properties) override;
    bool start(IOService *provider) override;
    void free() override;
    IOReturn clientClose() override;
    IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *arguments,
        IOExternalMethodDispatch *dispatch = nullptr, OSObject *target = nullptr,
        void *reference = nullptr) override;
};
extern "C" kern_return_t s540ExperimentalModuleStartBackend(kmod_info_t *);
extern "C" kern_return_t s540ExperimentalModuleStopBackend(void);
#endif
