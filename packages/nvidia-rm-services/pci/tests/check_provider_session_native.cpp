// SPDX-License-Identifier: MIT
#include "../S540NvidiaProviderSession.hpp"
#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>
#include <chrono>
#include <new>
using namespace S540NvidiaRmPci;
namespace {
std::atomic<unsigned> checks{0}, failures{0};
void check(bool passed) {
    const unsigned n = ++checks;
    if (!passed) { ++failures; std::fprintf(stderr, "Provider-session check %u failed\n", n); }
}
struct Fixture {
    unsigned char config[4096];
    std::atomic<unsigned> retains{0}, releases{0}, refs{0}, reads{0}, invalidReads{0};
    std::atomic<bool> failRetain{false}, failRead{false}, gone{false}, failBdf{false};
    std::mutex mutex; std::condition_variable changed;
    bool block{false}, entered{false}, resume{false};
    Fixture() : config{} {
        put(0, 0x1f9110de); put(8, 0x030000a1); put(0x2c, 0x380617aa);
        put(0x100, 0x12345678); put(4092, 0xabcdef01);
    }
    void put(unsigned offset, NvU32 value) {
        for (unsigned i = 0; i < 4; ++i) config[offset + i] = static_cast<unsigned char>(value >> (8 * i));
    }
    static bool retain(void *opaque) {
        auto &f = *static_cast<Fixture *>(opaque); if (f.failRetain.load()) return false;
        ++f.retains; ++f.refs; return true;
    }
    static void release(void *opaque) {
        auto &f = *static_cast<Fixture *>(opaque); ++f.releases; --f.refs;
    }
    static bool read(void *opaque, NvU32 offset, NvU32 width, NvU32 &value) {
        auto &f = *static_cast<Fixture *>(opaque); ++f.reads;
        if (!validConfigurationAccess(offset, width)) { ++f.invalidReads; return false; }
        if (f.refs == 0) { ++f.invalidReads; return false; }
        if (f.failRead.load()) return false;
        std::unique_lock<std::mutex> lock(f.mutex);
        if (f.block && offset == 0x100) {
            f.entered = true; f.changed.notify_all();
            f.changed.wait(lock, [&] { return f.resume; });
        }
        value = 0;
        for (NvU32 i = 0; i < width; ++i) value |= NvU32{f.config[offset + i]} << (8 * i);
        return true;
    }
    static bool inactive(void *opaque) { return static_cast<Fixture *>(opaque)->gone.load(); }
    static bool bdf(void *opaque, NvU8 &bus, NvU8 &device, NvU8 &function) {
        if (static_cast<Fixture *>(opaque)->failBdf.load()) return false;
        bus = 1; device = 0; function = 0; return true;
    }
    ProviderSession::Backend backend(bool segmentKnown = true) {
        return {this, retain, release, read, inactive, bdf, segmentKnown, 7};
    }
};
}
int main() {
    check(validConfigurationAccess(4095, 1)); check(validConfigurationAccess(4094, 2));
    check(validConfigurationAccess(4092, 4)); check(validConfigurationAccess(256, 4));
    check(!validConfigurationAccess(4096, 1)); check(!validConfigurationAccess(4095, 2));
    check(!validConfigurationAccess(4094, 4)); check(!validConfigurationAccess(~NvU32{0}, 4));
    check(!validConfigurationAccess(0, 0)); check(!validConfigurationAccess(0, 8));
    const auto startup = S540NvidiaRmPci::check();
    check(startup.passed() && startup.session && startup.reads && startup.handles && startup.lifecycle && startup.cleanup);
    Fixture f; ProviderSession session; check(session.ready()); check(!session.active());
    NvU8 byte = 9; NvU16 word = 9; NvU32 dword = 9;
    check(session.readDword(reinterpret_cast<void *>(1), 0, &dword) != NV_OK && dword == 0);
    check(session.startNative(f.backend()) == NV_OK); check(f.refs == 1);
    void *token = session.handle(); check(token != nullptr); check(session.active());
    Metadata metadata = {}; check(session.metadata(metadata) == NV_OK);
    check(metadata.identityVerified && metadata.readOnly && !metadata.providerOpened);
    check(metadata.vendorDevice == 0x1f9110de && metadata.revisionClass == 0x030000a1);
    check(metadata.subsystem == 0x380617aa && metadata.bus == 1 && metadata.device == 0 && metadata.function == 0);
    check(metadata.segmentKnown && metadata.segment == 7 && metadata.generation != 0);
    check(session.startNative(f.backend()) == NV_ERR_STATE_IN_USE && f.retains == 1);
    check(session.readByte(token, 0, &byte) == NV_OK && byte == 0xde);
    check(session.readWord(token, 0, &word) == NV_OK && word == 0x10de);
    check(session.readDword(token, 0, &dword) == NV_OK && dword == 0x1f9110de);
    check(session.readDword(token, 0x100, &dword) == NV_OK && dword == 0x12345678);
    check(session.readByte(token, 4095, &byte) == NV_OK && byte == 0xab);
    check(session.readWord(token, 4094, &word) == NV_OK && word == 0xabcd);
    check(session.readDword(token, 4092, &dword) == NV_OK && dword == 0xabcdef01);
    check(session.readByte(nullptr, 0, &byte) != NV_OK && byte == 0);
    check(session.readDword(reinterpret_cast<void *>(~NvUPtr{0}), 0, &dword) != NV_OK && dword == 0);
    check(session.readWord(token, 1, &word) == NV_ERR_INVALID_ARGUMENT && word == 0);
    check(session.readDword(token, 2, &dword) == NV_ERR_INVALID_ARGUMENT && dword == 0);
    check(session.readDword(token, 4096, &dword) == NV_ERR_INVALID_ARGUMENT && dword == 0);
    check(session.readByte(token, 0, nullptr) == NV_ERR_INVALID_POINTER);
    check(session.readWord(token, 0, nullptr) == NV_ERR_INVALID_POINTER);
    check(session.readDword(token, 0, nullptr) == NV_ERR_INVALID_POINTER);
    void *selected = nullptr; NvU16 vendor = 0, device = 0;
    check(session.lookup(7, 1, 0, 0, &selected, &vendor, &device) == NV_OK && selected == token && vendor == 0x10de && device == 0x1f91);
    check(session.lookup(8, 1, 0, 0, &selected, &vendor, &device) == NV_ERR_OBJECT_NOT_FOUND && selected == nullptr && vendor == 0xffff && device == 0xffff);
    check(session.lookup(7, 2, 0, 0, &selected, nullptr, nullptr) == NV_ERR_OBJECT_NOT_FOUND);
    check(session.lookup(7, 1, 32, 0, &selected, nullptr, nullptr) == NV_ERR_OBJECT_NOT_FOUND);
    check(session.lookup(7, 1, 0, 8, &selected, nullptr, nullptr) == NV_ERR_OBJECT_NOT_FOUND);
    check(session.lookup(7, 1, 0, 0, nullptr, &vendor, &device) == NV_ERR_INVALID_POINTER && vendor == 0xffff && device == 0xffff);
    f.failRead = true; check(session.readDword(token, 0, &dword) != NV_OK && dword == 0); f.failRead = false;
    f.gone = true; check(session.readDword(token, 0, &dword) == NV_ERR_INVALID_STATE && dword == 0); f.gone = false;
    f.put(0, 0); check(session.readDword(token, 0, &dword) == NV_ERR_INVALID_STATE && dword == 0); f.put(0, 0x1f9110de);
    Metadata after = {}; check(session.metadata(after) == NV_OK && std::memcmp(&after, &metadata, sizeof(metadata)) == 0);
    check(session.inFlight() == 0); check(session.stop() == NV_OK); check(f.refs == 0 && f.releases == 1);
    check(session.handle() == nullptr && !session.active()); check(session.stop() == NV_OK && f.releases == 1);
    check(session.readDword(token, 0, &dword) != NV_OK && dword == 0);
    check(session.metadata(after) == NV_ERR_NOT_READY && after.generation == 0);
    check(session.startNative(f.backend(false)) == NV_OK); void *secondToken = session.handle(); check(secondToken != token);
    check(session.readDword(token, 0, &dword) != NV_OK && dword == 0);
    check(session.lookup(0, 1, 0, 0, &selected, &vendor, &device) == NV_ERR_NOT_SUPPORTED && selected == nullptr && vendor == 0xffff && device == 0xffff);
    check(session.readDword(secondToken, 0, &dword) == NV_OK); check(session.stop() == NV_OK);
    ProviderSession foreign; check(foreign.startNative(f.backend()) == NV_OK);
    check(foreign.readDword(secondToken, 0, &dword) != NV_OK && dword == 0); check(foreign.stop() == NV_OK);
    // Failed starts balance provider retention and do not publish a handle.
    f.failRetain = true; check(session.startNative(f.backend()) == NV_ERR_NO_MEMORY && f.refs == 0); f.failRetain = false;
    f.failRead = true; check(session.startNative(f.backend()) != NV_OK && f.refs == 0); f.failRead = false;
    f.failBdf = true; check(session.startNative(f.backend()) != NV_OK && f.refs == 0); f.failBdf = false;
    f.gone = true; check(session.startNative(f.backend()) != NV_OK && f.refs == 0); f.gone = false;
    f.put(0x2c, 0); check(session.startNative(f.backend()) != NV_OK && f.refs == 0); f.put(0x2c, 0x380617aa);
    auto invalid = f.backend(); invalid.read = nullptr; check(session.startNative(invalid) == NV_ERR_INVALID_POINTER);
    // Concurrent reads are real operations; no buffer or provider is freed
    // while either the ordinary read lease or stop's drain is in progress.
    check(session.startNative(f.backend()) == NV_OK); token = session.handle();
    std::vector<std::thread> readers;
    std::atomic<unsigned> completed{0};
    for (unsigned worker = 0; worker < 4; ++worker) readers.emplace_back([&] {
        for (unsigned i = 0; i < 1000; ++i) { NvU32 value = 0; if (session.readDword(token, 0x100, &value) == NV_OK && value == 0x12345678) ++completed; }
    });
    for (auto &reader : readers) reader.join();
    check(completed == 4000); check(session.inFlight() == 0); check(session.stop() == NV_OK);
    // A held backend read proves stop waits and rejects new read/start leases.
    check(session.startNative(f.backend()) == NV_OK); token = session.handle();
    { std::lock_guard<std::mutex> lock(f.mutex); f.block = true; f.resume = false; f.entered = false; }
    std::atomic<bool> readDone{false}, stopDone{false};
    std::thread held([&] { NvU32 value = 0; check(session.readDword(token, 0x100, &value) == NV_OK && value == 0x12345678); readDone = true; });
    { std::unique_lock<std::mutex> lock(f.mutex); check(f.changed.wait_for(lock, std::chrono::seconds(2), [&] { return f.entered; })); }
    check(session.inFlight() == 1);
    std::thread stopping([&] { check(session.stop() == NV_OK); stopDone = true; });
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (session.active() && std::chrono::steady_clock::now() < deadline) std::this_thread::yield();
    check(!session.active()); check(!stopDone && !readDone && f.refs == 1);
    check(session.readDword(token, 0, &dword) != NV_OK && dword == 0);
    check(session.startNative(f.backend()) == NV_ERR_STATE_IN_USE);
    { std::lock_guard<std::mutex> lock(f.mutex); f.resume = true; f.block = false; f.changed.notify_all(); }
    held.join(); stopping.join(); check(readDone && stopDone && f.refs == 0);
    check(f.retains == f.releases && f.invalidReads == 0);
    // Two concurrent stop callers must not double-release; the next start
    // publishes an independent generation after both callers have completed.
    for (unsigned attempt = 0; attempt < 16; ++attempt) {
        check(session.startNative(f.backend()) == NV_OK); token = session.handle();
        { std::lock_guard<std::mutex> lock(f.mutex); f.block = true; f.resume = false; f.entered = false; }
        std::thread blocked([&] { NvU32 value = 0; check(session.readDword(token, 0x100, &value) == NV_OK); });
        { std::unique_lock<std::mutex> lock(f.mutex); check(f.changed.wait_for(lock, std::chrono::seconds(2), [&] { return f.entered; })); }
        std::atomic<unsigned> stopped{0};
        std::thread first([&] { check(session.stop() == NV_OK); ++stopped; });
        const auto stopDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        while (session.active() && std::chrono::steady_clock::now() < stopDeadline) std::this_thread::yield();
        check(!session.active());
        std::thread follower([&] { check(session.stop() == NV_OK); ++stopped; });
        { std::lock_guard<std::mutex> lock(f.mutex); f.resume = true; f.block = false; f.changed.notify_all(); }
        blocked.join(); first.join(); follower.join();
        check(stopped == 2 && f.refs == 0);
        check(session.startNative(f.backend()) == NV_OK);
        check(session.handle() != token && f.refs == 1);
        check(session.stop() == NV_OK && f.refs == 0);
    }
    // Reusing object storage does not revive a handle from its previous owner.
    alignas(ProviderSession) unsigned char storage[sizeof(ProviderSession)];
    auto *oldOwner = new (storage) ProviderSession;
    check(oldOwner->startNative(f.backend()) == NV_OK); void *oldStorageToken = oldOwner->handle();
    oldOwner->~ProviderSession();
    auto *newOwner = new (storage) ProviderSession;
    check(newOwner->startNative(f.backend()) == NV_OK);
    check(newOwner->handle() != oldStorageToken);
    check(newOwner->readDword(oldStorageToken, 0, &dword) != NV_OK && dword == 0);
    newOwner->~ProviderSession();
    // Destruction drains/release automatically in ordinary thread context.
    { ProviderSession automatic; check(automatic.startNative(f.backend()) == NV_OK && f.refs == 1); }
    check(f.refs == 0 && f.retains == f.releases);
    std::printf("{\"format\":1,\"component\":\"nvidia-provider-session\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\",\"gpu_access\":false,\"concurrent_reads\":4000,\"retention_balanced\":%s,\"pci_writes\":false,\"interrupt_registration\":false}\n", failures ? "failed" : "passed", checks.load(), failures.load(), f.retains == f.releases ? "true" : "false");
    return failures ? 1 : 0;
}
