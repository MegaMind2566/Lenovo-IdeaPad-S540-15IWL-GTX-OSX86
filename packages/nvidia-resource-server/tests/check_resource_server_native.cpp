// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaResourceServer.hpp"
#include <cstdio>
int main() {
    const auto r = S540NvidiaResourceServer::check();
    std::printf("{\"format\":1,\"component\":\"nvidia-resource-server\",\"status\":\"%s\",\"checks\":%u,\"failures\":%u,\"server\":%s,\"clients\":%s,\"resources\":%s,\"sharing\":%s,\"control\":%s,\"cleanup\":%s,\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\",\"gpu_access\":false}\n",r.passed()?"passed":"failed",r.checks,r.failures,r.server?"true":"false",r.clients?"true":"false",r.resources?"true":"false",r.sharing?"true":"false",r.control?"true":"false",r.cleanup?"true":"false");
    return r.passed()?0:1;
}
