// SPDX-License-Identifier: MIT
#include "S540Sensors.hpp"

#include <IOKit/IOLib.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/libkern.h>

OSDefineMetaClassAndStructors(S540Sensors, IOService)

SMC_RESULT S540NvidiaTemperatureKey::readAccess() {
	const auto value = owner ? owner->nvidiaTemperature() : 0;
	*reinterpret_cast<uint16_t *>(data) =
		VirtualSMCAPI::encodeIntSp(SmcKeyTypeSp78, static_cast<int16_t>(value));
	return SmcSuccess;
}

bool S540Sensors::start(IOService *provider) {
	if (!IOService::start(provider))
		return false;

	if (!VirtualSMCAPI::addKey(KeyTG0D, vsmcPlugin.data,
		VirtualSMCAPI::valueWithSp(0, SmcKeyTypeSp78,
			new S540NvidiaTemperatureKey(this))))
		return false;

	qsort(const_cast<VirtualSMCKeyValue *>(vsmcPlugin.data.data()),
		vsmcPlugin.data.size(), sizeof(VirtualSMCKeyValue),
		VirtualSMCKeyValue::compare);

	workloop = IOWorkLoop::workLoop();
	timer = IOTimerEventSource::timerEventSource(this,
		[](OSObject *object, IOTimerEventSource *) {
			auto sensors = OSDynamicCast(S540Sensors, object);
			if (sensors)
				sensors->timerCallback();
		});
	if (!workloop || !timer || workloop->addEventSource(timer) != kIOReturnSuccess)
		return false;

	refreshNvidiaTemperature();
	timer->setTimeoutMS(PollIntervalMs);
	vsmcNotifier = VirtualSMCAPI::registerHandler(vsmcNotificationHandler, this);
	if (!vsmcNotifier)
		return false;

	setProperty("VersionInfo", "1.0.0");
	setProperty("SensorSource", "NVAccel/PerformanceStatistics/Temperature(C)");
	registerService();
	return true;
}

void S540Sensors::stop(IOService *provider) {
	if (timer) {
		timer->cancelTimeout();
		if (workloop)
			workloop->removeEventSource(timer);
		timer->release();
		timer = nullptr;
	}
	if (workloop) {
		workloop->release();
		workloop = nullptr;
	}
	IOService::stop(provider);
}

void S540Sensors::timerCallback() {
	refreshNvidiaTemperature();
	if (timer)
		timer->setTimeoutMS(PollIntervalMs);
}

void S540Sensors::refreshNvidiaTemperature() {
	auto matching = IOService::serviceMatching("NVAccel");
	if (!matching)
		return;
	auto service = IOService::copyMatchingService(matching);
	matching->release();
	if (!service)
		return;

	auto statistics = OSDynamicCast(OSDictionary,
		service->getProperty("PerformanceStatistics"));
	auto temperature = statistics ? OSDynamicCast(OSNumber,
		statistics->getObject("Temperature(C)")) : nullptr;
	if (temperature) {
		const auto value = temperature->unsigned32BitValue();
		if (value > 0 && value < 126) {
			cachedNvidiaTemperature = value;
			setProperty("NvidiaTemperatureC", value, 32);
		}
	}
	service->release();
}

bool S540Sensors::vsmcNotificationHandler(void *sensors, void *,
	IOService *vsmc, IONotifier *) {
	if (!sensors || !vsmc)
		return false;
	auto instance = static_cast<S540Sensors *>(sensors);
	return vsmc->callPlatformFunction(VirtualSMCAPI::SubmitPlugin, true,
		sensors, &instance->vsmcPlugin, nullptr, nullptr) == kIOReturnSuccess;
}
