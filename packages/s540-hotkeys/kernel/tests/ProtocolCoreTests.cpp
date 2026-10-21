// SPDX-License-Identifier: GPL-2.0-only
#include "../ProtocolCore.hpp"
#include <cstdlib>
#include <iostream>
#include <vector>

using namespace S540Protocol;
static unsigned checks = 0;
static void require(bool condition, const char *message) {
    ++checks;
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}
struct Step {
    char operation;
    uint32_t index, value;
    bool success;
    uint64_t elapsed;
    bool stopAfter;
    Step(char op, uint32_t slot, uint32_t data, bool ok = true, uint64_t ns = 0, bool stop = false)
        : operation(op), index(slot), value(data), success(ok), elapsed(ns), stopAfter(stop) {}
};
struct Fake {
    std::vector<Step> steps;
    size_t position = 0;
    uint64_t time = 0;
    bool running = true;
    explicit Fake(std::initializer_list<Step> source = {}) : steps(source) {}
    bool operational() { return running; }
    uint64_t nowNs() { return time; }
    Step consume(char operation, uint32_t index) {
        require(position < steps.size(), "no unexpected EC operation");
        Step step = steps[position++];
        require(step.operation == operation && step.index == index, "exact register handshake order");
        time += step.elapsed;
        if (step.stopAfter) running = false;
        return step;
    }
    bool readRegister(uint32_t index, uint32_t &value) {
        Step step = consume('R', index); value = step.value; return step.success;
    }
    bool writeRegister(uint32_t index, uint32_t value) {
        Step step = consume('W', index);
        require(step.value == value, "exact command/data allowlist on transport");
        return step.success;
    }
    void pause() { time += 1000000ULL; }
    void complete() { require(position == steps.size(), "entire expected transcript consumed"); }
};
static void allowlists() {
    for (uint32_t command = 0; command < 256; ++command) {
        bool allowedRead = command == 0x10 || command == 0x1A || command == 0x1D;
        require(readAllowed(command) == allowedRead, "read command capability is closed");
        require(writeAllowed(command, 0, true) == (command == 0x1E), "write command capability is closed");
    }
    require(!writeAllowed(WriteCamera, 2, true), "camera accepts only a Boolean payload");
    require(!writeAllowed(WriteCamera, 1, false), "camera requires internal physical-event authorization");
    Fake empty;
    require(read(empty, 0x14).error == InvalidCommand, "guessed F9 query never reaches firmware");
    require(write(empty, 0x1E, 1, false).error == InvalidCommand, "unauthorized control never reaches firmware");
    require(write(empty, 0x1E, 2, true).error == InvalidCommand, "invalid payload never reaches firmware");
    empty.complete();
}
static void successfulHandshakes() {
    Fake readLow {{'R',1,0},{'W',1,0x10},{'R',1,0x10},{'R',1,0},{'R',0,0x81}};
    Result result = read(readLow, ReadEventsLow);
    require(result.good() && result.value == 0x81, "low event byte returned after completion");
    readLow.complete();
    Fake high {{'R',1,0},{'W',1,0x1A},{'R',1,0},{'R',0,0x20}};
    result = read(high, ReadEventsHigh);
    require(result.good() && result.value == 0x20, "high event byte remains independent");
    high.complete();
    Fake noEvent {{'R',1,0},{'W',1,0x10},{'R',1,0},{'R',0,0}};
    result = read(noEvent, ReadEventsLow);
    require(result.good() && result.value == 0, "zero event is ordinary data, no recovery/control command");
    noEvent.complete();
    for (uint32_t value = 0; value <= 1; ++value) {
        Fake camera {{'R',1,0},{'W',0,value},{'W',1,0x1E},{'R',1,0x1E},{'R',1,0}};
        require(write(camera, WriteCamera, value, true).good(), "camera writes data before command and waits idle");
        camera.complete();
    }
}
static void refusalAndFailure() {
    Fake busy {{'R',1,0x42}};
    require(read(busy, ReadEventsLow).error == BusyBeforeCommand, "busy owner is never overwritten"); busy.complete();
    Fake busyWrite {{'R',1,0x1D}};
    require(write(busyWrite, WriteCamera, 0, true).error == BusyBeforeCommand, "busy owner receives no camera data"); busyWrite.complete();
    Fake badStatus {{'R',1,0},{'W',1,0x10},{'R',1,0xEE}};
    require(read(badStatus, ReadEventsLow).error == UnexpectedStatus, "unknown status stops, without retry"); badStatus.complete();
    Fake initialRead {{'R',1,0,false}};
    require(read(initialRead, ReadCamera).error == ReadFailed, "failed ownership status aborts"); initialRead.complete();
    Fake commandWrite {{'R',1,0},{'W',1,0x10,false}};
    require(read(commandWrite, ReadEventsLow).error == WriteFailed, "failed query command aborts"); commandWrite.complete();
    Fake statusRead {{'R',1,0},{'W',1,0x10},{'R',1,0,false}};
    require(read(statusRead, ReadEventsLow).error == ReadFailed, "failed completion status aborts"); statusRead.complete();
    Fake payload {{'R',1,0},{'W',1,0x1D},{'R',1,0},{'R',0,0,false}};
    require(read(payload, ReadCamera).error == PayloadReadFailed, "completed command distinguishes failed payload"); payload.complete();
    Fake wide {{'R',1,0},{'W',1,0x10},{'R',1,0},{'R',0,256}};
    require(read(wide, ReadEventsLow).error == PayloadOutOfRange, "event query cannot leak arbitrary integer payload"); wide.complete();
    Fake dataWrite {{'R',1,0},{'W',0,1,false}};
    require(write(dataWrite, WriteCamera, 1, true).error == WriteFailed, "failed camera data prevents command"); dataWrite.complete();
    Fake cameraCommand {{'R',1,0},{'W',0,0},{'W',1,0x1E,false}};
    require(write(cameraCommand, WriteCamera, 0, true).error == WriteFailed, "failed camera command has no retry"); cameraCommand.complete();
}
static void boundsAndPower() {
    Fake timeout {{'R',1,0},{'W',1,0x10}};
    for (unsigned i = 0; i < 200; ++i) timeout.steps.emplace_back('R',1,0x10);
    require(read(timeout, ReadEventsLow).error == Timeout, "busy command terminates at 200ms");
    require(timeout.time == TimeoutNs, "bounded polling elapsed exactly the configured deadline"); timeout.complete();
    Fake slowAML {{'R',1,0,true,TimeoutNs}};
    require(read(slowAML, ReadEventsLow).error == Timeout, "overdue AML return issues no following command"); slowAML.complete();
    Fake slowData {{'R',1,0},{'W',0,1,true,TimeoutNs}};
    require(write(slowData, WriteCamera, 1, true).error == Timeout, "overdue data write does not issue camera command"); slowData.complete();
    Fake stopped;
    stopped.running = false;
    require(read(stopped, ReadCamera).error == Stopped, "stopped driver does not query"); stopped.complete();
    Fake powerRead {{'R',1,0,false,0,true}};
    require(read(powerRead, ReadCamera).error == Stopped, "power transition differs from transport fault"); powerRead.complete();
    Fake powerCommand {{'R',1,0},{'W',1,0x10,true,0,true}};
    require(read(powerCommand, ReadEventsLow).error == Stopped, "sleep after command forbids further polls"); powerCommand.complete();
    require(deadlineFrom(UINT64_MAX - 1) == UINT64_MAX, "deadline arithmetic cannot wrap");
}
static void cameraPolicy() {
    require(cameraAdvertised(ExpectedCFG), "exact model CFG advertises camera and OSD");
    require(!cameraAdvertised(ExpectedCFG & ~(1U << 19)), "no camera capability means no camera action");
    require(!cameraAdvertised(ExpectedCFG & ~(1U << 31)), "no camera OSD means no event action");
    require(cameraDecision(0,0,true) == CameraRequestToggle, "unchanged valid baseline authorizes an explicit user toggle");
    require(cameraDecision(1,1,true) == CameraRequestToggle, "both Boolean baseline states supported");
    require(cameraDecision(1,0,true) == CameraObserveFirmware, "already changed camera must not be toggled twice");
    require(cameraDecision(0,1,true) == CameraObserveFirmware, "already changed disabled camera is observed");
    require(cameraDecision(1,0,false) == CameraRefuse, "unknown baseline cannot authorize a write");
    require(cameraDecision(2,0,true) == CameraRefuse && cameraDecision(0,UnknownCamera,true) == CameraRefuse,
            "non-Boolean camera states cannot authorize a write");
    require(quietTrigger(0,0,false), "first physical camera event is accepted");
    require(!quietTrigger(QuietPeriodNs-1,0,true), "rapid repeats are suppressed");
    require(quietTrigger(QuietPeriodNs,0,true), "fresh quiet period accepts next event");
    require(!quietTrigger(1,2,true), "backward clock cannot authorize a repeat");
}
int main() {
    allowlists(); successfulHandshakes(); refusalAndFailure(); boundsAndPower(); cameraPolicy();
    std::cout << "Protocol/camera contract checks passed: " << checks << '\n';
}
