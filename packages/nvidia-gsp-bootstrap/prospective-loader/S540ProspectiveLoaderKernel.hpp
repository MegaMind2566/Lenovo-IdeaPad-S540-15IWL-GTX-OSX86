// SPDX-License-Identifier: MIT
#ifndef S540_PROSPECTIVE_LOADER_KERNEL_HPP
#define S540_PROSPECTIVE_LOADER_KERNEL_HPP
#if !defined(KERNEL)
#error This header describes a source-only real IOKit backend
#endif
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <mach/kmod.h>
#include "S540ProspectiveLoaderState.h"
class S540ProspectiveLoaderControl final : public IOService {
    OSDeclareDefaultStructors(S540ProspectiveLoaderControl);
    bool counted = false;
public:
    bool init(OSDictionary *properties = nullptr) override;
    void free() override;
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    IOReturn newUserClient(task_t task, void *security, UInt32 type,
        OSDictionary *properties, IOUserClient **handler) override;
};
class S540ProspectiveLoaderClient final : public IOUserClient {
    OSDeclareDefaultStructors(S540ProspectiveLoaderClient);
    S540ProspectiveLoaderControl *control = nullptr;
    bool counted = false;
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
extern "C" kern_return_t s540ProspectiveModuleStartBackend(kmod_info_t *);
extern "C" kern_return_t s540ProspectiveModuleStopBackend(void);
#endif
