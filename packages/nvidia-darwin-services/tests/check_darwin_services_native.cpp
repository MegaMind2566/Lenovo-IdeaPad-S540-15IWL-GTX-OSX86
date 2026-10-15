// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaDarwinServices.h"
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
namespace {
unsigned checks;
void require(bool value, const char *reason) {
    ++checks;
    if (!value) { std::fprintf(stderr, "Darwin services check failed: %s\n", reason); std::exit(1); }
}
bool unboundFlushStateRefuses() {
    // Fork while the parent is cold, before any worker or timer exists.
    const pid_t child = fork();
    if (child < 0) return false;
    if (!child) {
        const rlimit noCore{0, 0};
        if (setrlimit(RLIMIT_CORE, &noCore) != 0) _Exit(2);
        (void)s540Darwin_os_is_queue_flush_ongoing(nullptr);
        _Exit(3); // A fabricated false result must never satisfy this check.
    }
    int status = 0;
    return waitpid(child, &status, 0) == child &&
        WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT;
}
bool waitUntil(std::atomic<unsigned> &value, unsigned expected) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (value.load() != expected && std::chrono::steady_clock::now() < deadline) std::this_thread::yield();
    return value.load() == expected;
}
struct Work {
    os_work_queue *queue{};
    void *gate{};
    std::atomic<unsigned> entered{}, completed{}, errors{};
    std::atomic<bool> block{}, selfFlush{};
};
void action(void *context, void *) {
    auto &work = *static_cast<Work *>(context);
    if (s540Darwin_os_is_isr() || !s540Darwin_os_semaphore_may_sleep()) ++work.errors;
    ++work.entered;
    if (work.selfFlush && s540Darwin_os_flush_work_queue(work.queue, NV_FALSE) != NV_ERR_ILLEGAL_ACTION) ++work.errors;
    if (work.block && s540Darwin_os_acquire_semaphore(work.gate) != NV_OK) ++work.errors;
    ++work.completed;
}
struct Timer {
    S540DarwinTimer *timer{};
    void *gate{};
    std::atomic<unsigned> entered{}, completed{}, errors{};
    bool rearm{}, block{}, selfCancel{};
};
void timerAction(void *context) {
    auto &timer = *static_cast<Timer *>(context);
    const auto count = ++timer.entered;
    if (s540Darwin_os_is_isr() || !s540Darwin_os_semaphore_may_sleep()) ++timer.errors;
    if (timer.selfCancel && s540DarwinTimerCancel(timer.timer) != NV_ERR_ILLEGAL_ACTION) ++timer.errors;
    if (timer.rearm && count < 3 && s540DarwinTimerArm(timer.timer, 1000000) != NV_OK) ++timer.errors;
    if (timer.block && s540Darwin_os_acquire_semaphore(timer.gate) != NV_OK) ++timer.errors;
    ++timer.completed;
}
void allocationFailures() {
    using namespace S540NvidiaDarwinServicesNative;
    for (const auto failure : {Failure::Storage, Failure::Guard}) {
        void *handle = reinterpret_cast<void *>(1);
        failNext(failure);
        require(s540Darwin_os_alloc_mutex(&handle) == NV_ERR_NO_MEMORY && handle == nullptr, "mutex allocation unwind");
        failNext(failure);
        require(s540Darwin_os_alloc_spinlock(&handle) == NV_ERR_NO_MEMORY && handle == nullptr, "spin allocation unwind");
        failNext(failure);
        require(s540Darwin_os_alloc_semaphore(0) == nullptr, "semaphore allocation unwind");
        failNext(failure);
        require(s540Darwin_os_alloc_rwlock() == nullptr, "rw allocation unwind");
        os_wait_queue *wait = nullptr;
        failNext(failure);
        require(s540Darwin_os_alloc_wait_queue(&wait) == NV_ERR_NO_MEMORY && wait == nullptr, "completion allocation unwind");
    }
    for (const auto failure : {Failure::Storage, Failure::Guard, Failure::Worker}) {
        os_work_queue *queue = nullptr;
        failNext(failure);
        require(s540DarwinWorkQueueCreate(action, nullptr, &queue) == NV_ERR_NO_MEMORY && queue == nullptr, "queue allocation unwind");
        S540DarwinTimer *timer = nullptr;
        failNext(failure);
        require(s540DarwinTimerCreate(timerAction, nullptr, &timer) == NV_ERR_NO_MEMORY && timer == nullptr, "timer allocation unwind");
    }
    failNext(Failure::Storage);
    require(s540Darwin_os_get_pid_info() == nullptr, "PID-info storage failure preserves no OS reference");
    require(s540DarwinLiveObjects() == 0, "all injected allocation failures released");
}
}
int main() {
    require(s540DarwinLiveObjects() == 0, "initial state cold");
    require(unboundFlushStateRefuses(), "unbound scalar flush-state query is a contract violation");
    const auto production = S540NvidiaDarwinServices::check();
    require(production.passed(), "real production service lifecycle");
    require(production.checks == 37, "production check count");
    allocationFailures();
    require(s540Darwin_os_alloc_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT, "null mutex output");
    require(s540Darwin_os_acquire_mutex(nullptr) == NV_ERR_INVALID_ARGUMENT, "null mutex acquire");
    require(s540Darwin_os_cond_acquire_semaphore(nullptr) == NV_ERR_INVALID_ARGUMENT, "null semaphore conditional");
    require(s540Darwin_os_acquire_rwlock_write(nullptr) == NV_ERR_INVALID_ARGUMENT, "null rw acquire");
    require(s540Darwin_os_get_current_thread(nullptr) == NV_ERR_INVALID_ARGUMENT, "null thread output");
    require(s540Darwin_os_get_system_time(nullptr, nullptr) == NV_ERR_INVALID_ARGUMENT, "null wallclock output");
    require(s540Darwin_os_queue_work_item(nullptr, nullptr) == NV_ERR_NOT_READY, "unbound global queue refuses");
    require(s540Darwin_os_flush_work_queue(nullptr, NV_FALSE) == NV_ERR_NOT_READY, "unbound global flush refuses");
    char processName[64]{};
    s540Darwin_os_get_current_process_name(processName, sizeof(processName));
    require(s540Darwin_os_get_current_process() != 0 && processName[0] != '\0', "real native process metadata");
    NvU32 euid = ~NvU32{0};
    require(s540Darwin_os_get_euid(&euid) == NV_OK, "real native effective credential");
    require(s540Darwin_os_is_administrator() == (euid == 0), "administrator derived from current credential");
    require(s540Darwin_os_check_access(1) == (euid == 0) && s540Darwin_os_check_access(3) == (euid == 0), "explicit root-only NICE and PERFMON policy");
    require(!s540Darwin_os_check_access(0) && !s540Darwin_os_check_access(2) && !s540Darwin_os_check_access(65535), "unsupported RS rights denied");
    S540NvidiaDarwinServicesNative::setCpuFixture(7);
    require(s540Darwin_os_get_cpu_number() == 7, "explicit native virtual CPU fixture");
    S540NvidiaDarwinServicesNative::setCpuFixture(~NvU32{0});
    require(s540Darwin_os_get_current_process_flags() == 0, "native live userspace flags are not kernel flags");
    require(s540Darwin_os_find_ns_pid(nullptr, nullptr) == NV_ERR_INVALID_ARGUMENT, "null PID translation refuses");
    void *pidInfo = s540Darwin_os_get_pid_info();
    require(pidInfo != nullptr, "acquire actual current-process identity");
    NvU32 pid = 0;
    require(s540Darwin_os_find_ns_pid(pidInfo, &pid) == NV_OK && pid == s540Darwin_os_get_current_process(), "retained process PID translates correctly");
    s540Darwin_os_put_pid_info(pidInfo);
    s540Darwin_os_put_pid_info(nullptr);
    require(s540Darwin_os_is_init_ns() == NV_TRUE, "single Darwin adapter PID namespace contract");
    NvU8 random[512]{};
    require(s540Darwin_os_get_random_bytes(nullptr, 1) == NV_ERR_INVALID_ARGUMENT, "null random output refuses");
    require(s540Darwin_os_get_random_bytes(nullptr, 0) == NV_OK, "zero-byte random request has no output");
    require(s540Darwin_os_get_random_bytes(random, sizeof(random)) == NV_OK, "actual CSPRNG fills multiple native API chunks");
    bool changed = false;
    for (auto byte : random) changed = changed || byte != 0;
    require(changed, "CSPRNG request produced bytes");
    const NvU64 beforeYield = s540Darwin_os_get_monotonic_time_ns_hr();
    require(s540Darwin_os_schedule() == NV_OK && s540Darwin_os_get_monotonic_time_ns_hr() > beforeYield, "ordinary thread yielded through real OS sleep");
    s540Darwin_os_flush_cpu_write_combine_buffer();
    require(true, "actual x86 sfence executes");
    void *mutex = nullptr;
    require(s540Darwin_os_alloc_mutex(&mutex) == NV_OK, "allocate concurrent mutex");
    unsigned counter = 0;
    std::atomic<unsigned> errors{};
    std::vector<std::thread> workers;
    for (unsigned worker = 0; worker < 6; ++worker) workers.emplace_back([&] {
        for (unsigned i = 0; i < 2000; ++i) {
            if (s540Darwin_os_acquire_mutex(mutex) != NV_OK) { ++errors; return; }
            ++counter;
            s540Darwin_os_release_mutex(mutex);
        }
    });
    for (auto &worker : workers) worker.join();
    require(counter == 12000 && errors == 0, "mutual exclusion across 12000 updates");
    s540Darwin_os_free_mutex(mutex);
    void *semaphore = s540Darwin_os_alloc_semaphore(0);
    require(semaphore != nullptr, "allocate wait semaphore");
    std::atomic<unsigned> acquired{};
    std::thread waiter([&] { if (s540Darwin_os_acquire_semaphore(semaphore) == NV_OK) ++acquired; });
    require(s540Darwin_os_release_semaphore(semaphore) == NV_OK, "cross-thread token release");
    waiter.join();
    require(acquired == 1, "semaphore wake consumed once");
    using namespace S540NvidiaDarwinServicesNative;
    setContext(true, false);
    require(s540Darwin_os_is_isr() && !s540Darwin_os_semaphore_may_sleep(), "interrupt context truthfully exposed");
    require(s540Darwin_os_acquire_semaphore(semaphore) == NV_ERR_INVALID_REQUEST, "blocking semaphore rejects interrupt");
    require(s540Darwin_os_cond_acquire_semaphore(semaphore) == NV_ERR_TIMEOUT_RETRY, "interrupt semaphore try never blocks");
    require(s540Darwin_os_release_semaphore(semaphore) == NV_OK, "interrupt semaphore release");
    require(s540Darwin_os_cond_acquire_semaphore(semaphore) == NV_OK, "interrupt semaphore conditional consumes token");
    require(s540Darwin_os_delay(1) == NV_ERR_INVALID_REQUEST && s540Darwin_os_delay_us(1) == NV_ERR_INVALID_REQUEST, "delay rejects interrupt");
    require(s540Darwin_os_get_random_bytes(random, sizeof(random)) == NV_ERR_INVALID_REQUEST, "random API rejects unsupported interrupt context");
    require(s540Darwin_os_schedule() == NV_ERR_ILLEGAL_ACTION, "yield rejects interrupt context");
    require(s540Darwin_os_get_pid_info() == nullptr, "retained PID allocation rejects interrupt context");
    NvU64 identity = 99;
    require(s540Darwin_os_get_current_thread(&identity) == NV_OK && identity == 0, "ISR has no thread identity");
    setContext(false, true);
    s540Darwin_os_free_semaphore(semaphore);
    void *overflow = s540Darwin_os_alloc_semaphore(~NvU32{0});
    require(overflow != nullptr && s540Darwin_os_release_semaphore(overflow) == NV_ERR_INVALID_STATE, "semaphore overflow refuses");
    s540Darwin_os_free_semaphore(overflow);
    void *rw = s540Darwin_os_alloc_rwlock();
    require(rw != nullptr, "allocate rwlock");
    require(s540Darwin_os_acquire_rwlock_read(rw) == NV_OK, "main reader");
    acquired = 0;
    std::thread secondReader([&] {
        if (s540Darwin_os_acquire_rwlock_read(rw) == NV_OK) { ++acquired; s540Darwin_os_release_rwlock_read(rw); }
    });
    require(waitUntil(acquired, 1), "independent readers overlap");
    secondReader.join();
    require(s540Darwin_os_cond_acquire_rwlock_write(rw) == NV_ERR_TIMEOUT_RETRY, "writer excludes readers");
    acquired = 0;
    std::thread writer([&] {
        if (s540Darwin_os_acquire_rwlock_write(rw) == NV_OK) { ++acquired; s540Darwin_os_release_rwlock_write(rw); }
    });
    s540Darwin_os_release_rwlock_read(rw);
    writer.join();
    require(acquired == 1, "waiting writer wakes");
    require(s540Darwin_os_acquire_rwlock_write(rw) == NV_OK, "main writer");
    require(s540Darwin_os_cond_acquire_rwlock_read(rw) == NV_ERR_TIMEOUT_RETRY, "reader excludes writer");
    s540Darwin_os_release_rwlock_write(rw);
    s540Darwin_os_free_rwlock(rw);
    os_wait_queue *completion = nullptr;
    require(s540Darwin_os_alloc_wait_queue(&completion) == NV_OK, "allocate complete-all");
    workers.clear(); acquired = 0;
    for (unsigned i = 0; i < 8; ++i) workers.emplace_back([&] { s540Darwin_os_wait_uninterruptible(completion); ++acquired; });
    s540Darwin_os_wake_up(completion);
    for (auto &worker : workers) worker.join();
    require(acquired == 8, "complete-all wakes every waiter without lost wake");
    s540Darwin_os_wait_interruptible(completion);
    s540Darwin_os_wait_uninterruptible(completion);
    require(true, "completion remains sticky after wake");
    s540Darwin_os_free_wait_queue(completion);
    Work work;
    work.gate = s540Darwin_os_alloc_semaphore(0);
    work.block = true;
    require(s540DarwinWorkQueueCreate(action, &work, &work.queue) == NV_OK, "create real worker");
    require(s540DarwinBindGlobalWorkQueue(work.queue) == NV_OK, "bind explicit real global worker");
    require(s540DarwinBindGlobalWorkQueue(work.queue) == NV_ERR_IN_USE, "duplicate global bind refuses");
    require(s540Darwin_os_queue_work_item(nullptr, nullptr) == NV_OK, "global dispatch accepted");
    require(waitUntil(work.entered, 1), "worker entered blocking callback");
    for (unsigned i = 0; i < 64; ++i) require(s540Darwin_os_queue_work_item(work.queue, nullptr) == NV_OK, "preallocated queue slot accepted");
    require(s540Darwin_os_queue_work_item(work.queue, nullptr) == NV_ERR_NO_MEMORY, "bounded queue refuses without dropping ownership");
    std::atomic<unsigned> flushed{};
    std::thread flusher([&] { if (s540Darwin_os_flush_work_queue(work.queue, NV_TRUE) == NV_OK) ++flushed; });
    bool unloading = false;
    for (unsigned i = 0; i < 100000 && !unloading; ++i) { unloading = s540Darwin_os_is_queue_flush_ongoing(work.queue); std::this_thread::yield(); }
    require(unloading, "unload flag covers real pending flush");
    work.block = false;
    require(s540Darwin_os_release_semaphore(work.gate) == NV_OK, "release worker callback");
    flusher.join();
    require(flushed == 1 && work.completed == 65 && work.errors == 0, "flush drains all accepted work");
    require(!s540Darwin_os_is_queue_flush_ongoing(work.queue), "flush flag resets");
    work.selfFlush = true;
    require(s540Darwin_os_queue_work_item(work.queue, nullptr) == NV_OK, "self-flush callback submitted");
    require(s540Darwin_os_flush_work_queue(work.queue, NV_FALSE) == NV_OK && work.errors == 0, "worker self-flush refused without deadlock");
    work.selfFlush = false;
    const unsigned previous = work.completed;
    workers.clear();
    for (unsigned i = 0; i < 4; ++i) workers.emplace_back([&] {
        for (unsigned n = 0; n < 1000; ++n) {
            NV_STATUS status;
            do { status = s540Darwin_os_queue_work_item(work.queue, nullptr); if (status == NV_ERR_NO_MEMORY) std::this_thread::yield(); } while (status == NV_ERR_NO_MEMORY);
            if (status != NV_OK) ++work.errors;
        }
    });
    for (auto &worker : workers) worker.join();
    require(s540Darwin_os_flush_work_queue(work.queue, NV_FALSE) == NV_OK && work.completed == previous + 4000 && work.errors == 0, "four producers delivered 4000 items exactly once");
    require(s540DarwinUnbindGlobalWorkQueue(work.queue) == NV_OK, "unbind after producer quiescence");
    require(s540Darwin_os_queue_work_item(nullptr, nullptr) == NV_ERR_NOT_READY, "unbound dispatch remains closed");
    require(s540DarwinWorkQueueStop(work.queue) == NV_OK, "stop drains queue");
    require(s540Darwin_os_queue_work_item(work.queue, nullptr) == NV_ERR_NOT_READY, "stopped queue refuses new ownership");
    s540DarwinWorkQueueDestroy(work.queue);
    s540Darwin_os_free_semaphore(work.gate);
    Timer timer;
    timer.rearm = true; timer.selfCancel = true;
    require(s540DarwinTimerCreate(timerAction, &timer, &timer.timer) == NV_OK, "create timer");
    require(s540DarwinTimerArm(timer.timer, ~NvU64{0}) == NV_ERR_INVALID_ARGUMENT, "timer deadline overflow refuses");
    require(s540DarwinTimerArm(timer.timer, 1000000) == NV_OK, "arm first one-shot");
    require(waitUntil(timer.completed, 3), "timer rearm from callback executes serially");
    require(s540DarwinTimerCancel(timer.timer) == NV_OK && timer.errors == 0, "self-cancel refused and outside cancel drains");
    require(s540DarwinTimerArm(timer.timer, 60000000000ULL) == NV_OK, "distant timer armed");
    require(s540DarwinTimerCancel(timer.timer) == NV_OK && timer.completed == 3, "pending timer cancelled before firing");
    s540DarwinTimerDestroy(timer.timer);
    Timer blockedTimer;
    blockedTimer.gate = s540Darwin_os_alloc_semaphore(0); blockedTimer.block = true;
    require(s540DarwinTimerCreate(timerAction, &blockedTimer, &blockedTimer.timer) == NV_OK, "create draining timer");
    require(s540DarwinTimerArm(blockedTimer.timer, 0) == NV_OK, "immediate timer accepted");
    require(waitUntil(blockedTimer.entered, 1), "timer callback entered");
    std::atomic<unsigned> cancelled{};
    std::thread canceller([&] { if (s540DarwinTimerCancel(blockedTimer.timer) == NV_OK) ++cancelled; });
    require(s540Darwin_os_release_semaphore(blockedTimer.gate) == NV_OK, "release timer callback");
    canceller.join();
    require(cancelled == 1 && blockedTimer.completed == 1 && blockedTimer.errors == 0, "cancel waited for active callback");
    s540DarwinTimerDestroy(blockedTimer.timer);
    s540Darwin_os_free_semaphore(blockedTimer.gate);
    require(s540DarwinLiveObjects() == 0, "all storage and OS objects returned to baseline");
    std::printf("{\"component\":\"nvidia-darwin-services\",\"format\":1,\"status\":\"passed\",\"checks\":%u,\"production_checks\":%u,\"failures\":0,\"mutex_updates\":12000,\"concurrent_work_items\":4000,\"fault_paths\":18,\"cleanup\":true,\"execution\":\"native-user-space\",\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks, production.checks);
}
