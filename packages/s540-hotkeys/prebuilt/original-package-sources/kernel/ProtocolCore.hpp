// SPDX-License-Identifier: GPL-2.0-only
// Lenovo VPC transaction ordering follows YogaSMC 1.5.3 IdeaVPC.cpp and Linux ideapad-laptop.
#ifndef S540_HOTKEYS_PROTOCOL_CORE_HPP
#define S540_HOTKEYS_PROTOCOL_CORE_HPP

#include <stdint.h>

namespace S540Protocol {
static const uint32_t ExpectedCFG = 0xFE0D0014U;
static const uint32_t ReadEventsLow = 0x10U;
static const uint32_t ReadEventsHigh = 0x1AU;
static const uint32_t ReadCamera = 0x1DU;
static const uint32_t WriteCamera = 0x1EU;
static const uint64_t TimeoutNs = 200000000ULL;
static const uint64_t QuietPeriodNs = 300000000ULL;
static const uint32_t UnknownCamera = 0xFFFFFFFFU;

enum Error : uint32_t {
    OK = 0, InvalidCommand = 1, Stopped = 2, ReadFailed = 3, WriteFailed = 4,
    BusyBeforeCommand = 5, UnexpectedStatus = 6, Timeout = 7,
    PayloadOutOfRange = 8, ResourceFailure = 9, NotificationOverflow = 10,
    SequenceOverflow = 11, PayloadReadFailed = 12, BaselineNotQuiet = 13
};
enum CameraResult : uint32_t {
    CameraNeverRequested = 0, CameraUnsupported = 1, CameraChanged = 2,
    CameraDebounced = 3, CameraInvalidState = 4, CameraReadbackMismatch = 5,
    CameraProtocolFailure = 6, CameraFirmwareChanged = 7
};
enum CameraDecision : uint32_t {
    CameraRefuse = 0, CameraObserveFirmware = 1, CameraRequestToggle = 2
};
struct Result {
    Error error;
    uint32_t value;
    Result(Error e = OK, uint32_t v = 0) : error(e), value(v) {}
    bool good() const { return error == OK; }
};

inline bool readAllowed(uint32_t command) {
    return command == ReadEventsLow || command == ReadEventsHigh || command == ReadCamera;
}
inline bool writeAllowed(uint32_t command, uint32_t value, bool cameraEventAuthorized) {
    return cameraEventAuthorized && command == WriteCamera && value <= 1;
}
inline bool cameraAdvertised(uint32_t cfg) {
    return (cfg & (1U << 19)) != 0 && (cfg & (1U << 31)) != 0;
}
inline bool quietTrigger(uint64_t now, uint64_t previous, bool previousValid) {
    return !previousValid || (now >= previous && now - previous >= QuietPeriodNs);
}
inline CameraDecision cameraDecision(uint32_t current, uint32_t baseline, bool baselineValid) {
    if (!baselineValid || current > 1 || baseline > 1) return CameraRefuse;
    return current == baseline ? CameraRequestToggle : CameraObserveFirmware;
}
inline uint64_t deadlineFrom(uint64_t now) {
    return now > UINT64_MAX - TimeoutNs ? UINT64_MAX : now + TimeoutNs;
}

// Transport supplies operational(), nowNs(), readRegister(index, value),
// writeRegister(index, value), and pause(). No arbitrary command reaches it.
template <typename Transport>
inline Error boundary(Transport &transport, uint64_t deadline) {
    if (!transport.operational()) return Stopped;
    return transport.nowNs() >= deadline ? Timeout : OK;
}

template <typename Transport>
Result waitCommand(Transport &transport, uint32_t command, uint64_t deadline) {
    for (;;) {
        Error limit = boundary(transport, deadline);
        if (limit != OK) return Result(limit);
        uint32_t status = 0;
        if (!transport.readRegister(1, status))
            return Result(transport.operational() ? ReadFailed : Stopped);
        limit = boundary(transport, deadline);
        if (limit != OK) return Result(limit);
        if (status == 0) return Result();
        if (status != command) return Result(UnexpectedStatus);
        transport.pause();
    }
}

template <typename Transport>
Result read(Transport &transport, uint32_t command) {
    if (!readAllowed(command)) return Result(InvalidCommand);
    uint64_t deadline = deadlineFrom(transport.nowNs());
    Error limit = boundary(transport, deadline);
    if (limit != OK) return Result(limit);
    uint32_t status = 0;
    if (!transport.readRegister(1, status))
        return Result(transport.operational() ? ReadFailed : Stopped);
    limit = boundary(transport, deadline);
    if (limit != OK) return Result(limit);
    if (status != 0) return Result(BusyBeforeCommand);
    if (!transport.writeRegister(1, command))
        return Result(transport.operational() ? WriteFailed : Stopped);
    Result completed = waitCommand(transport, command, deadline);
    if (!completed.good()) return completed;
    uint32_t value = 0;
    if (!transport.readRegister(0, value))
        return Result(transport.operational() ? PayloadReadFailed : Stopped);
    limit = boundary(transport, deadline);
    if (limit != OK) return Result(limit);
    if (value > 255) return Result(PayloadOutOfRange);
    return Result(OK, value);
}

template <typename Transport>
Result write(Transport &transport, uint32_t command, uint32_t value, bool cameraEventAuthorized) {
    if (!writeAllowed(command, value, cameraEventAuthorized)) return Result(InvalidCommand);
    uint64_t deadline = deadlineFrom(transport.nowNs());
    Error limit = boundary(transport, deadline);
    if (limit != OK) return Result(limit);
    uint32_t status = 0;
    if (!transport.readRegister(1, status))
        return Result(transport.operational() ? ReadFailed : Stopped);
    limit = boundary(transport, deadline);
    if (limit != OK) return Result(limit);
    if (status != 0) return Result(BusyBeforeCommand);
    if (!transport.writeRegister(0, value))
        return Result(transport.operational() ? WriteFailed : Stopped);
    limit = boundary(transport, deadline);
    if (limit != OK) return Result(limit);
    if (!transport.writeRegister(1, command))
        return Result(transport.operational() ? WriteFailed : Stopped);
    return waitCommand(transport, command, deadline);
}
} // namespace S540Protocol
#endif
