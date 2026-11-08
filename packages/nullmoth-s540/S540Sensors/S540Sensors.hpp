// SPDX-License-Identifier: MIT
#ifndef S540Sensors_hpp
#define S540Sensors_hpp

#include <IOKit/IOService.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/IOWorkLoop.h>
#include <VirtualSMCSDK/kern_vsmcapi.hpp>

class S540Sensors;

class S540NvidiaTemperatureKey : public VirtualSMCValue {
public:
	explicit S540NvidiaTemperatureKey(S540Sensors *owner) : owner(owner) {}

protected:
	SMC_RESULT readAccess() override;

private:
	S540Sensors *owner;
};

class EXPORT S540Sensors : public IOService {
	OSDeclareDefaultStructors(S540Sensors)

public:
	bool start(IOService *provider) override;
	void stop(IOService *provider) override;
	uint32_t nvidiaTemperature() const { return cachedNvidiaTemperature; }

private:
	static constexpr uint32_t PollIntervalMs = 1000;
	static constexpr SMC_KEY KeyTG0D = SMC_MAKE_IDENTIFIER('T', 'G', '0', 'D');

	VirtualSMCAPI::Plugin vsmcPlugin {
		"S540Sensors",
		10000,
		VirtualSMCAPI::Version,
		{},
		{},
	};

	IONotifier *vsmcNotifier {nullptr};
	IOWorkLoop *workloop {nullptr};
	IOTimerEventSource *timer {nullptr};
	volatile uint32_t cachedNvidiaTemperature {0};

	void refreshNvidiaTemperature();
	void timerCallback();
	static bool vsmcNotificationHandler(void *sensors, void *refCon,
		IOService *vsmc, IONotifier *notifier);
};

#endif
