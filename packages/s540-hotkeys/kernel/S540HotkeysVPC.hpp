// SPDX-License-Identifier: GPL-2.0-only
#ifndef S540_HOTKEYS_VPC_HPP
#define S540_HOTKEYS_VPC_HPP

#include <IOKit/IOService.h>
#include <IOKit/IOCommandGate.h>
#include <IOKit/IOInterruptEventSource.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOLocks.h>
#include <IOKit/acpi/IOACPIPlatformDevice.h>
#include "ProtocolCore.hpp"

class S540HotkeysVPC : public IOService {
    OSDeclareDefaultStructors(S540HotkeysVPC)
public:
    bool init(OSDictionary *dictionary = nullptr) override;
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    void free() override;
    IOReturn message(UInt32 type, IOService *provider, void *argument = nullptr) override;
    IOReturn setProperties(OSObject *properties) override;
    IOReturn setPowerState(unsigned long state, IOService *device) override;

private:
    struct Record { UInt64 sequence; UInt32 mask; UInt64 timeNs; };
    enum { RingCapacity = 32, PendingLimit = 1024 };
    IOACPIPlatformDevice *_acpi {nullptr};
    IOWorkLoop *_workLoop {nullptr};
    IOCommandGate *_gate {nullptr};
    IOInterruptEventSource *_events {nullptr};
    IOLock *_lock {nullptr};
    bool _opened {false}, _gateAdded {false}, _eventsAdded {false};
    bool _pmStarted {false}, _pmSawState {false}, _awake {true}, _powerPending {false};
    bool _transportAwake {true}, _pmAckPending {false};
    bool _stopping {false}, _accepting {false}, _fault {false};
    bool _pendingOverflow {false}, _cameraEnabled {false}, _cameraSeen {false};
    bool _cameraBaselineValid {false};
    UInt32 _pending {0}, _cfg {0}, _lastMask {0};
    UInt32 _error {0};
    IOReturn _lastIOReturn {kIOReturnSuccess};
    UInt32 _cameraState {S540Protocol::UnknownCamera};
    UInt32 _cameraResult {S540Protocol::CameraNeverRequested};
    UInt32 _cameraError {0};
    UInt64 _notifyCount {0}, _queryCount {0}, _queryFailureCount {0};
    UInt64 _notificationGeneration {0};
    UInt64 _sequence {0}, _lastCameraSeenNs {0};
    UInt32 _baselineMask {0}, _ringStart {0}, _ringCount {0};
    Record _ring[RingCapacity] {};

    static void eventAction(OSObject *owner, IOInterruptEventSource *source, int count);
    static IOReturn readyAction(OSObject *owner, void *, void *, void *, void *);
    static IOReturn stopAction(OSObject *owner, void *, void *, void *, void *);
    static UInt64 nowNs();
    bool operational();
    bool competingClient();
    bool readRegister(UInt32 index, UInt32 &value);
    bool writeRegister(UInt32 index, UInt32 value);
    void pause();
    S540Protocol::Result readCommand(UInt32 command);
    S540Protocol::Result writeCameraCommand(UInt32 value);
    bool readMask(UInt32 &mask);
    void handleEvents();
    void handleCamera(UInt64 timestamp, bool singleNotification);
    bool baselineCamera();
    bool establishBaseline();
    void cameraFailure(S540Protocol::Error error);
    void failProtocol(S540Protocol::Error error);
    void acknowledgePowerTransition();
    bool publishSnapshot(const char *state);
    void releaseRuntime();
    friend struct S540VPCTransport;
};
#endif
