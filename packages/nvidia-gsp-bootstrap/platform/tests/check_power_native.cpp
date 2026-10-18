// SPDX-License-Identifier: MIT
#include "../S540NvidiaGspPower.hpp"
#include <cstdio>
#include <cstdlib>
namespace {
unsigned checks;
void expect(bool value, const char *reason) {
    ++checks;
    if (!value) { std::fprintf(stderr, "Power protocol check failed: %s\n", reason); std::exit(1); }
}
}
int main() {
    using S540NvidiaGspPower::Detail::Protocol;
    Protocol p;
    expect(!p.ready(), "empty protocol cannot prove power");
    expect(!p.setState(false) && !p.snapshot().revoked, "initial off state needs no shutdown");
    p.requested();
    expect(!p.ready(), "accepted PM request is not completion");
    expect(!p.setState(true) && !p.ready(), "on callback is not completed power transition");
    p.completed();
    expect(p.ready() && p.snapshot().onCompleted, "on completion admits the protocol");
    expect(p.setState(false), "down after on requires a real posted stop");
    auto state = p.snapshot();
    expect(!p.ready() && state.revoked && state.acknowledgementPending && !state.acknowledgementSent,
        "revocation removes admission without acknowledging");
    p.posted(NV_OK);
    expect(p.snapshot().acknowledgementPending && !p.snapshot().acknowledgementSent,
        "queue acceptance cannot acknowledge original resource cleanup");
    expect(!p.setState(false), "duplicate down cannot enqueue duplicate stop");
    p.setState(true); p.completed();
    expect(!p.ready(), "a wake callback never resurrects a revoked RM session");
    p.acknowledged();
    expect(!p.snapshot().acknowledgementPending && p.snapshot().acknowledgementSent,
        "actual successful ack records completion separately");
    p.stopped();
    expect(p.snapshot().stopped && !p.ready(), "stop keeps admission closed");
    Protocol refused;
    refused.requested(); refused.setState(true); refused.completed(); refused.setState(false);
    refused.posted(NV_ERR_INSUFFICIENT_RESOURCES);
    state = refused.snapshot();
    expect(state.postFailures == 1 && state.revocationPosts == 1 &&
        state.acknowledgementPending && !state.acknowledgementSent,
        "failed dispatcher admission retains pending acknowledgement");
    Protocol racing;
    racing.requested(); racing.setState(true);
    expect(racing.setState(false), "revocation may race initial on completion");
    racing.completed();
    expect(!racing.ready() && racing.snapshot().revoked,
        "late completion cannot overwrite revocation");
    std::printf("{\"format\":1,\"component\":\"nvidia-gsp-power-protocol\",\"status\":\"passed\","
        "\"checks\":%u,\"failures\":0,\"pm_events_fixture\":true,\"native_protocol_only\":true,"
        "\"power_domain_acquired\":false,\"execution\":\"native-user-space\","
        "\"kernel_execution\":\"not_tested\",\"gpu_access\":false}\n", checks);
}
