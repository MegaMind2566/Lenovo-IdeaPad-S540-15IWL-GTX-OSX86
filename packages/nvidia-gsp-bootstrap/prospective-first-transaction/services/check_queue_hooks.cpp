// SPDX-License-Identifier: MIT
// Real queue implementation. Record hook controls below test wiring and its
// guarded pull probes only; this executable does not authorize RM callbacks.
#include "overlay/S540NvidiaDarwinWork.cpp"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <unistd.h>
#include <sys/wait.h>
namespace {
unsigned checks, failures;
void expect(bool value, const char *why) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "queue hooks: %s\n", why); }
}
int exactState, work;
constexpr NvU64 generation = 19;
NvU64 nextLease, admissionThread, enteredThread;
unsigned admits, enters, returns, rejects, retains;
std::atomic<bool> hold{false}, arrived{false}, released{false}, stopReturned{false};
bool failAdmission, failReturned;
void require(bool v) { if (!v) std::abort(); }
void wait(std::atomic<bool> &value) {
    for (unsigned n = 0; !value && n != 3000; ++n) usleep(1000);
    require(value);
}
void action(void *, void *data) {
    require(data == &work);
    arrived = true;
    if (hold) wait(released);
}
bool context(const void *q, NvU32 stage, const void *data) {
    S540FirstTxnServiceContext c = {};
    return s540FirstTxnServicesReadQueueContext(q, &c) == NV_OK &&
        c.stage == stage && c.data == data && c.thread == identity() &&
        c.generation == generation;
}
void healthy() {
    os_work_queue *device = nullptr, *global = nullptr;
    require(s540DarwinWorkQueueCreate(action, nullptr, &device) == NV_OK);
    require(s540DarwinWorkQueueCreate(action, nullptr, &global) == NV_OK);
    expect(s540FirstTxnQueueBind(device, &exactState, generation) == NV_OK &&
        s540FirstTxnQueueBind(global, &exactState, generation) == NV_OK,
        "exact immutable bindings are installed before real acceptance");
    expect(s540DarwinBindGlobalWorkQueue(global) == NV_OK,
        "global identity is the real published service queue");
    S540FirstTxnServiceContext c = {};
    expect(s540FirstTxnServicesReadQueueContext(device, &c) != NV_OK,
        "ordinary caller cannot fabricate an actual guarded dispatch stage");
    expect(s540FirstTxnQueueBind(device, &exactState, generation) != NV_OK,
        "a second binding cannot replace immutable ownership");
    failAdmission = true;
    expect(s540Darwin_os_queue_work_item(device, &work) == NV_ERR_NOT_SUPPORTED &&
        device->accepted == 0 && !device->count,
        "record refusal happens before irrevocable real queue publication");
    failAdmission = false;
    hold = true;
    expect(s540Darwin_os_queue_work_item(device, &work) == NV_OK,
        "accepted real item obtains its lease before publication");
    wait(arrived);
    expect(enteredThread != admissionThread && enters == 1,
        "actual worker identity enters the exact admitted lease");
    std::thread stopper([&] {
        require(s540DarwinWorkQueueStop(device) == NV_OK);
        stopReturned = true;
    });
    usleep(10000);
    expect(!stopReturned && device->completed == 0,
        "actual drain cannot complete before the original action returns");
    released = true; stopper.join();
    expect(stopReturned && returns == 1 && device->completed == 1,
        "lease completion is after the real action return");
    expect(s540FirstTxnQueueValidateStopped(device, &exactState, generation) == NV_OK,
        "actual guard state validates all accepted work and callback return");
    expect(s540FirstTxnQueueValidateStopped(device, &work, generation) != NV_OK &&
        s540FirstTxnQueueValidateStopped(device, &exactState, generation + 1) != NV_OK,
        "neither wrong owner nor stale generation can claim retirement");
    expect(s540FirstTxnQueueSeal(global, &exactState, generation) == NV_OK &&
        s540DarwinWorkQueueStop(global) == NV_OK,
        "real global admission barrier also closes the NULL route");
    expect(s540Darwin_os_queue_work_item(nullptr, &work) == NV_ERR_NOT_READY && rejects == 1,
        "enqueue through NULL reaches the sealed real global queue and records refusal");
    expect(s540DarwinUnbindGlobalWorkQueue(global) == NV_ERR_IN_USE,
        "no final transaction release exists, so global binding remains retained");
    const NvU32 live = s540DarwinLiveObjects();
    s540DarwinWorkQueueDestroy(device);
    s540DarwinWorkQueueDestroy(global);
    expect(s540DarwinLiveObjects() == live && live == 2,
        "void destruction cannot free transaction callback identities or text owners");
}
void failedReturn() {
    os_work_queue *queue = nullptr;
    require(s540DarwinWorkQueueCreate(action, nullptr, &queue) == NV_OK);
    require(s540FirstTxnQueueBind(queue, &exactState, generation) == NV_OK);
    failReturned = true;
    require(s540Darwin_os_queue_work_item(queue, &work) == NV_OK);
    wait(arrived);
    expect(s540DarwinWorkQueueStop(queue) == NV_ERR_INVALID_STATE,
        "failed completion returns refusal instead of waiting on a fictional completion");
    expect(queue->accepted == 1 && queue->completed == 0 && queue->retainedCount == 1 && retains == 1,
        "failed ticket and owner remain recorded, never counted as completed");
    expect(s540FirstTxnQueueValidateStopped(queue, &exactState, generation) != NV_OK,
        "drained ring alone cannot hide a failed lifetime boundary");
}
}
extern "C" NV_STATUS s540FirstTxnWorkAdmit(const void *nv, const void *q,
    const void *data, NvU64 *lease) {
    require(nv == &exactState && context(q, S540_FIRST_SERVICE_ADMIT, data));
    admissionThread = identity(); ++admits;
    if (failAdmission) return NV_ERR_NOT_SUPPORTED;
    *lease = ++nextLease; return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnWorkRejected(const void *nv, const void *q,
    const void *data, NV_STATUS status) {
    require(nv == &exactState && status != NV_OK && context(q, S540_FIRST_SERVICE_ADMIT, data));
    ++rejects; return status;
}
extern "C" NV_STATUS s540FirstTxnWorkEnter(const void *nv, const void *q,
    const void *data, NvU64 lease) {
    require(nv == &exactState && lease && context(q, S540_FIRST_SERVICE_ENTER, data));
    enteredThread = identity(); ++enters; return NV_OK;
}
extern "C" NV_STATUS s540FirstTxnWorkReturned(const void *nv, const void *q, NvU64 lease) {
    require(nv == &exactState && lease && context(q, S540_FIRST_SERVICE_RETURNED, nullptr));
    ++returns; return failReturned ? NV_ERR_INVALID_STATE : NV_OK;
}
extern "C" NV_STATUS s540FirstTxnWorkRetain(const void *nv, const void *, NvU64 lease, NV_STATUS status) {
    require(nv == &exactState && lease && status != NV_OK); ++retains; return status;
}
int main() {
    for (unsigned test = 0; test != 2; ++test) {
        int pipefd[2]; require(pipe(pipefd) == 0);
        const pid_t child = fork(); require(child >= 0);
        if (!child) {
            close(pipefd[0]); checks = failures = 0;
            if (!test) healthy(); else failedReturn();
            std::fflush(stderr);
            unsigned result[2] = {checks, failures};
            require(write(pipefd[1], result, sizeof(result)) == sizeof(result));
            close(pipefd[1]);
            // Deliberately retained service objects die with this test process.
            _Exit(failures ? 1 : 0);
        }
        close(pipefd[1]); unsigned childResult[2] = {};
        require(read(pipefd[0], childResult, sizeof(childResult)) == sizeof(childResult));
        close(pipefd[0]); checks += childResult[0]; failures += childResult[1];
        int result = 0; require(waitpid(child, &result, 0) == child);
        expect(WIFEXITED(result) && WEXITSTATUS(result) == 0,
            test ? "failed callback control passes" : "healthy callback control passes");
    }
    std::printf("{\"checks\":%u,\"failures\":%u,\"component\":\"real-queue-first-transaction-hook-controls\","
        "\"record_hooks\":\"explicit-controls\",\"original_callback_policy_admitted\":false,"
        "\"hardware_admission\":false}\n", checks, failures);
    return failures ? 1 : 0;
}
